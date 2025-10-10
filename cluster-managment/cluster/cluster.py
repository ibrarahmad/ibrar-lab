#!/usr/bin/env python3
"""
PostgreSQL Cluster Manager
==========================

Manages PostgreSQL clusters and connection poolers with full configuration
driven from YAML files. No hardcoded values.

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
import getpass
from pathlib import Path
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip3 install -r requirements.txt")
    sys.exit(1)

#==============================================================================
# OS Detection
#==============================================================================

class OSDetector:
    """Detect and handle OS-specific operations"""
    
    @staticmethod
    def detect():
        """Detect operating system"""
        system = platform.system().lower()
        if system == 'darwin':
            return 'macos'
        elif system == 'linux':
            try:
                with open('/etc/os-release', 'r') as f:
                    content = f.read().lower()
                    if 'rocky' in content or 'rhel' in content or 'centos' in content:
                        return 'rocky'
                    elif 'ubuntu' in content or 'debian' in content:
                        return 'ubuntu'
                    elif 'fedora' in content:
                        return 'fedora'
            except:
                pass
            return 'linux'
        return system
    
    @staticmethod
    def get_package_manager(os_type):
        """Get package manager for OS"""
        return {
            'macos': 'brew',
            'rocky': 'dnf',
            'ubuntu': 'apt',
            'fedora': 'dnf',
            'linux': 'apt'
        }.get(os_type, 'apt')
    
    @staticmethod
    def get_default_user(os_type):
        """Get default PostgreSQL user for OS"""
        return getpass.getuser() if os_type == 'macos' else 'postgres'

#==============================================================================
# Colors & Formatting
#==============================================================================

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

#==============================================================================
# Command Execution
#==============================================================================

def run_cmd(cmd, check=True, capture=False, shell=False):
    """Run shell command with optional verbose output"""
    verbose = os.environ.get('CLUSTER_VERBOSE', '0') == '1'
    
    if verbose and not capture:
        cmd_str = cmd if isinstance(cmd, str) else ' '.join(str(c) for c in cmd)
        print(f"{Colors.CYAN}Running: {cmd_str}{Colors.NC}")
    
    try:
        if capture:
            result = subprocess.run(cmd, shell=shell, check=check, 
                                  stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True)
            if verbose and result.stdout:
                print(result.stdout)
            if verbose and result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode == 0, result.stdout.strip()
        else:
            if verbose:
                result = subprocess.run(cmd, shell=shell, check=check,
                                      stdin=subprocess.DEVNULL)
            else:
                result = subprocess.run(cmd, shell=shell, check=check,
                                      stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True)
            return result.returncode == 0, ""
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"{Colors.RED}Command failed: {e}{Colors.NC}")
        return False, str(e)

#==============================================================================
# Configuration Manager
#==============================================================================

class ConfigManager:
    """Handle configuration loading and merging"""
    
    @staticmethod
    def load(config_path):
        """Load YAML configuration"""
        try:
            if not config_path.exists():
                print(f"{Colors.YELLOW}⚠ Config not found: {config_path}{Colors.NC}")
                return {}
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                print(f"{Colors.GREEN}✓ Loaded config: {config_path}{Colors.NC}")
                return config
        except Exception as e:
            print(f"{Colors.RED}✗ Failed to load config: {e}{Colors.NC}")
            return {}
    
    @staticmethod
    def merge(base, override):
        """Merge two config dictionaries"""
        return {**(base or {}), **(override or {})}
    
    @staticmethod
    def get_nested(config, *keys, default=None):
        """Safely get nested config value"""
        result = config
        for key in keys:
            if not isinstance(result, dict):
                return default
            result = result.get(key)
            if result is None:
                return default
        return result

#==============================================================================
# PostgreSQL Configuration Writer
#==============================================================================

class PostgreSQLConfigWriter:
    """Write PostgreSQL configuration files from YAML config"""
    
    @staticmethod
    def write_postgresql_conf(data_dir, port, node_config, repl_config, conn_config, 
                             sync_standby_names=None, is_replica=False, slot_name=None):
        """Write postgresql.conf from config - ONLY values from YAML"""
        conf_path = data_dir / "postgresql.conf"
        
        with open(conf_path, "a") as f:
            f.write(f"\n# Configuration from cluster-config.yaml\n")
            f.write(f"# Generated: {datetime.now()}\n\n")
            
            # Port (always required)
            f.write(f"port = {port}\n")
            
            # Network settings
            if node_config.get('listen_addresses'):
                f.write(f"listen_addresses = '{node_config['listen_addresses']}'\n")
            
            # WAL & Replication settings
            if node_config.get('wal_level'):
                f.write(f"wal_level = {node_config['wal_level']}\n")
            if node_config.get('hot_standby'):
                f.write(f"hot_standby = {node_config['hot_standby']}\n")
            
            # Primary-specific replication settings
            if not is_replica and repl_config:
                if repl_config.get('max_wal_senders'):
                    f.write(f"max_wal_senders = {repl_config['max_wal_senders']}\n")
                if repl_config.get('max_replication_slots'):
                    f.write(f"max_replication_slots = {repl_config['max_replication_slots']}\n")
                if repl_config.get('wal_keep_size'):
                    f.write(f"wal_keep_size = '{repl_config['wal_keep_size']}'\n")
                
                # NOTE: synchronous_commit and synchronous_standby_names should be set
                # AFTER replicas are created to avoid blocking initial setup
                # We comment them out initially and enable via ALTER SYSTEM later
                if 'synchronous' in repl_config:
                    sync_val = 'on' if repl_config['synchronous'] else 'off'
                    f.write(f"#synchronous_commit = {sync_val}  # Enable after replicas are up\n")
                if sync_standby_names:
                    f.write(f"#synchronous_standby_names = '{sync_standby_names}'  # Enable after replicas are up\n")
            
            # Replica-specific settings
            if is_replica and slot_name:
                f.write(f"primary_slot_name = '{slot_name}'\n")
            
            # Connection/Performance settings
            if conn_config:
                f.write(f"\n# Performance Settings\n")
                for key, value in conn_config.items():
                    f.write(f"{key} = {value}\n")
            
            # Additional node-specific settings
            excluded = {'encoding', 'locale', 'listen_addresses', 'wal_level', 'hot_standby', 'port'}
            extras = {k: v for k, v in node_config.items() if k not in excluded}
            if extras:
                f.write(f"\n# Additional node settings\n")
                for key, value in extras.items():
                    f.write(f"{key} = {value}\n")
    
    @staticmethod
    def write_pg_hba_conf(data_dir, hba_entries, replacements=None):
        """Write pg_hba.conf from config - ONLY entries from YAML"""
        if not hba_entries:
            return
        
        hba_path = data_dir / "pg_hba.conf"
        replacements = replacements or {}
        
        with open(hba_path, "a") as f:
            f.write(f"\n# pg_hba entries from cluster-config.yaml\n")
            f.write(f"# Generated: {datetime.now()}\n")
            for entry in hba_entries:
                for key, value in replacements.items():
                    entry = entry.replace(f'{{{key}}}', value)
                f.write(f"{entry}\n")

#==============================================================================
# PostgreSQL Node Manager
#==============================================================================

class PostgreSQLNode:
    """Manage a single PostgreSQL node"""
    
    def __init__(self, pg_bin, data_dir, port, os_type, log_dir=None):
        self.pg_bin = Path(pg_bin)
        self.data_dir = Path(data_dir)
        self.port = port
        self.os_type = os_type
        self.os_user = OSDetector.get_default_user(os_type)
        self.log_dir = Path(log_dir) if log_dir else data_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def init(self, encoding, locale):
        """Initialize PostgreSQL data directory"""
        cmd = [
            str(self.pg_bin / "initdb"),
            "-D", str(self.data_dir)
        ]
        if encoding:
            cmd.append(f"--encoding={encoding}")
        if locale:
            cmd.append(f"--locale={locale}")
        
        success, _ = run_cmd(cmd, check=False)
        return success
    
    def start(self):
        """Start PostgreSQL node (logs to log_dir)"""
        log_file = self.log_dir / f"postgres_port_{self.port}.log"
        cmd = [
            str(self.pg_bin / "pg_ctl"),
            "-D", str(self.data_dir),
            "-l", str(log_file),
            "start"
        ]
        success, _ = run_cmd(cmd, check=False)
        return success
    
    def stop(self):
        """Stop PostgreSQL node"""
        cmd = [
            str(self.pg_bin / "pg_ctl"),
            "-D", str(self.data_dir),
            "stop",
            "-m", "fast"
        ]
        run_cmd(cmd, check=False)
    
    def wait_ready(self, timeout=30):
        """Wait for node to be ready to accept connections"""
        for i in range(timeout):
            cmd = ['pg_isready', '-h', 'localhost', '-p', str(self.port), '-d', 'postgres']
            success, _ = run_cmd(cmd, check=False, capture=True)
            if success:
                return True
            time.sleep(1)
        return False
    
    def psql(self, sql, database='postgres'):
        """Execute SQL on this node (use Unix socket for local connections)"""
        cmd = [
            str(self.pg_bin / "psql"),
            "-p", str(self.port),
            "-U", self.os_user,
            "-d", database,
            "-t",  # Tuples only (no headers/footers)
            "-A",  # Unaligned output
            "-c", sql
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)
    
    def is_running(self):
        """Check if node is running"""
        cmd = ['pg_isready', '-h', 'localhost', '-p', str(self.port), '-d', 'postgres']
        success, _ = run_cmd(cmd, check=False, capture=True)
        return success

#==============================================================================
# Cluster Manager
#==============================================================================

class ClusterManager:
    """PostgreSQL cluster and pooler manager"""
    
    def __init__(self, config_file=None):
        self.os_type = OSDetector.detect()
        self.pkg_manager = OSDetector.get_package_manager(self.os_type)
        
        print(f"{Colors.BLUE}Detected OS: {self.os_type} (Package Manager: {self.pkg_manager}){Colors.NC}")
        
        # Paths (cluster.py is in cluster/ directory)
        self.script_dir = Path(__file__).parent.absolute()
        self.conf_dir = self.script_dir / "conf"
        self.log_dir = self.script_dir / "log"
        self.project_root = self.script_dir.parent.parent
        self.log_dir.mkdir(exist_ok=True)
        
        # Load configuration (default: conf/cluster-config.yaml)
        if config_file:
            config_path = Path(config_file)
        else:
            config_path = self.conf_dir / "cluster-config.yaml"
        
        self.config = ConfigManager.load(config_path)
    
    ##########################################################################
    # Cleanup Operations
    ##########################################################################
    
    def cleanup_environment(self, base_dir):
        """Clean up old PostgreSQL instances and shared memory"""
        print_section("Cleaning up environment")
        
        # Stop all postgres processes
        run_cmd(['pkill', '-9', 'postgres'], check=False)
        time.sleep(2)
        
        # Remove old data directories
        if base_dir.exists():
            run_cmd(['rm', '-rf', str(base_dir)], check=False)
        
        # Clean shared memory (macOS specific)
        if self.os_type == 'macos':
            print(f"{Colors.BLUE}Cleaning shared memory segments...{Colors.NC}")
            run_cmd("ipcs -m | grep $(whoami) | awk '{print $2}' | xargs -I {} ipcrm -m {} 2>/dev/null", 
                   shell=True, check=False)
        
        base_dir.mkdir(parents=True, exist_ok=True)
        print(f"{Colors.GREEN}✓ Environment cleaned{Colors.NC}")
    
    ##########################################################################
    # Configuration Helpers
    ##########################################################################
    
    def get_pg_version(self):
        """Get PostgreSQL version from config"""
        return str(ConfigManager.get_nested(self.config, 'cluster', 'version', default='17'))
    
    def get_pg_bin(self, version):
        """Get PostgreSQL binary path from config or auto-detect"""
        configured_path = ConfigManager.get_nested(self.config, 'paths', 'pg_bin')
        if configured_path:
            return configured_path
        
        if self.os_type == 'macos':
            return f'/opt/homebrew/opt/postgresql@{version}/bin'
        elif self.os_type in ['rocky', 'fedora']:
            return f'/usr/pgsql-{version}/bin'
        else:
            return f'/usr/lib/postgresql/{version}/bin'
    
    def get_base_data_dir(self):
        """Get base data directory from config or auto-detect"""
        configured_path = ConfigManager.get_nested(self.config, 'paths', 'pg_data')
        if configured_path:
            return Path(configured_path)
        return Path.home() / "pgdata"
    
    def get_node_config(self, node_data):
        """Get merged node configuration"""
        global_pg_config = ConfigManager.get_nested(self.config, 'postgresql', default={})
        node_pg_config = node_data.get('postgresql') or {}
        return ConfigManager.merge(global_pg_config, node_pg_config)
    
    def get_hba_entries(self, node_data):
        """Get merged pg_hba entries for a node"""
        global_hba = ConfigManager.get_nested(self.config, 'pg_hba', 'entries', default=[])
        node_hba = node_data.get('pg_hba') or []
        return (global_hba or []) + node_hba
    
    ##########################################################################
    # PostgreSQL Cluster Setup
    ##########################################################################
    
    def setup_primary_node(self, pg_bin, data_dir, port, node_config):
        """Setup and start primary node"""
        print_section(f"Setting up PRIMARY node (port {port})")
        
        # Get init settings from config
        encoding = node_config.get('encoding')
        locale = node_config.get('locale')
        
        # Initialize (logs go to self.log_dir)
        node = PostgreSQLNode(pg_bin, data_dir, port, self.os_type, log_dir=self.log_dir)
        if not node.init(encoding, locale):
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: Failed to initialize PostgreSQL primary node")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"Check the system has enough resources:")
            print(f"  • Free disk space: df -h {data_dir.parent}")
            print(f"  • Shared memory: ipcs -m")
            print(f"\nTo clean up:")
            print(f"  pkill -9 postgres")
            print(f"  ipcs -m | grep $(whoami) | awk '{{print $2}}' | xargs -I {{}} ipcrm -m {{}}")
            sys.exit(1)
        
        # Get configuration sections from YAML
        repl_config = self.config.get('replication', {}) or {}
        conn_config = self.config.get('connection', {}) or {}
        replicas = ConfigManager.get_nested(self.config, 'nodes', 'replicas', default=[])
        
        # Build sync standby names from config
        replica_names = ', '.join([r.get('name', f'replica{i}') for i, r in enumerate(replicas, start=1)])
        sync_mode = repl_config.get('synchronous_mode', '')
        sync_standby_names = f"{sync_mode} ({replica_names})" if sync_mode and replicas else None
        
        # Write postgresql.conf from config
        try:
            PostgreSQLConfigWriter.write_postgresql_conf(
                data_dir, port, node_config, repl_config, conn_config,
                sync_standby_names=sync_standby_names, is_replica=False
            )
        except Exception as e:
            print(f"\n{Colors.RED}ERROR: Failed to write postgresql.conf: {e}{Colors.NC}")
            sys.exit(1)
        
        # Write pg_hba.conf from config
        hba_entries = self.get_hba_entries(ConfigManager.get_nested(self.config, 'nodes', 'primary', default={}))
        repl_user = repl_config.get('user', '')
        
        if not repl_user:
            print(f"\n{Colors.RED}ERROR: replication.user not configured in cluster-config.yaml{Colors.NC}")
            sys.exit(1)
        
        PostgreSQLConfigWriter.write_pg_hba_conf(data_dir, hba_entries, {'repl_user': repl_user})
        
        # Start node
        print(f"{Colors.BLUE}Starting primary node...{Colors.NC}")
        if not node.start():
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: Failed to start primary PostgreSQL node")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"Check the log file:")
            print(f"  tail -50 {self.log_dir}/postgres_port_{port}.log")
            sys.exit(1)
        
        # Wait for ready
        print(f"{Colors.BLUE}Waiting for primary to accept connections...{Colors.NC}")
        if not node.wait_ready(timeout=30):
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: Primary node failed to become ready within 30 seconds")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"Check the log file:")
            print(f"  tail -100 {self.log_dir}/postgres_port_{port}.log")
            print(f"\nCommon issues:")
            print(f"  • Port {port} already in use: lsof -i :{port}")
            print(f"  • Configuration error in postgresql.conf")
            print(f"  • Insufficient resources")
            sys.exit(1)
        
        time.sleep(3)
        
        # Create all roles in a single transaction to avoid locking issues
        print(f"{Colors.BLUE}Creating database roles...{Colors.NC}")
        repl_pass = repl_config.get('password', '')
        
        # Use a single SQL script with all commands
        sql_script = f"""
DO $$
BEGIN
    -- Create postgres role if not exists
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
        CREATE ROLE postgres WITH SUPERUSER LOGIN;
    END IF;
    
    -- Create replication user if not exists
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{repl_user}') THEN
        CREATE USER {repl_user} REPLICATION LOGIN PASSWORD '{repl_pass}';
    END IF;
END
$$;
"""
        
        success, output = node.psql(sql_script)
        
        if not success:
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: Failed to create database roles")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"The primary node is running but SQL commands are failing.")
            print(f"\nTry connecting manually:")
            print(f"  psql -p {port} -U {node.os_user} -d postgres")
            print(f"\nCheck the log:")
            print(f"  tail -50 {self.log_dir}/postgres_port_{port}.log")
            sys.exit(1)
        
        print(f"{Colors.GREEN}✓ Created database roles{Colors.NC}")
        
        print(f"{Colors.GREEN}✓ Primary node running on port {port}{Colors.NC}")
        return node
    
    def setup_replica_node(self, pg_bin, data_dir, port, replica_data, primary_node):
        """Setup and start replica node"""
        replica_name = replica_data.get('name', 'replica')
        print_section(f"Setting up {replica_name.upper()} node (port {port})")
        
        # Get replication config from YAML
        repl_config = self.config.get('replication', {}) or {}
        repl_user = repl_config.get('user', '')
        repl_pass = repl_config.get('password', '')
        
        if not repl_user:
            print(f"\n{Colors.RED}ERROR: replication.user not configured in cluster-config.yaml{Colors.NC}")
            sys.exit(1)
        
        # Create replication slot (if not exists)
        slot_name = f"{replica_name}_slot"
        sql = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '{slot_name}') THEN
        PERFORM pg_create_physical_replication_slot('{slot_name}');
    END IF;
END
$$;
"""
        success, _ = primary_node.psql(sql)
        if success:
            print(f"{Colors.GREEN}✓ Replication slot '{slot_name}' ready{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}⚠ Could not verify/create replication slot{Colors.NC}")
        
        # Clone from primary using pg_basebackup
        print(f"{Colors.BLUE}Cloning from primary using pg_basebackup...{Colors.NC}")
        cmd = [
            f"{pg_bin}/pg_basebackup",
            "-h", "localhost",
            "-p", str(primary_node.port),
            "-U", repl_user,
            "-D", str(data_dir),
            "-Fp", "-Xs", "-P", "-R"
        ]
        
        success, _ = run_cmd(cmd, check=False)
        if not success or not data_dir.exists():
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: pg_basebackup failed for {replica_name}")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"Possible causes:")
            print(f"  • Primary not accessible: pg_isready -p {primary_node.port}")
            print(f"  • Replication user '{repl_user}' doesn't exist or lacks permissions")
            print(f"  • pg_hba.conf doesn't allow replication connections")
            print(f"\nVerify replication user:")
            print(f"  psql -p {primary_node.port} -U {primary_node.os_user} -d postgres -c \"SELECT rolname, rolreplication FROM pg_roles WHERE rolname='{repl_user}';\"")
            print(f"\nCheck pg_hba.conf:")
            print(f"  cat {primary_node.data_dir}/pg_hba.conf | grep replication")
            print(f"\nTest manual connection:")
            print(f"  psql -h localhost -p {primary_node.port} -U {repl_user} -d postgres")
            sys.exit(1)
        
        # Get node configuration from YAML
        node_config = self.get_node_config(replica_data)
        
        # Write replica-specific postgresql.conf settings from config
        PostgreSQLConfigWriter.write_postgresql_conf(
            data_dir, port, node_config, None, None,
            is_replica=True, slot_name=slot_name
        )
        
        # Update primary_conninfo in postgresql.auto.conf
        auto_conf = data_dir / "postgresql.auto.conf"
        if auto_conf.exists():
            new_conninfo = f"primary_conninfo = 'host=localhost port={primary_node.port} user={repl_user} password={repl_pass} application_name={replica_name}'\n"
            
            # Read and replace the primary_conninfo line
            lines = []
            with open(auto_conf, 'r') as f:
                for line in f:
                    if line.strip().startswith('primary_conninfo'):
                        lines.append(new_conninfo)
                    else:
                        lines.append(line)
            
            # Write back
            with open(auto_conf, 'w') as f:
                f.writelines(lines)
        
        # Write replica-specific pg_hba entries from config
        hba_entries = self.get_hba_entries(replica_data)
        if hba_entries:
            PostgreSQLConfigWriter.write_pg_hba_conf(data_dir, hba_entries, {'repl_user': repl_user})
        
        # Start replica (logs go to self.log_dir)
        print(f"{Colors.BLUE}Starting {replica_name}...{Colors.NC}")
        node = PostgreSQLNode(pg_bin, data_dir, port, self.os_type, log_dir=self.log_dir)
        if not node.start():
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: Failed to start {replica_name}")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"Check the log file:")
            print(f"  tail -50 {self.log_dir}/postgres_port_{port}.log")
            print(f"\nCommon issues:")
            print(f"  • Port {port} already in use")
            print(f"  • primary_conninfo incorrect in postgresql.auto.conf")
            sys.exit(1)
        
        time.sleep(2)
        
        # Verify replica is in recovery mode
        success, _ = run_cmd(['pg_isready', '-h', 'localhost', '-p', str(port), '-d', 'postgres'], check=False, capture=True)
        if not success:
            print(f"{Colors.YELLOW}⚠ {replica_name} started but not yet accepting connections{Colors.NC}")
        
        print(f"{Colors.GREEN}✓ {replica_name} running on port {port}{Colors.NC}")
        return node
    
    def setup_postgres_macos(self, version):
        """Setup PostgreSQL cluster on macOS - fully config-driven"""
        print_banner(f"PostgreSQL Cluster Setup (macOS, Version: {version})")
        
        # Set locale environment (critical for macOS PostgreSQL)
        os.environ['LC_ALL'] = 'en_US.UTF-8'
        os.environ['LANG'] = 'en_US.UTF-8'
        os.environ['LC_CTYPE'] = 'en_US.UTF-8'
        
        # Validate configuration
        nodes_config = self.config.get('nodes', {}) or {}
        primary_data = nodes_config.get('primary', {}) or {}
        replicas_data = nodes_config.get('replicas', []) or []
        
        primary_port = primary_data.get('port')
        if not primary_port:
            print(f"\n{Colors.RED}{'='*80}")
            print(f"ERROR: Primary port not configured")
            print(f"{'='*80}{Colors.NC}\n")
            print(f"Add to cluster-config.yaml:")
            print(f"  nodes:")
            print(f"    primary:")
            print(f"      port: 5432")
            sys.exit(1)
        
        # Validate replicas
        for idx, replica in enumerate(replicas_data, start=1):
            if not replica.get('port'):
                print(f"\n{Colors.RED}ERROR: Replica {idx} missing port in cluster-config.yaml{Colors.NC}")
                sys.exit(1)
            if not replica.get('name'):
                print(f"{Colors.YELLOW}⚠ Replica {idx} missing name, using 'replica{idx}'{Colors.NC}")
        
        # Get paths
        pg_bin = self.get_pg_bin(version)
        base_dir = self.get_base_data_dir()
        primary_dir = base_dir / "primary"
        
        # Cleanup
        self.cleanup_environment(base_dir)
        
        # Setup primary
        primary_config = self.get_node_config(primary_data)
        primary_node = self.setup_primary_node(pg_bin, primary_dir, primary_port, primary_config)
        
        if not primary_node:
            return False
        
        # Setup replicas
        replica_nodes = []
        for idx, replica_data in enumerate(replicas_data, start=1):
            replica_port = replica_data.get('port')
            replica_name = replica_data.get('name', f'replica{idx}')
            replica_dir = base_dir / replica_name
            
            replica_node = self.setup_replica_node(pg_bin, replica_dir, replica_port, replica_data, primary_node)
            if replica_node:
                replica_nodes.append(replica_node)
        
        # Enable synchronous replication now that replicas are up
        repl_config = self.config.get('replication', {}) or {}
        if repl_config.get('synchronous') and replica_nodes:
            print_section("Enabling synchronous replication")
            
            replica_names = ', '.join([r.get('name', f'replica{i}') for i, r in enumerate(replicas_data, start=1)])
            sync_mode = repl_config.get('synchronous_mode', 'FIRST 1')
            
            # Enable synchronous commit
            success, _ = primary_node.psql("ALTER SYSTEM SET synchronous_commit = on;")
            
            # Set synchronous standby names
            success2, _ = primary_node.psql(f"ALTER SYSTEM SET synchronous_standby_names = '{sync_mode} ({replica_names})';")
            
            # Reload configuration
            success3, _ = primary_node.psql("SELECT pg_reload_conf();")
            
            if success and success2 and success3:
                print(f"{Colors.GREEN}✓ Enabled synchronous replication{Colors.NC}")
                time.sleep(1)
                # Verify
                primary_node.psql("SELECT application_name, state, sync_state FROM pg_stat_replication;")
            else:
                print(f"{Colors.YELLOW}⚠ Could not enable synchronous replication (continuing anyway){Colors.NC}")
        
        # Verification
        print_section("Verifying cluster setup")
        time.sleep(2)
        self.show_postgres_status()
        
        print(f"\n{Colors.GREEN}✓ PostgreSQL cluster setup complete!{Colors.NC}\n")
        print(f"{Colors.BLUE}Connections:{Colors.NC}")
        print(f"  Primary:  psql -h localhost -p {primary_port} -U {getpass.getuser()}")
        for idx, replica_data in enumerate(replicas_data, start=1):
            print(f"  Replica {idx}: psql -h localhost -p {replica_data.get('port')} -U {getpass.getuser()}")
        
        print(f"\n{Colors.BLUE}Logs:{Colors.NC}")
        print(f"  Primary:  tail -f {self.log_dir}/postgres_port_{primary_port}.log")
        for idx, replica_data in enumerate(replicas_data, start=1):
            print(f"  Replica {idx}: tail -f {self.log_dir}/postgres_port_{replica_data.get('port')}.log")
        
        return True
    
    def setup_postgres(self, version=None):
        """Setup PostgreSQL cluster"""
        version = version or self.get_pg_version()
        
        if self.os_type == 'macos':
            return self.setup_postgres_macos(version)
        else:
            print(f"{Colors.YELLOW}Linux setup: Please configure PostgreSQL manually{Colors.NC}")
            print(f"{Colors.BLUE}Use your distribution's package manager and systemd services{Colors.NC}")
            return False
    
    ##########################################################################
    # Status & Monitoring
    ##########################################################################
    
    def show_postgres_status(self):
        """Show PostgreSQL cluster status"""
        print_banner("PostgreSQL Cluster Status")
        
        # Get config
        primary = ConfigManager.get_nested(self.config, 'nodes', 'primary', default={})
        replicas = ConfigManager.get_nested(self.config, 'nodes', 'replicas', default=[])
        
        primary_port = primary.get('port', 5432)
        primary_host = primary.get('host', 'localhost')
        pg_user = os.environ.get('PGUSER', OSDetector.get_default_user(self.os_type))
        
        # Check primary
        print_section(f"Primary Server (port {primary_port})")
        success, _ = run_cmd(['pg_isready', '-h', primary_host, '-p', str(primary_port), '-d', 'postgres'], 
                            check=False, capture=True)
        status = f"{Colors.GREEN}✓ RUNNING{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
        print(f"Status: {status}\n")
        
        if success:
            cmd = ['psql', '-h', primary_host, '-p', str(primary_port), '-U', pg_user, '-d', 'postgres', '-c',
                   'SELECT application_name, client_addr, state, sync_state FROM pg_stat_replication;']
            run_cmd(cmd, check=False)
        
        # Check replicas
        print_section("Replica Servers")
        for replica in replicas:
            port = replica.get('port')
            host = replica.get('host', 'localhost')
            name = replica.get('name', f'port-{port}')
            
            success, _ = run_cmd(['pg_isready', '-h', host, '-p', str(port), '-d', 'postgres'], 
                                check=False, capture=True)
            status = f"{Colors.GREEN}✓ RUNNING{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
            print(f"{name} (port {port}): {status}")
    
    def show_replication_lag(self):
        """Show replication lag"""
        print_banner("Replication Lag")
        
        replicas = ConfigManager.get_nested(self.config, 'nodes', 'replicas', default=[])
        pg_user = os.environ.get('PGUSER', OSDetector.get_default_user(self.os_type))
        
        for replica in replicas:
            port = replica.get('port')
            host = replica.get('host', 'localhost')
            name = replica.get('name', f'port-{port}')
            
            print(f"\n{Colors.YELLOW}{name} (port {port}):{Colors.NC}")
            cmd = [
                'psql', '-h', host, '-p', str(port), '-U', pg_user, '-d', 'postgres', '-c',
                '''SELECT 
                    pg_is_in_recovery() AS is_replica,
                    pg_last_wal_receive_lsn() AS receive_lsn,
                    pg_last_wal_replay_lsn() AS replay_lsn,
                    EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;'''
            ]
            run_cmd(cmd, check=False)
    
    ##########################################################################
    # Pooler Management
    ##########################################################################
    
    def get_pooler_config(self, pooler_name):
        """Get pooler configuration from YAML"""
        return self.config.get('poolers', {}).get(pooler_name, {})
    
    def start_pooler(self, pooler_name):
        """Start pooler using config from YAML"""
        pooler_config = self.get_pooler_config(pooler_name)
        
        if not pooler_config:
            print(f"{Colors.RED}✗ Pooler '{pooler_name}' not configured in YAML{Colors.NC}")
            return False
        
        if not pooler_config.get('enabled', False):
            print(f"{Colors.YELLOW}⚠ Pooler '{pooler_name}' is disabled in config{Colors.NC}")
            return False
        
        print(f"{Colors.BLUE}Starting {pooler_name}...{Colors.NC}")
        
        # Get settings from config
        bin_path = pooler_config.get('bin_path', '')
        config_file = pooler_config.get('config_file', '')
        log_file = pooler_config.get('log_file', f'log/{pooler_name}.log')
        options = pooler_config.get('options', '')
        port = pooler_config.get('port')
        
        # Auto-detect binary if not in config
        if not bin_path:
            bin_path = self._detect_pooler_binary(pooler_name)
        
        # Auto-detect config if not in config
        if not config_file:
            config_file = self._detect_pooler_config(pooler_name)
        
        if not bin_path:
            print(f"{Colors.RED}✗ Cannot find binary for {pooler_name}{Colors.NC}")
            return False
        
        # Ensure log directory exists
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Build command from config
        cmd_parts = [bin_path]
        if options:
            cmd_parts.extend(options.split())
        if config_file:
            cmd_parts.extend(['-f', config_file])
        
        cmd = ' '.join(cmd_parts) + f" > {log_file} 2>&1 &"
        
        print(f"{Colors.CYAN}Command: {cmd}{Colors.NC}")
        run_cmd(cmd, shell=True, check=False)
        time.sleep(2)
        
        # Verify
        success, _ = run_cmd(['pgrep', '-f', pooler_name], check=False, capture=True)
        if success:
            print(f"{Colors.GREEN}✓ {pooler_name} started on port {port}{Colors.NC}")
            return True
        else:
            print(f"{Colors.RED}✗ Failed to start {pooler_name}. Check {log_file}{Colors.NC}")
            return False
    
    def _detect_pooler_binary(self, pooler_name):
        """Auto-detect pooler binary location"""
        if pooler_name == 'pgbalancer':
            locations = [
                self.project_root / "pgbalancer" / "build" / "bin" / "pgbalancer",
                self.project_root / "pgbalancer" / "src" / "pgbalancer"
            ]
            for loc in locations:
                if loc.exists():
                    return str(loc)
        
        # Check if in PATH
        success, path = run_cmd(['which', pooler_name], check=False, capture=True)
        return path if success else None
    
    def _detect_pooler_config(self, pooler_name):
        """Auto-detect pooler config file location"""
        config_map = {
            'pgbalancer': ['pgbalancer.yaml', 'build/etc/pgbalancer.yaml'],
            'pgbouncer': ['pgbouncer.ini'],
            'pgpool2': ['pgpool.conf'],
            'pgcat': ['pgcat.toml'],
            'haproxy': ['haproxy.cfg']
        }
        
        for filename in config_map.get(pooler_name, []):
            for base in [self.project_root, self.conf_dir, self.project_root / pooler_name]:
                loc = base / filename
                if loc.exists():
                    return str(loc)
        return None
    
    def stop_pooler(self, pooler_name):
        """Stop specific pooler"""
        print(f"{Colors.BLUE}Stopping {pooler_name}...{Colors.NC}")
        run_cmd(['pkill', '-9', pooler_name], check=False)
        time.sleep(1)
        
        success, _ = run_cmd(['pgrep', '-f', pooler_name], check=False, capture=True)
        if not success:
            print(f"{Colors.GREEN}✓ {pooler_name} stopped{Colors.NC}")
            return True
        else:
            print(f"{Colors.RED}✗ Failed to stop {pooler_name}{Colors.NC}")
            return False
    
    def start_all_poolers(self):
        """Start all enabled poolers from config"""
        poolers = self.config.get('poolers', {})
        started = []
        
        for pooler_name, pooler_config in poolers.items():
            if pooler_config and pooler_config.get('enabled', False):
                if self.start_pooler(pooler_name):
                    started.append(pooler_name)
        
        if started:
            print(f"\n{Colors.GREEN}✓ Started poolers: {', '.join(started)}{Colors.NC}")
        return len(started) > 0
    
    def stop_all_poolers(self):
        """Stop all poolers"""
        poolers = self.config.get('poolers', {})
        
        for pooler_name in poolers.keys():
            self.stop_pooler(pooler_name)
        
        return True
    
    def show_pooler_status(self):
        """Show status of all configured poolers"""
        print_banner("Pooler Status")
        
        poolers = self.config.get('poolers', {})
        
        for pooler_name, pooler_config in poolers.items():
            if not pooler_config:
                continue
            
            enabled = pooler_config.get('enabled', False)
            port = pooler_config.get('port')
            
            success, _ = run_cmd(['pgrep', '-f', pooler_name], check=False, capture=True)
            
            status_str = f"{Colors.GREEN}✓ RUNNING{Colors.NC}" if success else f"{Colors.RED}✗ DOWN{Colors.NC}"
            enabled_str = f"{Colors.GREEN}[enabled]{Colors.NC}" if enabled else f"{Colors.YELLOW}[disabled]{Colors.NC}"
            
            print(f"{pooler_name:15} Port {port if port else 'N/A':>5} {status_str} {enabled_str}")
    
    ##########################################################################
    # Health Check
    ##########################################################################
    
    def health_check(self):
        """Comprehensive health check"""
        print_banner("Health Check")
        
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'postgres': {},
            'replication': {},
            'poolers': {}
        }
        
        # Check PostgreSQL nodes from config
        primary = ConfigManager.get_nested(self.config, 'nodes', 'primary', default={})
        replicas = ConfigManager.get_nested(self.config, 'nodes', 'replicas', default=[])
        
        if primary.get('port'):
            success, _ = run_cmd(['pg_isready', '-h', 'localhost', '-p', str(primary.get('port')), '-d', 'postgres'], check=False, capture=True)
            health_report['postgres'][f"port_{primary.get('port')}"] = success
        
        active_replicas = 0
        for replica in replicas:
            port = replica.get('port')
            if port:
                success, _ = run_cmd(['pg_isready', '-h', 'localhost', '-p', str(port), '-d', 'postgres'], check=False, capture=True)
                health_report['postgres'][f"port_{port}"] = success
                if success:
                    active_replicas += 1
        
        health_report['replication']['active_replicas'] = active_replicas
        
        # Check poolers from config
        poolers = self.config.get('poolers', {})
        for pooler_name in poolers.keys():
            success, _ = run_cmd(['pgrep', '-f', pooler_name], check=False, capture=True)
            health_report['poolers'][pooler_name] = success
        
        # Save report
        report_file = self.log_dir / f"health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(health_report, f, indent=2)
        
        # Display
        print(json.dumps(health_report, indent=2))
        print(f"\n{Colors.GREEN}✓ Health report saved: {report_file}{Colors.NC}")
        
        return health_report
    
    ##########################################################################
    # Installation
    ##########################################################################
    
    def install_dependencies(self):
        """Install PostgreSQL and pooler dependencies"""
        print_banner(f"Installing Dependencies (OS: {self.os_type})")
        
        install_cmd_base = ['brew', 'install'] if self.os_type == 'macos' else ['sudo', self.pkg_manager, 'install', '-y']
        pg_version = self.get_pg_version()
        
        print_section("Installing PostgreSQL")
        if self.os_type == 'macos':
            packages = [f'postgresql@{pg_version}', 'libyaml', 'openssl@3']
        elif self.os_type in ['rocky', 'fedora']:
            packages = [f'postgresql{pg_version}', f'postgresql{pg_version}-server']
        else:
            packages = [f'postgresql-{pg_version}']
        
        run_cmd(install_cmd_base + packages, check=False)
        print(f"{Colors.GREEN}✓ PostgreSQL installed{Colors.NC}")
        
        print_section("Installing Poolers")
        if self.os_type == 'macos':
            run_cmd(['brew', 'install', 'pgbouncer'], check=False)
        else:
            run_cmd(install_cmd_base + ['pgbouncer', 'pgpool-II'], check=False)
        
        print(f"{Colors.GREEN}✓ Poolers installed{Colors.NC}")
        print(f"{Colors.GREEN}✓ All dependencies installed{Colors.NC}")

#==============================================================================
# Main Entry Point
#==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='PostgreSQL Cluster Manager - Configuration-driven cluster and pooler management',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Options
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output (show all command output)')
    parser.add_argument('--config', metavar='FILE',
                       help='Configuration file (default: conf/cluster-config.yaml)')
    
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
    pooler.add_argument('--start', metavar='POOLER',
                       help='Start pooler: all, pgbalancer, pgbouncer, pgpool2, pgcat, haproxy')
    pooler.add_argument('--stop', metavar='POOLER',
                       help='Stop pooler: all, pgbalancer, pgbouncer, pgpool2, pgcat, haproxy')
    pooler.add_argument('--pooler-status', action='store_true',
                       help='Show pooler status')
    
    # Health
    health = parser.add_argument_group('Health & Diagnostics')
    health.add_argument('--health-check', action='store_true',
                       help='Comprehensive health check')
    health.add_argument('--logs', metavar='COMPONENT',
                       help='Show logs (postgres, pooler_name)')
    health.add_argument('--lines', type=int, default=50,
                       help='Number of log lines')
    
    args = parser.parse_args()
    
    # Set verbose mode
    if args.verbose:
        os.environ['CLUSTER_VERBOSE'] = '1'
    
    # Initialize cluster manager
    cluster = ClusterManager(config_file=args.config)
    
    # Execute commands
    if args.install:
        cluster.install_dependencies()
    
    elif args.setup_postgres:
        cluster.setup_postgres(version=args.version)
    
    elif args.status:
        cluster.show_postgres_status()
    
    elif args.replication_lag:
        cluster.show_replication_lag()
    
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
    
    elif args.health_check:
        cluster.health_check()
    
    elif args.logs:
        # Show logs functionality
        print(f"{Colors.BLUE}Showing logs for {args.logs} (last {args.lines} lines):{Colors.NC}")
        log_file = cluster.log_dir / f"{args.logs}.log"
        if log_file.exists():
            run_cmd(['tail', '-n', str(args.lines), str(log_file)], check=False)
        else:
            print(f"{Colors.RED}✗ Log file not found: {log_file}{Colors.NC}")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
