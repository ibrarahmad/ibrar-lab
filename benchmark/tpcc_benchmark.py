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
import tarfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
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
    work_dir: str = "/tmp/tpcc_benchmark"
    postgres_data_dir: str = "/tmp/tpcc_pgdata"
    sysbench_dir: str = "/tmp/sysbench"
    
    # PostgreSQL settings
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_database: str = "tpcc"
    
    # Pooler settings
    poolers: Dict[str, Dict[str, Any]] = None
    
    # TPC-C settings
    warehouses: int = 10
    scale_factor: float = 1.0
    
    # Benchmark settings
    threads: int = 16
    time: int = 300
    report_interval: int = 10
    
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
                    "port": 9998,
                    "config_file": "pgbalancer.yaml"
                },
                "pgbouncer": {
                    "enabled": True,
                    "port": 9997,
                    "config_file": "pgbouncer.ini"
                },
                "pgcat": {
                    "enabled": True,
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

class TPCCBenchmarkSuite:
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
        
        # Setup PostgreSQL
        self._setup_postgresql()
        
        # Setup poolers
        self._setup_poolers()
        
        logger.info("✓ Environment setup completed")
    
    def _setup_postgresql(self):
        """Setup PostgreSQL instance"""
        logger.info("✓ Setting up PostgreSQL...")
        
        # Initialize PostgreSQL data directory
        if not Path(self.config.postgres_data_dir).exists():
            subprocess.run([
                "sudo", "-u", "postgres", "/usr/pgsql-17/bin/initdb",
                "-D", self.config.postgres_data_dir,
                "-U", self.config.postgres_user
            ], check=True)
        
        # Configure PostgreSQL
        postgresql_conf = Path(self.config.postgres_data_dir) / "postgresql.conf"
        pg_hba_conf = Path(self.config.postgres_data_dir) / "pg_hba.conf"
        
        # Update postgresql.conf for performance
        with open(postgresql_conf, 'a') as f:
            f.write(f"""
# TPC-C Benchmark Configuration
listen_addresses = 'localhost'
port = {self.config.postgres_port}
max_connections = 200
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB
wal_level = replica
max_wal_senders = 3
max_replication_slots = 3
hot_standby = on
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
""")
        
        # Update pg_hba.conf for local connections
        with open(pg_hba_conf, 'a') as f:
            f.write("""
# TPC-C Benchmark Configuration
local   all             postgres                                trust
host    all             postgres        127.0.0.1/32            trust
host    all             postgres        ::1/128                 trust
""")
        
        # Start PostgreSQL
        subprocess.run([
            "sudo", "-u", "postgres", "/usr/pgsql-17/bin/pg_ctl",
            "-D", self.config.postgres_data_dir,
            "-l", str(Path(self.config.postgres_data_dir) / "postgresql.log"),
            "start"
        ], check=True)
        
        # Wait for PostgreSQL to start
        time.sleep(5)
        
        # Create database
        subprocess.run([
            "sudo", "-u", "postgres", "/usr/pgsql-17/bin/createdb",
            "-p", str(self.config.postgres_port),
            "-h", "localhost",
            self.config.postgres_database
        ], check=True)
        
        logger.info("✓ PostgreSQL setup completed")
    
    def _setup_poolers(self):
        """Setup pooler configurations"""
        logger.info("✓ Setting up pooler configurations...")
        
        # pgpool2 configuration
        pgpool2_conf = Path(self.config.work_dir) / "pgpool2.conf"
        with open(pgpool2_conf, 'w') as f:
            f.write(f"""
listen_addresses = 'localhost'
port = {self.config.poolers['pgpool2']['port']}
num_init_children = 32
max_pool = 4
backend_hostname0 = 'localhost'
backend_port0 = {self.config.postgres_port}
backend_weight0 = 1
""")
        
        # pgbalancer configuration
        pgbalancer_conf = Path(self.config.work_dir) / "pgbalancer.yaml"
        with open(pgbalancer_conf, 'w') as f:
            f.write(f"""
---
network:
  listen_addresses: localhost
  port: {self.config.poolers['pgbalancer']['port']}
  socket_dir: /tmp

connection_pool:
  num_init_children: 32
  max_pool: 4

authentication:
  enable_pool_hba: off

logging:
  destination: stderr
  pid_file_name: /tmp/pgbalancer_tpcc.pid

backends:
  - hostname: localhost
    port: {self.config.postgres_port}
    weight: 1
    flag: ALLOW_TO_FAILOVER
""")
        
        # pgbouncer configuration
        pgbouncer_conf = Path(self.config.work_dir) / "pgbouncer.ini"
        with open(pgbouncer_conf, 'w') as f:
            f.write(f"""
[databases]
{self.config.postgres_database} = host=localhost port={self.config.postgres_port} dbname={self.config.postgres_database}

[pgbouncer]
listen_addr = localhost
listen_port = {self.config.poolers['pgbouncer']['port']}
auth_type = trust
pool_mode = transaction
max_client_conn = 100
default_pool_size = 32
""")
        
        # pgcat configuration
        pgcat_conf = Path(self.config.work_dir) / "pgcat.toml"
        with open(pgcat_conf, 'w') as f:
            f.write(f"""
[shards]
0 = "host=localhost port={self.config.postgres_port} dbname={self.config.postgres_database}"

[shard]
0 = 0

[pool]
pool_mode = "Transaction"
max_client_conn = 100
default_pool_size = 32

[pgcat]
listen_addr = "0.0.0.0"
listen_port = {self.config.poolers['pgcat']['port']}
""")
        
        logger.info("✓ Pooler configurations created")
    
    def initialize_tpcc(self):
        """Initialize TPC-C schema and data"""
        logger.info("✓ === INITIALIZING TPC-C ===")
        
        # Create TPC-C schema
        self._create_tpcc_schema()
        
        # Generate TPC-C data
        self._generate_tpcc_data()
        
        logger.info("✓ TPC-C initialization completed")
    
    def _create_tpcc_schema(self):
        """Create TPC-C schema"""
        logger.info("✓ Creating TPC-C schema...")
        
        schema_sql = """
-- TPC-C Schema
CREATE TABLE warehouse (
    w_id INTEGER PRIMARY KEY,
    w_name VARCHAR(10),
    w_street_1 VARCHAR(20),
    w_street_2 VARCHAR(20),
    w_city VARCHAR(20),
    w_state CHAR(2),
    w_zip CHAR(9),
    w_tax DECIMAL(4,4),
    w_ytd DECIMAL(12,2)
);

CREATE TABLE district (
    d_id INTEGER,
    d_w_id INTEGER,
    d_name VARCHAR(10),
    d_street_1 VARCHAR(20),
    d_street_2 VARCHAR(20),
    d_city VARCHAR(20),
    d_state CHAR(2),
    d_zip CHAR(9),
    d_tax DECIMAL(4,4),
    d_ytd DECIMAL(12,2),
    d_next_o_id INTEGER,
    PRIMARY KEY (d_w_id, d_id)
);

CREATE TABLE customer (
    c_id INTEGER,
    c_d_id INTEGER,
    c_w_id INTEGER,
    c_first VARCHAR(16),
    c_middle CHAR(2),
    c_last VARCHAR(16),
    c_street_1 VARCHAR(20),
    c_street_2 VARCHAR(20),
    c_city VARCHAR(20),
    c_state CHAR(2),
    c_zip CHAR(9),
    c_phone CHAR(16),
    c_since TIMESTAMP,
    c_credit CHAR(2),
    c_credit_lim DECIMAL(12,2),
    c_discount DECIMAL(4,4),
    c_balance DECIMAL(12,2),
    c_ytd_payment DECIMAL(12,2),
    c_payment_cnt INTEGER,
    c_delivery_cnt INTEGER,
    c_data VARCHAR(500),
    PRIMARY KEY (c_w_id, c_d_id, c_id)
);

CREATE TABLE history (
    h_c_id INTEGER,
    h_c_d_id INTEGER,
    h_c_w_id INTEGER,
    h_d_id INTEGER,
    h_w_id INTEGER,
    h_date TIMESTAMP,
    h_amount DECIMAL(6,2),
    h_data VARCHAR(24)
);

CREATE TABLE new_order (
    no_o_id INTEGER,
    no_d_id INTEGER,
    no_w_id INTEGER,
    PRIMARY KEY (no_w_id, no_d_id, no_o_id)
);

CREATE TABLE orders (
    o_id INTEGER,
    o_d_id INTEGER,
    o_w_id INTEGER,
    o_c_id INTEGER,
    o_entry_d TIMESTAMP,
    o_carrier_id INTEGER,
    o_ol_cnt DECIMAL(2,0),
    o_all_local DECIMAL(1,0),
    PRIMARY KEY (o_w_id, o_d_id, o_id)
);

CREATE TABLE order_line (
    ol_o_id INTEGER,
    ol_d_id INTEGER,
    ol_w_id INTEGER,
    ol_number INTEGER,
    ol_i_id INTEGER,
    ol_supply_w_id INTEGER,
    ol_delivery_d TIMESTAMP,
    ol_quantity DECIMAL(2,0),
    ol_amount DECIMAL(6,2),
    ol_dist_info CHAR(24),
    PRIMARY KEY (ol_w_id, ol_d_id, ol_o_id, ol_number)
);

CREATE TABLE item (
    i_id INTEGER PRIMARY KEY,
    i_im_id INTEGER,
    i_name VARCHAR(24),
    i_price DECIMAL(5,2),
    i_data VARCHAR(50)
);

CREATE TABLE stock (
    s_i_id INTEGER,
    s_w_id INTEGER,
    s_quantity DECIMAL(4,0),
    s_dist_01 CHAR(24),
    s_dist_02 CHAR(24),
    s_dist_03 CHAR(24),
    s_dist_04 CHAR(24),
    s_dist_05 CHAR(24),
    s_dist_06 CHAR(24),
    s_dist_07 CHAR(24),
    s_dist_08 CHAR(24),
    s_dist_09 CHAR(24),
    s_dist_10 CHAR(24),
    s_ytd DECIMAL(8,0),
    s_order_cnt INTEGER,
    s_remote_cnt INTEGER,
    s_data VARCHAR(50),
    PRIMARY KEY (s_w_id, s_i_id)
);

-- Create indexes
CREATE INDEX idx_customer_name ON customer (c_w_id, c_d_id, c_last, c_first);
CREATE INDEX idx_orders_customer ON orders (o_w_id, o_d_id, o_c_id, o_id);
CREATE INDEX idx_order_line ON order_line (ol_supply_w_id, ol_i_id);
"""
        
        # Execute schema creation
        subprocess.run([
            "sudo", "-u", "postgres", "/usr/pgsql-17/bin/psql",
            "-p", str(self.config.postgres_port),
            "-h", "localhost",
            "-d", self.config.postgres_database,
            "-c", schema_sql
        ], check=True)
        
        logger.info("✓ TPC-C schema created")
    
    def _generate_tpcc_data(self):
        """Generate TPC-C test data using sysbench"""
        logger.info(f"Generating TPC-C data for {self.config.warehouses} warehouses...")
        
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
        
        logger.info("✓ TPC-C data generated")
    
    def run_benchmark(self, poolers: List[str], threads: int, time: int):
        """Run TPC-C benchmark"""
        logger.info("✓ === RUNNING TPC-C BENCHMARK ===")
        
        for pooler in poolers:
            if pooler not in self.config.poolers:
                logger.error(f"Unknown pooler: {pooler}")
                continue
            
            if not self.config.poolers[pooler]["enabled"]:
                logger.info(f"Skipping disabled pooler: {pooler}")
                continue
            
            logger.info(f"Testing {pooler}...")
            
            # Start pooler
            if not self._start_pooler(pooler):
                logger.error(f"Failed to start {pooler}")
                continue
            
            try:
                # Run benchmark
                result = self._run_tpcc_test(pooler, threads, time)
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
            if pooler_name == "pgpool2":
                cmd = ["pgpool", "-f", str(Path(self.config.work_dir) / "pgpool2.conf"), "-D"]
            elif pooler_name == "pgbalancer":
                cmd = ["/usr/local/bin/pgbalancer", "-f", str(Path(self.config.work_dir) / "pgbalancer.yaml"), "-D"]
            elif pooler_name == "pgbouncer":
                cmd = ["pgbouncer", "-d", str(Path(self.config.work_dir) / "pgbouncer.ini")]
            elif pooler_name == "pgcat":
                cmd = ["pgcat", str(Path(self.config.work_dir) / "pgcat.toml")]
            else:
                return False
            
            self.processes[pooler_name] = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            
            # Wait for pooler to start
            time.sleep(3)
            
            # Check if pooler is accepting connections
            return self._check_pooler_connection(pooler_name)
            
        except Exception as e:
            logger.error(f"Failed to start {pooler_name}: {e}")
            return False
    
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
    
    def _run_tpcc_test(self, pooler_name: str, threads: int, time: int) -> BenchmarkResult:
        """Run TPC-C test for a specific pooler"""
        port = self.config.poolers[pooler_name]["port"]
        
        # Run sysbench TPC-C test with proper parameters
        cmd = [
            "sysbench", "tpcc",
            f"--pgsql-host=localhost",
            f"--pgsql-port={port}",
            f"--pgsql-user={self.config.postgres_user}",
            f"--pgsql-db={self.config.postgres_database}",
            f"--warehouses={self.config.warehouses}",
            f"--threads={threads}",
            f"--time={time}",
            f"--report-interval={self.config.report_interval}",
            "--percentile=95",
            "--histogram=on",
            "run"
        ]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = time.time()
        
        # Parse results
        tps = 0.0
        qps = 0.0
        latency_avg = 0.0
        latency_p95 = 0.0
        latency_p99 = 0.0
        errors = 0
        reconnects = 0
        
        # Parse sysbench output
        for line in result.stdout.split('\n'):
            if 'tps:' in line:
                try:
                    tps = float(line.split('tps:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
            elif 'qps:' in line:
                try:
                    qps = float(line.split('qps:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
            elif 'avg:' in line and 'latency' in line:
                try:
                    latency_avg = float(line.split('avg:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
            elif '95th percentile:' in line:
                try:
                    latency_p95 = float(line.split('95th percentile:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
            elif '99th percentile:' in line:
                try:
                    latency_p99 = float(line.split('99th percentile:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
            elif 'errors:' in line:
                try:
                    errors = int(line.split('errors:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
            elif 'reconnects:' in line:
                try:
                    reconnects = int(line.split('reconnects:')[1].split()[0])
                except (IndexError, ValueError):
                    pass
        
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

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Modular TPC-C Benchmark Suite")
    
    # Main commands
    parser.add_argument("--install", action="store_true", help="Install all dependencies")
    parser.add_argument("--setup", action="store_true", help="Setup PostgreSQL and poolers")
    parser.add_argument("--init", action="store_true", help="Initialize TPC-C schema and data")
    parser.add_argument("--run", action="store_true", help="Run benchmark")
    
    # Benchmark parameters
    parser.add_argument("--t", "--time", type=int, default=300, help="Test duration in seconds")
    parser.add_argument("--n", "--threads", type=int, default=16, help="Number of threads")
    parser.add_argument("--warehouses", type=int, default=10, help="Number of warehouses")
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
            warehouses=args.warehouses
        )
    
    # Create benchmark suite
    suite = TPCCBenchmarkSuite(config)
    
    try:
        if args.install:
            suite.install_dependencies()
        
        if args.setup:
            suite.setup_environment()
        
        if args.init:
            suite.initialize_tpcc()
        
        if args.run:
            suite.run_benchmark(args.poolers, args.threads, args.t)
    
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
