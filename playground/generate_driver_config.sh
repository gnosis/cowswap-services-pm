#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEMPLATE_PATH="$SCRIPT_DIR/configs/driver.toml.template"
OUTPUT_PATH="$SCRIPT_DIR/configs/driver.toml"
SOLVER_ENV_PATH="$SCRIPT_DIR/../../prediction-market-cowswap-solver/.env"

if [ ! -f "$SOLVER_ENV_PATH" ]; then
    echo "Env file not found: $SOLVER_ENV_PATH" >&2
    exit 1
fi

PYSOLVER_KEY=$(sed -n "s/^SOLVER_PRIVATE_KEY=['\"]\{0,1\}\([^'\"#[:space:]]*\)['\"]\{0,1\}[[:space:]]*$/\1/p" "$SOLVER_ENV_PATH" | head -n 1)

if [ -z "$PYSOLVER_KEY" ]; then
    echo "Missing SOLVER_PRIVATE_KEY in prediction-market-cowswap-solver/.env" >&2
    exit 1
fi

# Use the same key for both for simplicity.
sed \
    -e "s|{{SOLVER_PRIVATE_KEY}}|$PYSOLVER_KEY|g" \
    -e "s|{{BASELINE_PRIVATE_KEY}}|$PYSOLVER_KEY|g" \
    "$TEMPLATE_PATH" > "$OUTPUT_PATH"
echo "Generated $OUTPUT_PATH"
