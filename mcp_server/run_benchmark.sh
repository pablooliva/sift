#!/bin/bash
# Wrapper script to run performance benchmarks with proper environment

cd "$(dirname "$0")"

# Load environment from parent .env
set -a
source ../.env
set +a

# Override for local connection
export NEO4J_URI="bolt://localhost:7687"
export TXTAI_API_URL="http://localhost:8300"

# Run simplified benchmark
python benchmark_simple.py
