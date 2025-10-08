# Modular TPC-C Benchmark Suite

A highly modular benchmark suite for testing PostgreSQL poolers with TPC-C workload using sysbench.

## Features

- **Highly Modular**: Separate commands for install, setup, init, and run
- **TPC-C Workload**: Industry-standard OLTP benchmark
- **Multi-Pooler Support**: pgpool2, pgbalancer, pgbouncer, pgcat
- **Sysbench Integration**: Uses sysbench for accurate TPC-C testing
- **Comprehensive Metrics**: TPS, QPS, latency, errors, memory, CPU
- **Configurable**: YAML configuration with all parameters
- **Automated Setup**: One-command installation and setup

## Quick Start

### 1. Install Dependencies
```bash
sudo ./run_tpcc_benchmark.sh --install
```

### 2. Setup Environment
```bash
./run_tpcc_benchmark.sh --setup
```

### 3. Initialize TPC-C
```bash
./run_tpcc_benchmark.sh --init
```

### 4. Run Benchmark
```bash
./run_tpcc_benchmark.sh --run --t 300 --n 16
```

## Commands

### --install
Downloads and installs all required dependencies:
- System packages (build tools, libraries)
- Sysbench (built from source with PostgreSQL support)
- PostgreSQL poolers (pgbouncer, pgcat)
- Python packages (psycopg2, pyyaml, psutil)

**Requires:** Root privileges (sudo)

### --setup
Sets up the complete environment:
- PostgreSQL instance with optimized configuration
- Pooler configurations (pgpool2, pgbalancer, pgbouncer, pgcat)
- Database creation and user setup

### --init
Initializes TPC-C schema and data:
- Creates TPC-C tables (warehouse, district, customer, etc.)
- Generates test data using sysbench
- Configurable number of warehouses

### --run
Runs the TPC-C benchmark with configurable parameters:

**Options:**
- `--t, --time SECONDS`: Test duration (default: 300)
- `--n, --threads NUM`: Number of threads (default: 16)
- `--w, --warehouses NUM`: Number of warehouses (default: 10)
- `--p, --poolers LIST`: Poolers to test (default: pgbalancer pgbouncer)

**Examples:**
```bash
# 5-minute test with 32 threads
./run_tpcc_benchmark.sh --run --t 300 --n 32

# Test specific poolers
./run_tpcc_benchmark.sh --run --p "pgbalancer pgbouncer pgpool2"

# 20 warehouses, 10 minutes, 16 threads
./run_tpcc_benchmark.sh --run --w 20 --t 600 --n 16
```

### --cleanup
Cleans up all resources:
- Stops all pooler processes
- Stops PostgreSQL
- Removes temporary directories

### --status
Shows current status of the benchmark suite:
- Configuration files
- PostgreSQL status
- Available poolers
- Sysbench availability

## Configuration

### tpcc_config.yaml
```yaml
# Directories
work_dir: "/tmp/tpcc_benchmark"
postgres_data_dir: "/tmp/tpcc_pgdata"
sysbench_dir: "/tmp/sysbench"

# PostgreSQL settings
postgres_port: 5432
postgres_user: "postgres"
postgres_password: ""
postgres_database: "tpcc"

# Pooler configurations
poolers:
  pgpool2:
    enabled: true
    port: 9999
  pgbalancer:
    enabled: true
    port: 9998
  pgbouncer:
    enabled: true
    port: 9997
  pgcat:
    enabled: false  # Requires Rust
    port: 9996

# TPC-C settings
warehouses: 10
scale_factor: 1.0

# Benchmark settings
threads: 16
time: 300
report_interval: 10
```

## TPC-C Schema

The benchmark creates the standard TPC-C schema:

- **warehouse**: Warehouse information
- **district**: District information
- **customer**: Customer data
- **history**: Transaction history
- **new_order**: New order tracking
- **orders**: Order information
- **order_line**: Order line items
- **item**: Item catalog
- **stock**: Stock levels

## Metrics

### Performance Metrics
- **TPS**: Transactions per second
- **QPS**: Queries per second
- **Latency**: Average, 95th percentile, 99th percentile
- **Errors**: Number of failed transactions
- **Reconnects**: Connection reconnection count

### Resource Metrics
- **Memory Usage**: RAM consumption per pooler
- **CPU Usage**: CPU utilization per pooler

## Output

### Console Output
```
TPC-C BENCHMARK RESULTS
================================================================================

PGBALANCER:
  TPS: 1250.50
  QPS: 6250.25
  Avg Latency: 12.80ms
  95th Percentile: 25.60ms
  99th Percentile: 45.20ms
  Errors: 0
  Memory: 45.20MB
  CPU: 15.30%

PGBOUNCER:
  TPS: 1180.75
  QPS: 5903.75
  Avg Latency: 13.50ms
  95th Percentile: 27.00ms
  99th Percentile: 48.50ms
  Errors: 0
  Memory: 12.80MB
  CPU: 12.40%
```

### JSON Report
Detailed results saved to `/tmp/tpcc_benchmark/tpcc_benchmark_report.json`:

```json
{
  "timestamp": "2025-10-07 18:30:00",
  "config": {
    "warehouses": 10,
    "threads": 16,
    "time": 300
  },
  "results": [
    {
      "pooler_name": "pgbalancer",
      "test_name": "tpcc",
      "threads": 16,
      "duration": 300.5,
      "tps": 1250.50,
      "qps": 6250.25,
      "latency_avg": 12.80,
      "latency_p95": 25.60,
      "latency_p99": 45.20,
      "errors": 0,
      "reconnects": 0,
      "memory_usage": 45.20,
      "cpu_usage": 15.30,
      "timestamp": "2025-10-07 18:30:00"
    }
  ]
}
```

## Pooler Configurations

### pgbalancer
```yaml
---
network:
  listen_addresses: localhost
  port: 9998

connection_pool:
  num_init_children: 32
  max_pool: 4

backends:
  - hostname: localhost
    port: 5432
    weight: 1
    flag: ALLOW_TO_FAILOVER
```

### pgbouncer
```ini
[databases]
tpcc = host=localhost port=5432 dbname=tpcc

[pgbouncer]
listen_addr = localhost
listen_port = 9997
pool_mode = transaction
max_client_conn = 100
default_pool_size = 32
```

### pgpool2
```conf
listen_addresses = 'localhost'
port = 9999
num_init_children = 32
max_pool = 4
backend_hostname0 = 'localhost'
backend_port0 = 5432
backend_weight0 = 1
```

## Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   sudo ./run_tpcc_benchmark.sh --install
   ```

2. **PostgreSQL Not Starting**
   ```bash
   # Check if port is in use
   netstat -tlnp | grep 5432
   
   # Check PostgreSQL logs
   tail -f /tmp/tpcc_pgdata/postgresql.log
   ```

3. **Pooler Connection Failed**
   ```bash
   # Check pooler configuration
   cat /tmp/tpcc_benchmark/pgbalancer.yaml
   
   # Check if pooler is running
   ps aux | grep pgbalancer
   ```

4. **Sysbench Not Found**
   ```bash
   # Reinstall sysbench
   sudo ./run_tpcc_benchmark.sh --install
   ```

### Debug Mode
```bash
# Enable debug logging
export PYTHONPATH=.
python3 -c "import logging; logging.basicConfig(level=logging.DEBUG)"
./run_tpcc_benchmark.sh --run --t 60 --n 4
```

## Performance Tuning

### PostgreSQL Tuning
The benchmark automatically configures PostgreSQL for performance:
- `shared_buffers = 256MB`
- `effective_cache_size = 1GB`
- `work_mem = 4MB`
- `maintenance_work_mem = 64MB`
- `checkpoint_completion_target = 0.9`

### Pooler Tuning
- **Connection Pool Size**: Adjust `max_pool` and `num_init_children`
- **Thread Count**: Match `--threads` to pooler capacity
- **Warehouse Count**: Scale `--warehouses` based on available memory

## Best Practices

1. **Warm-up**: Run short tests before long benchmarks
2. **Consistent Environment**: Use same hardware and PostgreSQL version
3. **Resource Monitoring**: Monitor CPU, memory, and I/O during tests
4. **Multiple Runs**: Run tests multiple times for accuracy
5. **Clean State**: Use `--cleanup` between test runs

## Requirements

### System Requirements
- Linux (Ubuntu/Debian recommended)
- 4GB+ RAM
- 10GB+ disk space
- Root privileges for installation

### Software Requirements
- Python 3.7+
- PostgreSQL 12+
- Build tools (gcc, cmake, make)
- Git

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: [Repository Issues]
- Documentation: [Project Documentation]
- Email: support@pgelephant.com
