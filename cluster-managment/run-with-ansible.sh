#!/bin/bash
# Integrated Benchmark Runner with Ansible Setup
# This script combines Ansible cluster setup with benchmark execution

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_DIR="$SCRIPT_DIR"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print banner
print_banner() {
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║   pgbalancer Cluster Setup & Benchmark Suite            ║"
    echo "║   Powered by Ansible + TPC-C                             ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Print usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

CLUSTER SETUP (Ansible):
  --setup-cluster         Full cluster setup with Ansible (PostgreSQL + pgbalancer)
  --setup-deps            Install dependencies only
  --setup-build           Build pgbalancer only
  --verify-cluster        Verify cluster setup

BENCHMARK OPERATIONS:
  --init-benchmark        Initialize benchmark data (warehouses)
  --run-benchmark         Run TPC-C benchmark
  --full-benchmark        Setup + Init + Run (complete workflow)

BENCHMARK OPTIONS:
  --poolers POOLERS       Poolers to test (default: pgbalancer)
                         Choices: pgbalancer, pgbouncer, pgpool2, pgcat
  --duration SECONDS      Test duration in seconds (default: 60)
  --threads NUM           Number of threads (default: 16)
  --warehouses NUM        Number of warehouses (default: 10)
  --type TYPE             Benchmark type: tpcc, tpcb, tpch (default: tpcc)

EXAMPLES:
  # Full setup and benchmark
  $0 --full-benchmark --poolers pgbalancer --duration 60 --threads 16

  # Setup cluster only
  $0 --setup-cluster

  # Run benchmark only (cluster already setup)
  $0 --run-benchmark --poolers pgbalancer --duration 120 --threads 32

  # Quick test
  $0 --full-benchmark --duration 30 --threads 8 --warehouses 5

  # Compare poolers
  $0 --run-benchmark --poolers pgbalancer pgbouncer --duration 60

EOF
}

# Check if Ansible is installed
check_ansible() {
    if ! command -v ansible-playbook &> /dev/null; then
        echo -e "${YELLOW}Ansible not found. Installing...${NC}"
        sudo dnf install -y ansible 2>/dev/null || \
        sudo yum install -y ansible 2>/dev/null || \
        sudo apt-get install -y ansible 2>/dev/null
    fi
}

# Run Ansible setup
setup_cluster() {
    local MODE=$1
    echo -e "${GREEN}=== CLUSTER SETUP WITH ANSIBLE ===${NC}"
    
    check_ansible
    
    cd "$BENCHMARK_DIR"
    
    case $MODE in
        full)
            echo -e "${BLUE}Running full cluster setup...${NC}"
            ansible-playbook -i ansible-inventory.ini ansible-setup.yml --ask-become-pass
            ;;
        deps)
            echo -e "${BLUE}Installing dependencies only...${NC}"
            ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=deps,python --ask-become-pass
            ;;
        build)
            echo -e "${BLUE}Building pgbalancer...${NC}"
            ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=build,config
            ;;
        verify)
            echo -e "${BLUE}Verifying cluster setup...${NC}"
            ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=verify
            ;;
    esac
    
    echo -e "${GREEN}✓ Cluster setup completed${NC}"
}

# Start pgbalancer
start_pgbalancer() {
    echo -e "${GREEN}=== STARTING PGBALANCER ===${NC}"
    
    # Check if already running
    if pgrep -x pgbalancer > /dev/null; then
        echo -e "${YELLOW}pgbalancer is already running${NC}"
        return 0
    fi
    
    # Start pgbalancer
    cd "$PROJECT_ROOT"
    
    if [ -f "pgbalancer.yaml" ]; then
        CONFIG_FILE="$PROJECT_ROOT/pgbalancer.yaml"
    elif [ -f "$BENCHMARK_DIR/conf/pgbalancer.yaml" ]; then
        CONFIG_FILE="$BENCHMARK_DIR/conf/pgbalancer.yaml"
    else
        echo -e "${RED}✗ pgbalancer.yaml not found${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Starting pgbalancer with config: $CONFIG_FILE${NC}"
    ./pgbalancer/src/pgbalancer -n -f "$CONFIG_FILE" -d > "$BENCHMARK_DIR/log/pgbalancer.log" 2>&1 &
    
    # Wait for startup
    sleep 3
    
    # Verify
    if pgrep -x pgbalancer > /dev/null; then
        echo -e "${GREEN}✓ pgbalancer started successfully${NC}"
        
        # Show pool status
        if psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;" 2>/dev/null; then
            echo -e "${GREEN}✓ pgbalancer is accepting connections${NC}"
        fi
    else
        echo -e "${RED}✗ Failed to start pgbalancer${NC}"
        tail -20 "$BENCHMARK_DIR/log/pgbalancer.log"
        return 1
    fi
}

# Initialize benchmark data
init_benchmark() {
    echo -e "${GREEN}=== INITIALIZING BENCHMARK DATA ===${NC}"
    
    cd "$BENCHMARK_DIR"
    
    python3 benchmark.py --init \
        --warehouses ${WAREHOUSES:-10} \
        --type ${BENCHMARK_TYPE:-tpcc}
    
    echo -e "${GREEN}✓ Benchmark initialization completed${NC}"
}

# Run benchmark
run_benchmark() {
    echo -e "${GREEN}=== RUNNING BENCHMARK ===${NC}"
    
    cd "$BENCHMARK_DIR"
    
    local POOLER_ARGS=""
    if [ -n "$POOLERS" ]; then
        POOLER_ARGS="--poolers $POOLERS"
    fi
    
    python3 benchmark.py --run \
        --t ${DURATION:-60} \
        --n ${THREADS:-16} \
        --type ${BENCHMARK_TYPE:-tpcc} \
        $POOLER_ARGS
    
    echo -e "${GREEN}✓ Benchmark completed${NC}"
}

# Full benchmark workflow
full_benchmark() {
    echo -e "${GREEN}=== FULL BENCHMARK WORKFLOW ===${NC}"
    
    setup_cluster full
    start_pgbalancer
    init_benchmark
    run_benchmark
    
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║   BENCHMARK COMPLETE!                                    ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Parse arguments
OPERATION=""
POOLERS=""
DURATION=""
THREADS=""
WAREHOUSES=""
BENCHMARK_TYPE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --setup-cluster)
            OPERATION="setup_full"
            shift
            ;;
        --setup-deps)
            OPERATION="setup_deps"
            shift
            ;;
        --setup-build)
            OPERATION="setup_build"
            shift
            ;;
        --verify-cluster)
            OPERATION="verify"
            shift
            ;;
        --init-benchmark)
            OPERATION="init"
            shift
            ;;
        --run-benchmark)
            OPERATION="run"
            shift
            ;;
        --full-benchmark)
            OPERATION="full"
            shift
            ;;
        --poolers)
            POOLERS="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --threads)
            THREADS="$2"
            shift 2
            ;;
        --warehouses)
            WAREHOUSES="$2"
            shift 2
            ;;
        --type)
            BENCHMARK_TYPE="$2"
            shift 2
            ;;
        --help|-h)
            print_banner
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# Execute operation
print_banner

case $OPERATION in
    setup_full)
        setup_cluster full
        ;;
    setup_deps)
        setup_cluster deps
        ;;
    setup_build)
        setup_cluster build
        ;;
    verify)
        setup_cluster verify
        ;;
    init)
        init_benchmark
        ;;
    run)
        start_pgbalancer
        run_benchmark
        ;;
    full)
        full_benchmark
        ;;
    "")
        echo -e "${YELLOW}No operation specified${NC}"
        echo
        usage
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"

