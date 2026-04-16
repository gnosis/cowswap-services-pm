import datetime
import json
import pprint
from typing import Annotated, Dict, List, Literal, Optional, Union

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from models import *


# --------------------------------------------------------------------------
# 2. FastAPI Application
# --------------------------------------------------------------------------

app = FastAPI(
    title="Solver API",
    description="A mock implementation of the Solver API for Autopilot queries.",
    version="0.0.1",
)


def get_mock_address(index: int = 0) -> Address:
    return f"0x{'1'*(39-len(str(index)))}{index}aBcDeF"


# --- API Endpoints ---


@app.get(
    "/quote",
    response_model=QuoteResponseKind,
    summary="Get price estimation quote",
    tags=["Solver"],
)
async def get_quote(
    sellToken: Address = Query(..., example=get_mock_address(1)),
    buyToken: Address = Query(..., example=get_mock_address(2)),
    kind: Literal["buy", "sell"] = Query(...),
    amount: TokenAmount = Query(..., example="1000000000000000000"),
    deadline: DateTime = Query(...),
):
    """
    Provides a mock price estimation quote.

    HOW IT'S CALLED BY THE DRIVER:
    The driver's source code confirms it calls this endpoint via an HTTP GET
    request. The parameters (sellToken, buyToken, etc.) are sent as query
    strings in the URL, not in a request body.
    Ref: /crates/driver/src/infra/api/routes/quote/mod.rs [cite: 881, 882]
    """
    print("Received quote request with parameters:")
    print(f"  sellToken: {sellToken}")
    print(f"  buyToken: {buyToken}")
    print(f"  kind: {kind}")
    print(f"  amount: {amount}")
    print(f"  deadline: {deadline}")
    if kind == "sell":
        buy_amount = str(int(amount) * 95 // 100)
        sell_amount = amount
    else:  # kind == "buy"
        sell_amount = str(int(amount) * 100 // 95)
        buy_amount = amount

    return QuoteResponse(
        clearingPrices={
            sellToken: "1000000000000000000",
            buyToken: "950000000000000000",
        },
        preInteractions=[],
        interactions=[],
        solver=get_mock_address(0),
        gas=150000,
        txOrigin=None,
        jitOrders=[],
    )


def find_pool_for_pair(
    liquidity: List[SolverLiquidity], sell_token: str, buy_token: str
) -> Optional[SolverLiquidity]:
    """Find a liquidity pool that contains both tokens."""
    sell_token_lower = sell_token.lower()
    buy_token_lower = buy_token.lower()
    for pool in liquidity:
        pool_tokens = [t.lower() for t in pool.tokens.keys()]
        if sell_token_lower in pool_tokens and buy_token_lower in pool_tokens:
            return pool
    return None


def get_reserves(
    pool: SolverLiquidity, input_token: str, output_token: str
) -> tuple[int, int]:
    """Get input and output reserves from pool (case-insensitive)."""
    input_token_lower = input_token.lower()
    output_token_lower = output_token.lower()
    input_reserve = 0
    output_reserve = 0
    for token, balance in pool.tokens.items():
        if token.lower() == input_token_lower:
            input_reserve = int(balance.balance)
        elif token.lower() == output_token_lower:
            output_reserve = int(balance.balance)
    return input_reserve, output_reserve


def calculate_amm_output(
    pool: SolverLiquidity, input_token: str, output_token: str, input_amount: int
) -> int:
    """
    Calculate output amount using constant product formula: x * y = k
    output = (input_amount * output_reserve * (1 - fee)) / (input_reserve + input_amount * (1 - fee))
    """
    input_reserve, output_reserve = get_reserves(pool, input_token, output_token)

    if input_reserve == 0 or output_reserve == 0:
        return 0

    # Parse fee (e.g., "0.003" -> 0.3%)
    fee = float(pool.fee) if pool.fee else 0.003
    fee_multiplier = 1 - fee

    # Constant product AMM formula with fee
    input_with_fee = int(input_amount * fee_multiplier * 1000) // 1000
    numerator = input_with_fee * output_reserve
    denominator = input_reserve + input_with_fee

    if denominator == 0:
        return 0

    return numerator // denominator


def calculate_amm_input(
    pool: SolverLiquidity, input_token: str, output_token: str, output_amount: int
) -> int:
    """
    Calculate required input amount to get a specific output (inverse of calculate_amm_output).
    input = (output_amount * input_reserve) / ((output_reserve - output_amount) * (1 - fee))
    """
    input_reserve, output_reserve = get_reserves(pool, input_token, output_token)

    if input_reserve == 0 or output_reserve == 0:
        return 0

    # Cannot buy more than available in reserve
    if output_amount >= output_reserve:
        return 0

    # Parse fee
    fee = float(pool.fee) if pool.fee else 0.003
    fee_multiplier = 1 - fee

    # Inverse constant product formula
    numerator = output_amount * input_reserve
    denominator = int((output_reserve - output_amount) * fee_multiplier * 1000) // 1000

    if denominator == 0:
        return 0

    # Add 1 to round up (ensure we provide enough input)
    return (numerator // denominator) + 1


@app.post(
    "/solve",
    response_model=SolveResponse,
    summary="Solve the passed in auction",
    tags=["Solver"],
)
async def solve_auction(request: SolverRequest):
    """
    This endpoint computes a solution using constant product AMM math
    based on the actual liquidity pool reserves provided by the driver.
    """
    print("Received solve request with the following details:")
    print(f"  orders: {request.orders}")
    print(f"  liquidity: {request.liquidity}")

    first_order = request.orders[0] if request.orders else None

    if not first_order:
        print("No valid order found.")
        return SolveResponse(solutions=[])

    # Find a pool that has both tokens
    pool = find_pool_for_pair(
        request.liquidity, first_order.sellToken, first_order.buyToken
    )

    if not pool:
        print(
            f"No pool found for pair {first_order.sellToken} / {first_order.buyToken}"
        )
        return SolveResponse(solutions=[])

    print(f"Using pool {pool.address} with tokens {list(pool.tokens.keys())}")

    # Calculate realistic amounts based on order type
    if first_order.kind == "sell":
        # User wants to sell exact amount, we compute what they get
        sell_amount = int(first_order.sellAmount)
        buy_amount = calculate_amm_output(
            pool, first_order.sellToken, first_order.buyToken, sell_amount
        )
        executed_amount = str(sell_amount)
    else:
        # User wants to buy exact amount - calculate required sell amount
        target_buy = int(first_order.buyAmount)
        max_sell = int(first_order.sellAmount)

        # Use inverse AMM formula to calculate required input
        sell_amount = calculate_amm_input(
            pool, first_order.sellToken, first_order.buyToken, target_buy
        )

        if sell_amount <= 0:
            print(f"Cannot compute required input for output {target_buy}")
            return SolveResponse(solutions=[])

        # Check if required sell exceeds user's max
        if sell_amount > max_sell:
            print(f"Required sell {sell_amount} exceeds max {max_sell}")
            return SolveResponse(solutions=[])

        # Verify the output we'd actually get
        buy_amount = calculate_amm_output(
            pool, first_order.sellToken, first_order.buyToken, sell_amount
        )

        # For buy orders, executed_amount is the buy amount
        executed_amount = str(target_buy)

    if buy_amount <= 0:
        print(f"Cannot compute valid output amount (got {buy_amount})")
        return SolveResponse(solutions=[])

    print(f"Computed trade: sell {sell_amount} -> buy {buy_amount}")

    # Create solution with realistic clearing prices
    # prices[token] represents "how much of reference token per unit of this token"
    # For the math to work: prices[sellToken] * sellAmount = prices[buyToken] * buyAmount
    mock_solution = Solution(
        id=0,
        prices={
            first_order.sellToken: str(buy_amount),
            first_order.buyToken: str(sell_amount),
        },
        trades=[
            TradeFulfillment(
                order=first_order.uid,
                executedAmount=executed_amount,
            )
        ],
        interactions=[
            LiquidityInteraction(
                internalize=False,
                id=pool.id,
                inputToken=first_order.sellToken,
                outputToken=first_order.buyToken,
                inputAmount=str(sell_amount),
                outputAmount=str(buy_amount),
            )
        ],
        gas=250000,
    )
    print("Generated mock solution:")
    pprint.pprint(mock_solution.dict())

    return SolveResponse(solutions=[mock_solution])


# ##########################################################################


# Other endpoints for completeness
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post(
    "/reveal",
    response_model=RevealResponse,
    summary="Reveal the calldata of the previously solved auction",
    tags=["Solver"],
)
async def reveal_solution(request: RevealRequest):
    """
    Reveals mock calldata for a given solution ID.

    HOW IT'S CALLED BY THE DRIVER:
    The driver calls this endpoint via POST with a simple JSON body
    containing the `solutionId` and `auctionId`.
    Ref: /crates/driver/src/infra/api/routes/reveal/mod.rs [cite: 901, 902]
    """
    return RevealResponse(
        calldata=Calldata(
            internalized="0xdeadbeef1234", uninternalized="0xfeedface5678"
        )
    )


@app.post(
    "/settle",
    status_code=200,
    summary="Execute the previously solved auction on chain",
    tags=["Solver"],
)
async def settle_solution(request: SettleRequest):
    """
    Accepts a request to execute a solution.

    HOW IT'S CALLED BY THE DRIVER:
    The driver calls this endpoint via POST with a JSON body containing
    the `solutionId`, `submissionDeadlineLatestBlock` and `auctionId`.
    Ref: /crates/driver/src/infra/api/routes/settle/mod.rs [cite: 914, 915]
    """
    print(
        f"Accepted request to settle solution {request.solutionId} for auction {request.auctionId}."
    )
    return {}


@app.post(
    "/notify",
    status_code=200,
    summary="Receive a notification with a specific reason",
    tags=["Solver"],
)
async def receive_notification(
    # The driver sends a more complex notification object than the OpenAPI spec suggests.
    # For simplicity, we accept a raw dictionary and print it.
    notification: Dict,
):
    """
    Receives a notification from the driver.

    HOW IT'S CALLED BY THE DRIVER:
    The driver sends various notifications (e.g., Timeout, Banned, Settled)
    to this endpoint via a POST request with a JSON body.
    Ref: /crates/driver/src/infra/solver/dto/notification.rs [cite: 1265, 1266]
    """
    print(f"Notification received: {notification}")
    return {}
