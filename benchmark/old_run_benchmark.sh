#!/bin/bash
# Modular TPC-C Benchmark Runner
# ==============================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/tpcc_config.yaml"
PYTHON_SCRIPT="${SCRIPT_DIR}/tpcc_benchmark.py"

# Default parameters
DEFAULT_THREADS=16
DEFAULT_TIME=300
DEFAULT_WAREHOUSES=10
DEFAULT_POOLERS="pgbalancer pgbouncer"

# Function to print colored output
print_status() {
    echo -e "${BLUE}✓${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Function to show usage
show_usage() {
    cat << 'USAGE_EOF'
Modular TPC-C Benchmark Suite
=============================

Usage: $0 [COMMAND] [OPTIONS]

COMMANDS:
    --install                 Install all dependencies (requires sudo)
    --setup                   Setup PostgreSQL and poolers
    --init                    Initialize TPC-C schema and data
    --run                     Run benchmark
    --cleanup                 Cleanup all resources
    --help                    Show this help message

OPTIONS (for --run):
    --t, --time SECONDS       Test duration in seconds (default: 300)
    --n, --threads NUM        Number of threads (default: 16)
    --w, --warehouses NUM     Number of warehouses (default: 10)
    --p, --poolers LIST       Poolers to test (default: pgbalancer pgbouncer)
    --config FILE             Configuration file

EXAMPLES:
    $0 --install                                    # Install dependencies
    $0 --setup                                      # Setup environment
    $0 --init                                       # Initialize TPC-C
    $0 --run --t 600 --n 32                        # Run 10-minute test with 32 threads
    $0 --run --p "pgbalancer pgbouncer pgpool2"    # Test specific poolers
    $0 --run --w 20 --t 300 --n 16                 # 20 warehouses, 5 minutes, 16 threads
    $0 --cleanup                                    # Cleanup everything

POOLERS:
    pgpool2      - Original pgpool-II
    pgbalancer   - Enhanced pgbalancer
    pgbouncer    - Lightweight connection pooler
    pgcat        - Modern connection pooler (requires Rust)
USAGE_EOF
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 >/dev/null 2>&1; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check if script exists
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Check if config exists
    if [ ! -f "$CONFIG_FILE" ]; then
        print_warning "Config file not found: $CONFIG_FILE"
        print_status "Using default configuration"
    fi
    
    print_success "Prerequisites check completed"
}

# Function to install dependencies
install_dependencies() {
    print_status "Installing dependencies..."
    
    if [ "$EUID" -ne 0 ]; then
        print_error "Installation requires root privileges. Please run with sudo."
        exit 1
    fi
    
    python3 "$PYTHON_SCRIPT" --install
    print_success "Dependencies installed"
}

# Function to setup environment
setup_environment() {
    print_status "Setting up environment..."
    
    python3 "$PYTHON_SCRIPT" --setup --config "$CONFIG_FILE"
    print_success "Environment setup completed"
}

# Function to initialize TPC-C
initialize_tpcc() {
    print_status "Initializing TPC-C..."
    
    python3 "$PYTHON_SCRIPT" --init --config "$CONFIG_FILE"
    print_success "TPC-C initialization completed"
}

# Function to run benchmark
run_benchmark() {
    local threads=$DEFAULT_THREADS
    local time=$DEFAULT_TIME
    local warehouses=$DEFAULT_WAREHOUSES
    local poolers=$DEFAULT_POOLERS
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --t|--time)
                time="$2"
                shift 2
                ;;
            --n|--threads)
                threads="$2"
                shift 2
                ;;
            --w|--warehouses)
                warehouses="$2"
                shift 2
                ;;
            --p|--poolers)
                poolers="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    print_status "Running TPC-C benchmark..."
    print_status "  threads: $threads"
    print_status "  time: $time seconds"
    print_status "  warehouses: $warehouses"
    print_status "  poolers: $poolers"
    
    python3 "$PYTHON_SCRIPT" --run \
        --config "$CONFIG_FILE" \
        --threads "$threads" \
        --time "$time" \
        --warehouses "$warehouses" \
        --poolers $poolers
    
    print_success "Benchmark completed"
}

# Function to cleanup
cleanup() {
    print_status "Cleaning up resources..."
    
    # Kill any running processes
    pkill -f "pgpool" 2>/dev/null || true
    pkill -f "pgbalancer" 2>/dev/null || true
    pkill -f "pgbouncer" 2>/dev/null || true
    pkill -f "pgcat" 2>/dev/null || true
    pkill -f "postgres" 2>/dev/null || true
    
    # Remove temporary directories
    rm -rf /tmp/tpcc_benchmark /tmp/tpcc_pgdata /tmp/sysbench 2>/dev/null || true
    
    print_success "Cleanup completed"
}

# Function to show status
show_status() {
    print_status "TPC-C Benchmark Suite Status"
    print_status "============================"
    
    echo ""
    print_status "Configuration:"
    printf "  %-15s %s\n" "config_file:" "$CONFIG_FILE"
    printf "  %-15s %s\n" "python_script:" "$PYTHON_SCRIPT"
    printf "  %-15s %s\n" "work_directory:" "/tmp/tpcc_benchmark"
    
    echo ""
    print_status "PostgreSQL:"
    if pg_isready -p 5432 -h localhost >/dev/null 2>&1; then
        print_success "  postgresql: running on port 5432"
    else
        print_warning "  postgresql: not running"
    fi
    
    echo ""
    print_status "Poolers:"
    printf "  %-12s %-10s\n" "Pooler" "Status"
    printf "  %-12s %-10s\n" "------" "------"
    for pooler in pgpool2 pgbalancer pgbouncer pgcat; do
        if command -v "$pooler" >/dev/null 2>&1; then
            printf "  %-12s %-10s\n" "$pooler" "available"
        else
            printf "  %-12s %-10s\n" "$pooler" "not available"
        fi
    done
    
    echo ""
    print_status "Sysbench:"
    if command -v sysbench >/dev/null 2>&1; then
        print_success "  sysbench: available"
    else
        print_warning "  sysbench: not available"
    fi
}

# Main script logic
main() {
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                MODULAR TPC-C BENCHMARK SUITE                     ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Parse main command
    case "${1:-}" in
        --install)
            install_dependencies
            ;;
        --setup)
            setup_environment
            ;;
        --init)
            initialize_tpcc
            ;;
        --run)
            shift
            run_benchmark "$@"
            ;;
        --cleanup)
            cleanup
            ;;
        --status)
            show_status
            ;;
        --help|-h)
            show_usage
            ;;
        "")
            print_error "No command specified"
            echo ""
            show_usage
            exit 1
            ;;
        *)
            print_error "Unknown command: $1"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
