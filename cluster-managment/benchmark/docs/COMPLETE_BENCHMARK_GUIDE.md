# Complete PostgreSQL Pooler Benchmark Guide

## 🎯 Complete Benchmark Suite

### 5 Poolers + 3 Benchmark Tools = Comprehensive Testing

**Poolers Supported:**
1. ✅ **pgbalancer** (port 9999) - YAML-configured, load balancing, replication
2. ✅ **pgbouncer** (port 9997) - Lightweight, high-throughput
3. ✅ **pgpool2** (port 9998) - Full-featured, query caching
4. ✅ **pgcat** (port 9996) - Modern Rust-based pooler
5. ✅ **HAProxy** (port 9995) - TCP load balancer

**Benchmark Tools:**
1. ✅ **TPC-C** (benchmark.py) - OLTP workload
2. ✅ **pgbench** (run-pgbench.sh) - PostgreSQL built-in tool
3. ✅ **HammerDB** (run-hammerdb.sh) - Industry-standard TPC-C/H

## 🚀 One-Command Setup

```bash
cd /home/pgedge/pge/benchmark

# Setup all 5 poolers with Ansible
./run-with-ansible.sh --setup-cluster
```

**This installs:**
- PostgreSQL 13
- pgbalancer (compiled from source)
- pgbouncer (via dnf)
- pgpool2 (via dnf)
- pgcat (compiled from Rust)
- HAProxy (via dnf)
- All dependencies and configurations

## 📊 Benchmark Options

### Option 1: TPC-C Benchmark (Python)
```bash
# Quick test (all 5 poolers)
./compare-poolers.sh --duration 30 --threads 8

# Full benchmark
./compare-poolers.sh --duration 120 --threads 32 --warehouses 10

# Specific poolers
./compare-poolers.sh --poolers pgbalancer haproxy --duration 60
```

### Option 2: pgbench (Built-in PostgreSQL)
```bash
# Standard pgbench test (all poolers)
./run-pgbench.sh --scale 100 --duration 60 --clients 32

# Read-only workload
./run-pgbench.sh --mode select-only --duration 120 --clients 64

# Specific poolers
./run-pgbench.sh --poolers pgbalancer pgbouncer --duration 90
```

### Option 3: HammerDB (Industry Standard)
```bash
# TPC-C benchmark (all poolers)
./run-hammerdb.sh --warehouses 100 --duration 5 --users 16

# Large scale test
./run-hammerdb.sh --warehouses 500 --duration 30 --users 64

# Specific poolers
./run-hammerdb.sh --poolers pgbalancer pgcat --duration 10
```

## 🎯 Port Assignments

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Backend database |
| **pgbalancer** | 9999 | Connection pooler |
| **pgpool2** | 9998 | Connection pooler |
| **pgbouncer** | 9997 | Connection pooler |
| **pgcat** | 9996 | Connection pooler |
| **HAProxy** | 9995 | TCP load balancer |
| HAProxy Stats | 8404 | Web statistics |

## 🔧 Pooler Management

### Start/Stop All Poolers

```bash
# Start all
./manage-poolers.sh start all

# Stop all
./manage-poolers.sh stop all

# Check status
./manage-poolers.sh status

# Test connections
./manage-poolers.sh test all
```

### Individual Control

```bash
# Start specific pooler
./manage-poolers.sh start pgbalancer
./manage-poolers.sh start pgbouncer
./manage-poolers.sh start pgpool2
./manage-poolers.sh start pgcat
./manage-poolers.sh start haproxy

# View logs
./manage-poolers.sh logs pgbalancer
./manage-poolers.sh logs haproxy
```

## 📋 Complete Workflow

### Full Comparison Test

```bash
# 1. Setup environment (one time)
./run-with-ansible.sh --setup-cluster

# 2. Verify all poolers
./manage-poolers.sh status

# 3. Run TPC-C comparison
./compare-poolers.sh --duration 120 --threads 32

# 4. Run pgbench comparison
./run-pgbench.sh --scale 100 --duration 60 --clients 32

# 5. Run HammerDB comparison
./run-hammerdb.sh --warehouses 100 --duration 5 --users 16

# 6. View all results
ls -lh results/
```

## 📊 Comparison Matrix

### Features Comparison

| Feature | pgbalancer | pgbouncer | pgpool2 | pgcat | HAProxy |
|---------|------------|-----------|---------|-------|---------|
| **Connection Pooling** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Load Balancing** | ✅ | ❌ | ✅ | ✅ | ✅ |
| **Replication Support** | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Health Checks** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Query Caching** | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Failover** | ✅ | ❌ | ✅ | ❌ | ✅ |
| **Sharding** | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Statistics UI** | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Config Format** | YAML | INI | CONF | TOML | CFG |
| **Language** | C | C | C | Rust | C |

### Performance Tiers (Typical)

**Ultra-Fast (< 5ms latency):**
- pgbouncer
- pgcat

**Fast (5-15ms latency):**
- HAProxy
- pgbalancer

**Feature-Rich (15-30ms latency):**
- pgpool2

*Note: Actual performance depends on workload, configuration, and hardware*

## 🎯 When to Use Which Pooler

### Use pgbalancer When:
- ✅ You need YAML configuration
- ✅ Load balancing across replicas
- ✅ Streaming replication support
- ✅ Health check automation
- ✅ Modern configuration management

### Use pgbouncer When:
- ✅ Maximum throughput is critical
- ✅ Minimal latency required
- ✅ Simple connection pooling
- ✅ Stateless applications
- ✅ Lowest memory footprint

### Use pgpool2 When:
- ✅ Query caching needed
- ✅ Complex replication setups
- ✅ Automatic failover required
- ✅ Legacy enterprise features
- ✅ Write query distribution

### Use pgcat When:
- ✅ Sharding is required
- ✅ Modern Rust ecosystem
- ✅ Query routing needed
- ✅ Admin UI wanted
- ✅ Low latency + modern features

### Use HAProxy When:
- ✅ Simple TCP load balancing
- ✅ Multiple PostgreSQL backends
- ✅ Layer 4 distribution only
- ✅ Proven enterprise solution
- ✅ Web stats dashboard needed

## 📝 Configuration Files

### All Pooler Configs

```bash
# pgbalancer
/usr/local/etc/pgbalancer.yaml
conf/pgbalancer.yaml

# pgbouncer
/etc/pgbouncer/pgbouncer.ini
conf/pgbouncer.ini

# pgpool2
/etc/pgpool-II/pgpool.conf
conf/pgpool2.conf

# pgcat
/tmp/pgcat/pgcat.toml

# HAProxy
/etc/haproxy/haproxy.cfg
```

### View Configurations

```bash
# pgbalancer (with --show-config!)
../pgbalancer/src/pgbalancer --show-config -f conf/pgbalancer.yaml | less

# pgbouncer
cat /etc/pgbouncer/pgbouncer.ini

# pgpool2
cat /etc/pgpool-II/pgpool.conf

# pgcat
cat /tmp/pgcat/pgcat.toml

# HAProxy
cat /etc/haproxy/haproxy.cfg
```

## 🔍 Monitoring & Statistics

### pgbalancer
```bash
psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;"
psql -h localhost -p 9999 -U postgres -c "SHOW pool_processes;"
```

### pgbouncer
```bash
psql -h localhost -p 9997 -U postgres pgbouncer -c "SHOW STATS;"
psql -h localhost -p 9997 -U postgres pgbouncer -c "SHOW POOLS;"
```

### pgpool2
```bash
psql -h localhost -p 9998 -U postgres -c "SHOW pool_nodes;"
psql -h localhost -p 9998 -U postgres -c "SHOW pool_pools;"
```

### pgcat
```bash
# Admin interface (if configured)
psql -h localhost -p 9996 -U admin pgcat
```

### HAProxy
```bash
# Web statistics dashboard
curl http://localhost:8404/stats
# or browse to http://localhost:8404/stats

# Socket stats
echo "show stat" | sudo socat stdio /run/haproxy/admin.sock
```

## 📊 Sample Benchmark Commands

### Quick Test (All Poolers, All Tools)

```bash
# TPC-C (30 seconds)
./compare-poolers.sh --duration 30 --threads 8

# pgbench (30 seconds)
./run-pgbench.sh --scale 50 --duration 30 --clients 16

# HammerDB (2 minutes)
./run-hammerdb.sh --warehouses 50 --duration 2 --users 8
```

### Standard Test (Recommended)

```bash
# TPC-C (120 seconds)
./compare-poolers.sh --duration 120 --threads 32

# pgbench (60 seconds)
./run-pgbench.sh --scale 100 --duration 60 --clients 32

# HammerDB (5 minutes)
./run-hammerdb.sh --warehouses 100 --duration 5 --users 16
```

### Stress Test (Production Simulation)

```bash
# TPC-C (10 minutes)
./compare-poolers.sh --duration 600 --threads 64

# pgbench (5 minutes)
./run-pgbench.sh --scale 1000 --duration 300 --clients 128

# HammerDB (30 minutes)
./run-hammerdb.sh --warehouses 500 --duration 30 --users 64
```

## 📈 Results Format

All benchmark scripts generate:
- **Console output** - Real-time progress
- **Text reports** - Saved to `results/` directory
- **JSON data** - For programmatic analysis
- **Logs** - Individual pooler logs in `log/` directory

### View Results

```bash
# Latest TPC-C comparison
cat results/comparison_*.txt | tail -100

# Latest pgbench results
cat results/pgbench_comparison_*.txt

# Latest HammerDB results
cat results/hammerdb_comparison_*.txt

# All results
ls -lh results/
```

## 🎓 Step-by-Step Tutorial

### Day 1: Setup & Verification

```bash
# Setup
./run-with-ansible.sh --setup-cluster

# Verify
./manage-poolers.sh status
./manage-poolers.sh test all

# Test each pooler manually
psql -h localhost -p 9999 -U postgres -c "SELECT version();"  # pgbalancer
psql -h localhost -p 9997 -U postgres -c "SELECT version();"  # pgbouncer
psql -h localhost -p 9998 -U postgres -c "SELECT version();"  # pgpool2
psql -h localhost -p 9996 -U postgres -c "SELECT version();"  # pgcat
psql -h localhost -p 9995 -U postgres -c "SELECT version();"  # HAProxy
```

### Day 2: Quick Benchmarks

```bash
# Quick TPC-C
./compare-poolers.sh --duration 30 --threads 8 --warehouses 5

# Quick pgbench
./run-pgbench.sh --scale 10 --duration 30 --clients 8

# View results
cat results/*.txt
```

### Day 3: Full Benchmarks

```bash
# Full TPC-C
./compare-poolers.sh --duration 300 --threads 32 --warehouses 20

# Full pgbench
./run-pgbench.sh --scale 1000 --duration 300 --clients 64

# Full HammerDB
./run-hammerdb.sh --warehouses 200 --duration 10 --users 32
```

### Day 4: Analysis

```bash
# Compare all results
ls -lh results/
cat results/comparison_*.txt
cat results/pgbench_*.txt
cat results/hammerdb_*.txt

# Generate report
# (Results show which pooler performs best for your workload)
```

## 🏆 Quick Command Reference

| Task | Command |
|------|---------|
| **Setup all poolers** | `./run-with-ansible.sh --setup-cluster` |
| **Start all poolers** | `./manage-poolers.sh start all` |
| **Stop all poolers** | `./manage-poolers.sh stop all` |
| **Check status** | `./manage-poolers.sh status` |
| **Test connections** | `./manage-poolers.sh test all` |
| **Run TPC-C** | `./compare-poolers.sh --duration 60` |
| **Run pgbench** | `./run-pgbench.sh --scale 100 --duration 60` |
| **Run HammerDB** | `./run-hammerdb.sh --warehouses 100 --duration 5` |
| **View results** | `ls -lh results/` |
| **View logs** | `./manage-poolers.sh logs [pooler]` |

## 🎯 Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Benchmark Tools Layer                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   TPC-C    │  │  pgbench   │  │  HammerDB  │             │
│  │  (Python)  │  │ (Built-in) │  │   (Java)   │             │
│  └────────────┘  └────────────┘  └────────────┘             │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│                    Connection Poolers                         │
│  ┌────────────┬────────────┬────────────┬────────────────┐  │
│  │pgbalancer  │ pgbouncer  │  pgpool2   │     pgcat      │  │
│  │ :9999      │  :9997     │   :9998    │    :9996       │  │
│  └────────────┴────────────┴────────────┴────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  HAProxy (TCP LB)                      │  │
│  │                    :9995                               │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│                    PostgreSQL 13                              │
│                      :5432                                    │
└──────────────────────────────────────────────────────────────┘
```

## 📚 Documentation Index

| Document | Purpose |
|----------|---------|
| **COMPLETE_BENCHMARK_GUIDE.md** | This file - Master guide |
| **INDEX.md** | Quick reference index |
| **POOLER_COMPARISON.md** | Detailed pooler comparison |
| **README_ANSIBLE.md** | Ansible integration guide |
| **QUICK_START.md** | Quick start guide |
| **ANSIBLE_SETUP.md** | Ansible details |
| **BENCHMARK_README.md** | General benchmark info |
| **TPCC_BENCHMARK_README.md** | TPC-C specific |

## 🚀 Getting Started - FAST TRACK

```bash
cd /home/pgedge/pge/benchmark

# 1. One-command setup (installs everything)
./run-with-ansible.sh --setup-cluster

# 2. Verify (should show all 5 poolers)
./manage-poolers.sh status

# 3. Run quick comparison with TPC-C
./compare-poolers.sh --duration 30 --threads 8

# 4. Or run pgbench comparison
./run-pgbench.sh --scale 50 --duration 30 --clients 16

# 5. View results
cat results/*.txt
```

## 🎯 Example Results (Sample)

```
╔══════════════════════════════════════════════════════════╗
║   Pooler Performance Comparison                          ║
╚══════════════════════════════════════════════════════════╝

pgbalancer:  1,234 TPS │ 12.5ms avg │ 145 MB │ ⭐⭐⭐⭐
pgbouncer:   1,567 TPS │  8.2ms avg │  12 MB │ ⭐⭐⭐⭐⭐
pgpool2:     1,089 TPS │ 15.1ms avg │ 180 MB │ ⭐⭐⭐
pgcat:       1,623 TPS │  6.8ms avg │  28 MB │ ⭐⭐⭐⭐⭐
HAProxy:     1,445 TPS │  9.3ms avg │   8 MB │ ⭐⭐⭐⭐⭐

Winner (TPS): pgcat
Winner (Latency): pgcat  
Winner (Memory): HAProxy
```

## 🔧 Troubleshooting

### Quick Diagnostics

```bash
# Check all services
./manage-poolers.sh status

# Check PostgreSQL
pg_isready -h localhost -p 5432

# Check all ports
ss -tlnp | grep -E ":(5432|9995|9996|9997|9998|9999|8404)"

# Test all connections
./manage-poolers.sh test all
```

### Common Issues

**Pooler won't start**:
```bash
# View logs
./manage-poolers.sh logs [pooler_name]

# Check port conflicts
ss -tlnp | grep :[port]

# Restart
./manage-poolers.sh restart [pooler_name]
```

**Benchmark fails**:
```bash
# Verify pooler connection
./manage-poolers.sh test [pooler_name]

# Check PostgreSQL
psql -h localhost -p 5432 -U postgres -l

# Reinitialize
python3 benchmark.py --init --warehouses 10
```

## 📞 Support & Resources

### Official Documentation
- **pgbalancer**: `../pgbalancer/README.md`
- **pgbouncer**: https://www.pgbouncer.org/
- **pgpool2**: https://www.pgpool.net/
- **pgcat**: https://github.com/postgresml/pgcat
- **HAProxy**: https://www.haproxy.org/

### Quick Links
- Ansible Setup: `ANSIBLE_SETUP.md`
- Pooler Comparison: `POOLER_COMPARISON.md`
- Quick Start: `QUICK_START.md`
- Index: `INDEX.md`

---

## 🎉 TL;DR - Ultra Quick Start

```bash
cd /home/pgedge/pge/benchmark

# Setup (one time)
./run-with-ansible.sh --setup-cluster

# Run comparison
./compare-poolers.sh --duration 60

# Done! Check results
cat results/comparison_*.txt
```

**5 poolers + 3 benchmark tools = Complete PostgreSQL performance testing! 🚀**

