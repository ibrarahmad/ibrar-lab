# PostgreSQL Pooler Benchmark Suite

A comprehensive benchmarking tool for PostgreSQL connection poolers including pgpool2, pgbalancer, pgbouncer, and pgcat.

## Features

- **Multi-Pooler Support**: Test pgpool2, pgbalancer, pgbouncer, and pgcat
- **Comprehensive Tests**: Single query, concurrent connections, and load balancing tests
- **Detailed Metrics**: QPS, latency, success rate, memory usage, CPU usage
- **JSON Reports**: Detailed results in JSON format for analysis
- **Configurable**: Customizable test duration, connection counts, and parameters

## Quick Start

### Prerequisites

```bash
# Install Python dependencies
pip3 install asyncpg psycopg2-binary

# Ensure PostgreSQL is running
sudo systemctl start postgresql
```

### Basic Usage

```bash
# Run benchmark with default settings
python3 benchmark.py

# Run specific poolers
python3 benchmark.py --poolers pgbalancer pgbouncer

# Run specific tests
python3 benchmark.py --tests single_query concurrent_connections

# Custom duration and connections
python3 benchmark.py --duration 60 --max-connections 50
```

### Using the Runner Script

```bash
# Run comprehensive benchmark suite
./run_benchmark.sh
```

## Test Types

### 1. Single Query Test
- **Purpose**: Measure basic query performance
- **Method**: Continuous `SELECT 1` queries
- **Metrics**: QPS, response time, success rate

### 2. Concurrent Connections Test
- **Purpose**: Test connection pooling under load
- **Method**: Multiple concurrent connections with sleep queries
- **Metrics**: Connection handling, resource usage

### 3. Load Balancing Test
- **Purpose**: Verify load distribution across backends
- **Method**: Queries that identify server addresses
- **Metrics**: Load distribution, backend utilization

## Configuration

### Command Line Options

```bash
--poolers {pgpool2,pgbalancer,pgbouncer,pgcat}  # Poolers to test
--tests {single_query,concurrent_connections,load_balancing}  # Tests to run
--duration DURATION  # Test duration in seconds (default: 30)
--host HOST  # PostgreSQL host (default: localhost)
--port PORT  # Pooler port (default: 9999)
--database DATABASE  # Database name (default: postgres)
--user USER  # Database user (default: postgres)
--password PASSWORD  # Database password
--max-connections MAX_CONNECTIONS  # Max connections (default: 20)
--output OUTPUT  # Output file (default: benchmark_report.json)
```

### YAML Configuration

Create `benchmark_config.yaml`:

```yaml
test_duration: 30
max_connections: 20
postgresql:
  host: localhost
  port: 5432
  database: postgres
  user: postgres
  password: ""

poolers:
  pgbalancer:
    enabled: true
    port: 9998
  pgbouncer:
    enabled: true
    port: 9997
```

## Output

### JSON Report

The benchmark generates detailed JSON reports with:

```json
{
  "timestamp": "2025-10-07 18:09:28",
  "summary": {
    "single_query": {
      "best_qps": {
        "pooler": "pgbalancer",
        "qps": 1250.5
      },
      "best_latency": {
        "pooler": "pgbouncer",
        "avg_response_time": 0.002
      }
    }
  },
  "detailed_results": [...]
}
```

### Console Output

```
BENCHMARK SUMMARY
================================================================================

SINGLE_QUERY:
  Best QPS: pgbalancer (1250.50 QPS)
  Best Latency: pgbouncer (2.00ms)
  Best Success Rate: pgbalancer (99.95%)
  Best Memory: pgbouncer (15.20MB)
```

## Pooler Setup

### pgbalancer

```yaml
---
network:
  listen_addresses: localhost
  port: 9998

connection_pool:
  num_init_children: 20
  max_pool: 4

backends:
  - hostname: localhost
    port: 5432
    weight: 1
```

### pgbouncer

```ini
[databases]
postgres = host=localhost port=5432 dbname=postgres

[pgbouncer]
listen_addr = localhost
listen_port = 9997
pool_mode = transaction
max_client_conn = 40
default_pool_size = 20
```

### pgpool2

```conf
listen_addresses = 'localhost'
port = 9999
num_init_children = 20
max_pool = 4
backend_hostname0 = 'localhost'
backend_port0 = 5432
backend_weight0 = 1
```

## Performance Metrics

### Key Metrics

- **QPS (Queries Per Second)**: Throughput measurement
- **Latency**: Response time (avg, min, max, p95, p99)
- **Success Rate**: Percentage of successful queries
- **Memory Usage**: RAM consumption
- **CPU Usage**: CPU utilization

### Benchmarking Best Practices

1. **Consistent Environment**: Use same hardware and PostgreSQL version
2. **Warm-up Period**: Allow poolers to stabilize before testing
3. **Multiple Runs**: Run tests multiple times for accuracy
4. **Resource Monitoring**: Monitor system resources during tests
5. **Clean State**: Ensure clean state between tests

## Troubleshooting

### Common Issues

1. **Connection Refused**: Ensure PostgreSQL is running
2. **Pooler Start Failed**: Check configuration files
3. **Permission Denied**: Run with appropriate user permissions
4. **Port Conflicts**: Use different ports for each pooler

### Debug Mode

```bash
# Enable debug logging
export PYTHONPATH=.
python3 -c "import logging; logging.basicConfig(level=logging.DEBUG)"
python3 benchmark.py --poolers pgbalancer
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: [Repository Issues]
- Documentation: [Project Documentation]
- Email: support@pgelephant.com
