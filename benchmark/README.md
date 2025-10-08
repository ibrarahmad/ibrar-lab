# pgbalancer Benchmark Suite

This directory contains comprehensive benchmarking tools for PostgreSQL poolers including pgpool2, pgbalancer, pgbouncer, and pgcat.

## Directory Structure

```
benchmark/
├── README.md                    # This file
├── benchmark.py                 # General benchmark script
├── run_benchmark.sh             # General benchmark runner
├── benchmark_config.yaml        # General benchmark configuration
├── BENCHMARK_README.md          # General benchmark documentation
├── tpcc_benchmark.py            # TPC-C benchmark script
├── run_tpcc_benchmark.sh        # TPC-C benchmark runner
├── tpcc_config.yaml             # TPC-C benchmark configuration
├── TPCC_BENCHMARK_README.md     # TPC-C benchmark documentation
├── example_output.txt           # Example output format
└── tabular_example.txt          # Tabular output example
```

## Quick Start

### General Benchmarking
```bash
cd benchmark/
./run_benchmark.sh --poolers pgbalancer pgbouncer --tests single_query concurrent_connections
```

### TPC-C Benchmarking
```bash
cd benchmark/
sudo ./run_tpcc_benchmark.sh --install
./run_tpcc_benchmark.sh --setup
./run_tpcc_benchmark.sh --init
./run_tpcc_benchmark.sh --run --t 300 --n 16
```

## Features

- **Multi-Pooler Support**: pgpool2, pgbalancer, pgbouncer, pgcat
- **Multiple Test Types**: Single query, concurrent connections, load balancing
- **TPC-C Workload**: Industry-standard OLTP benchmark with sysbench
- **Tabular Output**: Professional tabular format for easy comparison
- **Modular Design**: Separate install, setup, init, and run commands
- **Comprehensive Metrics**: TPS, QPS, latency, errors, memory, CPU

## Documentation

- `BENCHMARK_README.md` - General benchmark documentation
- `TPCC_BENCHMARK_README.md` - TPC-C benchmark documentation

## Configuration

- `benchmark_config.yaml` - General benchmark configuration
- `tpcc_config.yaml` - TPC-C benchmark configuration

## Examples

See `example_output.txt` and `tabular_example.txt` for output format examples.
