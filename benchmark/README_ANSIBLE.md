# pgbalancer Benchmark Suite with Ansible Integration

## 🎯 Overview

This benchmark suite provides **complete cluster automation** using Ansible. When you run `--setup`, it uses Ansible to deploy and configure the entire PostgreSQL + pgbalancer cluster.

## 🚀 Quick Start - ONE COMMAND

```bash
cd /home/pgedge/pge/benchmark

# Complete setup + benchmark (Ansible does everything!)
./run-with-ansible.sh --full-benchmark --duration 60 --threads 16 --poolers pgbalancer
```

## 📋 What Ansible Does

### When You Run `--setup-cluster`:

**Ansible automatically:**

1. ✅ **Installs PostgreSQL 13**
   - Server and contrib packages
   - Development headers
   - Client tools (pg_isready, psql)

2. ✅ **Installs System Dependencies**
   - GCC and build tools
   - libyaml for YAML parsing
   - memcached for query caching
   - Python 3 with pip

3. ✅ **Installs Python Packages**
   - asyncpg (async PostgreSQL driver)
   - psycopg2-binary (PostgreSQL adapter)
   - pyyaml (YAML parser)
   - tabulate (table formatting)

4. ✅ **Configures PostgreSQL**
   - Initializes data directory
   - Configures pg_hba.conf for trust authentication
   - Enables and starts service
   - Creates benchmark database

5. ✅ **Builds pgbalancer**
   - Cleans previous builds
   - Compiles from source with -j4
   - Installs to /usr/local/etc

6. ✅ **Configures pgbalancer**
   - Copies YAML configuration
   - Sets up pool_passwd file
   - Creates log directories
   - Sets proper permissions

## 📊 Integrated Commands

### Full Workflow
```bash
# Setup cluster + run benchmark (all-in-one)
./run-with-ansible.sh --full-benchmark \
    --poolers pgbalancer \
    --duration 60 \
    --threads 16 \
    --warehouses 10
```

This command:
1. Runs Ansible playbook for cluster setup
2. Starts pgbalancer
3. Initializes TPC-C data
4. Runs benchmark
5. Shows results

### Step-by-Step

#### Step 1: Setup Cluster
```bash
./run-with-ansible.sh --setup-cluster
```

**Ansible Tasks Executed:**
- Install all dependencies (PostgreSQL, Python, build tools)
- Build pgbalancer from source
- Configure PostgreSQL and pgbalancer
- Create directories and databases
- Verify installation

#### Step 2: Initialize Benchmark Data
```bash
./run-with-ansible.sh --init-benchmark --warehouses 10
```

Creates TPC-C schema with 10 warehouses.

#### Step 3: Run Benchmark
```bash
./run-with-ansible.sh --run-benchmark \
    --poolers pgbalancer \
    --duration 60 \
    --threads 16
```

Runs TPC-C workload for 60 seconds with 16 threads.

## 🔧 Ansible Options

### Full Setup
```bash
./run-with-ansible.sh --setup-cluster
```
Runs complete Ansible playbook with all tasks.

### Selective Setup (Ansible Tags)

```bash
# Install dependencies only
./run-with-ansible.sh --setup-deps
# Ansible tags: deps, python

# Build and configure only
./run-with-ansible.sh --setup-build
# Ansible tags: build, config

# Verify installation
./run-with-ansible.sh --verify-cluster
# Ansible tags: verify
```

### Manual Ansible Execution

```bash
cd /home/pgedge/pge/benchmark

# Run specific tags
ansible-playbook -i ansible-inventory.ini ansible-setup.yml \
    --tags=postgres,build \
    --ask-become-pass

# Run without sudo prompt (if configured)
ansible-playbook -i ansible-inventory.ini ansible-setup.yml

# Dry run (check mode)
ansible-playbook -i ansible-inventory.ini ansible-setup.yml --check
```

## 📁 Ansible Files

### Playbook: `ansible-setup.yml`
Main Ansible playbook with tasks:
- **deps**: System package installation
- **python**: Python package installation  
- **postgres**: PostgreSQL setup and configuration
- **build**: pgbalancer compilation
- **config**: Configuration file deployment
- **dirs**: Directory creation
- **sysbench**: Optional TPC-C tool installation
- **verify**: Verification tasks

### Inventory: `ansible-inventory.ini`
```ini
[localhost]
127.0.0.1 ansible_connection=local

[all:vars]
ansible_python_interpreter=/usr/bin/python3
```

### Verification: `verify-cluster.yml`
Ansible playbook to verify cluster status.

## 🎯 Benchmark Architecture

```
┌─────────────────────────────────────────────┐
│  Ansible Automation Layer                   │
│  ┌────────────────────────────────────────┐ │
│  │ 1. Install PostgreSQL 13               │ │
│  │ 2. Install Dependencies                │ │
│  │ 3. Build pgbalancer                    │ │
│  │ 4. Configure Services                  │ │
│  │ 5. Create Database                     │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  PostgreSQL Cluster                         │
│  ┌────────────────────────────────────────┐ │
│  │ PostgreSQL 13                          │ │
│  │ Port: 5432                             │ │
│  │ Database: benchmark, tpcc              │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  pgbalancer Connection Pooler               │
│  ┌────────────────────────────────────────┐ │
│  │ Port: 9999                             │ │
│  │ Config: pgbalancer.yaml                │ │
│  │ Pool Size: 32 children                 │ │
│  │ Max Pool: 4                            │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  TPC-C Benchmark Suite                      │
│  ┌────────────────────────────────────────┐ │
│  │ Threads: 16                            │ │
│  │ Duration: 60s                          │ │
│  │ Warehouses: 10                         │ │
│  │ Metrics: TPS, QPS, Latency             │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

## 🔍 Verification

### Quick Verification
```bash
./verify-setup.sh
```

Shows:
- PostgreSQL status
- pgbalancer process status
- Port listening status
- Connection test results
- Pool nodes information
- Configuration file location

### Detailed Verification with Ansible
```bash
ansible-playbook -i ansible-inventory.ini verify-cluster.yml
```

## 📊 Running Benchmarks

### Quick Test (30 seconds)
```bash
./run-with-ansible.sh --run-benchmark --duration 30 --threads 8
```

### Production Benchmark (5 minutes)
```bash
./run-with-ansible.sh --run-benchmark --duration 300 --threads 32 --warehouses 20
```

### Compare Multiple Poolers
```bash
./run-with-ansible.sh --run-benchmark \
    --poolers pgbalancer pgbouncer \
    --duration 120 \
    --threads 16
```

## 🛠️ Ansible Installation

If Ansible is not installed:

```bash
# RHEL/Rocky/AlmaLinux
sudo dnf install -y ansible

# Ubuntu/Debian
sudo apt-get install -y ansible

# Or via pip
pip3 install ansible
```

## 📝 Configuration

### Ansible Variables

Edit `ansible-setup.yml` to customize:

```yaml
vars:
  benchmark_dir: "/home/pgedge/pge/benchmark"
  pgbalancer_dir: "/home/pgedge/pge/pgbalancer"
  postgres_version: 13
```

### pgbalancer Configuration

Edit `/home/pgedge/pge/pgbalancer.yaml`:

```yaml
backend_clustering_mode: streaming_replication
port: 9999
num_init_children: 32
backend_hostname0: 'localhost'
backend_port0: 5432
```

### Benchmark Configuration

Edit `config.yaml`:

```yaml
poolers:
  pgbalancer:
    enabled: true
    port: 9999

threads: 16
time: 60
warehouses: 10
```

## 🐛 Troubleshooting

### Ansible Fails
```bash
# Check Ansible version
ansible --version

# Test connection
ansible localhost -i ansible-inventory.ini -m ping

# Run with verbose output
ansible-playbook -i ansible-inventory.ini ansible-setup.yml -vvv
```

### PostgreSQL Won't Start
```bash
# Check status
sudo systemctl status postgresql-13

# View logs
sudo journalctl -u postgresql-13 -n 50

# Reinitialize (if needed)
sudo rm -rf /var/lib/pgsql/13/data
sudo -u postgres /usr/pgsql-13/bin/initdb /var/lib/pgsql/13/data
```

### pgbalancer Build Fails
```bash
# Clean and rebuild
cd /home/pgedge/pge/pgbalancer
make clean
make -j4

# Check for missing dependencies
./configure
```

### Port Already in Use
```bash
# Find what's using the port
sudo ss -tlnp | grep 9999

# Kill pgbalancer
pkill -9 pgbalancer

# Check no zombies
ps aux | grep pgbalancer
```

## 📚 Documentation Files

- **QUICK_START.md** - Quick start guide
- **ANSIBLE_SETUP.md** - Detailed Ansible documentation
- **README_ANSIBLE.md** - This file
- **BENCHMARK_README.md** - General benchmark guide
- **TPCC_BENCHMARK_README.md** - TPC-C specific documentation

## 🎯 Complete Example Workflow

```bash
# 1. Verify current status
./verify-setup.sh

# 2. If needed, setup cluster with Ansible
./run-with-ansible.sh --setup-cluster

# 3. Verify again
./verify-setup.sh

# 4. Initialize benchmark data
./run-with-ansible.sh --init-benchmark --warehouses 10

# 5. Run quick test
./run-with-ansible.sh --run-benchmark --duration 30 --threads 8

# 6. Run full benchmark
./run-with-ansible.sh --run-benchmark --duration 300 --threads 32

# 7. View configuration
../pgbalancer/src/pgbalancer --show-config -f ../benchmark/conf/pgbalancer.yaml | less
```

## 📈 Expected Results

After running benchmark, you'll see:

```
╔══════════════════════════════════════════════════════════╗
║   TPC-C Benchmark Results                                ║
╚══════════════════════════════════════════════════════════╝

Pooler: pgbalancer
Duration: 60 seconds
Threads: 16
Warehouses: 10

Metrics:
  TPS (Transactions Per Second): 1,234.56
  QPS (Queries Per Second): 15,432.10
  Average Latency: 12.5 ms
  P95 Latency: 25.3 ms
  P99 Latency: 45.8 ms
  Success Rate: 99.95%
  
Resource Usage:
  Memory: 145 MB
  CPU: 42%
```

## 🚀 Advantages of Ansible Integration

1. **Idempotent** - Run multiple times safely
2. **Repeatable** - Same setup every time
3. **Automated** - No manual steps
4. **Documented** - All steps in playbook
5. **Scalable** - Easy to add more nodes
6. **Configurable** - Centralized variable management

## 🔄 CI/CD Integration

```yaml
# Example GitLab CI
benchmark:
  script:
    - cd benchmark
    - ./run-with-ansible.sh --setup-cluster
    - ./run-with-ansible.sh --run-benchmark --duration 60
  artifacts:
    paths:
      - benchmark/results/
```

## 📞 Support

- **GitHub Issues**: Report problems
- **Documentation**: See other README files
- **Logs**: Check `log/pgbalancer.log`
- **Config Help**: Run `pgbalancer --show-config`

---

**Ready to benchmark! 🎉**

Run `./verify-setup.sh` to check your cluster status anytime.

