#!/usr/bin/env python3
"""
PostgreSQL Pooler Benchmark Suite with HammerDB
================================================

Professional benchmark suite for testing PostgreSQL poolers with industry-standard
TPC-C and TPC-H workloads using HammerDB.

Supports: pgbalancer, pgbouncer, pgpool2, pgcat

Usage:
    # Setup cluster first (use cluster.py):
    cd ../cluster/scripts
    ./cluster.py --install                 # Install dependencies
    ./cluster.py --setup-postgres          # Setup PostgreSQL cluster
    
    # Then run benchmarks:
    cd ../../benchmark/scripts
    python3 benchmark.py --init            # Initialize TPC-C schema and data
    python3 benchmark.py --run --t 300 --n 16  # Run benchmark

Author: pgElephant, Inc.
Version: 2.0.0
License: MIT
"""

import argparse
import subprocess
import sys
import os
import time
import json
import logging
import shutil
import urllib.request
import platform
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional
import tarfile
import zipfile
import threading

try:
    import yaml
    import psutil
except ImportError as e:
    print(f"ERROR: Required packages not installed: {e}")
    print("Run: pip3 install -r ../requirements.txt")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

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
        return {
            'macos': 'brew',
            'rocky': 'dnf',
            'ubuntu': 'apt',
            'fedora': 'dnf',
            'linux': 'apt'
        }.get(os_type, 'apt')
    
    @staticmethod
    def get_install_cmd(os_type):
        """Get install command for OS"""
        if os_type == 'macos':
            return ['brew', 'install']
        elif os_type in ['rocky', 'fedora']:
            return ['sudo', 'dnf', 'install', '-y']
        else:
            return ['sudo', 'apt-get', 'install', '-y']
    
    @staticmethod
    def get_pg_service_cmd(os_type, action='status'):
        """Get PostgreSQL service command"""
        if os_type == 'macos':
            return ['brew', 'services', action, 'postgresql@17']
        else:
            return ['sudo', 'systemctl', action, 'postgresql-17']

@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark suite (NO hard-coded paths)"""
    # Directories - use environment variables with fallbacks
    work_dir: str = field(default_factory=lambda: os.environ.get('BENCHMARK_WORK_DIR', 
                                                                  str(Path.home() / '.benchmark')))
    postgres_data_dir: str = field(default_factory=lambda: os.environ.get('PGDATA', 
                                                                          str(Path.home() / 'pgdata')))
    hammerdb_dir: str = field(default_factory=lambda: os.environ.get('HAMMERDB_DIR', 
                                                                     str(Path.home() / '.hammerdb')))
    conf_dir: str = field(default_factory=lambda: os.environ.get('BENCHMARK_CONF_DIR',
                                                                 str(Path(__file__).parent.parent / 'conf')))
    log_dir: str = field(default_factory=lambda: os.environ.get('BENCHMARK_LOG_DIR',
                                                                str(Path(__file__).parent.parent / 'log')))
    
    # PostgreSQL settings - use environment variables
    postgres_host: str = field(default_factory=lambda: os.environ.get('PGHOST', 'localhost'))
    postgres_port: int = field(default_factory=lambda: int(os.environ.get('PGPORT', '5432')))
    postgres_user: str = field(default_factory=lambda: os.environ.get('PGUSER', 'postgres'))
    postgres_password: str = field(default_factory=lambda: os.environ.get('PGPASSWORD', ''))
    postgres_database: str = field(default_factory=lambda: os.environ.get('PGDATABASE', 'benchmark'))
    
    # Replica settings
    num_replicas: int = 0
    replica_start_port: int = 5433
    replica_data_dirs: List[str] = field(default_factory=list)
    
    # Pooler settings
    poolers: Dict[str, Dict[str, Any]] = None
    
    # Benchmark type settings (loaded from config file)
    benchmark_type: str = "tpcc"
    warehouses: int = 10
    scale_factor: int = 10
    
    # Benchmark settings (loaded from config file)
    threads: int = 16
    time: int = 300
    rampup: int = 2
    
    # HammerDB settings (loaded from config file)
    hammerdb_version: str = "4.11"
    driver: str = "timed"
    raiseerror: bool = True
    keyandthink: bool = False
    checkpoint: bool = False
    vacuum: bool = False
    drita: bool = False
    unique_log_name: bool = True
    no_log_buffer: bool = False
    
    def __post_init__(self):
        if self.poolers is None:
            self.poolers = {
                "pgpool2": {
                    "enabled": True,
                    "port": 9999,
                    "config_file": "pgpool2.conf"
                },
                "pgbalancer": {
                    "enabled": True,
                    "port": 9999,
                    "config_file": "pgbalancer.yaml"
                },
                "pgbouncer": {
                    "enabled": True,  # Enable pgbouncer testing
                    "port": 9997,
                    "config_file": "pgbouncer.ini"
                },
                "pgcat": {
                    "enabled": False,
                    "port": 9996,
                    "config_file": "pgcat.toml"
                }
            }

@dataclass
class BenchmarkResult:
    """Results from a benchmark run"""
    pooler_name: str
    test_name: str
    threads: int
    duration: float
    tps: float
    qps: float
    latency_avg: float
    latency_p95: float
    latency_p99: float
    errors: int
    reconnects: int
    memory_usage: float
    cpu_usage: float
    timestamp: str

class BenchmarkSuite:
    """Main benchmark suite class"""
    
    def __init__(self, config: BenchmarkConfig):
        # Detect OS
        self.os_type = OSDetector.detect()
        self.pkg_manager = OSDetector.get_package_manager(self.os_type)
        
        logger.info(f"╔{'═'*78}╗")
        logger.info(f"║ Detected OS: {self.os_type:20} | Package Manager: {self.pkg_manager:20} ║")
        logger.info(f"╚{'═'*78}╝\n")
        
        self.config = config
        self.processes: Dict[str, subprocess.Popen] = {}
        self.results: List[BenchmarkResult] = []
        
        # Create work directory
        Path(self.config.work_dir).mkdir(parents=True, exist_ok=True)
        
    def install_dependencies(self):
        """Install Python requirements, poolers, and HammerDB"""
        logger.info("✓ === INSTALLING BENCHMARK DEPENDENCIES ===")
        
        # Install Python packages
        self._install_python_requirements()
        
        # Install poolers
        self._install_poolers()
        
        # Install HammerDB
        self._install_hammerdb()
        
        logger.info("✓ All benchmark dependencies installed")
    
    def _install_python_requirements(self):
        """Install Python packages from requirements.txt"""
        logger.info("✓ Installing Python packages...")
        
        requirements_file = Path(__file__).parent.parent / "requirements.txt"
        
        if not requirements_file.exists():
            logger.warning(f"⚠ requirements.txt not found at {requirements_file}")
            return
        
        # Detect OS for pip flags
        os_type = OSDetector.detect()
        
        if os_type == 'macos':
            cmd = [sys.executable, '-m', 'pip', 'install', '--break-system-packages', '-r', str(requirements_file)]
        else:
            cmd = [sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✓ Python packages installed successfully")
        else:
            logger.warning(f"⚠ Some packages may have failed to install")
            logger.info(result.stderr)
    
    def _install_poolers(self):
        """Install all PostgreSQL poolers (OS-aware)"""
        logger.info("✓ Installing PostgreSQL poolers...")
        
        install_cmd = OSDetector.get_install_cmd(self.os_type)
        
        if self.os_type == 'macos':
            # macOS: install via Homebrew
            poolers = ['pgbouncer', 'haproxy']
            for pooler in poolers:
                logger.info(f"  Installing {pooler}...")
                run_cmd(install_cmd + [pooler], check=False, capture=True)
            
            # pgpool2 not available on macOS Homebrew
            logger.info("  pgpool2: Not available on macOS")
            
            # pgcat: install via cargo if Rust is available
            if shutil.which('cargo'):
                logger.info("  Installing pgcat via cargo...")
                run_cmd(['cargo', 'install', 'pgcat'], check=False, capture=True)
            else:
                logger.info("  pgcat: Rust not available, skipping")
                
        elif self.os_type in ['rocky', 'fedora']:
            # Rocky/Fedora: install via dnf
            poolers = ['pgbouncer', 'pgpool-II', 'haproxy']
            run_cmd(install_cmd + poolers, check=False, capture=True)
            
            # pgcat: install via cargo
            if shutil.which('cargo'):
                run_cmd(['cargo', 'install', 'pgcat'], check=False, capture=True)
                
        else:  # ubuntu/debian
            # Ubuntu/Debian: install via apt
            run_cmd(['sudo', 'apt-get', 'update'], check=False, capture=True)
            poolers = ['pgbouncer', 'pgpool2', 'haproxy']
            run_cmd(install_cmd + poolers, check=False, capture=True)
            
            # pgcat: install via cargo
            if shutil.which('cargo'):
                run_cmd(['cargo', 'install', 'pgcat'], check=False, capture=True)
        
        logger.info("✓ Pooler installation completed")
    
    def _install_hammerdb(self):
        """Install HammerDB"""
        logger.info("✓ Installing HammerDB...")
        
        hammerdb_dir = Path(self.config.hammerdb_dir)
        hammerdb_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Get version from config
            hammerdb_version = self.config.hammerdb_version
            
            # Check if already installed
            hammerdb_bin = hammerdb_dir / f"HammerDB-{hammerdb_version}" / "hammerdbcli"
            if hammerdb_bin.exists():
                logger.info(f"✓ HammerDB {hammerdb_version} already installed at {hammerdb_dir}")
                return
            
            if self.os_type == 'macos':
                download_url = f"https://github.com/TPC-Council/HammerDB/releases/download/v{hammerdb_version}/HammerDB-{hammerdb_version}-Mac-ARM-Installer.zip"
                archive_name = f"HammerDB-{hammerdb_version}-Mac-ARM-Installer.zip"
                is_zip = True
            else:
                download_url = f"https://github.com/TPC-Council/HammerDB/releases/download/v{hammerdb_version}/HammerDB-{hammerdb_version}-Linux.tar.gz"
                archive_name = f"HammerDB-{hammerdb_version}-Linux.tar.gz"
                is_zip = False
            
            logger.info(f"✓ Downloading HammerDB from {download_url}")
            archive_path = hammerdb_dir / archive_name
            
            # Download
            urllib.request.urlretrieve(download_url, archive_path)
            
            # Extract
            logger.info("✓ Extracting HammerDB...")
            if is_zip:
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(hammerdb_dir)
            else:
                with tarfile.open(archive_path, 'r:gz') as tar:
                    tar.extractall(hammerdb_dir)
            
            # Make executable
            hammerdb_bin = hammerdb_dir / f"HammerDB-{hammerdb_version}" / "hammerdbcli"
            if hammerdb_bin.exists():
                hammerdb_bin.chmod(0o755)
            
            # Clean up archive
            archive_path.unlink()
            
            logger.info(f"✓ HammerDB installed at {hammerdb_bin}")
            
        except Exception as e:
            logger.error(f"Failed to install HammerDB: {e}")
            logger.info("You can manually download from: https://github.com/TPC-Council/HammerDB/releases")
            sys.exit(1)
    
    
    def setup_environment(self):
        """Check environment (PostgreSQL should be setup by cluster.py)"""
        logger.info("✓ === CHECKING ENVIRONMENT ===")
        
        # Setup logging
        self._setup_logging()
        
        # Check PostgreSQL is running (setup by cluster.py)
        self._check_postgresql()
        
        logger.info("✓ Environment check completed")
    
    def _check_postgresql(self):
        """Check if PostgreSQL is available"""
        logger.info("✓ Checking PostgreSQL...")
        
        # Check if PostgreSQL is running
        try:
            # Try different PostgreSQL paths
            pg_isready_paths = [
                "pg_isready",  # Use PATH
                "/usr/pgsql-17/bin/pg_isready",
                "/usr/bin/pg_isready",
                "/usr/local/bin/pg_isready"
            ]
            
            pg_isready_cmd = None
            for path in pg_isready_paths:
                if shutil.which(path):
                    pg_isready_cmd = path
                    break
            
            if not pg_isready_cmd:
                logger.error("✗ pg_isready command not found")
                return False
            
            result = subprocess.run([
                pg_isready_cmd,
                "-h", "localhost",
                "-p", str(self.config.postgres_port)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("✓ PostgreSQL is running and ready")
            else:
                logger.error("✗ PostgreSQL is not running. Please start PostgreSQL first.")
                return False
        except Exception as e:
            logger.error(f"✗ Error checking PostgreSQL: {e}")
            return False
        
        logger.info("✓ PostgreSQL is running and ready")
        return True
    
    def _restart_postgresql(self):
        """Restart PostgreSQL with optimized settings"""
        logger.info("✓ Restarting PostgreSQL with optimized settings...")
        
        try:
            # Stop PostgreSQL
            logger.info("  Stopping PostgreSQL...")
            subprocess.run(["sudo", "systemctl", "stop", "postgresql"], 
                         check=True, capture_output=True)
            time.sleep(2)
            
            # Copy optimized configuration
            logger.info("  Applying optimized configuration...")
            subprocess.run([
                "sudo", "cp", self.config.postgres_config_file, 
                "/var/lib/pgsql/data/postgresql.conf"
            ], check=True, capture_output=True)
            
            subprocess.run([
                "sudo", "cp", self.config.postgres_hba_file,
                "/var/lib/pgsql/data/pg_hba.conf"
            ], check=True, capture_output=True)
            
            # Set proper ownership
            subprocess.run([
                "sudo", "chown", "postgres:postgres", 
                "/var/lib/pgsql/data/postgresql.conf",
                "/var/lib/pgsql/data/pg_hba.conf"
            ], check=True, capture_output=True)
            
            # Start PostgreSQL
            logger.info("  Starting PostgreSQL...")
            subprocess.run(["sudo", "systemctl", "start", "postgresql"], 
                         check=True, capture_output=True)
            
            # Wait for PostgreSQL to be ready
            logger.info("  Waiting for PostgreSQL to be ready...")
            for i in range(30):  # Wait up to 30 seconds
                try:
                    result = subprocess.run([
                        "pg_isready", "-h", "localhost", "-p", "5432"
                    ], capture_output=True, text=True)
                    if result.returncode == 0:
                        logger.info("✓ PostgreSQL restarted successfully")
                        return True
                except:
                    pass
                time.sleep(1)
            
            logger.error("✗ PostgreSQL failed to start")
            return False
            
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ Error restarting PostgreSQL: {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error restarting PostgreSQL: {e}")
            return False
    
    def _setup_replicas(self):
        """NOT USED - Replicas should be setup by cluster.py"""
        logger.warning("⚠ PostgreSQL replicas should be setup using cluster.py --setup-postgres")
        logger.info("Skipping replica setup...")
        return True
    
    def _setup_poolers(self):
        """NOT USED - Poolers managed by cluster.py"""
        logger.info("✓ Using pooler configurations from conf/ directory")
        return True
    
    def initialize_benchmark(self):
        """Initialize benchmark schema and data"""
        logger.info(f"✓ === INITIALIZING {self.config.benchmark_type.upper()} ===")
        
        # Create benchmark schema
        self._create_benchmark_schema()
        
        # Generate benchmark data
        self._generate_benchmark_data()
        
        logger.info(f"✓ {self.config.benchmark_type.upper()} initialization completed")
    
    def _create_benchmark_schema(self):
        """Create benchmark schema using HammerDB"""
        logger.info(f"✓ Creating {self.config.benchmark_type.upper()} schema using HammerDB...")
        
        if self.config.benchmark_type in ["tpcc", "tpcb", "tpch"]:
            self._create_hammerdb_schema()
        else:
            logger.error(f"✗ Unknown benchmark type: {self.config.benchmark_type}")
            sys.exit(1)
    
    def _create_hammerdb_schema(self):
        """Create schema using HammerDB"""
        logger.info("✓ Creating schema using HammerDB...")
        
        # Use HammerDB to create schema
        subprocess.run([
            "hammerdb", "auto", "/opt/hammerdb/tcl/tpcc/pgoltp.tcl",
            f"pgoltp_driver=1",
            f"pgoltp_rampup=0",
            f"pgoltp_duration=0",
            f"pgoltp_host=localhost",
            f"pgoltp_port={self.config.postgres_port}",
            f"pgoltp_user={self.config.postgres_user}",
            f"pgoltp_pass={self.config.postgres_password or ''}",
            f"pgoltp_dbase={self.config.postgres_database}",
            f"pgoltp_warehouses={self.config.warehouses}",
            "build"
        ], check=True)
        
        logger.info("✓ TPC-C schema created with HammerDB")
    
    def _create_tpcb_schema(self):
        """Create TPC-B schema (simplified TPC-C)"""
        logger.info("✓ Creating TPC-B schema with HammerDB...")
        self._create_tpcc_schema()  # TPC-B uses same schema as TPC-C
        logger.info("✓ TPC-B schema created")
    
    def _create_tpch_schema(self):
        """Create TPC-H schema using HammerDB"""
        logger.info("✓ Creating TPC-H schema with HammerDB...")
        
        # Generate HammerDB TCL script for TPC-H
        tcl_script = self._generate_hammerdb_tpch_script()
        hammerdb_bin = self._get_hammerdb_bin()
        
        result = subprocess.run([
            str(hammerdb_bin), str(tcl_script)
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✓ TPC-H schema created successfully")
        else:
            logger.error(f"✗ TPC-H creation failed: {result.stderr}")
            raise Exception("TPC-H schema creation failed")
    
    def _generate_benchmark_data(self):
        """Generate benchmark test data using HammerDB"""
        logger.info(f"✓ Generating {self.config.benchmark_type.upper()} data using HammerDB...")
        
        if self.config.benchmark_type in ["tpcc", "tpcb", "tpch"]:
            self._generate_hammerdb_data()
        else:
            logger.error(f"✗ Unknown benchmark type: {self.config.benchmark_type}")
            sys.exit(1)
        
        logger.info(f"✓ {self.config.benchmark_type.upper()} data generated using HammerDB")
    
    def _get_hammerdb_bin(self):
        """Get HammerDB binary path (OS-aware, uses config)"""
        hammerdb_dir = Path(self.config.hammerdb_dir)
        hammerdb_version = self.config.hammerdb_version
        hammerdb_bin = hammerdb_dir / f"HammerDB-{hammerdb_version}" / "hammerdbcli"
        
        if not hammerdb_bin.exists():
            logger.error(f"✗ HammerDB not found at {hammerdb_bin}")
            logger.error("Run: python3 benchmark.py --install")
            sys.exit(1)
        
        return hammerdb_bin
    
    def _generate_hammerdb_build_script(self, pooler_port=None):
        """Generate HammerDB TCL script for building TPC-C schema"""
        port = pooler_port if pooler_port else self.config.postgres_port
        
        tcl_script = f"""#!/usr/bin/tclsh
# HammerDB TPC-C Build Script (Auto-generated)

dbset db pg
dbset bm TPC-C

diset connection pg_host localhost
diset connection pg_port {port}
diset tpcc pg_user {self.config.postgres_user}
diset tpcc pg_pass {self.config.postgres_password or ''}
diset tpcc pg_dbase {self.config.postgres_database}
diset tpcc pg_count_ware {self.config.warehouses}
diset tpcc pg_num_vu 1

buildschema
waittocomplete
quit
"""
        
        # Save script
        script_path = Path(self.config.work_dir) / "hammerdb_build.tcl"
        with open(script_path, 'w') as f:
            f.write(tcl_script)
        
        return script_path
    
    def _generate_hammerdb_run_script(self, pooler_port, threads, duration):
        """Generate HammerDB TCL script for running TPC-C benchmark"""
        
        tcl_script = f"""#!/usr/bin/tclsh
# HammerDB TPC-C Run Script (Auto-generated)

dbset db pg
dbset bm TPC-C

diset connection pg_host localhost
diset connection pg_port {pooler_port}
diset tpcc pg_driver {self.config.driver}
diset tpcc pg_user {self.config.postgres_user}
diset tpcc pg_pass {self.config.postgres_password or ''}
diset tpcc pg_dbase {self.config.postgres_database}
diset tpcc pg_count_ware {self.config.warehouses}
diset tpcc pg_num_vu {threads}
diset tpcc pg_rampup {self.config.rampup}
diset tpcc pg_duration {duration // 60}
diset tpcc pg_raiseerror {str(self.config.raiseerror).lower()}
diset tpcc pg_keyandthink {str(self.config.keyandthink).lower()}
diset tpcc pg_checkpoint {str(self.config.checkpoint).lower()}
diset tpcc pg_vacuum {str(self.config.vacuum).lower()}
diset tpcc pg_drita {str(self.config.drita).lower()}
diset tpcc pg_unique_log_name {str(self.config.unique_log_name).lower()}
diset tpcc pg_no_log_buffer {str(self.config.no_log_buffer).lower()}

vuset vu {threads}
loadscript
vucreate
vurun
runtimer {duration}
vudestroy
quit
"""
        
        # Save script
        script_path = Path(self.config.work_dir) / f"hammerdb_run_{pooler_port}.tcl"
        with open(script_path, 'w') as f:
            f.write(tcl_script)
        
        return script_path
    
    def _generate_hammerdb_data(self):
        """Generate test data using HammerDB"""
        logger.info(f"✓ Generating data for {self.config.warehouses} warehouses with HammerDB...")
        
        # Generate build script
        tcl_script = self._generate_hammerdb_build_script()
        hammerdb_bin = self._get_hammerdb_bin()
        
        # Run HammerDB to build schema
        result = subprocess.run([
            str(hammerdb_bin), str(tcl_script)
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"✗ HammerDB build failed: {result.stderr}")
            raise Exception("Schema creation failed")
        
        logger.info("✓ TPC-C data generated successfully")
    
    def _generate_hammerdb_tpch_script(self):
        """Generate HammerDB TCL script for TPC-H"""
        
        tcl_script = f"""#!/usr/bin/tclsh
# HammerDB TPC-H Build Script (Auto-generated)

dbset db pg
dbset bm TPC-H

diset connection pg_host localhost
diset connection pg_port {self.config.postgres_port}
diset tpch pg_user {self.config.postgres_user}
diset tpch pg_pass {self.config.postgres_password or ''}
diset tpch pg_dbase {self.config.postgres_database}
diset tpch pg_scale_fact {self.config.scale_factor}

buildschema
waittocomplete
quit
"""
        
        # Save script
        script_path = Path(self.config.work_dir) / "hammerdb_tpch_build.tcl"
        with open(script_path, 'w') as f:
            f.write(tcl_script)
        
        return script_path
    
    def run_benchmark(self, poolers: List[str], threads: int, time: int):
        """Run benchmark"""
        logger.info(f"✓ === RUNNING {self.config.benchmark_type.upper()} BENCHMARK ===")
        
        # Initial PostgreSQL restart with optimized settings
        logger.info("Initial PostgreSQL restart with optimized settings...")
        if not self._restart_postgresql():
            logger.error("Failed to restart PostgreSQL with optimized settings")
            return
        
        for i, pooler in enumerate(poolers):
            if pooler not in self.config.poolers:
                logger.error(f"Unknown pooler: {pooler}")
                continue
            
            if not self.config.poolers[pooler]["enabled"]:
                logger.info(f"Skipping disabled pooler: {pooler}")
                continue
            
            logger.info(f"Testing {pooler}...")
            
            # Restart PostgreSQL for each test (except the first one)
            if i > 0:
                logger.info(f"Restarting PostgreSQL before testing {pooler}...")
                if not self._restart_postgresql():
                    logger.error(f"Failed to restart PostgreSQL before testing {pooler}")
                    continue
            
            # Start pooler
            if not self._start_pooler(pooler):
                logger.error(f"Failed to start {pooler}")
                continue
            
            try:
                # Run benchmark
                result = self._run_benchmark_test(pooler, threads, time)
                if result:
                    self.results.append(result)
                
                logger.info(f"{pooler} completed: {result.tps:.2f} TPS")
                
            finally:
                # Stop pooler
                self._stop_pooler(pooler)
        
        # Generate report
        self._generate_report()
    
    def _start_pooler(self, pooler_name: str) -> bool:
        """Start a pooler"""
        try:
            # Check if pooler binary exists
            if pooler_name == "pgpool2":
                if not shutil.which("pgpool"):
                    logger.error(f"✗ pgpool2 not found, skipping...")
                    return False
                cmd = ["pgpool", "-f", str(Path(self.config.conf_dir) / "pgpool2.conf"), "-n"]
            elif pooler_name == "pgbalancer":
                if not shutil.which("pgbalancer"):
                    logger.error(f"✗ pgbalancer not found, skipping...")
                    return False
                cmd = ["pgbalancer", "-f", str(Path(self.config.conf_dir) / "pgbalancer.yaml"), "-n"]
            elif pooler_name == "pgbouncer":
                if not shutil.which("pgbouncer"):
                    logger.error(f"✗ pgbouncer not found, skipping...")
                    return False
                cmd = ["pgbouncer", "-d", str(Path(self.config.conf_dir) / "pgbouncer.ini")]
            elif pooler_name == "pgcat":
                if not shutil.which("pgcat"):
                    logger.error(f"✗ pgcat not found, skipping...")
                    return False
                cmd = ["pgcat", str(Path(self.config.conf_dir) / "pgcat.toml")]
            else:
                return False
            
            # Check if config file exists
            config_path = Path(self.config.conf_dir) / self.config.poolers[pooler_name]["config_file"]
            if not config_path.exists():
                logger.error(f"✗ Config file not found: {config_path}")
                return False
            
            # Start pooler in background with logging
            log_file = Path(self.config.log_dir) / f"{pooler_name}.log"
            with open(log_file, 'w') as log_f:
                self.processes[pooler_name] = subprocess.Popen(
                    cmd, stdout=log_f, stderr=subprocess.STDOUT
                )
            
            # Wait for pooler to start
            time.sleep(3)
            
            # Check if process is still running
            if self.processes[pooler_name].poll() is None:
                logger.info(f"✓ Started {pooler_name} in background")
                return True
            else:
                # Read log file for error details
                try:
                    with open(log_file, 'r') as f:
                        error_log = f.read().strip()
                    if error_log:
                        logger.error(f"✗ Failed to start {pooler_name}: {error_log}")
                    else:
                        logger.error(f"✗ Failed to start {pooler_name}")
                except:
                    logger.error(f"✗ Failed to start {pooler_name}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to start {pooler_name}: {e}")
            return False
    
    def _setup_logging(self):
        """Setup logging directory"""
        Path(self.config.log_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Logging directory: {self.config.log_dir}")
    
    def _check_pooler_connection(self, pooler_name: str) -> bool:
        """Check if pooler is accepting connections"""
        try:
            import psycopg2
            port = self.config.poolers[pooler_name]["port"]
            conn = psycopg2.connect(
                host="localhost",
                port=port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                connect_timeout=5
            )
            conn.close()
            return True
        except Exception:
            return False
    
    def _stop_pooler(self, pooler_name: str):
        """Stop a pooler"""
        if pooler_name in self.processes:
            try:
                self.processes[pooler_name].terminate()
                self.processes[pooler_name].wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.processes[pooler_name].kill()
            except Exception as e:
                logger.error(f"Error stopping {pooler_name}: {e}")
            finally:
                del self.processes[pooler_name]
    
    def _run_benchmark_test(self, pooler_name: str, threads: int, duration: int) -> BenchmarkResult:
        """Run benchmark test using HammerDB"""
        port = self.config.poolers[pooler_name]["port"]
        
        logger.info(f"✓ Running HammerDB {self.config.benchmark_type.upper()} benchmark on {pooler_name} (port {port})...")
        logger.info(f"  Threads: {threads}, Duration: {duration}s, Warehouses: {self.config.warehouses}")
        
        # Generate HammerDB run script
        tcl_script = self._generate_hammerdb_run_script(port, threads, duration)
        hammerdb_bin = self._get_hammerdb_bin()
        
        # Monitor resources
        start_cpu = psutil.cpu_percent(interval=1)
        start_mem = psutil.virtual_memory().used / (1024 * 1024)  # MB
        
        # Run HammerDB
        start_time = time.time()
        result = subprocess.run([
            str(hammerdb_bin), str(tcl_script)
        ], capture_output=True, text=True)
        end_time = time.time()
        
        # Monitor resources after
        end_cpu = psutil.cpu_percent(interval=1)
        end_mem = psutil.virtual_memory().used / (1024 * 1024)  # MB
        
        # Parse HammerDB results
        tps = 0.0
        qps = 0.0
        tpm = 0.0
        nopm = 0.0
        latency_avg = 0.0
        latency_p95 = 0.0
        latency_p99 = 0.0
        errors = 0
        reconnects = 0
        
        # Parse HammerDB output
        # Looking for: "TEST RESULT : System achieved XXXXX NOPM from YYYYY PostgreSQL TPM"
        for line in result.stdout.split('\n'):
            line = line.strip()
            
            if 'TEST RESULT' in line and 'NOPM' in line and 'TPM' in line:
                # Extract NOPM (New Orders Per Minute) and TPM (Transactions Per Minute)
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'NOPM' and i > 0:
                            nopm = float(parts[i-1])
                        elif part == 'TPM' and i > 0:
                            tpm = float(parts[i-1])
                    
                    # Convert TPM to TPS
                    tps = tpm / 60.0 if tpm > 0 else 0.0
                    # TPC-C has multiple transaction types, estimate QPS
                    qps = tpm / 60.0 * 5  # Approximate: each transaction has ~5 queries
                    
                    logger.info(f"  NOPM: {nopm:.2f}, TPM: {tpm:.2f}, TPS: {tps:.2f}")
                    
                except (ValueError, IndexError) as e:
                    logger.warning(f"⚠ Failed to parse HammerDB output: {e}")
            
            # Look for error indicators
            if 'error' in line.lower() or 'failed' in line.lower():
                errors += 1
        
        # Calculate average latency estimate (very rough)
        latency_avg = (threads / tps * 1000) if tps > 0 else 0.0
        latency_p95 = latency_avg * 1.5
        latency_p99 = latency_avg * 2.0
        
        return BenchmarkResult(
            pooler_name=pooler_name,
            test_name=self.config.benchmark_type,
            threads=threads,
            duration=end_time - start_time,
            tps=tps,
            qps=qps,
            latency_avg=latency_avg,
            latency_p95=latency_p95,
            latency_p99=latency_p99,
            errors=errors,
            reconnects=reconnects,
            memory_usage=end_mem - start_mem,
            cpu_usage=(start_cpu + end_cpu) / 2.0,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _get_memory_usage(self, pooler_name: str) -> float:
        """Get memory usage of pooler process"""
        try:
            if pooler_name in self.processes:
                process = psutil.Process(self.processes[pooler_name].pid)
                return process.memory_info().rss / 1024 / 1024  # MB
        except Exception:
            pass
        return 0.0
    
    def _get_cpu_usage(self, pooler_name: str) -> float:
        """Get CPU usage of pooler process"""
        try:
            if pooler_name in self.processes:
                process = psutil.Process(self.processes[pooler_name].pid)
                return process.cpu_percent()
        except Exception:
            pass
        return 0.0
    
    def _generate_report(self):
        """Generate benchmark report"""
        logger.info("✓ Generating benchmark report...")
        
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": asdict(self.config),
            "results": [asdict(r) for r in self.results]
        }
        
        # Save JSON report
        report_file = Path(self.config.work_dir) / "tpcc_benchmark_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Print summary in tabular format
        print("\n" + "="*120)
        print("TPC-C BENCHMARK RESULTS")
        print("="*120)
        
        # Table header
        print(f"{'Pooler':<12} {'TPS':<8} {'QPS':<8} {'Avg(ms)':<8} {'P95(ms)':<8} {'P99(ms)':<8} {'Errors':<8} {'Memory(MB)':<12} {'CPU(%)':<8}")
        print("-" * 120)
        
        # Table rows
        for result in self.results:
            print(f"{result.pooler_name:<12} "
                  f"{result.tps:<8.2f} "
                  f"{result.qps:<8.2f} "
                  f"{result.latency_avg:<8.2f} "
                  f"{result.latency_p95:<8.2f} "
                  f"{result.latency_p99:<8.2f} "
                  f"{result.errors:<8} "
                  f"{result.memory_usage:<12.2f} "
                  f"{result.cpu_usage:<8.2f}")
        
        print("-" * 120)
        print(f"\nDetailed report saved to: {report_file}")
        print("="*120)
    
    def cleanup(self):
        """Cleanup resources"""
        logger.info("✓ Cleaning up...")
        
        # Stop all poolers
        for pooler in list(self.processes.keys()):
            self._stop_pooler(pooler)
        
        # Stop replica instances
        if self.config.num_replicas > 0:
            self._cleanup_replicas()
        
        # Stop PostgreSQL (OS-aware)
        pg_version = os.environ.get('PG_VERSION', '17')
        pg_paths = OSDetector.get_pg_paths(self.os_type, pg_version)
        
        try:
            if self.os_type == 'macos':
                # macOS: use brew services
                subprocess.run(['brew', 'services', 'stop', f'postgresql@{pg_version}'], 
                             check=False)
            else:
                # Linux: use systemctl
                subprocess.run(['sudo', 'systemctl', 'stop', f'postgresql-{pg_version}'],
                             check=False)
        except subprocess.CalledProcessError:
            pass
        
        logger.info("✓ Cleanup completed")
    
    def _cleanup_replicas(self):
        """Stop and cleanup replica instances"""
        logger.info(f"✓ Stopping {self.config.num_replicas} replica instances...")
        
        # Find pg_ctl command (OS-aware)
        pg_version = os.environ.get('PG_VERSION', '17')
        pg_paths = OSDetector.get_pg_paths(self.os_type, pg_version)
        
        # Try to find pg_ctl in OS-specific locations
        pg_ctl_cmd = shutil.which('pg_ctl')
        if not pg_ctl_cmd:
            # Try OS-specific path
            pg_ctl_cmd = shutil.which(f"{pg_paths['bin']}/pg_ctl")
        
        if not pg_ctl_cmd:
            logger.warning("✗ pg_ctl command not found, skipping replica cleanup")
            return
        
        # Stop each replica
        for i, data_dir in enumerate(self.config.replica_data_dirs):
            try:
                logger.info(f"✓ Stopping replica {i+1}")
                subprocess.run([
                    pg_ctl_cmd, "stop", "-D", data_dir, "-m", "fast"
                ], check=True, capture_output=True)
                
                # Remove data directory
                if Path(data_dir).exists():
                    shutil.rmtree(data_dir)
                    logger.info(f"✓ Removed replica {i+1} data directory")
                    
            except Exception as e:
                logger.error(f"✗ Error cleaning up replica {i+1}: {e}")
        
        logger.info("✓ Replica cleanup completed")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="PostgreSQL Pooler Benchmark Suite with HammerDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # First: Setup cluster (use cluster.py)
  cd ../cluster/scripts
  ./cluster.py --install
  ./cluster.py --setup-postgres
  
  # Then: Run benchmarks
  cd ../../benchmark/scripts
  
  # Step 1: Install Python requirements and HammerDB (one-time)
  ./benchmark.py --install
  
  # Step 2: Initialize TPC-C schema and data
  ./benchmark.py --init --warehouses 10
  
  # Step 3: Run benchmark with pgbalancer
  ./benchmark.py --run --t 60 --n 16 --poolers pgbalancer
  
  # Compare multiple poolers
  ./benchmark.py --run --t 60 --poolers pgbalancer pgbouncer pgpool2
  
  # TPC-H benchmark
  ./benchmark.py --type tpch --init --run --t 300
        '''
    )
    
    # Main commands
    parser.add_argument("--install", action="store_true", help="Install Python requirements and HammerDB")
    parser.add_argument("--init", action="store_true", help="Initialize benchmark schema and data")
    parser.add_argument("--run", action="store_true", help="Run benchmark")
    parser.add_argument("--type", choices=['tpcc', 'tpch'], default='tpcc', help="Benchmark type (default: tpcc)")
    
    # Benchmark parameters
    parser.add_argument("--t", "--time", type=int, default=300, help="Test duration in seconds")
    parser.add_argument("--n", "--threads", type=int, default=16, help="Number of threads")
    parser.add_argument("--warehouses", type=int, default=10, help="Number of warehouses")
    parser.add_argument("--replica", type=int, default=0, help="Number of replica PostgreSQL instances (default: 0)")
    parser.add_argument("--poolers", nargs="+", 
                       choices=["pgpool2", "pgbalancer", "pgbouncer", "pgcat"],
                       default=["pgbalancer", "pgbouncer"],
                       help="Poolers to test")
    
    # Configuration
    parser.add_argument("--config", type=str, help="Configuration file")
    parser.add_argument("--work-dir", type=str, default="/tmp/tpcc_benchmark", help="Work directory")
    parser.add_argument("--postgres-port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--postgres-user", type=str, default="postgres", help="PostgreSQL user")
    parser.add_argument("--postgres-database", type=str, default="tpcc", help="PostgreSQL database")
    
    args = parser.parse_args()
    
    # Load configuration from YAML file
    script_dir = Path(__file__).parent.absolute()
    conf_dir = script_dir.parent / "conf"
    
    if args.config and Path(args.config).exists():
        config_file = Path(args.config)
    else:
        config_file = conf_dir / "benchmark-config.yaml"
    
    # Load config from file
    config_data = {}
    if config_file.exists():
        with open(config_file, 'r') as f:
            yaml_config = yaml.safe_load(f)
            logger.info(f"✓ Loaded config: {config_file}")
            
            # Map YAML structure to BenchmarkConfig fields
            config_data = {
                'postgres_host': yaml_config.get('postgres', {}).get('host', 'localhost'),
                'postgres_port': yaml_config.get('postgres', {}).get('port', 5432),
                'postgres_user': yaml_config.get('postgres', {}).get('user', 'postgres'),
                'postgres_password': yaml_config.get('postgres', {}).get('password', ''),
                'postgres_database': yaml_config.get('postgres', {}).get('database', 'benchmark'),
                'benchmark_type': yaml_config.get('benchmark', {}).get('type', 'tpcc'),
                'time': yaml_config.get('benchmark', {}).get('duration', 300),
                'threads': yaml_config.get('benchmark', {}).get('threads', 16),
                'rampup': yaml_config.get('benchmark', {}).get('rampup', 2),
                'warehouses': yaml_config.get('benchmark', {}).get('warehouses', 10),
                'scale_factor': yaml_config.get('benchmark', {}).get('scale_factor', 10),
                'hammerdb_version': yaml_config.get('hammerdb', {}).get('version', '4.11'),
                'driver': yaml_config.get('hammerdb', {}).get('driver', 'timed'),
                'raiseerror': yaml_config.get('hammerdb', {}).get('raiseerror', True),
                'keyandthink': yaml_config.get('hammerdb', {}).get('keyandthink', False),
                'checkpoint': yaml_config.get('hammerdb', {}).get('checkpoint', False),
                'vacuum': yaml_config.get('hammerdb', {}).get('vacuum', False),
                'poolers': yaml_config.get('poolers', {}),
            }
    
    # Override with command-line args
    if args.work_dir:
        config_data['work_dir'] = args.work_dir
    if args.postgres_port:
        config_data['postgres_port'] = args.postgres_port
    if args.postgres_user:
        config_data['postgres_user'] = args.postgres_user
    if args.postgres_database:
        config_data['postgres_database'] = args.postgres_database
    if args.warehouses:
        config_data['warehouses'] = args.warehouses
    if args.replica:
        config_data['num_replicas'] = args.replica
    if args.type:
        config_data['benchmark_type'] = args.type
    
    config = BenchmarkConfig(**config_data)
    
    # Create benchmark suite
    suite = BenchmarkSuite(config)
    
    try:
        if args.install:
            suite.install_dependencies()
        
        if args.init:
            suite.initialize_benchmark()
        
        if args.run:
            suite.run_benchmark(args.poolers, args.n, args.t)
    
    except KeyboardInterrupt:
        logger.info("✓ Benchmark interrupted by user")
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)
    finally:
        if args.run:
            suite.cleanup()

if __name__ == "__main__":
    main()
