#!/bin/bash
# pgbench benchmark wrapper for all poolers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Defaults
SCALE=100
DURATION=60
CLIENTS=32
JOBS=16
POOLERS="pgbalancer pgbouncer pgpool2 pgcat haproxy"
MODE="simple"
PROTOCOL="simple"

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run pgbench against PostgreSQL poolers for comparison

OPTIONS:
  --scale SCALE         Scale factor (default: 100)
  --duration SECONDS    Test duration (default: 60)
  --clients NUM         Number of clients (default: 32)
  --jobs NUM            Number of threads (default: 16)
  --poolers LIST        Poolers to test (default: all)
  --mode MODE           Benchmark mode (default: simple)
                       Choices: simple, select-only, read-write, read-only
  --protocol PROTOCOL   Protocol to use (default: simple)
                       Choices: simple, extended, prepared

POOLERS:
  pgbalancer (port 9999)
  pgbouncer (port 9997)
  pgpool2 (port 9998)
  pgcat (port 9996)
  haproxy (port 9995) - TCP load balancer
  direct (port 5432) - Direct PostgreSQL connection

MODES:
  simple         - Simple update test (default)
  select-only    - SELECT only (read-only)
  read-write     - Mix of reads and writes
  read-only      - Read-only workload

EXAMPLES:
  # Compare all poolers with default settings
  $0

  # Quick test
  $0 --scale 10 --duration 30 --clients 16

  # Read-only benchmark
  $0 --mode select-only --duration 120 --clients 64

  # Compare specific poolers
  $0 --poolers pgbalancer pgbouncer --duration 300

  # High-scale test
  $0 --scale 1000 --duration 300 --clients 128 --jobs 32

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --scale) SCALE=$2; shift 2 ;;
        --duration) DURATION=$2; shift 2 ;;
        --clients) CLIENTS=$2; shift 2 ;;
        --jobs) JOBS=$2; shift 2 ;;
        --poolers) shift; POOLERS="$@"; break ;;
        --mode) MODE=$2; shift 2 ;;
        --protocol) PROTOCOL=$2; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; usage; exit 1 ;;
    esac
done

# Map mode to pgbench options
case $MODE in
    simple) MODE_OPTS="" ;;
    select-only) MODE_OPTS="-S" ;;
    read-write) MODE_OPTS="" ;;
    read-only) MODE_OPTS="-S" ;;
    *) echo -e "${RED}Unknown mode: $MODE${NC}"; exit 1 ;;
esac

# Banner
echo -e "${CYAN}"
cat << 'EOF'
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║              pgbench Pooler Performance Comparison                           ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BLUE}Configuration:${NC}"
echo "  Scale: $SCALE"
echo "  Duration: ${DURATION}s"
echo "  Clients: $CLIENTS"
echo "  Jobs: $JOBS"
echo "  Mode: $MODE"
echo "  Protocol: $PROTOCOL"
echo "  Poolers: $POOLERS"
echo

# Find pgbench
PGBENCH=$(which pgbench 2>/dev/null || echo "/usr/pgsql-13/bin/pgbench")
if [ ! -x "$PGBENCH" ]; then
    echo -e "${RED}✗ pgbench not found${NC}"
    echo "Install with: sudo dnf install postgresql13-contrib"
    exit 1
fi

echo -e "${GREEN}Using pgbench: $PGBENCH${NC}"
echo

# Results file
RESULTS_FILE="$SCRIPT_DIR/results/pgbench_comparison_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$SCRIPT_DIR/results"

# Initialize database once on PostgreSQL
echo -e "${YELLOW}═══ Initializing pgbench Database ═══${NC}"
if ! $PGBENCH -i -s $SCALE -h localhost -p 5432 -U postgres postgres 2>&1; then
    echo -e "${RED}✗ Failed to initialize database${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Database initialized (scale: $SCALE)${NC}"
echo

# Run benchmark for each pooler
echo -e "${YELLOW}═══ Running Benchmarks ═══${NC}"
echo

{
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║   pgbench Pooler Performance Comparison                                      ║"
    echo "║   Generated: $(date '+%Y-%m-%d %H:%M:%S')                                                 ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo
    echo "Configuration:"
    echo "  Scale: $SCALE"
    echo "  Duration: ${DURATION}s"
    echo "  Clients: $CLIENTS"
    echo "  Jobs: $JOBS"
    echo "  Mode: $MODE"
    echo "  Protocol: $PROTOCOL"
    echo
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo
} > "$RESULTS_FILE"

# Benchmark each pooler
for POOLER in $POOLERS direct; do
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   Benchmarking: $POOLER${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo
    
    # Determine port
    case $POOLER in
        pgbalancer) PORT=9999 ;;
        pgbouncer) PORT=9997 ;;
        pgpool2) PORT=9998 ;;
        pgcat) PORT=9996 ;;
        haproxy) PORT=9995 ;;
        direct) PORT=5432 ;;
        *) continue ;;
    esac
    
    # Stop all poolers except the one we're testing
    if [ "$POOLER" != "direct" ]; then
        ./manage-poolers.sh stop all >/dev/null 2>&1
        sleep 2
        ./manage-poolers.sh start $POOLER
        sleep 3
        
        # Verify connection
        if ! ./manage-poolers.sh test $POOLER >/dev/null 2>&1; then
            echo -e "${RED}✗ Cannot connect to $POOLER, skipping...${NC}"
            echo
            {
                echo "$POOLER (port $PORT):"
                echo "  Status: FAILED - Could not connect"
                echo
            } >> "$RESULTS_FILE"
            continue
        fi
    fi
    
    # Run pgbench
    echo -e "${BLUE}Running pgbench on $POOLER (port $PORT)...${NC}"
    echo
    
    TEMP_RESULTS="/tmp/pgbench_${POOLER}.txt"
    
    if $PGBENCH \
        -h localhost \
        -p $PORT \
        -U postgres \
        -c $CLIENTS \
        -j $JOBS \
        -T $DURATION \
        -P 10 \
        --protocol=$PROTOCOL \
        $MODE_OPTS \
        postgres 2>&1 | tee "$TEMP_RESULTS"; then
        
        echo -e "${GREEN}✓ Benchmark completed for $POOLER${NC}"
        
        # Extract key metrics
        TPS=$(grep "^tps" "$TEMP_RESULTS" | tail -1 | awk '{print $3}')
        LATENCY=$(grep "^latency average" "$TEMP_RESULTS" | awk '{print $4}')
        
        {
            echo "$POOLER (port $PORT):"
            echo "  TPS: $TPS"
            echo "  Latency: ${LATENCY}ms"
            echo "  Raw Output:"
            grep -E "(tps|latency|including connections establishing)" "$TEMP_RESULTS" | sed 's/^/    /'
            echo
        } >> "$RESULTS_FILE"
    else
        echo -e "${RED}✗ Benchmark failed for $POOLER${NC}"
        {
            echo "$POOLER (port $PORT):"
            echo "  Status: FAILED"
            echo
        } >> "$RESULTS_FILE"
    fi
    
    echo
    echo "─────────────────────────────────────────────────────────"
    echo
    
    sleep 3
done

# Add summary
{
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo
    echo "PORT ASSIGNMENTS:"
    echo "  pgbalancer: 9999"
    echo "  pgbouncer: 9997"
    echo "  pgpool2: 9998"
    echo "  pgcat: 9996"
    echo "  direct PostgreSQL: 5432"
    echo
    echo "═══════════════════════════════════════════════════════════════════════════════"
} >> "$RESULTS_FILE"

# Display results
cat "$RESULTS_FILE"

echo
echo -e "${GREEN}Results saved to: $RESULTS_FILE${NC}"
echo

# Cleanup
echo -e "${YELLOW}═══ Cleanup ═══${NC}"
./manage-poolers.sh stop all >/dev/null 2>&1 || true

echo
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   pgbench Comparison Complete!                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

