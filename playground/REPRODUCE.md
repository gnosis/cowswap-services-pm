# Reproducing a working pysolver swap on a local Polygon fork

This branch builds on `pysolver-integration` and contains the config and compose
fixes needed to get an end-to-end USDCe → WPOL swap executed on a local anvil
fork **with the custom pysolver winning the auction and writing the settlement
tx**. The companion Python solver lives in
`github.com/gnosis/prediction-market-cowswap-solver` on branch
`tom/pysolver-swap-working`.

## TL;DR

```
# once
git clone git@github.com:gnosis/cowswap-services-pm.git
cd cowswap-services-pm && git checkout tom/pysolver-swap-working && cd ..
git clone git@github.com:gnosis/prediction-market-cowswap-solver.git
cd prediction-market-cowswap-solver && git checkout tom/pysolver-swap-working && cd ..

# in prediction-market-cowswap-solver/.env, add:
#   SOLVER_PRIVATE_KEY=0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97

cd cowswap-services-pm/playground
cp .env.example .env   # then set ETH_RPC_URL=<tenderly fork url> and CHAIN=137

# build (SERIAL — parallel build OOMs on default 7.6 GiB Docker)
docker compose -f docker-compose.non-interactive.yml build orderbook
docker compose -f docker-compose.non-interactive.yml build autopilot driver baseline db-migrations
docker compose -f docker-compose.non-interactive.yml build frontend
docker compose -f docker-compose.non-interactive.yml build explorer
docker compose -f docker-compose.non-interactive.yml build pysolver

# run
docker compose -f docker-compose.non-interactive.yml up -d

# approve the settlement contract from the solver EOA (one-time per fork)
docker run --rm --network playground_default \
  -v "$(pwd)/../../prediction-market-cowswap-solver/src:/app/src" \
  -v "$(pwd)/../../prediction-market-cowswap-solver/scripts:/app/scripts" \
  --env-file ../../prediction-market-cowswap-solver/.env \
  playground-pysolver:latest \
  uv run python scripts/approve_settlement.py --rpc-url http://chain:8545

# drive a swap (headless, no wallet needed) — prints before/after balances + tx
docker cp ../../prediction-market-cowswap-solver/scripts/prove_settlement.py playground-pysolver-1:/tmp/
docker exec playground-pysolver-1 uv run python /tmp/prove_settlement.py
```

Expected result: user WPOL balance increases by 10,000,000,000,000,000,000
(= 10 WPOL), settlement tx is signed by solver `0x23618e81…1E8f`, autopilot log
reports `winner driver=pysolver`.

## What's in this branch vs. `pysolver-integration`

Three files changed, no code:

| file | change | why |
|------|--------|-----|
| `playground/configs/autopilot.toml` | added `[run-loop] solve-deadline = "20s"`, removed the `baseline` `[[drivers]]` entry | default 900s deadline causes the autopilot HTTP client to time out before the driver returns solutions ("hide competition until deadline" changed this behavior in upstream `#4330`). Baseline is dropped from competition so the pysolver actually wins — when left in, its 1:1 hardcoded price is beaten by baseline's real QuickSwap route every time. |
| `playground/configs/orderbook.toml` | removed the `[shared.tracing]` block | `tempo:4317` isn't mandatory and otel-startup errors spam the log |
| `playground/docker-compose.non-interactive.yml` | inlined `SOLVER_PRIVATE_KEY=0x…ea67b97` on the `pysolver` service; changed the `frontend` `ETH_RPC_URL` build arg to `http://localhost:8545` | solver repo's `.env` doesn't define `SOLVER_PRIVATE_KEY` and without it `/quote` 500s. The frontend was built with `http://chain:8545` which is a docker-internal hostname the browser cannot resolve; the UI then falls back to a public Polygon RPC and shows 0 balance for fork-only tokens. |

## Detailed walk-through

### 0. Prerequisites

- Docker Desktop (16+ GiB allocated is comfortable; 7.6 GiB default works if you
  build serially — see §3).
- A Tenderly fork URL where the pysolver EOA `0x23618e81…1E8f` is pre-funded
  with USDCe, WPOL, USDC, stataPolUSDCn and some MATIC. Reuse the one in the
  original PR description or create your own Tenderly virtual testnet and fund
  the address manually.

### 1. Clone + checkout

```
git clone git@github.com:gnosis/cowswap-services-pm.git
git clone git@github.com:gnosis/prediction-market-cowswap-solver.git
(cd cowswap-services-pm && git checkout tom/pysolver-swap-working)
(cd prediction-market-cowswap-solver && git checkout tom/pysolver-swap-working)
```

Paths must be siblings — `docker-compose.non-interactive.yml` references
`../../prediction-market-cowswap-solver/…`.

### 2. Configure env

In `prediction-market-cowswap-solver/.env` (copy from `.env.example` if needed):

```
SOLVER_PRIVATE_KEY=0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97
```

(`0x23618e81…1E8f` is the derived address — it matches the `account` in
`cowswap-services-pm/playground/configs/driver.toml [[solver]] name="pysolver"`
and the `address` in
`cowswap-services-pm/playground/configs/autopilot.toml [[drivers]] name="pysolver"`.)

In `cowswap-services-pm/playground/.env` (copy from `.env.example`):

```
ETH_RPC_URL=<your Tenderly polygon fork URL>
CHAIN=137
# leave other keys at their defaults
```

### 3. Build — **serially**

`docker compose up --build` kicks off every image in parallel and peaks around
12 GiB, which OOMs the default 7.6 GiB Docker VM. Build one group at a time:

```
cd cowswap-services-pm/playground
docker compose -f docker-compose.non-interactive.yml build orderbook
docker compose -f docker-compose.non-interactive.yml build autopilot driver baseline db-migrations
docker compose -f docker-compose.non-interactive.yml build frontend
docker compose -f docker-compose.non-interactive.yml build explorer
docker compose -f docker-compose.non-interactive.yml build pysolver
```

The rust services share the same `cargo-build` stage, so after `orderbook` the
other three are cached. Frontend and explorer each `pnpm install` the cowswap
tree; combined they exceed 7.6 GiB, so they must be separate build invocations.

### 4. Start the stack

```
docker compose -f docker-compose.non-interactive.yml up -d
```

Wait ~15s for chain to be healthy. `docker ps` should show 14 services running.

Ports exposed on the host:

| port | service |
|------|---------|
| 8000 | cowswap UI (frontend) |
| 8001 | cow explorer |
| 8003 | otterscan |
| 8080 | orderbook REST API |
| 8545 | anvil (forked Polygon, chain id 137) |
| 5432 | postgres |
| 9000 | driver metrics/API |
| 9001 | baseline metrics/API |
| 9002 | pysolver HTTP |
| 9586 | orderbook metrics |

### 5. Approve settlement (one-time per fork)

The pysolver delivers buyToken to users via `buyToken.transferFrom(solver, settlement, amount)`.
That requires the solver EOA to have pre-approved the CoW settlement contract.
Run the helper script:

```
docker run --rm --network playground_default \
  -v "$PWD/../../prediction-market-cowswap-solver/src:/app/src" \
  -v "$PWD/../../prediction-market-cowswap-solver/scripts:/app/scripts" \
  --env-file ../../prediction-market-cowswap-solver/.env \
  playground-pysolver:latest \
  uv run python scripts/approve_settlement.py --rpc-url http://chain:8545
```

This is idempotent; re-running on an existing fork just sends 4 no-op approvals.

### 6. Testing

#### Option A — headless (no wallet)

Script lives at
`prediction-market-cowswap-solver/scripts/prove_settlement.py`. It uses the
well-known anvil account #0 as a throwaway user, funds it from the solver,
approves VaultRelayer, signs an EIP-712 order, posts to `/api/v1/orders`,
polls for the trade, and prints BEFORE / AFTER balances plus the tx receipt.

```
docker cp ../../prediction-market-cowswap-solver/scripts/prove_settlement.py playground-pysolver-1:/tmp/
docker exec playground-pysolver-1 uv run python /tmp/prove_settlement.py
```

Successful output ends with:

```
DELTA   user  USDCe=+0  WPOL=+10000000000000000000
=== SETTLEMENT TX ===
hash:     0x…
from:     0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f  (solver)
to:       0x9008D19f58AAbD9eD0D60971565AA8510560ab41  (GPv2Settlement)
status:   1
```

Correlate with the autopilot log — you should see
`winner driver=pysolver` and `solution settled tx_hash=…` in
`docker logs playground-autopilot-1`.

#### Option B — UI

1. Install Rabby (https://rabby.io). MetaMask won't accept chain id 137 on a
   custom RPC; Rabby will.
2. Rabby → More → RPC Node → Polygon → `http://localhost:8545`. Chain id 137.
3. Import the anvil test key
   `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`
   (address `0xf39Fd…2266`). Known public key — don't send real funds to it.
4. Fund that address on the fork (see `fund_test_user()` in
   `prediction-market-cowswap-solver/scripts/prove_settlement.py`, or just run
   `prove_settlement.py` once — it'll fund the same address).
5. Open `http://localhost:8000`. The URL bar must be `localhost` so the
   browser-baked RPC (`http://localhost:8545`) resolves.
6. Change the sell token to USDC.e by pasting
   `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`. The default "USDC" (at
   `0x3c499…`) is a different ERC20.
7. Amount: 1. The quote line should read `1 WPOL = 1 USDC.e` (that's the
   pysolver's 1:1 decimal-adjusted price).
8. Click Swap. Rabby prompts twice — approve VaultRelayer, then sign the
   EIP-712 order. Within ~20s the order flips from `Open` to `Fulfilled`.
9. Confirm pysolver settled it:
   `docker logs playground-autopilot-1 --tail 60 | grep -E "winner|settled"`

## Scope / what's NOT proven yet

This branch proves the **plumbing** is working: orders flow UI → orderbook →
autopilot → driver → pysolver → `GPv2Settlement.settle()` on chain. The swap
used is a stub 1:1 USDC.e ↔ WPOL exchange so the pysolver's `/solve` can emit a
single `buyToken.transferFrom(solver, settlement, amount)` interaction.

What's **stubbed out** on the companion `tom/pysolver-swap-working` branch:

- `/reveal` returns empty calldata. The real Polymarket-migration reveal path
  (`reveal_migration_calldata` → multisend of CTF splits / wrapped1155 ops)
  is still unsolved — it doesn't match the shape the CoW driver expects, and
  re-enabling it on a fresh fork would fail on `_precheck`
  (`ctf.setApprovalForAll(safe, true)` wasn't signed by the user).
- `HARDCODED_CONDITION_ID` / `HARDCODED_OUTCOME_INDEX` are placeholders
  (`0x00…00` / `0`) — the Polymarket hardcoded-appData fallback is
  effectively a no-op.

To get actual Polymarket outcome-token migration landing on chain, the interactions
returned by `/solve` need to be the real CTF split/merge/transfer calls
(not a bare `transferFrom`), and `/reveal` needs to either be empty or echo
the same calldata.

## Troubleshooting

- `error sending request for url (http://driver/pysolver/solve)` in autopilot:
  `solve-deadline` is still at default 900s. Check
  `docker logs playground-autopilot-1 | grep solve_deadline` — it must be `20s`.
- `SOLVER_PRIVATE_KEY missing in the environment` in pysolver logs: the env
  var isn't reaching the container. Verify with
  `docker exec playground-pysolver-1 printenv | grep SOLVER`. Either add the
  line to `prediction-market-cowswap-solver/.env` or confirm the compose override.
- UI shows 0 balance for USDC.e despite Rabby showing 100: hard-refresh
  (service worker caches aggressively). DevTools → Application → Service
  Workers → Unregister, then Cmd-Shift-R, or open in an incognito window.
- UI shows "insufficient balance" but Rabby agrees with the fork: CoW's own
  RPC still defaults to `https://polygon-rpc.com` for some calls. Check
  `docker exec playground-frontend-1 grep -Eho "http[s]?://[^\"]*8545[^\"]*" /usr/share/nginx/html/static/*.js | sort -u`
  — must include `http://localhost:8545`.
- Baseline wins the auction instead of pysolver: you're still running the
  original `autopilot.toml`. Confirm `baseline` is not in `[[drivers]]`.

## Ports / paths cheat sheet

- Solver private key (public): `0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97` → `0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f`
- Baseline solver key (anvil #9): `0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6` → `0xa0Ee7A142d267C1f36714E4a8F75612F20a79720`
- CoW settlement: `0x9008D19f58AAbD9eD0D60971565AA8510560ab41`
- CoW VaultRelayer: `0xC92E8bdf79f0507f65a392b0ab4667716BFE0110`
- USDC.e (Polygon): `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
- WPOL (wrapped MATIC): `0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270`
