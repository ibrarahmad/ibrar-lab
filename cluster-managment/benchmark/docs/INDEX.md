# pgbalancer Benchmark Suite - Complete Index

## 🎯 Quick Access

| What You Want | Command |
|---------------|---------|
| **Full automated setup + benchmark** | `./run-with-ansible.sh --full-benchmark --duration 60` |
| **Setup cluster only** | `./run-with-ansible.sh --setup-cluster` |
| **Verify cluster** | `./verify-setup.sh` |
| **Run benchmark** | `./run-with-ansible.sh --run-benchmark --duration 60` |
| **View pgbalancer config** | `../pgbalancer/src/pgbalancer --show-config -f ../benchmark/conf/pgbalancer.yaml` |

## 📁 File Organization

### Ansible Automation
| File | Purpose |
|------|---------|
| `ansible-setup.yml` | Ansible playbook for cluster setup |
| `ansible-inventory.ini` | Ansible inventory file |
| `verify-cluster.yml` | Ansible verification playbook |
| `run-with-ansible.sh` | **Main integrated runner (USE THIS!)** |
| `setup-with-ansible.sh` | Standalone Ansible setup script |
| `verify-setup.sh` | Quick verification script (no Ansible) |

### Documentation
| File | Description |
|------|-------------|
| `INDEX.md` | **This file - Start here!** |
| `QUICK_START.md` | Quick start guide |
| `README_ANSIBLE.md` | Complete Ansible integration guide |
| `ANSIBLE_SETUP.md` | Detailed Ansible documentation |
| `README.md` | General overview |
| `BENCHMARK_README.md` | General benchmark documentation |
| `TPCC_BENCHMARK_README.md` | TPC-C specific documentation |

### Benchmark Scripts
| File | Purpose |
|------|---------|
| `benchmark.py` | Main TPC-C benchmark script (Python) |
| `tpcc_benchmark.py` | Alternative TPC-C implementation |
| `run_benchmark.sh` | Shell-based benchmark runner |

### Configuration Files
| File | Description |
|------|-------------|
| `config.yaml` | Benchmark configuration |
| `benchmark_config.yaml` | Alternative config |
| `conf/pgbalancer.yaml` | pgbalancer YAML configuration |
| `conf/pool_passwd` | Password file |
| `conf/pgpool2.conf` | pgpool2 config (reference) |
| `conf/pgbouncer.ini` | pgbouncer config (reference) |

## 🚀 Usage Examples

### Complete Workflow (Recommended)
```bash
cd /home/pgedge/pge/benchmark

# 1. Full setup and benchmark
./run-with-ansible.sh --full-benchmark --poolers pgbalancer --duration 60 --threads 16
```

### Step by Step
```bash
# 1. Setup cluster with Ansible
./run-with-ansible.sh --setup-cluster

# 2. Verify setup
./verify-setup.sh

# 3. Initialize benchmark data
./run-with-ansible.sh --init-benchmark --warehouses 10

# 4. Run benchmark
./run-with-ansible.sh --run-benchmark --duration 60 --threads 16
```

### Quick Operations
```bash
# Verify cluster
./verify-setup.sh

# Run benchmark (cluster already setup)
./run-with-ansible.sh --run-benchmark --duration 60

# View configuration
../pgbalancer/src/pgbalancer --show-config -f conf/pgbalancer.yaml | less
```

## 🎓 Learning Path

1. **Start Here**: `INDEX.md` (this file)
2. **Quick Setup**: `QUICK_START.md`
3. **Ansible Details**: `README_ANSIBLE.md`
4. **TPC-C Info**: `TPCC_BENCHMARK_README.md`
5. **Advanced**: `ANSIBLE_SETUP.md`

## 🔧 Key Features

### Ansible Integration
- ✅ **One-command setup** - Complete cluster deployment
- ✅ **Idempotent** - Safe to run multiple times
- ✅ **Tagged tasks** - Run specific parts
- ✅ **Automatic verification** - Built-in health checks

### Benchmark Capabilities
- ✅ **TPC-C workload** - Industry standard OLTP benchmark
- ✅ **Multiple poolers** - Compare pgbalancer, pgbouncer, pgpool2
- ✅ **Configurable** - Duration, threads, warehouses
- ✅ **Detailed metrics** - TPS, QPS, latency, resource usage

### pgbalancer Features
- ✅ **YAML configuration** - Modern config format
- ✅ **--show-config** - Display all 188 parameters
- ✅ **Connection pooling** - 32 children, 4 max pool
- ✅ **Load balancing** - Automatic distribution
- ✅ **Health checks** - Automatic failover

## 📊 Command Reference

### Cluster Management
```bash
# Setup
./run-with-ansible.sh --setup-cluster          # Full cluster setup
./run-with-ansible.sh --setup-deps             # Dependencies only
./run-with-ansible.sh --setup-build            # Build only

# Verify
./verify-setup.sh                              # Quick verify
./run-with-ansible.sh --verify-cluster         # Ansible verify
```

### Benchmark Operations
```bash
# Initialize
./run-with-ansible.sh --init-benchmark --warehouses 10

# Run
./run-with-ansible.sh --run-benchmark --duration 60 --threads 16

# Full workflow
./run-with-ansible.sh --full-benchmark --duration 60
```

### pgbalancer Control
```bash
# Show config
../pgbalancer/src/pgbalancer --show-config -f conf/pgbalancer.yaml

# Start
cd /home/pgedge/pge
./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml -d &

# Stop
pkill pgbalancer

# Status
psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;"
```

## 🎯 Common Workflows

### First Time Setup
```bash
./verify-setup.sh                              # Check status
./run-with-ansible.sh --setup-cluster          # Setup with Ansible
./verify-setup.sh                              # Verify setup
./run-with-ansible.sh --init-benchmark         # Initialize data
./run-with-ansible.sh --run-benchmark          # Run benchmark
```

### Daily Testing
```bash
./verify-setup.sh                              # Verify cluster
./run-with-ansible.sh --run-benchmark --duration 120
```

### Performance Tuning
```bash
# Edit config
vim ../pgbalancer.yaml

# Restart pgbalancer
pkill pgbalancer
cd /home/pgedge/pge
./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml &

# Run benchmark
cd benchmark
./run-with-ansible.sh --run-benchmark --duration 300 --threads 32
```

## 📞 Getting Help

### View Logs
```bash
# pgbalancer logs
tail -f log/pgbalancer.log

# PostgreSQL logs
sudo tail -f /var/lib/pgsql/13/data/log/postgresql-*.log

# Benchmark output
ls -lh results/
```

### Check Status
```bash
# System
./verify-setup.sh

# PostgreSQL
pg_isready -h localhost -p 5432
psql -h localhost -p 5432 -U postgres -l

# pgbalancer
ps aux | grep pgbalancer
ss -tlnp | grep 9999
psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;"
```

### Configuration
```bash
# View current config
../pgbalancer/src/pgbalancer --show-config -f conf/pgbalancer.yaml

# Edit config
vim ../pgbalancer.yaml

# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('../pgbalancer.yaml'))"
```

## 🏆 Best Practices

1. **Always verify** before running benchmarks: `./verify-setup.sh`
2. **Use Ansible** for consistent setup: `./run-with-ansible.sh --setup-cluster`
3. **Start small** with quick tests: `--duration 30 --threads 8`
4. **Monitor resources** during benchmarks: `top`, `iostat`
5. **Save results** for comparison: Keep JSON output files
6. **Clean state** between tests: Restart pgbalancer

---

**🎉 You're all set! Start with `./verify-setup.sh` and then run `./run-with-ansible.sh --full-benchmark`**

