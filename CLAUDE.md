# PySolver playground on Gnosis Chain fork

Use these steps to run the local playground setup introduced in this PR:

1. Create a Tenderly testnet fork.
2. In `playground/`, copy `.env.example` to `.env`.
3. Set `ETH_RPC_URL` in `.env` to your Tenderly RPC URL.
4. Keep `CHAIN=100` (required for CoW backend compatibility in this setup).
5. In Tenderly, fund the testing PySolver account:
   - `0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f`
6. Start the stack:
   - `docker compose -f docker-compose.fork.yml up`
7. Open the UI and request quotes.

Notes:
- Use Gnosis Chain token addresses (do not reuse Ethereum mainnet token addresses).
- Rabby works better than MetaMask for this local setup because MetaMask blocks adding a local RPC with chain ID `100`.
- Real settlement is not expected here; PySolver is used for playground quoting/testing.
