# PostgreSQL Management Script (pg_script.py)

A Python script for managing PostgreSQL instances, including compilation from source, initialization, replication setup, and operational control (start, stop, status, cleanup, destroy).

## Prerequisites

1.  **Python 3.x:** Ensure Python 3.6 or higher is installed.
2.  **System Dependencies:** Run the `pre_req.sh` script to install necessary packages for compiling PostgreSQL and running the script:
    ```bash
    bash ./pre_req.sh
    ```
    This script typically installs `build-essential`, `libreadline-dev`, `zlib1g-dev`, `python3-pip`, etc., on Debian/Ubuntu based systems. Adjust for other Linux distributions if necessary.
3.  **PostgreSQL Source Code:**
    *   Download the desired PostgreSQL source tarball(s) (e.g., `postgresql-17.0.tar.gz`) from the [PostgreSQL website](https://www.postgresql.org/ftp/source/).
    *   Extract the source code into a directory. For example, if you extract `postgresql-17.0.tar.gz`, it will create a `postgresql-17.0` directory.
    *   The parent directory containing these version-specific source folders (e.g., `/usr/local/pgsql/source/`) should be specified as `source_path` in your `pg.conf` file.

## Configuration (`pg.conf`)

The `pg_script.py` uses a configuration file named `pg.conf` (in INI format). By default, it looks for this file in the current directory from which the script is executed. You can specify a different path using the `-c` or `--config` command-line option.

**Structure:**

*   **`[DEFAULT]` Section:** Defines default values applicable to all nodes unless overridden in a node-specific section. Paths can be absolute or relative to the script's current working directory.
    *   `source_path`: Path to the directory containing PostgreSQL source code folders (e.g., `/path/to/postgres_sources/` or `../postgres_sources/`).
    *   `base_data_directory`: Base directory where data directories for each node will be created (e.g., `./data/nodes/` or `/var/lib/pgsql/nodes/`). A subdirectory named after the node (e.g., `n1`) will be created here.
    *   `base_log_directory`: Base directory where log files for each node will be stored (e.g., `./logs/` or `/var/log/pgsql/nodes/`). Logs will be named `[node_name].log`.
    *   `base_bin_directory`: Base directory where compiled PostgreSQL versions will be installed (e.g., `/opt/pgversions/` or `./pgversions/`). Binaries for a version (e.g., 17) will be in a subdirectory like `pgsql-17`.
    *   `pg_version`: (Optional) Default PostgreSQL version string (e.g., `17`) to use if not specified in a node's section. The script defaults to "17" if not set here or in the node's config.

*   **Node-Specific Sections (e.g., `[n1]`, `[n2]`):** Define configuration for individual PostgreSQL nodes. These inherit from `[DEFAULT]`.
    *   `port`: The port number for this PostgreSQL instance (e.g., `5432`). **Required.**
    *   `pg_version`: (Optional) The PostgreSQL version string (e.g., `17`, `16.3`) for this node. Overrides `[DEFAULT].pg_version`. Used to locate binaries.
    *   `ip`: (Optional) IP address for the node. Defaults to `127.0.0.1` in some contexts (e.g., replication setup if not specified).
    *   `user`: (Optional) PostgreSQL username, often used for initial connections or administrative tasks on the node. (e.g., `postgres`, `pgedge`).
    *   `db`: (Optional) Default database name for connections. (e.g., `postgres`).
    *   Note on replication users: The script primarily uses a hardcoded user `replicator` (with password `replicator`) for setting up streaming replication via `pg_basebackup` and for entries in `pg_hba.conf`. The `user` field might be used by the script to connect to the primary to create roles if they don't exist.

*   **`[postgresql.auto.conf.nodename]` Sections (e.g., `[postgresql.auto.conf.n1]`):**
    *   This section defines custom settings that will be written directly into the `postgresql.auto.conf` file for the specified node (`nodename`) during `initdb`.
    *   Each key-value pair in this section becomes a line in `postgresql.auto.conf`. For example, `max_connections = 150` becomes `max_connections = 150`.
    *   This replaces the old `pgsetting_*` mechanism.

**Example `pg.conf`:**
```ini
[DEFAULT]
source_path = /path/to/pgsources  # Or relative: sources/
base_data_directory = ./data      # Data directories will be ./data/n1, ./data/n2 etc.
base_log_directory = ./logs       # Log files will be ./logs/n1.log, etc.
base_bin_directory = ./pginstalls # Binaries at ./pginstalls/pgsql-17, etc.
pg_version = 17                   # Default PG version for nodes

[n1]
port = 5432
ip = 127.0.0.1
user = pgedge
# pg_version = 17 (inherits from DEFAULT)

[postgresql.auto.conf.n1]
# Custom settings for n1's postgresql.auto.conf
listen_addresses = '*'
max_connections = 100
shared_buffers = 256MB
wal_level = replica             # Important for primary node in replication
max_wal_senders = 10            # Important for primary node in replication
# archive_mode = on             # Example for PITR
# archive_command = 'cp %p /path/to/archive/%f'

[n2]
port = 5433
ip = 127.0.0.1
user = pgedge
# pg_version = 17 (inherits from DEFAULT)

[postgresql.auto.conf.n2]
# Custom settings for n2's postgresql.auto.conf
listen_addresses = '*'
# For a replica, many settings are mirrored or determined by recovery process
# specific replica settings like hot_standby might go here.
hot_standby = on
```

## Usage

It's recommended to run the script from the root of the repository. The script itself is located in the `scripts/` directory.
Example: `python3 scripts/pg_script.py <command> [options]` or `./scripts/pg_script.py <command> [options]` (if executable and you are in the repo root).

If you are in the `scripts/` directory, you can run it as `python3 pg_script.py <command> [options]` or `./pg_script.py <command> [options]`.

**Global Options:**
*   `--help`: Show the main help message and exit.
*   `-c CONFIG_FILE, --config CONFIG_FILE`: Path to the configuration file (default: `pg.conf` in the current working directory).
*   `-v, --verbose`: Enable verbose output, showing commands being run and their immediate output.

**Commands:**

Use `scripts/pg_script.py <command> --help` for detailed help on a specific command.

*   **`compile <node_name> [--pg VERSION]`**
    *   Compiles PostgreSQL from source.
    *   `<node_name>`: Node identifier from `pg.conf` used to get `source_path` and `base_bin_directory`. Also used for logging context. The compiled binaries are not exclusively tied to this node after compilation.
    *   `--pg VERSION`: PostgreSQL version to compile (e.g., `17`, `16.3`). Defaults to "17" (or as set by `DEFAULT_PG_VERSION` in the script). The script will look for a source folder like `postgresql-VERSION` under `source_path`.
    *   **Important:** After compiling, update the `pg_version` for the relevant node(s) in `pg.conf` to this `VERSION` if you want other commands (`initdb`, `start`, etc.) to use these newly compiled binaries for that node.

*   **`initdb <node_name>`**
    *   Initializes a new PostgreSQL cluster for the specified node.
    *   `<node_name>`: The node (defined in `pg.conf`) to initialize. Uses the node's `data_directory`, `port`, and `pg_version`.
    *   PostgreSQL settings from the `[postgresql.auto.conf.nodename]` section in `pg.conf` are written to the node's `postgresql.auto.conf` file.
    *   Modifies the node's `pg_hba.conf` to:
        *   Trust local connections (IPv4 and IPv6) for all users.
        *   Allow replication connections from localhost for the `replicator` user.

*   **`replica <primary_node> <replica_node> [--sync|--async]`**
    *   Sets up `<replica_node>` as a streaming read replica of `<primary_node>`.
    *   `<primary_node>`: Name of the primary node. Must be initialized and running. The script will attempt to create `postgres` and `replicator` roles (with password 'replicator') on the primary if they don't exist, and then reload the primary. Ensure the primary's `pg_hba.conf` allows connection from the script/replica for this (typically handled if primary was also set up with `initdb` from this script). The primary's `postgresql.auto.conf` should have `wal_level = replica` (or higher) and adequate `max_wal_senders`.
    *   `<replica_node>`: Name of the new node to become the replica. Its data directory must be empty. Its `pg.conf` settings (port, pg_version, etc.) are used.
    *   `--async`: (Default) Configures asynchronous replication.
    *   `--sync`: Configures for synchronous replication. The script will note that `synchronous_standby_names` needs manual configuration on the primary.
    *   Uses `pg_basebackup` with the user `replicator` and password `replicator` (this password can be overridden by setting `replicator_password=yourpass` in the primary node's section in `pg.conf`).
    *   Writes `primary_conninfo` to the replica's `postgresql.auto.conf`.
    *   If the `<replica_node>` name contains "replica", `primary_slot_name = '<replica_node>_slot'` is also added to its `postgresql.auto.conf`.
    *   Any other settings from `[postgresql.auto.conf.replica_node]` are also applied to the replica.

*   **`start <node_name>`**
    *   Starts the PostgreSQL server for an initialized node.
    *   Uses `pg_ctl start`. Server logs are directed to `<base_log_directory>/<node_name>.log`.

*   **`stop <node_name>`**
    *   Stops the PostgreSQL server for the specified node.
    *   Uses `pg_ctl stop -m fast`.

*   **`status <node_name>`**
    *   Checks and prints the running status of the PostgreSQL server for the specified node.
    *   Uses `pg_ctl status`.

*   **`cleanup <node_name>`**
    *   Resets a node: stops the server, completely removes its data directory, and then re-initializes a fresh cluster. Useful for starting over with a node.

*   **`destroy <node_name>`**
    *   Permanently removes a node: stops the server and completely deletes its data directory. This action is irreversible for the node's data.

## Logging

*   The script creates a main log directory (e.g., `logs/` or as configured by `base_log_directory` in `pg.conf`).
*   Each command operating on a node creates/appends to a node-specific log file within this directory (e.g., `logs/n1.log`, `logs/n2.log`).
*   These logs contain:
    *   Operations performed by `pg_script.py` itself.
    *   Output from PostgreSQL commands like `initdb`, `pg_ctl`.
    *   PostgreSQL server logs when started by `pg_script.py start` (due to the `-l` option passed to `pg_ctl start`).

## Output Indicators

The script uses visual indicators for operations:
*   `✓` (Green Tick): Indicates a successful operation or step.
*   `✗` (Red Cross): Indicates a failed operation or step. The script usually exits upon failure.

## Example Workflow

1.  **Configure `pg.conf`**: Create a `pg.conf` file (e.g., in your project root). Set paths and define nodes `n1` (primary) and `n2` (replica).
    ```ini
    [DEFAULT]
    source_path = ./pgsources             # e.g., download sources to project_root/pgsources/postgresql-17
    base_data_directory = ./data/nodes    # Node data will be in ./data/nodes/n1, etc.
    base_log_directory = ./logs           # Node logs will be in ./logs/n1.log, etc.
    base_bin_directory = ./pginstalls     # Compiled PG will be in ./pginstalls/pgsql-17
    pg_version = 17                       # Default version for nodes

    [n1]
    port = 5432
    ip = 127.0.0.1
    user = mypguser                       # Optional: user for admin tasks

    [postgresql.auto.conf.n1]
    listen_addresses = '*'
    wal_level = replica
    max_wal_senders = 10
    # Optional: for point-in-time recovery (PITR)
    # archive_mode = on
    # archive_command = 'cp %p /path/to/archive_dir/%f'

    [n2] # This will be a replica
    port = 5433
    ip = 127.0.0.1
    user = mypguser

    [postgresql.auto.conf.n2]
    listen_addresses = '*'
    hot_standby = on # Good practice for replicas
    ```
2.  **Download PostgreSQL 17 source** (if `pg_version = 17`) into the directory specified by `source_path` (e.g., `./pgsources/postgresql-17`).
    Example: `mkdir -p ./pgsources && wget -O - https://ftp.postgresql.org/pub/source/v17.0/postgresql-17.0.tar.bz2 | tar -jx -C ./pgsources` (adjust version as needed).
3.  **Compile PostgreSQL** (if not already installed at the location defined by `base_bin_directory` and `pg_version`):
    `./scripts/pg_script.py compile n1 --pg 17`
    *(This compiles PG version 17. The node `n1` is used for context like `source_path`)*
4.  **Initialize Primary (n1):**
    `./scripts/pg_script.py initdb n1`
    *(This creates the data directory, sets up `postgresql.auto.conf` from `[postgresql.auto.conf.n1]`, and configures `pg_hba.conf` for local trust and replication from `replicator` user.)*
5.  **Start Primary (n1):**
    `./scripts/pg_script.py start n1`
6.  **Set up Replica (n2):**
    *(Ensure n2's data directory `./data/nodes/n2` is empty or does not exist. The script will create it.)*
    `./scripts/pg_script.py replica n1 n2`
    *(This uses `pg_basebackup` from primary `n1` to replica `n2`, creates `primary_conninfo` in `n2`'s `postgresql.auto.conf`, and applies settings from `[postgresql.auto.conf.n2]`.)*
7.  **Start Replica (n2):**
    `./scripts/pg_script.py start n2`
8.  **Check Status (Optional):**
    `./scripts/pg_script.py status n1`
    `./scripts/pg_script.py status n2`
9.  Check logs in `./logs/n1.log` and `./logs/n2.log` (or as configured by `base_log_directory`).
