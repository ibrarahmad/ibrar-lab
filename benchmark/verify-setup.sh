#!/bin/bash
# Verify pgbalancer cluster setup (No Ansible required)

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   pgbalancer Cluster Verification                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo

# Check PostgreSQL
echo -ne "${YELLOW}Checking PostgreSQL...${NC} "
if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo -e "${GREEN}✓ RUNNING${NC}"
    PG_OK=1
else
    echo -e "${RED}✗ NOT RUNNING${NC}"
    PG_OK=0
fi

# Check pgbalancer process
echo -ne "${YELLOW}Checking pgbalancer process...${NC} "
if pgrep -x pgbalancer > /dev/null; then
    PID=$(pgrep -x pgbalancer | head -1)
    echo -e "${GREEN}✓ RUNNING (PID: $PID)${NC}"
    PGB_PROC=1
else
    echo -e "${RED}✗ NOT RUNNING${NC}"
    PGB_PROC=0
fi

# Check pgbalancer port
echo -ne "${YELLOW}Checking pgbalancer port 9999...${NC} "
if ss -tlnp 2>/dev/null | grep -q :9999; then
    echo -e "${GREEN}✓ LISTENING${NC}"
    PGB_PORT=1
else
    echo -e "${RED}✗ NOT LISTENING${NC}"
    PGB_PORT=0
fi

# Test connection
echo -ne "${YELLOW}Testing pgbalancer connection...${NC} "
if psql -h localhost -p 9999 -U postgres -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ SUCCESS${NC}"
    PGB_CONN=1
else
    echo -e "${RED}✗ FAILED${NC}"
    PGB_CONN=0
fi

# Check pool nodes
echo
echo -e "${BLUE}Pool Nodes Status:${NC}"
if psql -h localhost -p 9999 -U postgres -d postgres -c "SHOW pool_nodes;" 2>/dev/null; then
    POOL_OK=1
else
    echo -e "${RED}Could not retrieve pool nodes${NC}"
    POOL_OK=0
fi

# Check configuration file
echo
echo -ne "${YELLOW}Checking YAML configuration...${NC} "
if [ -f "/home/pgedge/pge/pgbalancer.yaml" ]; then
    echo -e "${GREEN}✓ FOUND${NC}"
    echo -e "  Location: /home/pgedge/pge/pgbalancer.yaml"
    CONFIG_OK=1
elif [ -f "/home/pgedge/pge/benchmark/conf/pgbalancer.yaml" ]; then
    echo -e "${GREEN}✓ FOUND${NC}"
    echo -e "  Location: /home/pgedge/pge/benchmark/conf/pgbalancer.yaml"
    CONFIG_OK=1
else
    echo -e "${RED}✗ NOT FOUND${NC}"
    CONFIG_OK=0
fi

# Check benchmark files
echo -ne "${YELLOW}Checking benchmark files...${NC} "
if [ -f "/home/pgedge/pge/benchmark/benchmark.py" ]; then
    echo -e "${GREEN}✓ FOUND${NC}"
    BENCH_OK=1
else
    echo -e "${RED}✗ NOT FOUND${NC}"
    BENCH_OK=0
fi

# Overall status
echo
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Overall Status                                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

TOTAL_CHECKS=6
PASSED=$((PG_OK + PGB_PROC + PGB_PORT + PGB_CONN + CONFIG_OK + BENCH_OK))

if [ $PASSED -eq $TOTAL_CHECKS ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED ($PASSED/$TOTAL_CHECKS)${NC}"
    echo -e "${GREEN}✓ READY FOR BENCHMARKING!${NC}"
    echo
    echo -e "${BLUE}Next Steps:${NC}"
    echo "  ./run-with-ansible.sh --init-benchmark --warehouses 10"
    echo "  ./run-with-ansible.sh --run-benchmark --duration 60 --threads 16"
    exit 0
else
    echo -e "${RED}✗ SOME CHECKS FAILED ($PASSED/$TOTAL_CHECKS)${NC}"
    echo
    echo -e "${YELLOW}To fix:${NC}"
    
    if [ $PG_OK -eq 0 ]; then
        echo "  - Start PostgreSQL: sudo systemctl start postgresql-13"
    fi
    
    if [ $PGB_PROC -eq 0 ] || [ $PGB_PORT -eq 0 ]; then
        echo "  - Start pgbalancer: cd /home/pgedge/pge && ./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml &"
    fi
    
    if [ $CONFIG_OK -eq 0 ]; then
        echo "  - Create config: cp pgbalancer.yaml.sample pgbalancer.yaml"
    fi
    
    if [ $BENCH_OK -eq 0 ]; then
        echo "  - Check benchmark directory exists"
    fi
    
    echo
    echo -e "${BLUE}Or run full setup:${NC}"
    echo "  ./run-with-ansible.sh --setup-cluster"
    
    exit 1
fi

