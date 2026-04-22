# General Notes for development

- Use `docker compose -f docker-compose.non-interactive.yml up` in this directory to spin up everything
- If you want to be sure the orders are actually going through the solver you want to, make sure only that one is available for the services
- If you want to use our pysolver, or the defaut baseline, modify the solver the lines in:
  - `playground/configs/autopilot.toml`
  - `playground/configs/orderbook.toml`
- In `playground/configs/baseline.toml`, I replacted chain id to 137 (Polygon that we develop with now)
- I had to use Rabbit instead of MetaMask, because MetaMask didn't allow to use 137 in forked chain, however, CoW services didn't work with other id.
