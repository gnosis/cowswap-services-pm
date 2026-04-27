# General Notes for development

- Use `docker compose -f docker-compose.non-interactive.yml up` in this directory to spin up everything.
- In your wallet (preferable MetaMask) change Polygon to use local RPC `http://localhost:8545` with chain id `137`.
  - Note: Usually it's not recommended to use mainnet chain id for local development, but in this case it is required because CoW services didn't work otherwise.
- In contrast to official repository we have:
  - Our own polymarket-focued migration UI at `http://localhost:9003`
  - Our own pysolver API at `http://localhost:9002`
- `docker-compose.non-interactive.yml` assumes that `https://github.com/gnosis/prediction-market-cowswap-solver` is cloned in the same parent directory as this repostiory, as it mounts the source codes for easier local development.
- After you spin this up, you need to:
  1. Deploy pysolver's safe using `python scripts/deploy_solver_safe.py` in the `prediction-market-cowswap-solver` cloned repository.
  2. Add WPOL funds to it using

  ```bash

SAFE=0x684DEE0C2cBb3779eBF3a37DAf5bB766cA1C4605
WPOL=0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270
RPC=<http://localhost:8545>

cast rpc anvil_setBalance $SAFE 0x8AC7230489E80000 --rpc-url $RPC

cast rpc anvil_impersonateAccount $SAFE --rpc-url $RPC

cast send $WPOL "deposit()" \
  --from $SAFE \
  --value 1000000000 \
  --unlocked \
  --rpc-url $RPC

cast rpc anvil_stopImpersonatingAccount $SAFE --rpc-url $RPC

  ```
