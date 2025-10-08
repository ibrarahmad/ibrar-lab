# Ansible Setup for pgbalancer Benchmarking

Automated setup for pgbalancer benchmark environment using Ansible.

## Quick Start

```bash
cd /home/pgedge/pge/benchmark
./setup-with-ansible.sh
```

## What Gets Installed

### System Dependencies
- PostgreSQL 13 with contrib modules
- Python 3 with development headers
- libyaml for YAML parsing
- memcached for query caching
- GCC and build tools

### Python Packages
- `asyncpg` - Async PostgreSQL driver
- `psycopg2-binary` - PostgreSQL adapter
- `pyyaml` - YAML parser
- `tabulate` - Table formatting

### pgbalancer
- Builds from source in `/home/pgedge/pge/pgbalancer`
- Installs config to `/usr/local/etc/pgbalancer.yaml`
- Creates log directories

### PostgreSQL Setup
- Initializes data directory
- Configures authentication (trust for localhost)
- Creates benchmark database
- Starts and enables service

## Files Created

```
/home/pgedge/pge/benchmark/
├── ansible-setup.yml          # Ansible playbook
├── ansible-inventory.ini      # Inventory file
├── setup-with-ansible.sh      # Setup script
├── ANSIBLE_SETUP.md          # This file
├── conf/                      # Configuration files
│   ├── pgbalancer.yaml
│   └── pool_passwd
├── log/                       # Log directory
└── results/                   # Benchmark results
```

## Usage Options

### Full Setup (Default)
```bash
./setup-with-ansible.sh
```
Installs everything and configures the system.

### Install Dependencies Only
```bash
./setup-with-ansible.sh --deps-only
```
Installs system and Python packages only.

### Build and Configure Only
```bash
./setup-with-ansible.sh --build-only
```
Builds pgbalancer and sets up configuration.

### Verify Installation
```bash
./setup-with-ansible.sh --verify
```
Checks if everything is properly installed.

### Run Specific Ansible Tags
```bash
ansible-playbook -i ansible-inventory.ini ansible-setup.yml --tags=build,config --ask-become-pass
```

Available tags:
- `deps` - System dependencies
- `python` - Python packages
- `postgres` - PostgreSQL setup
- `build` - Build pgbalancer
- `config` - Configuration files
- `dirs` - Create directories
- `sysbench` - Install sysbench (optional)
- `verify` - Verification

## Running Benchmarks

### 1. Start pgbalancer

```bash
cd /home/pgedge/pge
./pgbalancer/src/pgbalancer -n -f pgbalancer.yaml -d &
```

### 2. Run Simple Benchmark

```bash
cd /home/pgedge/pge/benchmark
python3 benchmark.py --poolers pgbalancer --duration 30
```

### 3. Run Comprehensive Tests

```bash
./run_benchmark.sh --poolers pgbalancer --tests single_query concurrent_connections
```

### 4. View Configuration

```bash
../pgbalancer/src/pgbalancer --show-config -f ../pgbalancer.yaml
```

## Benchmark Tests Available

### Single Query Test
```bash
python3 benchmark.py --poolers pgbalancer --tests single_query --duration 60
```
- Measures QPS (Queries Per Second)
- Tests basic pooler performance
- Records latency metrics

### Concurrent Connections
```bash
python3 benchmark.py --poolers pgbalancer --tests concurrent_connections --max-connections 50
```
- Tests connection pooling
- Measures resource usage
- Validates connection handling

### Load Balancing
```bash
python3 benchmark.py --poolers pgbalancer --tests load_balancing
```
- Verifies load distribution
- Tests backend utilization
- Validates failover behavior

## Troubleshooting

### Ansible Not Found
```bash
sudo dnf install -y ansible
# or
sudo yum install -y ansible
```

### Permission Denied
The script will ask for sudo password. If it fails:
```bash
sudo ansible-playbook -i ansible-inventory.ini ansible-setup.yml
```

### PostgreSQL Won't Start
```bash
sudo systemctl status postgresql-13
sudo journalctl -u postgresql-13 -n 50
```

### Build Fails
```bash
cd /home/pgedge/pge/pgbalancer
make clean
make -j4
```

### Port Already in Use
```bash
# Check what's using port 9999
sudo ss -tlnp | grep 9999

# Kill existing pgbalancer
pkill -9 pgbalancer
```

## Configuration Files

### pgbalancer.yaml
Location: `/home/pgedge/pge/benchmark/conf/pgbalancer.yaml`

Key settings for benchmarking:
```yaml
backend_clustering_mode: streaming_replication
listen_addresses: 'localhost'
port: 9999
num_init_children: 32
max_pool: 4
backend_hostname0: 'localhost'
backend_port0: 5432
```

### config.yaml
Benchmark configuration:
```yaml
poolers:
  pgbalancer:
    enabled: true
    port: 9998
    config_file: "pgbalancer.yaml"

threads: 16
time: 60
```

## Advanced Usage

### Run Multiple Poolers
```bash
# Enable pgbouncer in config.yaml
python3 benchmark.py --poolers pgbalancer pgbouncer
```

### Custom Test Duration
```bash
python3 benchmark.py --poolers pgbalancer --duration 300 --max-connections 100
```

### Output to File
```bash
python3 benchmark.py --poolers pgbalancer --output results/pgbalancer_benchmark.json
```

### Run Specific PostgreSQL Port
```bash
python3 benchmark.py --poolers pgbalancer --host localhost --port 9999
```

## Monitoring During Benchmarks

### Watch pgbalancer Status
```bash
watch -n 1 'psql -h localhost -p 9999 -U postgres -c "SHOW pool_nodes;"'
```

### Monitor System Resources
```bash
# CPU and Memory
top -p $(pgrep pgbalancer | tr '\n' ',' | sed 's/,$//')

# Network
ss -s

# Disk I/O
iostat -x 1
```

### Check Logs
```bash
tail -f /home/pgedge/pge/benchmark/log/pgbalancer.log
```

## Cleanup

### Stop pgbalancer
```bash
pkill pgbalancer
```

### Remove Benchmark Data
```bash
cd /home/pgedge/pge/benchmark
rm -rf results/* log/*
```

### Uninstall (if needed)
```bash
sudo systemctl stop postgresql-13
sudo dnf remove postgresql13-*
```

## Performance Tuning

### PostgreSQL
Edit `/var/lib/pgsql/13/data/postgresql.conf`:
```
shared_buffers = 256MB
max_connections = 200
work_mem = 4MB
```

### pgbalancer
Edit config for higher performance:
```yaml
num_init_children: 64
max_pool: 8
connection_cache: true
```

### System
```bash
# Increase file descriptors
ulimit -n 65535

# Tune kernel parameters
sudo sysctl -w net.core.somaxconn=1024
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=2048
```

## Support

- Documentation: `/home/pgedge/pge/benchmark/README.md`
- TPC-C Benchmarks: `/home/pgedge/pge/benchmark/TPCC_BENCHMARK_README.md`
- Configuration: `./pgbalancer/src/pgbalancer --show-config`

## License

MIT License - see LICENSE file for details.

