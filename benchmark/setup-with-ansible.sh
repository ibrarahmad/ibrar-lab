#!/bin/bash
# Setup pgbalancer benchmark environment using Ansible

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}pgbalancer Benchmark Setup with Ansible${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Check if Ansible is installed
if ! command -v ansible-playbook &> /dev/null; then
    echo -e "${YELLOW}Ansible not found. Installing...${NC}"
    sudo dnf install -y ansible || sudo yum install -y ansible || sudo apt-get install -y ansible
fi

# Check Ansible version
echo -e "${GREEN}Ansible version:${NC}"
ansible --version | head -1

# Run Ansible playbook
echo
echo -e "${GREEN}Running Ansible playbook...${NC}"
echo

cd "$SCRIPT_DIR"

# Run with different tags based on arguments
if [ "$1" == "--deps-only" ]; then
    ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=deps,python
elif [ "$1" == "--build-only" ]; then
    ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=build,config
elif [ "$1" == "--verify" ]; then
    ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=verify
else
    # Run full setup
    ansible-playbook -i ansible-inventory.ini ansible-setup.yml --ask-become-pass
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${YELLOW}Quick Start Commands:${NC}"
echo
echo -e "  ${GREEN}1. Start pgbalancer:${NC}"
echo -e "     cd /home/pgedge/pge"
echo -e "     ./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml -d &"
echo
echo -e "  ${GREEN}2. Run simple benchmark:${NC}"
echo -e "     cd /home/pgedge/pge/benchmark"
echo -e "     python3 benchmark.py --poolers pgbalancer --duration 30"
echo
echo -e "  ${GREEN}3. Run comprehensive tests:${NC}"
echo -e "     ./run_benchmark.sh --poolers pgbalancer"
echo
echo -e "  ${GREEN}4. View configuration:${NC}"
echo -e "     ./pgbalancer/src/pgbalancer --show-config -f pgbalancer.yaml | less"
echo

