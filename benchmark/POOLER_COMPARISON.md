# PostgreSQL Pooler Comparison Guide

## 🎯 Five Poolers - One Benchmark Suite

This suite supports comprehensive benchmarking of all major PostgreSQL poolers:

| Pooler | Port | Language | Config Format | Type |
|--------|------|----------|---------------|------|
| **pgbalancer** | 9999 | C | YAML | Connection pool + Load balancer |
| **pgbouncer** | 9997 | C | INI | Lightweight pooler |
| **pgpool2** | 9998 | C | CONF | Full-featured pooler |
| **pgcat** | 9996 | Rust | TOML | Modern pooler |
| **HAProxy** | 9995 | C | CFG | TCP load balancer |

## 🚀 Quick Comparison Benchmark

### One Command - All Poolers!

```bash
cd /home/pgedge/pge/benchmark

# Compare all four poolers
./compare-poolers.sh --duration 120 --threads 32

# Compare specific poolers
./compare-poolers.sh --poolers pgbalancer pgbouncer --duration 60
```

## 📊 Individual Pooler Management

### Start/Stop Individual Poolers

```bash
# Start all poolers
./manage-poolers.sh start all

# Start specific pooler
./manage-poolers.sh start pgbalancer
./manage-poolers.sh start pgbouncer
./manage-poolers.sh start pgpool2
./manage-poolers.sh start pgcat

# Stop all poolers
./manage-poolers.sh stop all

# Check status
./manage-poolers.sh status

# Test connections
./manage-poolers.sh test all
```

## 🔧 Pooler Configurations

### 1. pgbalancer (Port 9999)

**Config**: `/usr/local/etc/pgbalancer.yaml` or `conf/pgbalancer.yaml`

```yaml
backend_clustering_mode: streaming_replication
listen_addresses: 'localhost'
port: 9999
num_init_children: 32
max_pool: 4
backend_hostname0: 'localhost'
backend_port0: 5432
backend_weight0: 1
load_balance_mode: true
connection_cache: true
```

**Features**:
- ✅ YAML configuration
- ✅ Load balancing
- ✅ Streaming replication support
- ✅ Health checks
- ✅ Connection pooling
- ✅ `--show-config` feature

**Start**:
```bash
cd /home/pgedge/pge
./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml &
```

**Test**:
```bash
psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;"
```

---

### 2. pgbouncer (Port 9997)

**Config**: `/etc/pgbouncer/pgbouncer.ini` or `conf/pgbouncer.ini`

```ini
[databases]
postgres = host=localhost port=5432 dbname=postgres
benchmark = host=localhost port=5432 dbname=benchmark

[pgbouncer]
listen_addr = localhost
listen_port = 9997
auth_type = trust
pool_mode = session
default_pool_size = 20
max_client_conn = 100
```

**Features**:
- ✅ Lightweight and fast
- ✅ Transaction pooling
- ✅ Session pooling
- ✅ Statement pooling
- ✅ Low memory footprint
- ✅ Simple configuration

**Start**:
```bash
pgbouncer -d /etc/pgbouncer/pgbouncer.ini
```

**Test**:
```bash
psql -h localhost -p 9997 -U postgres -c "SHOW STATS;"
```

---

### 3. pgpool2 (Port 9998)

**Config**: `/etc/pgpool-II/pgpool.conf` or `conf/pgpool2.conf`

```conf
listen_addresses = 'localhost'
port = 9998
num_init_children = 32
max_pool = 4
backend_hostname0 = 'localhost'
backend_port0 = 5432
load_balance_mode = on
connection_cache = on
```

**Features**:
- ✅ Connection pooling
- ✅ Load balancing
- ✅ Replication
- ✅ Automatic failover
- ✅ Query caching
- ✅ In-memory query cache

**Start**:
```bash
pgpool -n -f /etc/pgpool-II/pgpool.conf -D &
```

**Test**:
```bash
psql -h localhost -p 9998 -U postgres -c "SHOW pool_nodes;"
```

---

### 4. pgcat (Port 9996)

**Config**: `/tmp/pgcat/pgcat.toml`

```toml
[general]
host = "0.0.0.0"
port = 9996
admin_username = "admin"
admin_password = "admin"

[pools.postgres]
pool_mode = "transaction"
default_role = "any"
pool_size = 20

[pools.postgres.shards.0]
servers = [["localhost", 5432, "primary"]]
database = "postgres"
```

**Features**:
- ✅ Written in Rust (fast!)
- ✅ Modern architecture
- ✅ Sharding support
- ✅ Query routing
- ✅ Admin interface
- ✅ Low latency

**Start**:
```bash
/tmp/pgcat/target/release/pgcat /tmp/pgcat/pgcat.toml &
```

**Test**:
```bash
psql -h localhost -p 9996 -U postgres -c "SELECT 1;"
```

---

### 5. HAProxy (Port 9995)

**Config**: `/etc/haproxy/haproxy.cfg`

```cfg
global
    log /dev/log local0
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    user haproxy
    group haproxy
    daemon

defaults
    log global
    mode tcp
    option tcplog
    timeout connect 10s
    timeout client 1h
    timeout server 1h

frontend postgres_frontend
    bind *:9995
    default_backend postgres_backend

backend postgres_backend
    balance roundrobin
    option tcp-check
    server postgres1 localhost:5432 check

listen stats
    bind *:8404
    mode http
    stats enable
    stats uri /stats
```

**Features**:
- ✅ TCP load balancing
- ✅ High performance & proven
- ✅ Health checks & automatic failover
- ✅ Web statistics interface (port 8404)
- ✅ Multiple backend support
- ✅ Production-ready at scale
- ✅ Layer 4 (TCP) load balancing

**Start**:
```bash
sudo haproxy -f /etc/haproxy/haproxy.cfg -D
# or
./manage-poolers.sh start haproxy
```

**Test**:
```bash
psql -h localhost -p 9995 -U postgres -c "SELECT 1;"
```

**View Stats**:
```bash
# Web interface
curl http://localhost:8404/stats
# or browse to http://localhost:8404/stats
```

## 📊 Comparison Benchmark Workflow

### Complete Workflow

```bash
# 1. Setup all poolers with Ansible
./run-with-ansible.sh --setup-cluster

# 2. Verify installation
./manage-poolers.sh status

# 3. Run comparison benchmark
./compare-poolers.sh --duration 120 --threads 32

# 4. View results
cat results/comparison_*.txt
```

### Manual Step-by-Step

```bash
# 1. Stop all poolers
./manage-poolers.sh stop all

# 2. Initialize benchmark data
python3 benchmark.py --init --warehouses 10

# 3. Benchmark each pooler
./manage-poolers.sh start pgbalancer
python3 benchmark.py --run --t 60 --n 16 --poolers pgbalancer
./manage-poolers.sh stop pgbalancer

./manage-poolers.sh start pgbouncer
python3 benchmark.py --run --t 60 --n 16 --poolers pgbouncer
./manage-poolers.sh stop pgbouncer

# ... repeat for other poolers
```

## 📈 Expected Performance Characteristics

### Typical Performance Ranges (varies by workload)

| Pooler | TPS | Latency | Memory | Best For |
|--------|-----|---------|--------|----------|
| **pgbalancer** | High | Medium | Medium | Load balancing, replication |
| **pgbouncer** | Very High | Low | Very Low | High throughput, simple pooling |
| **pgpool2** | Medium | Medium | High | Full features, query caching |
| **pgcat** | Very High | Very Low | Low | Modern workloads, Rust ecosystem |
| **HAProxy** | High | Low | Very Low | TCP load balancing, multi-backend |

### Use Cases

**pgbalancer**:
- Multi-master replication
- Load balancing across replicas
- Health check automation
- YAML configuration preferred

**pgbouncer**:
- Maximum throughput
- Minimal overhead
- Simple pooling
- Stateless applications

**pgpool2**:
- Query caching needed
- Complex replication setups
- Automatic failover required
- Enterprise features

**pgcat**:
- Modern applications
- Sharding required
- Rust ecosystem
- High performance needs

**HAProxy**:
- TCP load balancing only
- Multiple PostgreSQL backends
- High availability setups
- Simple read/write splitting
- When you need proven reliability

## 🔍 Monitoring During Benchmarks

### Terminal 1: Run Benchmark
```bash
./compare-poolers.sh --duration 300 --threads 32
```

### Terminal 2: Monitor Resources
```bash
# CPU and Memory
watch -n 1 'ps aux | grep -E "(pgbalancer|pgbouncer|pgpool|pgcat)" | grep -v grep'

# Network connections
watch -n 1 'ss -s'

# Database connections
watch -n 1 'psql -h localhost -p 5432 -U postgres -c "SELECT count(*) FROM pg_stat_activity;"'
```

### Terminal 3: Monitor Logs
```bash
# All logs
tail -f log/*.log

# Specific pooler
./manage-poolers.sh logs pgbalancer
```

## 📝 Configuration Files Location

```
benchmark/
├── conf/
│   ├── pgbalancer.yaml      # pgbalancer config
│   ├── pgbouncer.ini         # pgbouncer config
│   ├── pgpool2.conf          # pgpool2 config
│   └── pool_passwd           # Password file
├── /tmp/pgcat/
│   └── pgcat.toml           # pgcat config
└── log/
    ├── pgbalancer.log
    ├── pgbouncer.log
    ├── pgpool2.log
    └── pgcat.log
```

## 🎯 Benchmark Scenarios

### Scenario 1: Lightweight Comparison
```bash
# Quick test - 30 seconds each
./compare-poolers.sh --duration 30 --threads 8 --warehouses 5
```

### Scenario 2: Standard Benchmark
```bash
# Standard test - 60 seconds each
./compare-poolers.sh --duration 60 --threads 16 --warehouses 10
```

### Scenario 3: Stress Test
```bash
# Heavy load - 300 seconds each
./compare-poolers.sh --duration 300 --threads 64 --warehouses 20
```

### Scenario 4: Two-Pooler Comparison
```bash
# Compare just pgbalancer vs pgbouncer
./compare-poolers.sh --poolers pgbalancer pgbouncer --duration 120
```

## 🔧 Troubleshooting

### Pooler Won't Start

**pgbalancer**:
```bash
# Check logs
tail -50 log/pgbalancer.log

# Check port
ss -tlnp | grep 9999

# Test config
../pgbalancer/src/pgbalancer --show-config -f conf/pgbalancer.yaml
```

**pgbouncer**:
```bash
# Check config
pgbouncer -v /etc/pgbouncer/pgbouncer.ini

# Check if installed
which pgbouncer

# Install if missing
sudo dnf install -y pgbouncer
```

**pgpool2**:
```bash
# Check config
pgpool --help

# Check if installed
which pgpool

# Install if missing
sudo dnf install -y pgpool-II
```

**pgcat**:
```bash
# Check if built
ls -lh /tmp/pgcat/target/release/pgcat

# Rebuild if needed
cd /tmp/pgcat && cargo build --release
```

### Port Conflicts

```bash
# Check what's using ports
sudo ss -tlnp | grep -E ":(9996|9997|9998|9999)"

# Kill all poolers
./manage-poolers.sh stop all

# Verify ports are free
ss -tlnp | grep -E ":(9996|9997|9998|9999)" || echo "All ports free"
```

### Connection Issues

```bash
# Test each pooler
./manage-poolers.sh test pgbalancer
./manage-poolers.sh test pgbouncer
./manage-poolers.sh test pgpool2
./manage-poolers.sh test pgcat

# Check PostgreSQL
pg_isready -h localhost -p 5432
```

## 📊 Results Analysis

### Viewing Results

```bash
# Latest comparison
cat results/comparison_*.txt | tail -100

# All JSON results
ls -lh results/*.json

# Specific pooler results
grep -A 10 "pgbalancer" results/comparison_*.txt
```

### Metrics to Compare

1. **TPS (Transactions Per Second)** - Higher is better
2. **QPS (Queries Per Second)** - Higher is better
3. **Average Latency** - Lower is better
4. **P95/P99 Latency** - Lower is better
5. **Success Rate** - Higher is better (aim for 99.9%+)
6. **Memory Usage** - Lower is better (for same performance)
7. **CPU Usage** - Lower is better (for same performance)

## 🏆 Benchmark Best Practices

1. **Consistent hardware** - Use same machine for all tests
2. **Clean state** - Stop all poolers between tests
3. **Warm-up** - Let poolers stabilize before benchmarking
4. **Multiple runs** - Run each test 3-5 times
5. **Same workload** - Use same duration, threads, warehouses
6. **Monitor resources** - Watch CPU, memory, connections
7. **Document results** - Save all output files

## 🎓 Example Complete Run

```bash
# 1. Setup everything with Ansible
./run-with-ansible.sh --setup-cluster

# 2. Verify all poolers installed
./manage-poolers.sh status

# 3. Initialize benchmark data once
python3 benchmark.py --init --warehouses 10

# 4. Run comparison (this tests all poolers)
./compare-poolers.sh --duration 120 --threads 32

# 5. View results
cat results/comparison_*.txt

# 6. Cleanup
./manage-poolers.sh stop all
```

## 📋 Command Reference

### Pooler Management
```bash
./manage-poolers.sh start all        # Start all poolers
./manage-poolers.sh stop all         # Stop all poolers
./manage-poolers.sh restart all      # Restart all poolers
./manage-poolers.sh status           # Show status
./manage-poolers.sh test all         # Test all connections
./manage-poolers.sh logs pgbalancer  # View logs
```

### Benchmark Comparison
```bash
# Quick comparison (30s)
./compare-poolers.sh --duration 30 --threads 8

# Standard comparison (60s)
./compare-poolers.sh --duration 60 --threads 16

# Full comparison (5min)
./compare-poolers.sh --duration 300 --threads 32

# Specific poolers
./compare-poolers.sh --poolers pgbalancer pgbouncer --duration 120
```

### Ansible Setup
```bash
# Full setup (all poolers)
./run-with-ansible.sh --setup-cluster

# Verify installation
./run-with-ansible.sh --verify-cluster

# Install dependencies
./run-with-ansible.sh --setup-deps
```

## 🎯 Test Scenarios

### Scenario 1: Quick Sanity Check
```bash
# 30 seconds, light load
./manage-poolers.sh start all
./manage-poolers.sh test all
./compare-poolers.sh --duration 30 --threads 4 --warehouses 5
```

### Scenario 2: Standard Performance Test
```bash
# 2 minutes, moderate load
./compare-poolers.sh --duration 120 --threads 16 --warehouses 10
```

### Scenario 3: Stress Test
```bash
# 10 minutes, heavy load
./compare-poolers.sh --duration 600 --threads 64 --warehouses 50
```

### Scenario 4: Head-to-Head
```bash
# Compare pgbalancer vs pgbouncer
./compare-poolers.sh \
    --poolers pgbalancer pgbouncer \
    --duration 180 \
    --threads 32
```

## 📈 Understanding Results

### Sample Output

```
╔══════════════════════════════════════════════════════════╗
║   PostgreSQL Pooler Performance Comparison               ║
╚══════════════════════════════════════════════════════════╝

pgbalancer (9999):
  TPS: 1,234.56
  Avg Latency: 12.5ms
  P95 Latency: 25.3ms
  Success Rate: 99.95%
  Memory: 145 MB
  CPU: 42%

pgbouncer (9997):
  TPS: 1,456.78
  Avg Latency: 8.2ms
  P95 Latency: 15.1ms
  Success Rate: 99.99%
  Memory: 12 MB
  CPU: 8%

pgpool2 (9998):
  TPS: 1,123.45
  Avg Latency: 14.8ms
  P95 Latency: 28.5ms
  Success Rate: 99.92%
  Memory: 180 MB
  CPU: 55%

pgcat (9996):
  TPS: 1,567.89
  Avg Latency: 6.5ms
  P95 Latency: 12.3ms
  Success Rate: 99.98%
  Memory: 25 MB
  CPU: 15%
```

### Interpretation

- **Highest TPS**: Best raw throughput
- **Lowest Latency**: Best response time
- **Success Rate**: Should be >99.9%
- **Memory**: Lower is better for same performance
- **CPU**: Lower is better for same performance

## 🔍 Verification

### Check All Poolers
```bash
./manage-poolers.sh status
```

### Test All Connections
```bash
./manage-poolers.sh test all
```

### View All Configurations
```bash
# pgbalancer
../pgbalancer/src/pgbalancer --show-config -f conf/pgbalancer.yaml

# pgbouncer
cat /etc/pgbouncer/pgbouncer.ini

# pgpool2
cat /etc/pgpool-II/pgpool.conf

# pgcat
cat /tmp/pgcat/pgcat.toml
```

## 🛠️ Advanced Configuration

### Tune for Maximum Performance

**pgbalancer**:
```yaml
num_init_children: 64
max_pool: 8
connection_cache: true
load_balance_mode: true
```

**pgbouncer**:
```ini
pool_mode = transaction
default_pool_size = 50
max_client_conn = 200
```

**pgpool2**:
```conf
num_init_children = 64
max_pool = 8
connection_cache = on
```

**pgcat**:
```toml
pool_size = 50
query_parser_enabled = true
primary_reads_enabled = true
```

## 📚 Additional Resources

- **pgbalancer**: `../pgbalancer/README.md`
- **pgbouncer**: https://www.pgbouncer.org/
- **pgpool2**: https://www.pgpool.net/
- **pgcat**: https://github.com/postgresml/pgcat

## 🎉 Quick Start Command

```bash
# One command to rule them all!
./compare-poolers.sh --duration 120 --threads 32 --poolers pgbalancer pgbouncer pgpool2 pgcat
```

This will:
1. ✅ Stop all poolers
2. ✅ Initialize benchmark data
3. ✅ Test each pooler individually
4. ✅ Generate comparison report
5. ✅ Save results to file

**Ready to compare all four poolers! 🚀**

