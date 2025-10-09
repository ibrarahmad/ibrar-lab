# PostgreSQL Cluster Manager

Comprehensive Ansible-based PostgreSQL cluster management with streaming replication, pooler management, and pgraft integration for automatic failover.

## Features

### PostgreSQL Cluster Management
- ✅ **Automated Setup** - One command to setup primary + replicas
- ✅ **Streaming Replication** - Built-in PostgreSQL replication
- ✅ **Promotion & Failover** - Promote replicas, test failover scenarios
- ✅ **Health Monitoring** - Comprehensive health checks and diagnostics

### Pooler Management  
- ✅ **Multi-Pooler Support** - pgbalancer, pgbouncer, pgpool2, pgcat, haproxy
- ✅ **Automated Installation** - Ansible playbooks for all poolers
- ✅ **Connection Testing** - Verify pooler connectivity
- ✅ **Log Management** - View logs for any component

## Quick Start

### 1. Setup PostgreSQL Cluster (Primary + 2 Replicas)

```bash
cd cluster/scripts

# Basic setup with PostgreSQL 17
./cluster.py --setup-postgres --version 17

# With pgraft for automatic failover
./cluster.py --setup-postgres --version 17 --pgraft
```

This will:
- Install PostgreSQL on all nodes
- Setup primary server with replication support
- Setup 2 replica servers with streaming replication
- Configure pg_hba.conf and postgresql.conf
- Create replication slots
- Optionally install and configure pgraft

### 2. Check Cluster Status

```bash
# Show PostgreSQL replication status
./cluster.py --postgres-status

# Show pgraft status (if enabled)
./cluster.py --pgraft-status

# Comprehensive health check
./cluster.py --health-check
```

### 3. Test Failover

```bash
# Test automatic failover
./cluster.py --test-failover

# Or manually promote a replica
./cluster.py --promote --port 5433
```

### 4. Setup Poolers

```bash
# Install and configure all poolers
./cluster.py --setup-poolers

# Start all poolers
./cluster.py --start all

# Check pooler status
./cluster.py --pooler-status

# Test connections
./cluster.py --test-poolers
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Applications                                       │
│  psql / pgbench / app                               │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│  Connection Poolers (pgbalancer, pgbouncer, etc.)   │
│  Port 9999, 9998, 9997, 9996, 9995                  │
└─────────────────────────────────────────────────────┘
                      ↓
         ┌────────────┴────────────┐
         ↓                         ↓
┌──────────────────┐    ┌──────────────────┐
│  PostgreSQL      │◄──►│  PostgreSQL      │
│  Primary         │    │  Replica 1       │
│  Port 5432       │    │  Port 5433       │
│  + pgraft node 1 │    │  + pgraft node 2 │
└──────────────────┘    └──────────────────┘
         │                      
         │              ┌──────────────────┐
         └─────────────►│  PostgreSQL      │
                        │  Replica 2       │
                        │  Port 5434       │
                        │  + pgraft node 3 │
                        └──────────────────┘

        Streaming Replication + pgraft Raft Consensus
```

## Configuration

### Ansible Inventory

Edit `conf/cluster-inventory.ini`:

```ini
[primary]
pg-primary ansible_host=localhost ansible_port=5432

[replicas]
pg-replica1 ansible_host=localhost ansible_port=5433
pg-replica2 ansible_host=localhost ansible_port=5434

[postgres:vars]
pg_version=17
pg_cluster_name=production
pg_repl_user=replicator
pg_repl_password=replpass
enable_pgraft=false
```

For multi-server setup, change `ansible_host` to actual IP addresses.

### Cluster Configuration

The Ansible playbook (`conf/postgresql-cluster-setup.yml`) configures:

**Primary Server:**
- `listen_addresses = '*'`
- `wal_level = replica`
- `max_wal_senders = 10`
- `max_replication_slots = 10`
- Replication user creation
- Replication slots for each replica

**Replica Servers:**
- `pg_basebackup` from primary
- `primary_conninfo` connection string
- `hot_standby = on`
- Replication slot assignment

**pgraft (Optional):**
- Cluster ID and node ID
- Raft communication ports
- Data directory for Raft state

## Commands Reference

### PostgreSQL Cluster

```bash
# Setup cluster
./cluster.py --setup-postgres --version 17 [--pgraft]

# Show status
./cluster.py --postgres-status
./cluster.py --pgraft-status

# Promotion & failover
./cluster.py --promote --port 5433
./cluster.py --test-failover
```

### Pooler Management

```bash
# Setup poolers
./cluster.py --setup-poolers

# Start/stop
./cluster.py --start all
./cluster.py --start pgbalancer
./cluster.py --stop all
./cluster.py --stop pgbouncer

# Status & testing
./cluster.py --pooler-status
./cluster.py --test-poolers
```

### Health & Diagnostics

```bash
# Health check (saves JSON report)
./cluster.py --health-check

# View logs
./cluster.py --logs postgres --lines 100
./cluster.py --logs pgbalancer --lines 50
./cluster.py --logs pgbouncer --lines 50
```

### Options

```bash
--no-password          # Don't ask for sudo password
--config FILE          # Load config from YAML file
--version VERSION      # PostgreSQL version (default: 17)
--port PORT           # Port for replica operations
--lines NUM           # Number of log lines to show
```

## File Structure

```
cluster/
├── scripts/
│   └── cluster.py              # Main cluster management script
├── conf/
│   ├── postgresql-cluster-setup.yml   # Ansible playbook for PostgreSQL
│   ├── cluster-inventory.ini         # Cluster inventory
│   ├── ansible-setup.yml             # Pooler setup playbook
│   └── ansible-inventory.ini         # Pooler inventory
└── docs/
    ├── ANSIBLE_SETUP.md
    └── README_ANSIBLE.md
```

## Requirements

- Python 3.8+
- Ansible 2.9+
- PostgreSQL 16/17/18
- Root/sudo access (for installation)

## Installation of Prerequisites

```bash
# Install Ansible
pip3 install ansible

# Install PostgreSQL repository (RHEL/Rocky)
sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm

# Install PostgreSQL repository (Ubuntu/Debian)
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt-get update
```

## Advanced Usage

### Multi-Server Setup

1. Edit `conf/cluster-inventory.ini` with actual server IPs:

```ini
[primary]
pg-primary ansible_host=192.168.1.10 ansible_user=postgres

[replicas]
pg-replica1 ansible_host=192.168.1.11 ansible_user=postgres
pg-replica2 ansible_host=192.168.1.12 ansible_user=postgres
```

2. Setup SSH keys for passwordless access:

```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id postgres@192.168.1.10
ssh-copy-id postgres@192.168.1.11
ssh-copy-id postgres@192.168.1.12
```

3. Run setup:

```bash
./cluster.py --setup-postgres --version 17 --no-password
```

### Custom Configuration

Create a config file `my-cluster.yaml`:

```yaml
postgres:
  version: 17
  port: 5432
  replication_user: replicator
  replication_password: mypassword

pgraft:
  enabled: true
  cluster_name: production
  
poolers:
  pgbalancer:
    enabled: true
    port: 9999
  pgbouncer:
    enabled: true
    port: 9997
```

Use it:

```bash
./cluster.py --config my-cluster.yaml --setup-postgres
```

## Monitoring

### Health Check Report

```bash
# Run health check
./cluster.py --health-check

# View saved report
cat log/health_check_*.json
```

Example output:

```json
{
  "timestamp": "2025-10-09T03:30:00",
  "postgres": {
    "port_5432": true,
    "port_5433": true,
    "port_5434": true
  },
  "replication": {
    "active_replicas": 2
  },
  "poolers": {
    "pgbalancer": true,
    "pgbouncer": true,
    "pgpool2": false
  }
}
```

### Replication Lag Monitoring

```sql
-- On primary
SELECT 
    application_name,
    client_addr,
    state,
    sync_state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS send_lag,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS write_lag
FROM pg_stat_replication;

-- On replica
SELECT 
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;
```

## Troubleshooting

### Replication Not Working

```bash
# Check replication slots
psql -h localhost -p 5432 -U postgres -c "SELECT * FROM pg_replication_slots;"

# Check replica connection
psql -h localhost -p 5433 -U postgres -c "SELECT pg_is_in_recovery();"

# View logs
./cluster.py --logs postgres --lines 100
```

### Pooler Won't Start

```bash
# Check if port is in use
sudo ss -tlnp | grep 9999

# Kill existing process
pkill -9 pgbalancer

# Check logs
./cluster.py --logs pgbalancer --lines 50
```

### pgraft Not Working

```bash
# Check if extension is installed
psql -h localhost -p 5432 -U postgres -c "SELECT * FROM pg_extension WHERE extname = 'pgraft';"

# Check pgraft status
./cluster.py --pgraft-status

# Check pgraft logs
tail -f /var/lib/pgsql/17/data/log/postgresql-*.log | grep pgraft
```

## Examples

### Example 1: Local Testing (Single Machine)

```bash
# Setup 3-node cluster on localhost
./cluster.py --setup-postgres --version 17

# Check status
./cluster.py --postgres-status

# Test failover
./cluster.py --test-failover
```

### Example 2: Production Setup with pgraft

```bash
# Setup with automatic failover
./cluster.py --setup-postgres --version 17 --pgraft

# Monitor cluster
watch -n 5 './cluster.py --health-check'

# Setup poolers
./cluster.py --setup-poolers
./cluster.py --start all
```

### Example 3: Pooler Comparison

```bash
# Setup all poolers
./cluster.py --setup-poolers

# Start them
./cluster.py --start all

# Test connections
./cluster.py --test-poolers

# Run benchmarks (see ../benchmark/ directory)
cd ../../benchmark/scripts
./benchmark.py --run --poolers pgbalancer pgbouncer --duration 60
```

## Integration with Benchmark Suite

This cluster manager integrates seamlessly with the benchmark suite:

```bash
# 1. Setup PostgreSQL cluster
cd cluster/scripts
./cluster.py --setup-postgres --version 17

# 2. Setup poolers
./cluster.py --setup-poolers
./cluster.py --start all

# 3. Run benchmarks
cd ../../benchmark/scripts
./benchmark.py --setup --init --run --t 60 --poolers pgbalancer
```

## Contributing

Contributions welcome! Please:
1. Test on Rocky Linux, Ubuntu, and macOS
2. Follow PostgreSQL best practices
3. Update documentation
4. Add tests for new features

## License

MIT License - See LICENSE file for details

## Support

- Documentation: https://pgelephant.com
- Issues: https://github.com/pgelephant/pge/issues
- Community: https://discord.gg/pgelephant

---

**Made with ❤️ by pgElephant, Inc.**

