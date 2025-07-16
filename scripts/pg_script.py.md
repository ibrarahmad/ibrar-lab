# pg_script.py

This script is a command-line tool for managing multi-node PostgreSQL clusters for testing or development purposes. Each node is defined in a configuration file (`pg.conf` by default) and has its own port, data directory, log file, and binaries.

## Usage

```bash
./pg_script.py [options] <command> [command-options]
```

### Options

- `-v`, `--verbose`: Enable verbose output.
- `-c`, `--config`: Path to the configuration file (default: `pg.conf`).

### Commands

- `status <node_name>`: Check if a node is running.
- `start <node_name>`: Start PostgreSQL for a node.
- `stop <node_name>`: Stop PostgreSQL for a node.
- `initdb <node_name>`: Initialize a PostgreSQL cluster for a node.
- `compile <node_name> [--pg <version>]`: Compile PostgreSQL from source for a node.
- `destroy <node_name>`: Stop and delete a node's data directory.
- `cleanup <node_name>`: Destroy and re-initialize a node.
- `replica <primary_node> <replica_node> [--sync]`: Create a streaming replica from a primary node.

### Configuration

The script uses a configuration file (e.g., `pg.conf`) to define the nodes. Here is an example:

```ini
[DEFAULT]
source_path = /path/to/postgres/source
base_data_directory = /path/to/data
base_log_directory = /path/to/logs
base_bin_directory = /path/to/binaries

[n1]
port = 5432

[n2]
port = 5433
```

Each section (e.g., `[n1]`) defines a node. The configuration from the `[DEFAULT]` section is inherited by each node.
