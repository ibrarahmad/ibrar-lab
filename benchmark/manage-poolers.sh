#!/bin/bash
# Manage all four PostgreSQL poolers for benchmarking

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Pooler configurations
PGBALANCER_PORT=9999
PGBOUNCER_PORT=9997
PGPOOL2_PORT=9998
PGCAT_PORT=9996
HAPROXY_PORT=9995

usage() {
    cat << EOF
Usage: $0 [COMMAND] [POOLER]

COMMANDS:
  start [POOLER]    Start specified pooler (or all if not specified)
  stop [POOLER]     Stop specified pooler (or all if not specified)
  restart [POOLER]  Restart specified pooler (or all if not specified)
  status            Show status of all poolers
  logs [POOLER]     Show logs for specified pooler
  test [POOLER]     Test connection to specified pooler (or all)

POOLERS:
  pgbalancer        pgbalancer (port $PGBALANCER_PORT)
  pgbouncer         pgbouncer (port $PGBOUNCER_PORT)
  pgpool2           pgpool2 (port $PGPOOL2_PORT)
  pgcat             pgcat (port $PGCAT_PORT)
  haproxy           HAProxy TCP load balancer (port $HAPROXY_PORT)
  all               All poolers (default)

EXAMPLES:
  $0 start all              # Start all poolers
  $0 start pgbalancer       # Start pgbalancer only
  $0 status                 # Show status of all poolers
  $0 test pgbouncer         # Test pgbouncer connection
  $0 stop all               # Stop all poolers

EOF
}

# Start pgbalancer
start_pgbalancer() {
    echo -e "${BLUE}Starting pgbalancer...${NC}"
    
    if pgrep -x pgbalancer > /dev/null; then
        echo -e "${YELLOW}pgbalancer is already running${NC}"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    if [ -f "$PROJECT_ROOT/pgbalancer.yaml" ]; then
        CONFIG="$PROJECT_ROOT/pgbalancer.yaml"
    else
        CONFIG="$SCRIPT_DIR/conf/pgbalancer.yaml"
    fi
    
    ./pgbalancer/src/pgbalancer -n -f "$CONFIG" > "$SCRIPT_DIR/log/pgbalancer.log" 2>&1 &
    sleep 2
    
    if pgrep -x pgbalancer > /dev/null; then
        echo -e "${GREEN}✓ pgbalancer started on port $PGBALANCER_PORT${NC}"
    else
        echo -e "${RED}✗ Failed to start pgbalancer${NC}"
        return 1
    fi
}

# Start pgbouncer
start_pgbouncer() {
    echo -e "${BLUE}Starting pgbouncer...${NC}"
    
    if pgrep -x pgbouncer > /dev/null; then
        echo -e "${YELLOW}pgbouncer is already running${NC}"
        return 0
    fi
    
    if [ -f /etc/pgbouncer/pgbouncer.ini ]; then
        CONFIG=/etc/pgbouncer/pgbouncer.ini
    else
        CONFIG="$SCRIPT_DIR/conf/pgbouncer.ini"
    fi
    
    pgbouncer -d "$CONFIG" > "$SCRIPT_DIR/log/pgbouncer.log" 2>&1 || true
    sleep 1
    
    if pgrep -x pgbouncer > /dev/null; then
        echo -e "${GREEN}✓ pgbouncer started on port $PGBOUNCER_PORT${NC}"
    else
        echo -e "${RED}✗ Failed to start pgbouncer (may not be installed)${NC}"
        return 1
    fi
}

# Start pgpool2
start_pgpool2() {
    echo -e "${BLUE}Starting pgpool2...${NC}"
    
    if pgrep -x pgpool > /dev/null; then
        echo -e "${YELLOW}pgpool2 is already running${NC}"
        return 0
    fi
    
    if [ -f /etc/pgpool-II/pgpool.conf ]; then
        CONFIG=/etc/pgpool-II/pgpool.conf
    else
        CONFIG="$SCRIPT_DIR/conf/pgpool2.conf"
    fi
    
    pgpool -n -f "$CONFIG" -D > "$SCRIPT_DIR/log/pgpool2.log" 2>&1 &
    sleep 2
    
    if pgrep -x pgpool > /dev/null; then
        echo -e "${GREEN}✓ pgpool2 started on port $PGPOOL2_PORT${NC}"
    else
        echo -e "${RED}✗ Failed to start pgpool2 (may not be installed)${NC}"
        return 1
    fi
}

# Start pgcat
start_pgcat() {
    echo -e "${BLUE}Starting pgcat...${NC}"
    
    if pgrep -x pgcat > /dev/null; then
        echo -e "${YELLOW}pgcat is already running${NC}"
        return 0
    fi
    
    if [ -f /tmp/pgcat/target/release/pgcat ]; then
        PGCAT_BIN=/tmp/pgcat/target/release/pgcat
    elif [ -f /usr/local/bin/pgcat ]; then
        PGCAT_BIN=/usr/local/bin/pgcat
    else
        echo -e "${RED}✗ pgcat binary not found (run Ansible setup)${NC}"
        return 1
    fi
    
    CONFIG=/tmp/pgcat/pgcat.toml
    
    $PGCAT_BIN "$CONFIG" > "$SCRIPT_DIR/log/pgcat.log" 2>&1 &
    sleep 2
    
    if pgrep -x pgcat > /dev/null; then
        echo -e "${GREEN}✓ pgcat started on port $PGCAT_PORT${NC}"
    else
        echo -e "${RED}✗ Failed to start pgcat${NC}"
        return 1
    fi
}

# Start HAProxy
start_haproxy() {
    echo -e "${BLUE}Starting HAProxy...${NC}"
    
    if pgrep -x haproxy > /dev/null; then
        echo -e "${YELLOW}HAProxy is already running${NC}"
        return 0
    fi
    
    if [ -f /etc/haproxy/haproxy.cfg ]; then
        CONFIG=/etc/haproxy/haproxy.cfg
    else
        echo -e "${RED}✗ HAProxy config not found (run Ansible setup)${NC}"
        return 1
    fi
    
    # Check if haproxy command exists
    if ! command -v haproxy &> /dev/null; then
        echo -e "${RED}✗ HAProxy not installed${NC}"
        return 1
    fi
    
    # Start HAProxy
    sudo haproxy -f "$CONFIG" -D > "$SCRIPT_DIR/log/haproxy.log" 2>&1 || \
        haproxy -f "$CONFIG" -D > "$SCRIPT_DIR/log/haproxy.log" 2>&1
    sleep 2
    
    if pgrep -x haproxy > /dev/null; then
        echo -e "${GREEN}✓ HAProxy started on port $HAPROXY_PORT${NC}"
        echo -e "${GREEN}✓ HAProxy stats available at http://localhost:8404/stats${NC}"
    else
        echo -e "${RED}✗ Failed to start HAProxy${NC}"
        return 1
    fi
}

# Stop poolers
stop_pgbalancer() {
    echo -e "${BLUE}Stopping pgbalancer...${NC}"
    pkill -9 pgbalancer 2>/dev/null || true
    echo -e "${GREEN}✓ pgbalancer stopped${NC}"
}

stop_pgbouncer() {
    echo -e "${BLUE}Stopping pgbouncer...${NC}"
    pkill -9 pgbouncer 2>/dev/null || true
    echo -e "${GREEN}✓ pgbouncer stopped${NC}"
}

stop_pgpool2() {
    echo -e "${BLUE}Stopping pgpool2...${NC}"
    pkill -9 pgpool 2>/dev/null || true
    echo -e "${GREEN}✓ pgpool2 stopped${NC}"
}

stop_pgcat() {
    echo -e "${BLUE}Stopping pgcat...${NC}"
    pkill -9 pgcat 2>/dev/null || true
    echo -e "${GREEN}✓ pgcat stopped${NC}"
}

stop_haproxy() {
    echo -e "${BLUE}Stopping HAProxy...${NC}"
    sudo pkill -9 haproxy 2>/dev/null || pkill -9 haproxy 2>/dev/null || true
    echo -e "${GREEN}✓ HAProxy stopped${NC}"
}

# Test connection
test_pooler() {
    local NAME=$1
    local PORT=$2
    
    echo -ne "${YELLOW}Testing $NAME (port $PORT)...${NC} "
    if psql -h localhost -p $PORT -U postgres -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ SUCCESS${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# Show status
show_status() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║   PostgreSQL Poolers Status                              ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # PostgreSQL
    echo -ne "${YELLOW}PostgreSQL (5432):${NC} "
    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        echo -e "${GREEN}✓ RUNNING${NC}"
    else
        echo -e "${RED}✗ NOT RUNNING${NC}"
    fi
    
    # pgbalancer
    echo -ne "${YELLOW}pgbalancer ($PGBALANCER_PORT):${NC} "
    if pgrep -x pgbalancer > /dev/null; then
        PID=$(pgrep -x pgbalancer | head -1)
        echo -e "${GREEN}✓ RUNNING (PID: $PID)${NC}"
    else
        echo -e "${RED}✗ NOT RUNNING${NC}"
    fi
    
    # pgbouncer
    echo -ne "${YELLOW}pgbouncer ($PGBOUNCER_PORT):${NC} "
    if pgrep -x pgbouncer > /dev/null; then
        PID=$(pgrep -x pgbouncer | head -1)
        echo -e "${GREEN}✓ RUNNING (PID: $PID)${NC}"
    else
        echo -e "${RED}✗ NOT RUNNING${NC}"
    fi
    
    # pgpool2
    echo -ne "${YELLOW}pgpool2 ($PGPOOL2_PORT):${NC} "
    if pgrep -x pgpool > /dev/null; then
        PID=$(pgrep -x pgpool | head -1)
        echo -e "${GREEN}✓ RUNNING (PID: $PID)${NC}"
    else
        echo -e "${RED}✗ NOT RUNNING${NC}"
    fi
    
    # pgcat
    echo -ne "${YELLOW}pgcat ($PGCAT_PORT):${NC} "
    if pgrep -x pgcat > /dev/null; then
        PID=$(pgrep -x pgcat | head -1)
        echo -e "${GREEN}✓ RUNNING (PID: $PID)${NC}"
    else
        echo -e "${RED}✗ NOT RUNNING${NC}"
    fi
    
    # HAProxy
    echo -ne "${YELLOW}HAProxy ($HAPROXY_PORT):${NC} "
    if pgrep -x haproxy > /dev/null; then
        PID=$(pgrep -x haproxy | head -1)
        echo -e "${GREEN}✓ RUNNING (PID: $PID)${NC}"
        echo -e "${BLUE}  Stats: http://localhost:8404/stats${NC}"
    else
        echo -e "${RED}✗ NOT RUNNING${NC}"
    fi
    
    # Listening ports
    echo
    echo -e "${BLUE}Listening Ports:${NC}"
    ss -tlnp 2>/dev/null | grep -E ":(5432|$PGBALANCER_PORT|$PGBOUNCER_PORT|$PGPOOL2_PORT|$PGCAT_PORT|$HAPROXY_PORT|8404)" | \
        awk '{print "  "$4}' | sort -u || echo "  None"
}

# Show logs
show_logs() {
    local POOLER=$1
    
    case $POOLER in
        pgbalancer)
            tail -50 "$SCRIPT_DIR/log/pgbalancer.log"
            ;;
        pgbouncer)
            tail -50 "$SCRIPT_DIR/log/pgbouncer.log"
            ;;
        pgpool2)
            tail -50 "$SCRIPT_DIR/log/pgpool2.log"
            ;;
        pgcat)
            tail -50 "$SCRIPT_DIR/log/pgcat.log"
            ;;
        haproxy)
            tail -50 "$SCRIPT_DIR/log/haproxy.log"
            ;;
        *)
            echo -e "${RED}Unknown pooler: $POOLER${NC}"
            exit 1
            ;;
    esac
}

# Main logic
COMMAND=$1
POOLER=${2:-all}

case $COMMAND in
    start)
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║   Starting Poolers                                       ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
        echo
        
        case $POOLER in
            pgbalancer) start_pgbalancer ;;
            pgbouncer) start_pgbouncer ;;
            pgpool2) start_pgpool2 ;;
            pgcat) start_pgcat ;;
            haproxy) start_haproxy ;;
            all)
                start_pgbalancer
                start_pgbouncer
                start_pgpool2
                start_pgcat
                start_haproxy
                ;;
            *) echo -e "${RED}Unknown pooler: $POOLER${NC}"; exit 1 ;;
        esac
        ;;
        
    stop)
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║   Stopping Poolers                                       ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
        echo
        
        case $POOLER in
            pgbalancer) stop_pgbalancer ;;
            pgbouncer) stop_pgbouncer ;;
            pgpool2) stop_pgpool2 ;;
            pgcat) stop_pgcat ;;
            haproxy) stop_haproxy ;;
            all)
                stop_pgbalancer
                stop_pgbouncer
                stop_pgpool2
                stop_pgcat
                stop_haproxy
                ;;
            *) echo -e "${RED}Unknown pooler: $POOLER${NC}"; exit 1 ;;
        esac
        ;;
        
    restart)
        $0 stop $POOLER
        sleep 2
        $0 start $POOLER
        ;;
        
    status)
        show_status
        ;;
        
    logs)
        if [ "$POOLER" == "all" ]; then
            echo -e "${RED}Please specify a pooler for logs${NC}"
            exit 1
        fi
        show_logs $POOLER
        ;;
        
    test)
        echo -e "${BLUE}Testing Pooler Connections:${NC}"
        echo
        
        case $POOLER in
            pgbalancer) test_pooler "pgbalancer" $PGBALANCER_PORT ;;
            pgbouncer) test_pooler "pgbouncer" $PGBOUNCER_PORT ;;
            pgpool2) test_pooler "pgpool2" $PGPOOL2_PORT ;;
            pgcat) test_pooler "pgcat" $PGCAT_PORT ;;
            haproxy) test_pooler "HAProxy" $HAPROXY_PORT ;;
            all)
                test_pooler "pgbalancer" $PGBALANCER_PORT
                test_pooler "pgbouncer" $PGBOUNCER_PORT
                test_pooler "pgpool2" $PGPOOL2_PORT
                test_pooler "pgcat" $PGCAT_PORT
                test_pooler "HAProxy" $HAPROXY_PORT
                ;;
            *) echo -e "${RED}Unknown pooler: $POOLER${NC}"; exit 1 ;;
        esac
        ;;
        
    --help|-h)
        usage
        ;;
        
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        usage
        exit 1
        ;;
esac

echo

