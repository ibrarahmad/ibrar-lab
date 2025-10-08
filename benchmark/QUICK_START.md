# pgbalancer Benchmark Quick Start Guide

## 📋 Summary

This benchmark suite provides:
- **Ansible automated setup** for easy deployment
- **TPC-C benchmark** for OLTP workload testing  
- **Multiple pooler support** (pgbalancer, pgbouncer, pgpool2, pgcat)
- **Comprehensive metrics** (QPS, latency, CPU, memory)
- **Integrated cluster setup** - Single command to setup entire cluster with Ansible

## 🚀 Quick Setup - ONE COMMAND!

### Full Setup + Benchmark (Easiest!)
```bash
cd /home/pgedge/pge/benchmark

# Setup entire cluster and run benchmark in one command!
./run-with-ansible.sh --full-benchmark --duration 60 --threads 16
```

This does EVERYTHING:
- ✅ Installs PostgreSQL 13 with Ansible
- ✅ Installs Python dependencies
- ✅ Builds pgbalancer
- ✅ Starts pgbalancer
- ✅ Initializes benchmark data
- ✅ Runs TPC-C benchmark
- ✅ Shows results

## 📊 Alternative: Step by Step

### 1. Setup Cluster with Ansible
```bash
cd /home/pgedge/pge/benchmark
./run-with-ansible.sh --setup-cluster
```

### 2. Run Benchmark
```bash
./run-with-ansible.sh --run-benchmark --poolers pgbalancer --duration 60
```

### 3. Or Use Python Directly
```bash
# Initialize data
python3 benchmark.py --init --warehouses 10

# Run benchmark
python3 benchmark.py --run --t 60 --n 16 --poolers pgbalancer
```

## 🎯 Integrated Cluster Setup Commands

### Full Workflow (Recommended)
```bash
# Complete setup + benchmark in one command
./run-with-ansible.sh --full-benchmark --duration 60 --threads 16 --poolers pgbalancer
```

### Individual Operations
```bash
# 1. Setup cluster with Ansible
./run-with-ansible.sh --setup-cluster

# 2. Initialize benchmark data
./run-with-ansible.sh --init-benchmark --warehouses 10

# 3. Run benchmark
./run-with-ansible.sh --run-benchmark --duration 60 --threads 16

# 4. Verify cluster setup
./run-with-ansible.sh --verify-cluster
```

### Partial Setup Options
```bash
# Install dependencies only
./run-with-ansible.sh --setup-deps

# Build pgbalancer only
./run-with-ansible.sh --setup-build
```

## 📊 Direct Benchmark Commands (Advanced)

### Using Python Directly
```bash
# 1. Initialize benchmark data
python3 benchmark.py --init --warehouses 10

# 2. Run benchmark
python3 benchmark.py --run --t 60 --n 16 --poolers pgbalancer
```

### Quick Commands
```bash
# All-in-one (setup + init + run)
python3 benchmark.py --setup --init --run --t 30 --n 8 --poolers pgbalancer

# Run only (after initial setup)
python3 benchmark.py --run --t 60 --n 16 --poolers pgbalancer

# Compare poolers
python3 benchmark.py --run --t 30 --poolers pgbalancer pgbouncer
```

### Options
```bash
--t <seconds>         # Test duration (default: 60)
--n <threads>         # Number of threads (default: 16)
--warehouses <num>    # Number of warehouses (default: 10)
--poolers <list>      # Poolers to test (pgbalancer, pgbouncer, etc.)
--type <tpcc|tpcb>    # Benchmark type
```

## 📈 View Results

### Show Configuration
```bash
../pgbalancer/src/pgbalancer --show-config -f ../pgbalancer.yaml | less
```

### Monitor pgbalancer
```bash
# Pool status
psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;"

# Process list
ps aux | grep pgbalancer

# Port check
ss -tlnp | grep 9999
```

### Test Connection
```bash
psql -h localhost -p 9999 -U postgres -d benchmark -c "SELECT version();"
```

## 🔧 Ansible Options

### Full Setup
```bash
./setup-with-ansible.sh
```

### Install Dependencies Only
```bash
./setup-with-ansible.sh --deps-only
```

### Build Only
```bash
./setup-with-ansible.sh --build-only
```

### Verify Installation
```bash
./setup-with-ansible.sh --verify
```

## 📝 Configuration Files

### pgbalancer Config
`/home/pgedge/pge/pgbalancer.yaml`:
```yaml
backend_clustering_mode: streaming_replication
port: 9999
num_init_children: 32
backend_hostname0: 'localhost'
backend_port0: 5432
```

### Benchmark Config
`config.yaml`:
```yaml
poolers:
  pgbalancer:
    enabled: true
    port: 9998

threads: 16
time: 60
warehouses: 10
```

## 🐛 Troubleshooting

### pgbalancer won't start
```bash
# Check if port is in use
sudo ss -tlnp | grep 9999

# Kill existing process
pkill -9 pgbalancer

# Check logs
tail -f log/pgbalancer.log
```

### PostgreSQL not running
```bash
sudo systemctl status postgresql-13
sudo systemctl start postgresql-13
```

### Benchmark fails
```bash
# Reinitialize
python3 benchmark.py --init --warehouses 10

# Check database
psql -h localhost -p 5432 -U postgres -l
```

## 📚 Documentation

- **Ansible Setup**: `ANSIBLE_SETUP.md`
- **Benchmark Guide**: `BENCHMARK_README.md`
- **TPC-C Details**: `TPCC_BENCHMARK_README.md`
- **General Info**: `README.md`

## 🎯 Example Workflow

```bash
# 1. Setup environment (one time)
cd /home/pgedge/pge/benchmark
./setup-with-ansible.sh

# 2. Start pgbalancer
cd /home/pgedge/pge  
./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml &

# 3. Wait for startup
sleep 2

# 4. Run benchmark
cd /home/pgedge/pge/benchmark
python3 benchmark.py --setup --init --run --t 60 --n 16 --poolers pgbalancer

# 5. View results
cat results/benchmark_results.json
```

## 📊 Expected Output

```
Starting TPC-C benchmark...
Warehouses: 10
Threads: 16
Duration: 60s
Pooler: pgbalancer (port 9999)

Results:
  TPS: 1,234.56
  QPS: 15,432.10
  Avg Latency: 12.5ms
  P95 Latency: 25.3ms
  Success Rate: 99.9%
```

## 🚀 Next Steps

1. ✅ Run setup with Ansible
2. ✅ Start pgbalancer  
3. ✅ Run quick benchmark (10s)
4. ✅ Run full benchmark (60s)
5. ✅ Compare with other poolers
6. ✅ Tune configuration for your workload

Happy Benchmarking! 🎉

