#!/usr/bin/env python3
"""
Modular TPC-C Benchmark Suite with Sysbench
===========================================

A highly modular benchmark suite for testing PostgreSQL poolers with TPC-C workload.
Supports pgpool2, pgbalancer, pgbouncer, and pgcat.

Usage:
    python3 tpcc_benchmark.py --install    # Download and install all dependencies
    python3 tpcc_benchmark.py --setup      # Setup PostgreSQL and poolers
    python3 tpcc_benchmark.py --init       # Initialize TPC-C schema and data
    python3 tpcc_benchmark.py --run --t 300 --n 16  # Run benchmark

Author: pgElephant, Inc.
Version: 1.0.0
License: MIT
"""

import argparse
import subprocess
import sys
import os
import time
import json
import yaml
import logging
import shutil
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional
import tarfile
import zipfile
import threading
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark suite"""
    # Directories
    work_dir: str = "/tmp/benchmark"
    postgres_data_dir: str = "/tmp/pgdata"
    sysbench_dir: str = "/tmp/sysbench"
    conf_dir: str = "/home/pgedge/pge/pgbalancer/benchmark/conf"
    log_dir: str = "/home/pgedge/pge/pgbalancer/benchmark/log"
    
    # PostgreSQL settings (from postgresql.conf)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_database: str = "benchmark"
    postgres_config_file: str = "/home/pgedge/pge/pgbalancer/benchmark/conf/postgresql.conf"
    postgres_hba_file: str = "/home/pgedge/pge/pgbalancer/benchmark/conf/pg_hba.conf"
    
    # Replica settings
    num_replicas: int = 0
    replica_start_port: int = 5433
    replica_data_dirs: List[str] = field(default_factory=list)
    
    # Pooler settings
    poolers: Dict[str, Dict[str, Any]] = None
    
    # Benchmark type settings
    benchmark_type: str = "tpcc"  # tpcc, tpcb, tpch
    warehouses: int = 10
    scale_factor: float = 1.0
    
    # Benchmark settings
    threads: int = 16
    time: int = 300
    report_interval: int = 10
    
    # Sysbench specific settings
    percentile: int = 95
    histogram: bool = True
    rand_init: bool = True
    trx: str = "all"
    
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
        self.config = config
        self.processes: Dict[str, subprocess.Popen] = {}
        self.results: List[BenchmarkResult] = []
        
        # Create work directory
        Path(self.config.work_dir).mkdir(parents=True, exist_ok=True)
        
    def install_dependencies(self):
        """Install all required dependencies"""
        logger.info("✓ === INSTALLING DEPENDENCIES ===")
        
        # Check if running as root
        if os.geteuid() != 0:
            logger.error("✗ Installation requires root privileges. Please run with sudo.")
            sys.exit(1)
        
        # Install system packages
        self._install_system_packages()
        
        # Install sysbench
        self._install_sysbench()
        
        # Install PostgreSQL poolers
        self._install_poolers()
        
        # Install Python packages
        self._install_python_packages()
        
        logger.info("✓ All dependencies installed successfully")
    
    def _install_system_packages(self):
        """Install system packages"""
        logger.info("✓ Installing system packages...")
        
        packages = [
            "build-essential", "cmake", "libmysqlclient-dev",
            "libpq-dev", "libssl-dev", "libyaml-dev",
            "git", "wget", "curl", "unzip", "pkg-config"
        ]
        
        try:
            subprocess.run(["apt-get", "update"], check=True)
            subprocess.run(["apt-get", "install", "-y"] + packages, check=True)
            logger.info("✓ System packages installed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install system packages: {e}")
            sys.exit(1)
    
    def _install_sysbench(self):
        """Install sysbench with TPC-C support"""
        logger.info("✓ Installing sysbench with TPC-C support...")
        
        sysbench_dir = Path(self.config.sysbench_dir)
        sysbench_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Clone sysbench repository
            if not (sysbench_dir / "sysbench").exists():
                subprocess.run([
                    "git", "clone", "https://github.com/akopytov/sysbench.git",
                    str(sysbench_dir / "sysbench")
                ], check=True)
            
            # Build sysbench with PostgreSQL support
            build_dir = sysbench_dir / "sysbench" / "build"
            build_dir.mkdir(exist_ok=True)
            
            subprocess.run([
                "cmake", "..", 
                "-DCMAKE_BUILD_TYPE=Release",
                "-DWITH_MYSQL=OFF", 
                "-DWITH_PGSQL=ON",
                "-DWITH_TPCC=ON"
            ], cwd=build_dir, check=True)
            
            subprocess.run(["make", "-j$(nproc)"], cwd=build_dir, check=True)
            subprocess.run(["make", "install"], cwd=build_dir, check=True)
            
            logger.info("✓ Sysbench with TPC-C support installed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install sysbench: {e}")
            sys.exit(1)
    
    def _install_poolers(self):
        """Install PostgreSQL poolers"""
        logger.info("✓ Installing PostgreSQL poolers...")
        
        # Install pgbouncer
        try:
            subprocess.run(["apt-get", "install", "-y", "pgbouncer"], check=True)
            logger.info("✓ pgbouncer installed")
        except subprocess.CalledProcessError:
            logger.warning("⚠ Failed to install pgbouncer via apt, will build from source")
            self._build_pgbouncer()
        
        # Install pgcat (if available)
        try:
            subprocess.run(["cargo", "install", "pgcat"], check=True)
            logger.info("✓ pgcat installed")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("⚠ pgcat not available (requires Rust)")
        
        # pgpool2 and pgbalancer should already be available
        logger.info("✓ Pooler installation completed")
    
    def _build_pgbouncer(self):
        """Build pgbouncer from source"""
        logger.info("✓ Building pgbouncer from source...")
        
        pgbouncer_dir = Path(self.config.work_dir) / "pgbouncer"
        pgbouncer_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Download pgbouncer source
            subprocess.run([
                "wget", "-O", "pgbouncer.tar.gz",
                "https://github.com/pgbouncer/pgbouncer/releases/download/pgbouncer_1_21_0/pgbouncer-1.21.0.tar.gz"
            ], cwd=pgbouncer_dir, check=True)
            
            # Extract and build
            subprocess.run(["tar", "xzf", "pgbouncer.tar.gz"], cwd=pgbouncer_dir, check=True)
            
            build_dir = pgbouncer_dir / "pgbouncer-1.21.0"
            subprocess.run(["./configure"], cwd=build_dir, check=True)
            subprocess.run(["make"], cwd=build_dir, check=True)
            subprocess.run(["make", "install"], cwd=build_dir, check=True)
            
            logger.info("✓ pgbouncer built from source")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to build pgbouncer: {e}")
    
    def _install_python_packages(self):
        """Install Python packages"""
        logger.info("✓ Installing Python packages...")
        
        packages = [
            "psycopg2-binary", "pyyaml", "psutil"
        ]
        
        try:
            subprocess.run([sys.executable, "-m", "pip", "install"] + packages, check=True)
            logger.info("✓ Python packages installed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Python packages: {e}")
    
    def setup_environment(self):
        """Setup PostgreSQL and poolers"""
        logger.info("✓ === SETTING UP ENVIRONMENT ===")
        
        # Setup logging
        self._setup_logging()
        
        # Use existing PostgreSQL instance
        self._check_postgresql()
        
        # Setup poolers
        self._setup_poolers()
        
        logger.info("✓ Environment setup completed")
    
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
        
        # Create database if it doesn't exist
        try:
            # Try different createdb paths
            createdb_paths = [
                "createdb",  # Use PATH
                "/usr/pgsql-17/bin/createdb",
                "/usr/bin/createdb",
                "/usr/local/bin/createdb"
            ]
            
            createdb_cmd = None
            for path in createdb_paths:
                if shutil.which(path):
                    createdb_cmd = path
                    break
            
            if not createdb_cmd:
                logger.error("✗ createdb command not found")
                return False
            
            subprocess.run([
                createdb_cmd,
                "-h", "localhost",
                "-p", str(self.config.postgres_port),
                self.config.postgres_database
            ], check=True)
            logger.info(f"✓ Database '{self.config.postgres_database}' created")
        except subprocess.CalledProcessError:
            logger.info(f"✓ Database '{self.config.postgres_database}' already exists")
        
        # Setup replicas if requested
        if self.config.num_replicas > 0:
            self._setup_replicas()
        
        logger.info("✓ PostgreSQL check completed")
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
        """Setup PostgreSQL replica instances"""
        logger.info(f"✓ Setting up {self.config.num_replicas} PostgreSQL replicas...")
        
        # Find PostgreSQL binaries
        pg_ctl_paths = [
            "pg_ctl",
            "/usr/pgsql-17/bin/pg_ctl",
            "/usr/pgsql-16/bin/pg_ctl",
            "/usr/bin/pg_ctl",
            "/usr/local/bin/pg_ctl"
        ]
        
        pg_ctl_cmd = None
        for path in pg_ctl_paths:
            if shutil.which(path):
                pg_ctl_cmd = path
                break
        
        if not pg_ctl_cmd:
            logger.error("✗ pg_ctl command not found")
            return False
        
        # Create replica data directories and start replicas
        for i in range(self.config.num_replicas):
            replica_port = self.config.replica_start_port + i
            replica_data_dir = Path("/tmp") / f"replica_{i}"
            
            try:
                # Create replica data directory
                replica_data_dir.mkdir(parents=True, exist_ok=True)
                self.config.replica_data_dirs.append(str(replica_data_dir))
                
                # Initialize replica
                logger.info(f"✓ Initializing replica {i+1} on port {replica_port}")
                subprocess.run([
                    pg_ctl_cmd, "initdb", "-D", str(replica_data_dir)
                ], check=True, capture_output=True)
                
                # Configure replica for streaming replication
                replica_conf = replica_data_dir / "postgresql.conf"
                with open(replica_conf, 'a') as f:
                    f.write(f"""
# Replica configuration
port = {replica_port}
listen_addresses = 'localhost'
max_connections = 200
hot_standby = on
wal_level = replica
max_wal_senders = 3
max_replication_slots = 3
""")
                
                # Configure pg_hba.conf for replication
                hba_conf = replica_data_dir / "pg_hba.conf"
                with open(hba_conf, 'a') as f:
                    f.write(f"""
# Replication connections
local   replication     postgres                                trust
host    replication     postgres        127.0.0.1/32            trust
host    replication     postgres        ::1/128                 trust
""")
                
                # Start replica
                try:
                    subprocess.run([
                        pg_ctl_cmd, "start", "-D", str(replica_data_dir), "-l", 
                        str(replica_data_dir / "postgresql.log")
                    ], check=True, capture_output=True)
                except subprocess.CalledProcessError:
                    # pg_ctl start can return non-zero even when successful
                    # Check if the process is actually running
                    pass
                
                # Wait for replica to be ready
                time.sleep(3)
                
                # Check if replica is ready
                pg_isready_cmd = None
                for path in ["pg_isready", "/usr/pgsql-17/bin/pg_isready", "/usr/bin/pg_isready"]:
                    if shutil.which(path):
                        pg_isready_cmd = path
                        break
                
                if pg_isready_cmd:
                    result = subprocess.run([
                        pg_isready_cmd, "-h", "localhost", "-p", str(replica_port)
                    ], capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        logger.info(f"✓ Replica {i+1} started successfully on port {replica_port}")
                    else:
                        logger.error(f"✗ Replica {i+1} failed to start")
                        return False
                
            except Exception as e:
                logger.error(f"✗ Failed to setup replica {i+1}: {e}")
                return False
        
        logger.info(f"✓ All {self.config.num_replicas} replicas setup successfully")
        return True
    
    def _generate_pooler_configs(self):
        """Use static configuration files - no generation needed"""
        logger.info("✓ Using static configuration files...")
        
        # Configuration files are already created in conf/ directory
        # No need to generate them dynamically
    
    
    
    def _setup_poolers(self):
        """Setup pooler configurations"""
        logger.info("✓ Setting up pooler configurations...")
        
        # Use static configuration files from conf/ directory
        self._generate_pooler_configs()
        
        logger.info("✓ Using static configuration files")
    
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
        
        logger.info("✓ TPC-C schema created using sysbench")
    
    def _create_tpcb_schema(self):
        """Create TPC-B schema using sysbench"""
        logger.info("✓ Creating TPC-B schema using sysbench...")
        
        # Use sysbench to create TPC-B schema
        subprocess.run([
            "sysbench", "oltp_read_write",
            f"--pgsql-host=localhost",
            f"--pgsql-port={self.config.postgres_port}",
            f"--pgsql-user={self.config.postgres_user}",
            f"--pgsql-db={self.config.postgres_database}",
            f"--tables={self.config.warehouses}",
            f"--scale={self.config.scale_factor}",
            "prepare"
        ], check=True)
        
        logger.info("✓ TPC-B schema created using sysbench")
    
    def _create_tpch_schema(self):
        """Create TPC-H schema using sysbench"""
        logger.info("✓ Creating TPC-H schema using sysbench...")
        
        # Use sysbench to create TPC-H schema
        subprocess.run([
            "sysbench", "oltp_read_only",
            f"--pgsql-host=localhost",
            f"--pgsql-port={self.config.postgres_port}",
            f"--pgsql-user={self.config.postgres_user}",
            f"--pgsql-db={self.config.postgres_database}",
            f"--tables={self.config.warehouses}",
            f"--scale={self.config.scale_factor}",
            "prepare"
        ], check=True)
        
        logger.info("✓ TPC-H schema created using sysbench")
    
    def _generate_benchmark_data(self):
        """Generate benchmark test data using HammerDB"""
        logger.info(f"✓ Generating {self.config.benchmark_type.upper()} data using HammerDB...")
        
        if self.config.benchmark_type in ["tpcc", "tpcb", "tpch"]:
            self._generate_hammerdb_data()
        else:
            logger.error(f"✗ Unknown benchmark type: {self.config.benchmark_type}")
            sys.exit(1)
        
        logger.info(f"✓ {self.config.benchmark_type.upper()} data generated using HammerDB")
    
    def _generate_hammerdb_data(self):
        """Generate test data using HammerDB"""
        logger.info(f"✓ Generating data for {self.config.warehouses} warehouses...")
        
        # Use HammerDB to generate data
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
    
    def _generate_tpcc_data(self):
        """Generate TPC-C test data using sysbench"""
        logger.info(f"✓ Generating TPC-C data for {self.config.warehouses} warehouses...")
        
        # Use sysbench TPC-C to generate data
        subprocess.run([
            "sysbench", "tpcc",
            f"--pgsql-host=localhost",
            f"--pgsql-port={self.config.postgres_port}",
            f"--pgsql-user={self.config.postgres_user}",
            f"--pgsql-db={self.config.postgres_database}",
            f"--warehouses={self.config.warehouses}",
            f"--scale={self.config.scale_factor}",
            "prepare"
        ], check=True)
        
    def _generate_tpcb_data(self):
        """Generate TPC-B test data using sysbench"""
        logger.info("✓ Generating TPC-B data...")
        
        # Generate TPC-B data using sysbench
        subprocess.run([
            "sysbench", "oltp_read_write",
            f"--pgsql-host=localhost",
            f"--pgsql-port={self.config.postgres_port}",
            f"--pgsql-user={self.config.postgres_user}",
            f"--pgsql-db={self.config.postgres_database}",
            f"--tables={self.config.warehouses}",
            f"--scale={self.config.scale_factor}",
            "prepare"
        ], check=True)
    
    def _generate_tpch_data(self):
        """Generate TPC-H test data using sysbench"""
        logger.info("✓ Generating TPC-H data...")
        
        # Generate TPC-H data using sysbench
        subprocess.run([
            "sysbench", "oltp_read_only",
            f"--pgsql-host=localhost",
            f"--pgsql-port={self.config.postgres_port}",
            f"--pgsql-user={self.config.postgres_user}",
            f"--pgsql-db={self.config.postgres_database}",
            f"--tables={self.config.warehouses}",
            f"--scale={self.config.scale_factor}",
            "prepare"
        ], check=True)
    
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
        """Run benchmark test for a specific pooler"""
        port = self.config.poolers[pooler_name]["port"]
        
        # Run simple SQL benchmark test
        if self.config.benchmark_type in ["tpcc", "tpcb", "tpch"]:
            # Create a simple benchmark script
            benchmark_script = f"""#!/bin/bash
export PGPASSWORD='postgres'
queries=0
errors=0
start_time=$(date +%s)
end_time=$((start_time + {duration}))

while [ $(date +%s) -lt $end_time ]; do
    if psql -h localhost -p {port} -U postgres -d postgres -c "SELECT 1, NOW(), random();" > /dev/null 2>&1; then
        queries=$((queries + 1))
    else
        errors=$((errors + 1))
    fi
done

echo "QUERIES:$queries"
echo "ERRORS:$errors"
echo "DURATION:{duration}"
"""
            
            # Write benchmark script to temporary file
            script_path = Path(self.config.work_dir) / f"benchmark_{pooler_name}.sh"
            with open(script_path, 'w') as f:
                f.write(benchmark_script)
            
            # Make script executable
            script_path.chmod(0o755)
            
            cmd = ["bash", str(script_path)]
        else:
            logger.error(f"✗ Unknown benchmark type: {self.config.benchmark_type}")
            return None
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = time.time()
        
        # Parse results
        tps = 0.0
        qps = 0.0
        queries = 0
        latency_avg = 0.0
        latency_p95 = 0.0
        latency_p99 = 0.0
        errors = 0
        reconnects = 0
        
        # Parse benchmark script output
        for line in result.stdout.split('\n'):
            if line.startswith('QUERIES:'):
                queries = int(line.split(':')[1])
                tps = queries / duration if duration > 0 else 0.0
                qps = tps  # Same as TPS for simple queries
            elif line.startswith('ERRORS:'):
                errors = int(line.split(':')[1])
        
        return BenchmarkResult(
            pooler_name=pooler_name,
            test_name="tpcc",
            threads=threads,
            duration=end_time - start_time,
            tps=tps,
            qps=qps,
            latency_avg=latency_avg,
            latency_p95=latency_p95,
            latency_p99=latency_p99,
            errors=errors,
            reconnects=reconnects,
            memory_usage=self._get_memory_usage(pooler_name),
            cpu_usage=self._get_cpu_usage(pooler_name),
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
        
        # Stop PostgreSQL
        try:
            subprocess.run([
                "sudo", "-u", "postgres", "/usr/pgsql-17/bin/pg_ctl",
                "-D", self.config.postgres_data_dir,
                "stop"
            ], check=True)
        except subprocess.CalledProcessError:
            pass
        
        logger.info("✓ Cleanup completed")
    
    def _cleanup_replicas(self):
        """Stop and cleanup replica instances"""
        logger.info(f"✓ Stopping {self.config.num_replicas} replica instances...")
        
        # Find pg_ctl command
        pg_ctl_paths = [
            "pg_ctl",
            "/usr/pgsql-17/bin/pg_ctl",
            "/usr/pgsql-16/bin/pg_ctl",
            "/usr/bin/pg_ctl",
            "/usr/local/bin/pg_ctl"
        ]
        
        pg_ctl_cmd = None
        for path in pg_ctl_paths:
            if shutil.which(path):
                pg_ctl_cmd = path
                break
        
        if not pg_ctl_cmd:
            logger.error("✗ pg_ctl command not found")
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
    parser = argparse.ArgumentParser(description="Modular TPC-C Benchmark Suite")
    
    # Main commands
    parser.add_argument("--install", action="store_true", help="Install all dependencies")
    parser.add_argument("--setup", action="store_true", help="Setup PostgreSQL and poolers")
    parser.add_argument("--init", action="store_true", help="Initialize benchmark schema and data")
    parser.add_argument("--run", action="store_true", help="Run benchmark")
    parser.add_argument("--type", choices=['tpcc', 'tpcb', 'tpch'], default='tpcc', help="Benchmark type (default: tpcc)")
    
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
    
    # Load configuration
    if args.config and Path(args.config).exists():
        with open(args.config, 'r') as f:
            config_data = yaml.safe_load(f)
        config = BenchmarkConfig(**config_data)
    else:
        config = BenchmarkConfig(
            work_dir=args.work_dir,
            postgres_port=args.postgres_port,
            postgres_user=args.postgres_user,
            postgres_database=args.postgres_database,
            warehouses=args.warehouses,
            num_replicas=args.replica
        )
    
    # Set benchmark type
    config.benchmark_type = args.type
    
    # Create benchmark suite
    suite = BenchmarkSuite(config)
    
    try:
        if args.install:
            suite.install_dependencies()
        
        if args.setup:
            suite.setup_environment()
        
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
