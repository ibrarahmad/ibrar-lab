#!/bin/bash
# Compare all four PostgreSQL poolers side-by-side

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Default values
DURATION=60
THREADS=16
WAREHOUSES=10
POOLERS="pgbalancer pgbouncer pgpool2 pgcat"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --duration) DURATION=$2; shift 2 ;;
        --threads) THREADS=$2; shift 2 ;;
        --warehouses) WAREHOUSES=$2; shift 2 ;;
        --poolers) shift; POOLERS="$@"; break ;;
        --help|-h)
            cat << EOF
Usage: $0 [OPTIONS]

Compare PostgreSQL poolers performance side-by-side

OPTIONS:
  --duration SECONDS    Test duration (default: 60)
  --threads NUM         Number of threads (default: 16)
  --warehouses NUM      Number of warehouses (default: 10)
  --poolers LIST        Poolers to compare (default: all)
                       Choices: pgbalancer pgbouncer pgpool2 pgcat

EXAMPLES:
  # Compare all poolers
  $0 --duration 120 --threads 32

  # Compare specific poolers
  $0 --poolers pgbalancer pgbouncer --duration 60

  # Quick test
  $0 --duration 30 --threads 8 --warehouses 5

EOF
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Print banner
echo -e "${CYAN}"
cat << 'EOF'
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║       PostgreSQL Pooler Performance Comparison                               ║
║                                                                              ║
║  pgbalancer  │  pgbouncer  │  pgpool2  │  pgcat                             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BLUE}Configuration:${NC}"
echo "  Duration: ${DURATION}s"
echo "  Threads: ${THREADS}"
echo "  Warehouses: ${WAREHOUSES}"
echo "  Poolers: ${POOLERS}"
echo

# Step 1: Stop all poolers
echo -e "${YELLOW}═══ Step 1: Stopping All Poolers ═══${NC}"
./manage-poolers.sh stop all
sleep 2
echo

# Step 2: Initialize benchmark data (if needed)
echo -e "${YELLOW}═══ Step 2: Initializing Benchmark Data ═══${NC}"
if ! python3 benchmark.py --init --warehouses $WAREHOUSES 2>&1 | grep -q "already exists"; then
    echo -e "${GREEN}✓ Benchmark data initialized${NC}"
else
    echo -e "${GREEN}✓ Using existing benchmark data${NC}"
fi
echo

# Step 3: Run benchmarks for each pooler
RESULTS_FILE="$SCRIPT_DIR/results/comparison_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$SCRIPT_DIR/results"

echo -e "${YELLOW}═══ Step 3: Running Benchmarks ═══${NC}"
echo

for POOLER in $POOLERS; do
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   Benchmarking: $POOLER${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo
    
    # Stop all poolers
    ./manage-poolers.sh stop all >/dev/null 2>&1
    sleep 2
    
    # Start this pooler
    ./manage-poolers.sh start $POOLER
    sleep 3
    
    # Test connection
    if ! ./manage-poolers.sh test $POOLER; then
        echo -e "${RED}✗ Failed to connect to $POOLER, skipping...${NC}"
        echo
        continue
    fi
    
    # Run benchmark
    echo
    echo -e "${BLUE}Running benchmark for $POOLER...${NC}"
    
    POOLER_RESULTS="$SCRIPT_DIR/results/${POOLER}_$(date +%Y%m%d_%H%M%S).json"
    
    if python3 benchmark.py --run \
        --t $DURATION \
        --n $THREADS \
        --poolers $POOLER 2>&1 | tee /tmp/bench_${POOLER}.log; then
        echo -e "${GREEN}✓ Benchmark completed for $POOLER${NC}"
    else
        echo -e "${RED}✗ Benchmark failed for $POOLER${NC}"
    fi
    
    echo
    echo "─────────────────────────────────────────────────────────"
    echo
    
    sleep 5
done

# Step 4: Generate comparison report
echo -e "${YELLOW}═══ Step 4: Generating Comparison Report ═══${NC}"
echo

cat > "$RESULTS_FILE" << EOF
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║              PostgreSQL Pooler Performance Comparison                        ║
║              Generated: $(date '+%Y-%m-%d %H:%M:%S')                                      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Test Configuration:
  Duration: ${DURATION} seconds
  Threads: ${THREADS}
  Warehouses: ${WAREHOUSES}
  Poolers: ${POOLERS}

═══════════════════════════════════════════════════════════════════════════════

RESULTS SUMMARY
───────────────────────────────────────────────────────────────────────────────

EOF

# Parse results from each pooler
for POOLER in $POOLERS; do
    echo "  ${POOLER}:" >> "$RESULTS_FILE"
    
    if [ -f "/tmp/bench_${POOLER}.log" ]; then
        # Extract TPS/QPS if available
        grep -E "(TPS|QPS|Latency|Success)" /tmp/bench_${POOLER}.log >> "$RESULTS_FILE" 2>/dev/null || \
            echo "    Results not available" >> "$RESULTS_FILE"
    else
        echo "    No results file" >> "$RESULTS_FILE"
    fi
    
    echo >> "$RESULTS_FILE"
done

cat >> "$RESULTS_FILE" << 'EOF'

═══════════════════════════════════════════════════════════════════════════════

PORT ASSIGNMENTS:
  pgbalancer: 9999
  pgbouncer: 9997
  pgpool2: 9998
  pgcat: 9996
  PostgreSQL: 5432

═══════════════════════════════════════════════════════════════════════════════
EOF

# Display results
cat "$RESULTS_FILE"

echo
echo -e "${GREEN}Results saved to: $RESULTS_FILE${NC}"
echo

# Cleanup
echo -e "${YELLOW}═══ Step 5: Cleanup ═══${NC}"
./manage-poolers.sh stop all
echo

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Comparison Benchmark Complete!                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo
echo -e "${BLUE}View detailed results:${NC}"
echo "  cat $RESULTS_FILE"
echo
echo -e "${BLUE}View JSON results:${NC}"
echo "  ls -lh $SCRIPT_DIR/results/*.json"
echo

