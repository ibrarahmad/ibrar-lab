#!/usr/bin/env python3
"""
PostgreSQL Cluster Manager
==========================

Standard PostgreSQL cluster management with Ansible for primary/replica setup
and pooler management (pgbalancer, pgbouncer, pgpool2).

Author: pgElephant, Inc.
License: MIT
"""

import argparse
import subprocess
import sys
import os
import time
import json
import platform
from pathlib import Path
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip3 install -r requirements.txt")
    sys.exit(1)

# OS Detection
class OSDetector:
    """Detect and handle OS-specific operations"""
    
    @staticmethod
    def detect():
        """Detect operating system"""
        system = platform.system().lower()
        if system == 'darwin':
            return 'macos'
        elif system == 'linux':
            # Detect Linux distribution
            try:
                with open('/etc/os-release', 'r') as f:
                    content = f.read().lower()
                    if 'rocky' in content or 'rhel' in content or 'centos' in content:
                        return 'rocky'
                    elif 'ubuntu' in content or 'debian' in content:
                        return 'ubuntu'
                    elif 'fedora' in content:
                        return 'fedora'
                    else:
                        return 'linux'
            except:
                return 'linux'
        else:
            return system
    
    @staticmethod
    def get_package_manager(os_type):
        """Get package manager for OS"""
        pkg_managers = {
            'macos': 'brew',
            'rocky': 'dnf',
            'ubuntu': 'apt',
            'fedora': 'dnf',
            'linux': 'apt'
        }
        return pkg_managers.get(os_type, 'apt')
    
    @staticmethod
    def get_pg_paths(os_type, version='17'):
        """Get PostgreSQL paths for OS"""
        if os_type == 'macos':
            return {
                'bin': f'/opt/homebrew/opt/postgresql@{version}/bin',
                'data': f'/opt/homebrew/var/postgresql@{version}',
                'config': f'/opt/homebrew/var/postgresql@{version}/postgresql.conf',
                'service': f'postgresql@{version}'
            }
        elif os_type in ['rocky', 'fedora']:
            return {
                'bin': f'/usr/pgsql-{version}/bin',
                'data': f'/var/lib/pgsql/{version}/data',
                'config': f'/var/lib/pgsql/{version}/data/postgresql.conf',
                'service': f'postgresql-{version}'
            }
        else:  # ubuntu/debian
            return {
                'bin': f'/usr/lib/postgresql/{version}/bin',
                'data': f'/var/lib/postgresql/{version}/main',
                'config': f'/etc/postgresql/{version}/main/postgresql.conf',
                'service': 'postgresql'
            }
    
    @staticmethod
    def get_install_cmd(os_type):
        """Get install command for OS"""
        if os_type == 'macos':
            return ['brew', 'install']
        elif os_type in ['rocky', 'fedora']:
            return ['sudo', 'dnf', 'install', '-y']
        else:
            return ['sudo', 'apt-get', 'install', '-y']

# Colors
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'

def print_banner(title):
    """Print formatted banner"""
    print(f"{Colors.CYAN}╔{'═'*78}╗")
    print(f"║ {title:76} ║")
    print(f"╚{'═'*78}╝{Colors.NC}\n")

def print_section(title):
    """Print section header"""
    print(f"\n{Colors.YELLOW}▶ {title}{Colors.NC}")
    print("─" * 80)

def run_cmd(cmd, check=True, capture=False, shell=False):
    """Run shell command"""
    try:
        if capture:
            result = subprocess.run(cmd, shell=shell, check=check, 
                                  capture_output=True, text=True)
            return result.returncode == 0, result.stdout.strip()
        else:
            result = subprocess.run(cmd, shell=shell, check=check)
            return result.returncode == 0, ""
    except subprocess.CalledProcessError as e:
        return False, str(e)

class ClusterManager:
    """PostgreSQL cluster and pooler manager"""
    
    def __init__(self, config_file=None):
        # Detect OS
        self.os_type = OSDetector.detect()
        self.pkg_manager = OSDetector.get_package_manager(self.os_type)
        
        # Print OS info
        print(f"{Colors.BLUE}Detected OS: {self.os_type} (Package Manager: {self.pkg_manager}){Colors.NC}")
        
        self.script_dir = Path(__file__).parent.absolute()
        self.conf_dir = self.script_dir.parent / "conf"
        self.project_root = self.script_dir.parent.parent.parent
        
        # Load configuration from file
        if config_file:
            config_path = Path(config_file)
        else:
            config_path = self.conf_dir / "cluster-config.yaml"
        
        self.config = self._load_config(config_path)
        
        # Ansible playbooks
        self.cluster_playbook = self.conf_dir / "postgresql-cluster-setup.yml"
        self.cluster_inventory = self.conf_dir / "cluster-inventory.ini"
        self.pooler_playbook = self.conf_dir / "ansible-setup.yml"
        self.pooler_inventory = self.conf_dir / "ansible-inventory.ini"
        
        # Get pooler ports from config
        self.poolers = self.config.get('poolers', {
            'pgbalancer': 9999,
            'pgbouncer': 9997,
            'pgpool2': 9998,
        })
    
    def _load_config(self, config_path):
        """Load configuration from YAML file"""
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    print(f"{Colors.GREEN}✓ Loaded config: {config_path}{Colors.NC}")
                    return config
            else:
                print(f"{Colors.YELLOW}⚠ Config not found: {config_path}, using defaults{Colors.NC}")
                return {}
        except Exception as e:
            print(f"{Colors.YELLOW}⚠ Failed to load config: {e}, using defaults{Colors.NC}")
            return {}
    
    def _run_ansible(self, playbook, inventory, extra_vars=None, tags=None, ask_pass=False):
        """Run Ansible playbook"""
        cmd = ['ansible-playbook', '-i', str(inventory), str(playbook)]
        
        if extra_vars:
            for key, value in extra_vars.items():
                cmd.extend(['-e', f"{key}={value}"])
        
        if tags:
            cmd.extend(['--tags', tags])
            
        if ask_pass:
            cmd.append('--ask-become-pass')
        
        print(f"{Colors.BLUE}Running: {' '.join(cmd)}{Colors.NC}\n")
        success, _ = run_cmd(cmd, check=False)
        return success
    
    ##########################################################################
    # INSTALLATION
    ##########################################################################
    
    def install_dependencies(self):
        """Install PostgreSQL and pooler dependencies"""
        print_banner(f"Installing Dependencies (OS: {self.os_type})")
        
        install_cmd = OSDetector.get_install_cmd(self.os_type)
        
        print_section("Installing PostgreSQL")
        pg_version = self.config.get('cluster', {}).get('version', '17')
        
        if self.os_type == 'macos':
            packages = [f'postgresql@{pg_version}', 'libyaml', 'openssl@3']
            run_cmd(install_cmd + packages, check=False)
            
        elif self.os_type in ['rocky', 'fedora']:
            # Install PostgreSQL repo
            run_cmd([
                'sudo', 'dnf', 'install', '-y',
                'https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm'
            ], check=False)
            
            packages = [
                f'postgresql{pg_version}',
                f'postgresql{pg_version}-server',
                f'postgresql{pg_version}-contrib',
                f'postgresql{pg_version}-devel',
                'libyaml-devel',
                'openssl-devel'
            ]
            run_cmd(install_cmd + packages, check=False)
            
        else:  # ubuntu/debian
            # Add PostgreSQL repo
            run_cmd(['sudo', 'apt-get', 'update'], check=False)
            packages = [
                f'postgresql-{pg_version}',
                f'postgresql-contrib-{pg_version}',
                f'postgresql-server-dev-{pg_version}',
                'libyaml-dev',
                'libssl-dev'
            ]
            run_cmd(install_cmd + packages, check=False)
        
        print(f"{Colors.GREEN}✓ PostgreSQL {pg_version} installed{Colors.NC}")
        
        print_section("Installing Poolers")
        if self.os_type == 'macos':
            run_cmd(['brew', 'install', 'pgbouncer'], check=False)
        elif self.os_type in ['rocky', 'fedora']:
            run_cmd(['sudo', 'dnf', 'install', '-y', 'pgbouncer', 'pgpool-II'], check=False)
        else:
            run_cmd(['sudo', 'apt-get', 'install', '-y', 'pgbouncer', 'pgpool2'], check=False)
        
        print(f"{Colors.GREEN}✓ Poolers installed{Colors.NC}")
        
        print_section("Installing Python packages")
        requirements_file = self.script_dir.parent / "requirements.txt"
        
        if self.os_type == 'macos':
            run_cmd(['pip3', 'install', '--break-system-packages', '-r', str(requirements_file)], check=False)
        else:
            run_cmd(['pip3', 'install', '-r', str(requirements_file)], check=False)
        
        print(f"{Colors.GREEN}✓ All dependencies installed{Colors.NC}")
    
    ##########################################################################
    # POSTGRESQL CLUSTER
    ##########################################################################
    
    def setup_postgres(self, version=None, ask_pass=True):
        """Setup PostgreSQL cluster (primary + replicas)"""
        # Get version from config if not provided
        if not version:
            version = str(self.config.get('cluster', {}).get('version', '17'))
        
        print_banner(f"PostgreSQL Cluster Setup (OS: {self.os_type}, Version: {version})")
        
        if not self.cluster_playbook.exists():
            print(f"{Colors.RED}✗ Playbook not found: {self.cluster_playbook}{Colors.NC}")
            return False
        
        # Check Ansible
        success, _ = run_cmd(['which', 'ansible-playbook'], check=False, capture=True)
        if not success:
            print(f"{Colors.YELLOW}Installing Ansible...{Colors.NC}")
            install_cmd = OSDetector.get_install_cmd(self.os_type)
            if self.os_type == 'macos':
                run_cmd(['pip3', 'install', 'ansible'], check=False)
            else:
                run_cmd(install_cmd + ['ansible'], check=False)
        
        # Get OS-specific PostgreSQL paths
        pg_paths = OSDetector.get_pg_paths(self.os_type, version)
        
        extra_vars = {
            'pg_version': version,
            'ansible_os_type': self.os_type
        }
        
        success = self._run_ansible(
            self.cluster_playbook,
            self.cluster_inventory,
            extra_vars=extra_vars,
            ask_pass=ask_pass
        )
        
        if success:
            print(f"\n{Colors.GREEN}✓ PostgreSQL cluster setup completed{Colors.NC}")
            print(f"{Colors.BLUE}PostgreSQL paths for {self.os_type}:")
            print(f"  Bin:     {pg_paths['bin']}")
            print(f"  Data:    {pg_paths['data']}")
            print(f"  Service: {pg_paths['service']}{Colors.NC}")
            time.sleep(2)
            self.show_postgres_status()
            return True
        else:
            print(f"{Colors.RED}✗ Setup failed{Colors.NC}")
            return False
    
    def show_postgres_status(self):
        """Show PostgreSQL cluster status"""
        print_banner("PostgreSQL Cluster Status")
        
        # Get settings from config file
        primary = self.config.get('nodes', {}).get('primary', {})
        replicas = self.config.get('nodes', {}).get('replicas', [])
        
        primary_port = str(primary.get('port', os.environ.get('PGPORT', '5432')))
        pg_host = primary.get('host', os.environ.get('PGHOST', 'localhost'))
        pg_user = os.environ.get('PGUSER', 'postgres')
        
        replica_ports = [str(r.get('port', '5433')) for r in replicas] if replicas else ['5433', '5434']
        
        # Check primary
        print_section(f"Primary Server (port {primary_port})")
        success, _ = run_cmd(['pg_isready', '-h', pg_host, '-p', primary_port], 
                            check=False, capture=True)
        status = f"{Colors.GREEN}✓ RUNNING{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
        print(f"Status: {status}\n")
        
        if success:
            cmd = ['psql', '-h', pg_host, '-p', primary_port, '-U', pg_user, '-c',
                   'SELECT application_name, client_addr, state, sync_state FROM pg_stat_replication;']
            run_cmd(cmd, check=False)
        
        # Check replicas
        print_section("Replica Servers")
        for port in replica_ports:
            port = port.strip()
            success, _ = run_cmd(['pg_isready', '-h', pg_host, '-p', port], 
                                check=False, capture=True)
            status = f"{Colors.GREEN}✓ RUNNING{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
            print(f"Port {port}: {status}")
    
    def show_replication_lag(self):
        """Show replication lag"""
        print_banner("Replication Lag")
        
        # Get settings from config file
        replicas = self.config.get('nodes', {}).get('replicas', [])
        primary = self.config.get('nodes', {}).get('primary', {})
        
        replica_ports = [str(r.get('port', '5433')) for r in replicas] if replicas else ['5433', '5434']
        pg_host = primary.get('host', os.environ.get('PGHOST', 'localhost'))
        pg_user = os.environ.get('PGUSER', 'postgres')
        
        for port in replica_ports:
            port = port.strip()
            print(f"\n{Colors.YELLOW}Replica on port {port}:{Colors.NC}")
            cmd = [
                'psql', '-h', pg_host, '-p', port, '-U', pg_user, '-c',
                '''SELECT 
                    pg_is_in_recovery() AS is_replica,
                    pg_last_wal_receive_lsn() AS receive_lsn,
                    pg_last_wal_replay_lsn() AS replay_lsn,
                    EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;'''
            ]
            run_cmd(cmd, check=False)
    
    ##########################################################################
    # POOLER MANAGEMENT
    ##########################################################################
    
    def setup_poolers(self, ask_pass=True):
        """Setup poolers using Ansible"""
        print_banner("Pooler Setup")
        
        if not self.pooler_playbook.exists():
            print(f"{Colors.RED}✗ Playbook not found: {self.pooler_playbook}{Colors.NC}")
            return False
        
        success = self._run_ansible(
            self.pooler_playbook,
            self.pooler_inventory,
            tags='poolers',
            ask_pass=ask_pass
        )
        
        if success:
            print(f"\n{Colors.GREEN}✓ Pooler setup completed{Colors.NC}")
            self.show_pooler_status()
            return True
        else:
            print(f"{Colors.RED}✗ Setup failed{Colors.NC}")
            return False
    
    def start_pooler(self, pooler):
        """Start specific pooler"""
        print(f"{Colors.BLUE}Starting {pooler}...{Colors.NC}")
        
        if pooler == 'pgbalancer':
            config = self.project_root / "pgbalancer.yaml"
            if not config.exists():
                config = self.conf_dir / "pgbalancer.yaml"
            
            pgbalancer_bin = self.project_root / "pgbalancer" / "src" / "pgbalancer"
            if not pgbalancer_bin.exists():
                print(f"{Colors.RED}✗ pgbalancer not built{Colors.NC}")
                return False
            
            log_dir = self.script_dir.parent / "log"
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "pgbalancer.log"
            
            cmd = f"{pgbalancer_bin} -n -f {config} > {log_file} 2>&1 &"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(2)
            
        elif pooler == 'pgbouncer':
            cmd = "pgbouncer -d /etc/pgbouncer/pgbouncer.ini"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(1)
            
        elif pooler == 'pgpool2':
            cmd = "pgpool -n -D"
            run_cmd(cmd, shell=True, check=False)
            time.sleep(2)
        
        # Verify
        success, _ = run_cmd(['pgrep', '-x', pooler], check=False, capture=True)
        if success:
            print(f"{Colors.GREEN}✓ {pooler} started on port {self.poolers.get(pooler, '?')}{Colors.NC}")
            return True
        else:
            print(f"{Colors.RED}✗ Failed to start {pooler}{Colors.NC}")
            return False
    
    def stop_pooler(self, pooler):
        """Stop specific pooler"""
        print(f"{Colors.BLUE}Stopping {pooler}...{Colors.NC}")
        run_cmd(['pkill', '-9', pooler], check=False)
        print(f"{Colors.GREEN}✓ {pooler} stopped{Colors.NC}")
        return True
    
    def start_all_poolers(self):
        """Start all poolers"""
        print_banner("Starting All Poolers")
        for pooler in self.poolers.keys():
            self.start_pooler(pooler)
            print()
    
    def stop_all_poolers(self):
        """Stop all poolers"""
        print_banner("Stopping All Poolers")
        for pooler in self.poolers.keys():
            self.stop_pooler(pooler)
    
    def show_pooler_status(self):
        """Show pooler status"""
        print_banner("Pooler Status")
        
        for pooler, port in self.poolers.items():
            print(f"{Colors.YELLOW}{pooler:15} (port {port}):{Colors.NC} ", end='')
            
            success, output = run_cmd(['pgrep', '-x', pooler], check=False, capture=True)
            if success:
                pid = output.split('\n')[0] if output else '?'
                print(f"{Colors.GREEN}✓ RUNNING (PID: {pid}){Colors.NC}")
            else:
                print(f"{Colors.RED}✗ NOT RUNNING{Colors.NC}")
        
    def test_poolers(self):
        """Test pooler connections"""
        print_banner("Testing Pooler Connections")
        
        for pooler, port in self.poolers.items():
            print(f"{Colors.YELLOW}Testing {pooler:15} (port {port})...{Colors.NC} ", end='')
            
            cmd = ['psql', '-h', 'localhost', '-p', str(port), '-U', 'postgres', 
                   '-d', 'postgres', '-c', 'SELECT 1;']
            
            success, _ = run_cmd(cmd, check=False, capture=True)
            print(f"{Colors.GREEN}✓ SUCCESS{Colors.NC}" if success else f"{Colors.RED}✗ FAILED{Colors.NC}")
    
    ##########################################################################
    # HEALTH & DIAGNOSTICS
    ##########################################################################
    
    def health_check(self):
        """Comprehensive health check"""
        print_banner("Cluster Health Check")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'postgres': {},
            'poolers': {}
        }
        
        # Get settings from config file
        primary = self.config.get('nodes', {}).get('primary', {})
        replicas = self.config.get('nodes', {}).get('replicas', [])
        
        primary_port = str(primary.get('port', os.environ.get('PGPORT', '5432')))
        pg_host = primary.get('host', os.environ.get('PGHOST', 'localhost'))
        
        replica_ports = [str(r.get('port', '5433')) for r in replicas] if replicas else ['5433', '5434']
        all_ports = [primary_port] + replica_ports
        
        # Check PostgreSQL
        print_section("PostgreSQL Health")
        for port in all_ports:
            success, _ = run_cmd(['pg_isready', '-h', pg_host, '-p', str(port)], 
                                check=False, capture=True)
            status = f"{Colors.GREEN}✓ READY{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
            print(f"Port {port}: {status}")
            results['postgres'][f'port_{port}'] = success
        
        # Check poolers
        print_section("Pooler Health")
        for pooler in self.poolers.keys():
            success, _ = run_cmd(['pgrep', '-x', pooler], check=False, capture=True)
            status = f"{Colors.GREEN}✓ RUNNING{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
            print(f"{pooler:15}: {status}")
            results['poolers'][pooler] = success
        
        # Save results
        log_dir = self.script_dir.parent / "log"
        log_dir.mkdir(exist_ok=True)
        results_file = log_dir / f"health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n{Colors.BLUE}Results saved: {results_file}{Colors.NC}")
        return results
    
    def show_logs(self, component, lines=50):
        """Show logs (OS-aware, no hard-coded paths)"""
        print_banner(f"{component.upper()} Logs (last {lines} lines)")
        
        # Get PostgreSQL version and paths
        pg_version = os.environ.get('PG_VERSION', '17')
        pg_paths = OSDetector.get_pg_paths(self.os_type, pg_version)
        
        # Build log paths dynamically
        log_map = {}
        
        if component == 'postgres':
            # Use OS-specific data directory
            if self.os_type == 'macos':
                log_map['postgres'] = f"{pg_paths['data']}/log/postgresql-*.log"
            else:
                log_map['postgres'] = f"{pg_paths['data']}/log/postgresql-*.log"
        elif component == 'pgbalancer':
            log_map['pgbalancer'] = self.script_dir.parent / "log" / "pgbalancer.log"
        elif component == 'pgbouncer':
            # Try multiple locations
            for path in ["/var/log/pgbouncer/pgbouncer.log", 
                        f"{Path.home()}/pgbouncer.log",
                        "./pgbouncer.log"]:
                if Path(path).exists():
                    log_map['pgbouncer'] = path
                    break
        elif component == 'pgpool2':
            # Try multiple locations
            for path in ["/var/log/pgpool-II/pgpool.log",
                        f"{Path.home()}/pgpool.log",
                        "./pgpool.log"]:
                if Path(path).exists():
                    log_map['pgpool2'] = path
                    break
        
        log_file = log_map.get(component)
        if log_file:
            if Path(str(log_file)).exists() or '*' in str(log_file):
                cmd = f"tail -n {lines} {log_file} 2>/dev/null || echo 'No logs found'"
                run_cmd(cmd, shell=True, check=False)
            else:
                print(f"{Colors.YELLOW}Log file not found: {log_file}{Colors.NC}")
        else:
            print(f"{Colors.RED}Unknown component: {component}{Colors.NC}")

def main():
    parser = argparse.ArgumentParser(
        description='PostgreSQL Cluster Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Step 1: Install dependencies
  ./cluster.py --install

  # Step 2: Setup PostgreSQL cluster (1 primary + 2 sync replicas)
  ./cluster.py --setup-postgres

  # Step 3: Check cluster status
  ./cluster.py --status
  ./cluster.py --replication-lag

  # Step 4: Setup poolers
  ./cluster.py --setup-poolers
  ./cluster.py --start all

  # Health monitoring
  ./cluster.py --health-check
  ./cluster.py --test-poolers
  ./cluster.py --logs postgres
        '''
    )
    
    # Installation
    install_group = parser.add_argument_group('Installation')
    install_group.add_argument('--install', action='store_true',
                              help='Install PostgreSQL and pooler dependencies')
    
    # PostgreSQL
    pg = parser.add_argument_group('PostgreSQL Cluster')
    pg.add_argument('--setup-postgres', action='store_true',
                   help='Setup PostgreSQL cluster (primary + replicas)')
    pg.add_argument('--version', default=None,
                   help='PostgreSQL version (default: from config)')
    pg.add_argument('--status', action='store_true',
                   help='Show cluster status')
    pg.add_argument('--replication-lag', action='store_true',
                   help='Show replication lag')
    
    # Poolers
    pooler = parser.add_argument_group('Pooler Management')
    pooler.add_argument('--setup-poolers', action='store_true',
                       help='Setup poolers')
    pooler.add_argument('--start', metavar='POOLER',
                       help='Start pooler (use "all" for all)')
    pooler.add_argument('--stop', metavar='POOLER',
                       help='Stop pooler (use "all" for all)')
    pooler.add_argument('--pooler-status', action='store_true',
                       help='Show pooler status')
    pooler.add_argument('--test-poolers', action='store_true',
                       help='Test pooler connections')
    
    # Health
    health = parser.add_argument_group('Health & Diagnostics')
    health.add_argument('--health-check', action='store_true',
                       help='Comprehensive health check')
    health.add_argument('--logs', metavar='COMPONENT',
                       help='Show logs (postgres, pgbalancer, pgbouncer, pgpool2)')
    health.add_argument('--lines', type=int, default=50,
                       help='Number of log lines (default: 50)')
    
    # Options
    parser.add_argument('--no-password', action='store_true',
                       help='Do not ask for sudo password')
    parser.add_argument('--config', metavar='FILE',
                       help='Configuration file (default: conf/cluster-config.yaml)')
    
    args = parser.parse_args()
    
    cluster = ClusterManager(config_file=args.config)
    ask_pass = not args.no_password
    
    # Execute
    if args.install:
        cluster.install_dependencies()
        
    elif args.setup_postgres:
        cluster.setup_postgres(version=args.version, ask_pass=ask_pass)
        
    elif args.status:
        cluster.show_postgres_status()
        
    elif args.replication_lag:
        cluster.show_replication_lag()
        
    elif args.setup_poolers:
        cluster.setup_poolers(ask_pass=ask_pass)
        
    elif args.start:
        if args.start == 'all':
            cluster.start_all_poolers()
        else:
            cluster.start_pooler(args.start)
            
    elif args.stop:
        if args.stop == 'all':
            cluster.stop_all_poolers()
        else:
            cluster.stop_pooler(args.stop)
            
    elif args.pooler_status:
        cluster.show_pooler_status()
        
    elif args.test_poolers:
        cluster.test_poolers()
        
    elif args.health_check:
        cluster.health_check()
        
    elif args.logs:
        cluster.show_logs(args.logs, args.lines)
        
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
