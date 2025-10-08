#!/usr/bin/env python3
"""
PostgreSQL Pooler Cluster Manager
==================================

Manages multi-pooler PostgreSQL cluster setup, configuration, and operations.
Supports: pgbalancer, pgbouncer, pgpool2, pgcat, HAProxy

Author: pgElephant, Inc.
License: MIT
"""

import argparse
import subprocess
import sys
import os
import time
import yaml
import shutil
from pathlib import Path

# Colors for output
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'

def print_banner(title):
    """Print a formatted banner"""
    print(f"{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print(f"║  {title:76}║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.NC}")

def run_cmd(cmd, check=True, capture=False, shell=False):
    """Run a shell command"""
    try:
        if capture:
            result = subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
            return result.returncode == 0, result.stdout
        else:
            result = subprocess.run(cmd, shell=shell, check=check)
            return result.returncode == 0, ""
    except subprocess.CalledProcessError as e:
        return False, str(e)

class ClusterManager:
    """Manages PostgreSQL pooler cluster"""
    
    def __init__(self):
        self.script_dir = Path(__file__).parent.absolute()
        self.project_root = self.script_dir.parent
        
        # Port assignments
        self.ports = {
            'postgres': 5432,
            'pgbalancer': 9999,
            'pgpool2': 9998,
            'pgbouncer': 9997,
            'pgcat': 9996,
            'haproxy': 9995,
            'haproxy_stats': 8404
        }
        
        self.poolers = ['pgbalancer', 'pgbouncer', 'pgpool2', 'pgcat', 'haproxy']
    
    def setup_cluster(self):
        """Setup entire cluster using Ansible"""
        print_banner("Setting Up Multi-Pooler Cluster with Ansible")
        
        print(f"{Colors.BLUE}Installing all poolers and dependencies...{Colors.NC}")
        print()
        
        ansible_playbook = self.script_dir / "ansible-setup.yml"
        ansible_inventory = self.script_dir / "ansible-inventory.ini"
        
        if not ansible_playbook.exists():
            print(f"{Colors.RED}✗ Ansible playbook not found: {ansible_playbook}{Colors.NC}")
            return False
        
        # Check if Ansible is installed
        success, _ = run_cmd(['which', 'ansible-playbook'], check=False, capture=True)
        if not success:
            print(f"{Colors.YELLOW}Ansible not found. Installing...{Colors.NC}")
            run_cmd(['sudo', 'dnf', 'install', '-y', 'ansible'], check=False)
        
        # Run Ansible playbook
        cmd = [
            'ansible-playbook',
            '-i', str(ansible_inventory),
            str(ansible_playbook),
            '--ask-become-pass'
        ]
        
        print(f"{Colors.CYAN}Running: {' '.join(cmd)}{Colors.NC}")
        print()
        
        success, _ = run_cmd(cmd, check=False)
        
        if success:
            print()
            print(f"{Colors.GREEN}✓ Cluster setup completed successfully{Colors.NC}")
            self.show_status()
            return True
        else:
            print(f"{Colors.RED}✗ Cluster setup failed{Colors.NC}")
            return False
    
    def start_pooler(self, pooler):
        """Start a specific pooler"""
        print(f"{Colors.BLUE}Starting {pooler}...{Colors.NC}")
        
        if pooler == 'pgbalancer':
            # Find config file
            config = self.project_root / "pgbalancer.yaml"
            if not config.exists():
                config = self.script_dir / "conf" / "pgbalancer.yaml"
            
            pgbalancer_bin = self.project_root / "pgbalancer" / "src" / "pgbalancer"
            if not pgbalancer_bin.exists():
                print(f"{Colors.RED}✗ pgbalancer not built{Colors.NC}")
                return False
            
            # Start pgbalancer
            log_file = self.script_dir / "log" / "pgbalancer.log"
            cmd = f"cd {self.project_root} && ./pgbalancer/src/pgbalancer -n -f {config} > {log_file} 2>&1 &"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(2)
            
        elif pooler == 'pgbouncer':
            config = "/etc/pgbouncer/pgbouncer.ini"
            if not os.path.exists(config):
                config = str(self.script_dir / "conf" / "pgbouncer.ini")
            
            log_file = self.script_dir / "log" / "pgbouncer.log"
            cmd = f"pgbouncer -d {config} > {log_file} 2>&1"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(1)
            
        elif pooler == 'pgpool2':
            config = "/etc/pgpool-II/pgpool.conf"
            if not os.path.exists(config):
                config = str(self.script_dir / "conf" / "pgpool2.conf")
            
            log_file = self.script_dir / "log" / "pgpool2.log"
            cmd = f"pgpool -n -f {config} -D > {log_file} 2>&1 &"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(2)
            
        elif pooler == 'pgcat':
            pgcat_bin = "/tmp/pgcat/target/release/pgcat"
            config = "/tmp/pgcat/pgcat.toml"
            
            if not os.path.exists(pgcat_bin):
                print(f"{Colors.RED}✗ pgcat not built{Colors.NC}")
                return False
            
            log_file = self.script_dir / "log" / "pgcat.log"
            cmd = f"{pgcat_bin} {config} > {log_file} 2>&1 &"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(2)
            
        elif pooler == 'haproxy':
            config = "/etc/haproxy/haproxy.cfg"
            
            if not os.path.exists(config):
                print(f"{Colors.RED}✗ HAProxy config not found{Colors.NC}")
                return False
            
            log_file = self.script_dir / "log" / "haproxy.log"
            cmd = f"sudo haproxy -f {config} -D > {log_file} 2>&1"
            success, _ = run_cmd(cmd, shell=True, check=False)
            if not success:
                cmd = f"haproxy -f {config} -D > {log_file} 2>&1"
                run_cmd(cmd, shell=True, check=False)
            time.sleep(2)
        else:
            print(f"{Colors.RED}✗ Unknown pooler: {pooler}{Colors.NC}")
            return False
        
        # Verify started
        success, _ = run_cmd(['pgrep', '-x', pooler], check=False, capture=True)
        if success:
            print(f"{Colors.GREEN}✓ {pooler} started on port {self.ports.get(pooler, '?')}{Colors.NC}")
            return True
        else:
            print(f"{Colors.RED}✗ Failed to start {pooler}{Colors.NC}")
            return False
    
    def stop_pooler(self, pooler):
        """Stop a specific pooler"""
        print(f"{Colors.BLUE}Stopping {pooler}...{Colors.NC}")
        
        if pooler == 'haproxy':
            run_cmd(['sudo', 'pkill', '-9', pooler], check=False)
        
        run_cmd(['pkill', '-9', pooler], check=False)
        print(f"{Colors.GREEN}✓ {pooler} stopped{Colors.NC}")
        return True
    
    def start_all(self):
        """Start all poolers"""
        print_banner("Starting All Poolers")
        for pooler in self.poolers:
            self.start_pooler(pooler)
            print()
    
    def stop_all(self):
        """Stop all poolers"""
        print_banner("Stopping All Poolers")
        for pooler in self.poolers:
            self.stop_pooler(pooler)
    
    def show_status(self):
        """Show status of all poolers"""
        print_banner("PostgreSQL Pooler Cluster Status")
        
        # Check PostgreSQL
        print(f"{Colors.YELLOW}PostgreSQL (5432):{Colors.NC} ", end='')
        success, _ = run_cmd(['pg_isready', '-h', 'localhost', '-p', '5432'], check=False, capture=True)
        if success:
            print(f"{Colors.GREEN}✓ RUNNING{Colors.NC}")
        else:
            print(f"{Colors.RED}✗ NOT RUNNING{Colors.NC}")
        
        # Check each pooler
        for pooler in self.poolers:
            port = self.ports.get(pooler, '?')
            print(f"{Colors.YELLOW}{pooler} ({port}):{Colors.NC} ", end='')
            
            success, output = run_cmd(['pgrep', '-x', pooler], check=False, capture=True)
            if success:
                pid = output.strip().split('\n')[0]
                print(f"{Colors.GREEN}✓ RUNNING (PID: {pid}){Colors.NC}")
            else:
                print(f"{Colors.RED}✗ NOT RUNNING{Colors.NC}")
        
        # Show listening ports
        print()
        print(f"{Colors.BLUE}Listening Ports:{Colors.NC}")
        success, output = run_cmd(['ss', '-tlnp'], check=False, capture=True)
        if success:
            for line in output.split('\n'):
                if any(str(p) in line for p in self.ports.values()):
                    port = line.split()[3] if len(line.split()) > 3 else ''
                    if port:
                        print(f"  {port}")
    
    def test_connections(self):
        """Test connections to all poolers"""
        print_banner("Testing Pooler Connections")
        
        for pooler in self.poolers:
            port = self.ports.get(pooler, 0)
            print(f"{Colors.YELLOW}Testing {pooler} (port {port})...{Colors.NC} ", end='')
            
            cmd = [
                'psql',
                '-h', 'localhost',
                '-p', str(port),
                '-U', 'postgres',
                '-d', 'postgres',
                '-c', 'SELECT 1;'
            ]
            
            success, _ = run_cmd(cmd, check=False, capture=True)
            if success:
                print(f"{Colors.GREEN}✓ SUCCESS{Colors.NC}")
            else:
                print(f"{Colors.RED}✗ FAILED{Colors.NC}")
    
    def show_config(self, pooler):
        """Show configuration for a pooler"""
        print_banner(f"{pooler.upper()} Configuration")
        
        if pooler == 'pgbalancer':
            pgbalancer_bin = self.project_root / "pgbalancer" / "src" / "pgbalancer"
            config = self.project_root / "pgbalancer.yaml"
            if not config.exists():
                config = self.script_dir / "conf" / "pgbalancer.yaml"
            
            cmd = [str(pgbalancer_bin), '--show-config', '-f', str(config)]
            run_cmd(cmd, check=False)
            
        elif pooler == 'pgbouncer':
            config = "/etc/pgbouncer/pgbouncer.ini"
            if os.path.exists(config):
                with open(config, 'r') as f:
                    print(f.read())
            else:
                print(f"{Colors.RED}Config not found{Colors.NC}")
                
        elif pooler == 'pgpool2':
            config = "/etc/pgpool-II/pgpool.conf"
            if os.path.exists(config):
                with open(config, 'r') as f:
                    print(f.read())
            else:
                print(f"{Colors.RED}Config not found{Colors.NC}")
                
        elif pooler == 'pgcat':
            config = "/tmp/pgcat/pgcat.toml"
            if os.path.exists(config):
                with open(config, 'r') as f:
                    print(f.read())
            else:
                print(f"{Colors.RED}Config not found{Colors.NC}")
                
        elif pooler == 'haproxy':
            config = "/etc/haproxy/haproxy.cfg"
            if os.path.exists(config):
                with open(config, 'r') as f:
                    print(f.read())
            else:
                print(f"{Colors.RED}Config not found{Colors.NC}")
    
    def show_logs(self, pooler, lines=50):
        """Show logs for a pooler"""
        print_banner(f"{pooler.upper()} Logs (last {lines} lines)")
        
        log_file = self.script_dir / "log" / f"{pooler}.log"
        
        if log_file.exists():
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    print(line.rstrip())
        else:
            print(f"{Colors.RED}Log file not found: {log_file}{Colors.NC}")

def main():
    parser = argparse.ArgumentParser(
        description='PostgreSQL Pooler Cluster Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Setup entire cluster with Ansible
  ./cluster.py --setup

  # Start all poolers
  ./cluster.py --start all

  # Start specific pooler
  ./cluster.py --start pgbalancer

  # Stop all poolers
  ./cluster.py --stop all

  # Check status
  ./cluster.py --status

  # Test connections
  ./cluster.py --test

  # View configuration
  ./cluster.py --config pgbalancer

  # View logs
  ./cluster.py --logs pgbalancer --lines 100

Poolers:
  pgbalancer (9999) - YAML-configured pooler with load balancing
  pgbouncer (9997)  - Lightweight connection pooler
  pgpool2 (9998)    - Full-featured pooler with query caching
  pgcat (9996)      - Modern Rust-based pooler
  haproxy (9995)    - TCP load balancer
        '''
    )
    
    # Commands
    parser.add_argument('--setup', action='store_true', 
                       help='Setup cluster using Ansible (installs all poolers)')
    parser.add_argument('--start', metavar='POOLER',
                       help='Start pooler (use "all" for all poolers)')
    parser.add_argument('--stop', metavar='POOLER',
                       help='Stop pooler (use "all" for all poolers)')
    parser.add_argument('--restart', metavar='POOLER',
                       help='Restart pooler (use "all" for all poolers)')
    parser.add_argument('--status', action='store_true',
                       help='Show status of all poolers')
    parser.add_argument('--test', action='store_true',
                       help='Test connections to all poolers')
    parser.add_argument('--config', metavar='POOLER',
                       help='Show configuration for pooler')
    parser.add_argument('--logs', metavar='POOLER',
                       help='Show logs for pooler')
    parser.add_argument('--lines', type=int, default=50,
                       help='Number of log lines to show (default: 50)')
    
    args = parser.parse_args()
    
    cluster = ClusterManager()
    
    # Execute command
    if args.setup:
        cluster.setup_cluster()
        
    elif args.start:
        if args.start == 'all':
            cluster.start_all()
        else:
            cluster.start_pooler(args.start)
            
    elif args.stop:
        if args.stop == 'all':
            cluster.stop_all()
        else:
            cluster.stop_pooler(args.stop)
            
    elif args.restart:
        if args.restart == 'all':
            cluster.stop_all()
            time.sleep(2)
            cluster.start_all()
        else:
            cluster.stop_pooler(args.restart)
            time.sleep(2)
            cluster.start_pooler(args.restart)
            
    elif args.status:
        cluster.show_status()
        
    elif args.test:
        cluster.test_connections()
        
    elif args.config:
        cluster.show_config(args.config)
        
    elif args.logs:
        cluster.show_logs(args.logs, args.lines)
        
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()

