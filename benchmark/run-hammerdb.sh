#!/bin/bash
# HammerDB benchmark wrapper for all poolers

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
WAREHOUSES=100
DURATION=5
USERS=16
POOLERS="pgbalancer pgbouncer pgpool2 pgcat haproxy"
BENCHMARK_TYPE="tpcc"

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run HammerDB benchmark against PostgreSQL poolers

OPTIONS:
  --warehouses NUM      Number of warehouses (default: 100)
  --duration MINUTES    Test duration in minutes (default: 5)
  --users NUM           Virtual users (default: 16)
  --poolers LIST        Poolers to test (default: all)
  --type TYPE           Benchmark type (default: tpcc)
                       Choices: tpcc, tpch

POOLERS:
  pgbalancer (port 9999)
  pgbouncer (port 9997)
  pgpool2 (port 9998)
  pgcat (port 9996)
  haproxy (port 9995)
  direct (port 5432)

EXAMPLES:
  # Standard TPC-C benchmark (all poolers)
  $0 --warehouses 100 --duration 5 --users 16

  # Quick test
  $0 --warehouses 10 --duration 2 --users 4

  # Compare specific poolers
  $0 --poolers pgbalancer pgbouncer --duration 10

  # Large scale test
  $0 --warehouses 500 --duration 30 --users 64

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --warehouses) WAREHOUSES=$2; shift 2 ;;
        --duration) DURATION=$2; shift 2 ;;
        --users) USERS=$2; shift 2 ;;
        --poolers) shift; POOLERS="$@"; break ;;
        --type) BENCHMARK_TYPE=$2; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; usage; exit 1 ;;
    esac
done

# Banner
echo -e "${CYAN}"
cat << 'EOF'
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║            HammerDB Pooler Performance Comparison                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check HammerDB installation
HAMMERDB="/usr/local/bin/hammerdbcli"
if [ ! -x "$HAMMERDB" ] && [ -f "/opt/HammerDB-4.9/hammerdbcli" ]; then
    HAMMERDB="/opt/HammerDB-4.9/hammerdbcli"
fi

if [ ! -x "$HAMMERDB" ]; then
    echo -e "${RED}✗ HammerDB not found${NC}"
    echo
    echo "Install with Ansible:"
    echo "  ./run-with-ansible.sh --setup-cluster"
    echo
    echo "Or manually:"
    echo "  wget https://github.com/TPC-Council/HammerDB/releases/download/v4.9/HammerDB-4.9-Linux.tar.gz"
    echo "  tar -xzf HammerDB-4.9-Linux.tar.gz -C /opt/"
    exit 1
fi

echo -e "${GREEN}Using HammerDB: $HAMMERDB${NC}"
echo
echo -e "${BLUE}Configuration:${NC}"
echo "  Type: $BENCHMARK_TYPE"
echo "  Warehouses: $WAREHOUSES"
echo "  Duration: ${DURATION} minutes"
echo "  Virtual Users: $USERS"
echo "  Poolers: $POOLERS"
echo

# Results file
RESULTS_FILE="$SCRIPT_DIR/results/hammerdb_comparison_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$SCRIPT_DIR/results"
mkdir -p "$SCRIPT_DIR/hammerdb"

{
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║   HammerDB Pooler Performance Comparison                                     ║"
    echo "║   Generated: $(date '+%Y-%m-%d %H:%M:%S')                                                 ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo
    echo "Configuration:"
    echo "  Benchmark Type: $BENCHMARK_TYPE"
    echo "  Warehouses: $WAREHOUSES"
    echo "  Duration: ${DURATION} minutes"
    echo "  Virtual Users: $USERS"
    echo
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo
} > "$RESULTS_FILE"

# Run benchmark for each pooler
for POOLER in $POOLERS direct; do
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   Benchmarking: $POOLER${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo
    
    # Determine port and host
    case $POOLER in
        pgbalancer) PORT=9999; HOST="localhost" ;;
        pgbouncer) PORT=9997; HOST="localhost" ;;
        pgpool2) PORT=9998; HOST="localhost" ;;
        pgcat) PORT=9996; HOST="localhost" ;;
        haproxy) PORT=9995; HOST="localhost" ;;
        direct) PORT=5432; HOST="localhost" ;;
        *) continue ;;
    esac
    
    # Stop all poolers and start the one we're testing
    if [ "$POOLER" != "direct" ]; then
        ./manage-poolers.sh stop all >/dev/null 2>&1
        sleep 2
        ./manage-poolers.sh start $POOLER
        sleep 3
        
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
    
    # Create HammerDB TCL script
    TCL_SCRIPT="$SCRIPT_DIR/hammerdb/benchmark_${POOLER}.tcl"
    
    cat > "$TCL_SCRIPT" << EOFTCL
#!/usr/bin/tclsh

puts "HammerDB TPC-C Benchmark for $POOLER"
puts "======================================="

dbset db pg
dbset bm TPC-C

diset connection pg_host $HOST
diset connection pg_port $PORT
diset tpcc pg_superuser postgres
diset tpcc pg_superuserpass ""
diset tpcc pg_defaultdbase postgres
diset tpcc pg_user postgres
diset tpcc pg_pass ""
diset tpcc pg_dbase hammerdb
diset tpcc pg_vacuum false
diset tpcc pg_dritasnap false
diset tpcc pg_oracompat false
diset tpcc pg_storedprocs false

# Build schema only on first run
if { "$POOLER" == "pgbalancer" } {
    diset tpcc pg_count_ware $WAREHOUSES
    diset tpcc pg_num_vu 1
    diset tpcc pg_timeprofile false
    puts "Building TPC-C schema..."
    buildschema
    waittocomplete
}

# Run benchmark
vuset logtotemp 1
loadscript
puts "Running TPC-C benchmark..."
vuset vu $USERS
vucreate
vurun
runtimer $DURATION
vudestroy
quit
EOFTCL
    
    echo -e "${BLUE}Running HammerDB on $POOLER (port $PORT)...${NC}"
    
    TEMP_OUTPUT="/tmp/hammerdb_${POOLER}.log"
    
    if $HAMMERDB auto "$TCL_SCRIPT" > "$TEMP_OUTPUT" 2>&1; then
        echo -e "${GREEN}✓ Benchmark completed for $POOLER${NC}"
        
        # Extract metrics
        TPM=$(grep -i "TPM" "$TEMP_OUTPUT" | tail -1 || echo "N/A")
        NOPM=$(grep -i "NOPM" "$TEMP_OUTPUT" | tail -1 || echo "N/A")
        
        {
            echo "$POOLER (port $PORT):"
            echo "  TPM: $TPM"
            echo "  NOPM: $NOPM"
            echo "  Raw Output:"
            tail -20 "$TEMP_OUTPUT" | sed 's/^/    /'
            echo
        } >> "$RESULTS_FILE"
    else
        echo -e "${RED}✗ Benchmark failed for $POOLER${NC}"
        {
            echo "$POOLER (port $PORT):"
            echo "  Status: FAILED"
            echo "  Error:"
            tail -10 "$TEMP_OUTPUT" | sed 's/^/    /'
            echo
        } >> "$RESULTS_FILE"
    fi
    
    echo
    echo "─────────────────────────────────────────────────────────"
    echo
    
    sleep 3
done

# Finalize results
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
echo "║   HammerDB Comparison Complete!                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo
echo -e "${BLUE}View detailed results:${NC}"
echo "  cat $RESULTS_FILE"
echo

