# General Notes for development

- Use `docker compose -f docker-compose.non-interactive.yml up` in this directory to spin up everything.
- In your wallet (preferable MetaMask) change Polygon to use local RPC `http://localhost:8545` with chain id `137`.
  - Note: Usually it's not recommended to use mainnet chain id for local development, but in this case it is required because CoW services didn't work otherwise.
- In contrast to official repository we have:
  - Our own polymarket-focued migration UI at `http://localhost:9003`
  - Our own pysolver API at `http://localhost:9002`
