# PostgreSQL Management Script (pg_script.py)

A Python script for managing PostgreSQL instances, including compilation from source, initialization, replication setup, and operational control (start, stop, restart, cleanup, destroy).

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

The `pg_script.py` uses a configuration file named `pg.conf` (in INI format) located in the same directory as the script.

**Structure:**

*   **`[DEFAULT]` Section:** Defines default values applicable to all nodes unless overridden in a node-specific section.
    *   `source_path`: Absolute path to the directory containing PostgreSQL source code folders (e.g., `/usr/local/src/postgres/`).
    *   `base_data_directory`: Base directory where data directories for each node will be created (e.g., `/var/lib/pgsql/nodes/`). A subdirectory named after the node (e.g., `n1`) will be created here.
    *   `base_log_directory`: Base directory where log files for each node will be stored (e.g., `/var/log/pgsql/nodes/`). Logs will be named `[node_name].log`.
    *   `base_bin_directory`: Base directory where compiled PostgreSQL versions will be installed (e.g., `/opt/postgres/`). Binaries for a version (e.g., 17) will be in a subdirectory like `pgsql-17`.

*   **Node-Specific Sections (e.g., `[n1]`, `[n2]`):** Define configuration for individual PostgreSQL nodes.
    *   `port`: The port number for this PostgreSQL instance (e.g., `5432`). **Required.**
    *   `pg_version`: The PostgreSQL version string (e.g., `17`, `16.3`) that this node should use. This tells the script where to find the binaries (relative to `base_bin_directory`/pgsql-<version>/bin) for operations like `initdb`, `start`, etc. Ensure this matches a compiled version if you used the `compile` command.
    *   `host`: (Optional) Hostname or IP address for the node. Defaults to `localhost`. Useful for replication if nodes are on different interfaces/machines.
    *   `replication_user`: (Optional, for primary nodes) The PostgreSQL username to be used for replication connections by replicas. Defaults to `postgres`.
    *   `pgsetting_*`: (Optional) Custom settings to be added to the node's `postgresql.auto.conf` during `initdb`. Example: `pgsetting_max_connections = 150`.

**Example `pg.conf`:**
```ini
[DEFAULT]
source_path = /usr/local/pgsql/source
base_data_directory = /var/lib/pgsql/pgnodes
base_log_directory = /var/log/pgsql/pgnodes
base_bin_directory = /opt/pgversions

[n1]
port = 5432
pg_version = 17
host = localhost
# Settings for n1's postgresql.auto.conf
pgsetting_max_connections = 100
pgsetting_shared_buffers = 256MB
pgsetting_wal_buffers = 16MB

[n2]
port = 5433
pg_version = 17
host = localhost
# n2 might be a replica, so fewer custom settings typically needed here initially
```

## Usage

Run the script from its directory: `python3 pg_script.py <command> [options]` or `./pg_script.py <command> [options]` (if executable).

**Global Options:**
*   `--help`: Show the main help message and exit.

**Commands:**

Use `pg_script.py <command> --help` for detailed help on a specific command.

*   **`compile <node_name> [--pg VERSION]`**
    *   Compiles PostgreSQL from source.
    *   `<node_name>`: Node identifier from `pg.conf` used to get `source_path` and `base_bin_directory`. Also used for logging context. The compiled binaries are not exclusively tied to this node after compilation.
    *   `--pg VERSION`: PostgreSQL version to compile (e.g., `17`, `16.3`). Defaults to "17" (or as set by `DEFAULT_PG_VERSION` in the script). The script will look for a source folder like `postgresql-VERSION` under `source_path`.
    *   **Important:** After compiling, update the `pg_version` for the relevant node(s) in `pg.conf` to this `VERSION` if you want other commands (`initdb`, `start`, etc.) to use these newly compiled binaries for that node.

*   **`initdb <node_name>`**
    *   Initializes a new PostgreSQL cluster for the specified node.
    *   `<node_name>`: The node (defined in `pg.conf`) to initialize. The script uses the node's `data_directory` (derived from `base_data_directory`), `port`, and `pg_version` (to find `initdb` executable).
    *   Any `pgsetting_*` values in the node's section in `pg.conf` are applied to `postgresql.auto.conf`.

*   **`replica <primary_node> <replica_node> [--sync|--async]`**
    *   Sets up `<replica_node>` as a streaming read replica of `<primary_node>`.
    *   `<primary_node>`: Name of the primary node. Must be initialized, running, and configured for replication (e.g., `wal_level=replica`, `max_wal_senders > 0`, correct `pg_hba.conf`).
    *   `<replica_node>`: Name of the new node to become the replica. Its data directory must be empty. Its `pg.conf` settings (port, pg_version for `pg_basebackup`) are used.
    *   `--async`: (Default) Configures asynchronous replication.
    *   `--sync`: Configures for synchronous replication. **Note:** This option mainly sets up the replica side. You must manually configure `synchronous_standby_names` in the primary's `postgresql.conf` and restart/reload the primary.
    *   Uses `pg_basebackup` for the setup.

*   **`start <node_name>`**
    *   Starts the PostgreSQL server for an initialized node.
    *   Uses `pg_ctl start`. Server logs are directed to `<base_log_directory>/<node_name>.log`.

*   **`stop <node_name>`**
    *   Stops the PostgreSQL server for the specified node.
    *   Uses `pg_ctl stop -m fast`.

*   **`restart <node_name>`**
    *   Restarts the PostgreSQL server for the specified node.
    *   Uses `pg_ctl restart -m fast`.

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
    *   PostgreSQL server logs when started by `pg_script.py start/restart` (due to `pg_ctl -l` option).

## Output Indicators

The script uses visual indicators for operations:
*   `✓` (Green Tick): Indicates a successful operation or step.
*   `✗` (Red Cross): Indicates a failed operation or step. The script usually exits upon failure.

## Example Workflow

1.  **Configure `pg.conf`**: Set paths and define nodes `n1` (primary) and `n2` (replica).
    ```ini
    [DEFAULT]
    source_path = /path/to/postgres_sources
    base_data_directory = /var/lib/pgdata
    base_log_directory = /var/log/pglogs
    base_bin_directory = /opt/pginstalls

    [n1]
    port = 5432
    pg_version = 17
    # Primary specific settings for replication in postgresql.auto.conf
    pgsetting_wal_level = replica
    pgsetting_max_wal_senders = 10
    pgsetting_archive_mode = off # Or 'on' with archive_command for PITR

    [n2]
    port = 5433
    pg_version = 17
    ```
2.  **Download PostgreSQL 17 source** to `/path/to/postgres_sources/postgresql-17.0` (or similar).
3.  **Compile PostgreSQL 17** (if not already installed at `/opt/pginstalls/pgsql-17`):
    `./pg_script.py compile n1 --pg 17`
4.  **Initialize Primary (n1):**
    `./pg_script.py initdb n1`
5.  **Start Primary (n1):**
    `./pg_script.py start n1`
    *(At this point, ensure primary's `pg_hba.conf` allows replication connections from replica's host for the replication user)*
6.  **Initialize Replica (n2) - but as a replica, so we use the replica command:**
    *(Ensure n2's data directory is empty or does not exist)*
    `./pg_script.py replica n1 n2`
7.  **Start Replica (n2):**
    `./pg_script.py start n2`
8.  Check logs in `/var/log/pglogs/n1.log` and `/var/log/pglogs/n2.log`.
