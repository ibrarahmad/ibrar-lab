# PostgreSQL Replication Setup Script

## Overview

This script automates the setup of PostgreSQL streaming replication (both asynchronous and synchronous) between a primary and a replica server. It performs the necessary configurations on the primary server, creates a replication user and slot, and then uses `pg_basebackup` to initialize the replica's data directory. The script is designed to be run from a control node or directly on the primary server.

## Prerequisites

Before running this script, ensure the following are met:

*   **Python:** Python 3.7+
*   **psycopg2:** The `psycopg2-binary` Python library must be installed (`pip install psycopg2-binary`).
*   **PostgreSQL:**
    *   A running PostgreSQL instance on the primary server.
    *   PostgreSQL client tools (especially `pg_basebackup`) must be installed and in the system's PATH on the machine where this script executes `pg_basebackup` (typically the primary or a control node that can access the primary and write to the replica's path if it's a shared/mounted location).
*   **Permissions:**
    *   The script needs credentials for a PostgreSQL superuser (or a user with rights to create roles, create replication slots, and modify `pg_hba.conf` and `postgresql.conf` through database queries if applicable, though this script modifies files directly).
    *   Sufficient OS permissions to:
        *   Read and write PostgreSQL configuration files (`postgresql.conf`, `pg_hba.conf`) on the primary.
        *   Restart the PostgreSQL service on the primary (typically requires `sudo`).
        *   Create the replica's data directory (`--replica-pgdata-path`) and write data into it (pg_basebackup). This path must be accessible from where the script runs.
        *   Run `sudo` for service restarts.

## Configuration

The script uses a layered configuration approach:
1.  **Command-Line Arguments:** Highest precedence.
2.  **Environment Variables:** Used as defaults for many command-line arguments if the argument is not provided.
3.  **Script Defaults:** Hardcoded defaults if neither CLI nor ENV var is set.

### Command-Line Arguments

The following arguments can be used to customize the script's behavior. You can also see these by running `python setup_replication.py --help`.

**PostgreSQL Common Settings:**
*   `--pg-version VERSION`: PostgreSQL version (e.g., '16'). Default: "16" or `PG_VERSION` env var.
*   `--pg-cluster-name NAME`: PostgreSQL cluster name (e.g., 'main'). Default: "main" or `PG_CLUSTER_NAME` env var.

**Primary Server Settings:**
*   `--primary-host HOST`: Primary server host. Default: "localhost" or `PG_PRIMARY_HOST` env var.
*   `--primary-port PORT`: Primary server port. Default: 5432 or `PG_PRIMARY_PORT` env var.
*   `--primary-db DBNAME`: Database name on primary for admin tasks. Default: "postgres" or `PG_DB_NAME` env var.
*   `--primary-user USER`: Admin user on primary. Default: "postgres" or `PG_ADMIN_USER` env var.
*   `--primary-password PASSWORD`: Password for admin user on primary. Default: value of `PG_ADMIN_PASSWORD` env var or None.
*   `--primary-psql-conf-path PATH`: Path to primary `postgresql.conf`. If not set, derived from version/cluster (e.g., `/etc/postgresql/16/main/postgresql.conf`).
*   `--primary-pg-hba-path PATH`: Path to primary `pg_hba.conf`. If not set, derived from version/cluster.
*   `--primary-service-name NAME`: Name of primary PostgreSQL service. If not set, derived (e.g., `postgresql@16-main`).

**Replica Server Settings:**
*   `--replica-pgdata-path PATH`: Path for replica's data directory. Default derived from PG_VERSION (e.g., `/var/lib/postgresql/16/replica_cluster_data`).
*   `--replica-ip-for-hba IP_ADDRESS`: Replica IP address for `pg_hba.conf` on primary. Default: "127.0.0.1" or `REPLICA_IP` env var.

**Replication Specific Settings:**
*   `--replication-user USER`: Replication username. Default: "repl_user" or `REPL_USER` env var.
*   `--replication-password PASSWORD`: Password for replication user. Default: value of `REPL_PASSWORD` env var or None.
*   `--replication-slot-name NAME`: Name for replication slot. Default: `{replication_user}_slot_physical`.
*   `--replication-type {async,sync}`: Replication type. Default: "async" or `REPLICATION_TYPE` env var.
*   `--sync-replica-app-name NAME`: Application name for synchronous replica (used if type is 'sync'). Default: "replica1_app_name" or `SYNC_REPLICA_NAME` env var. This name **must** be used in the replica's connection DSN (`application_name` parameter) if synchronous replication is chosen.

### Password Handling
Passwords (`--primary-password`, `--replication-password`) are optional arguments.
- If not provided via CLI, the script attempts to use the corresponding environment variables (`PG_ADMIN_PASSWORD`, `REPL_PASSWORD`).
- If still not found, and a password is required for an operation (e.g., database connection, `pg_basebackup`), that operation may fail unless other authentication methods (like a `~/.pgpass` file or `trust` authentication for local connections) are already configured for the respective PostgreSQL users. The script will issue a warning if these passwords are not explicitly set.

## Usage

1.  **Review Configuration:** Carefully check and update the default values in the script or provide them via environment variables / command-line arguments to match your environment.
2.  **Run the Script:** Execute the script, typically on the primary server or a control node with access to the primary and its configuration files.

    ```bash
    python setup_replication.py [OPTIONS]
    ```

**Example (Asynchronous Replication - common defaults):**
```bash
# Ensure PG_ADMIN_PASSWORD and REPL_PASSWORD environment variables are set, or provide via CLI
# export PG_ADMIN_PASSWORD="your_secure_admin_password"
# export REPL_PASSWORD="your_secure_replication_password"

python setup_replication.py \
    --pg-version 16 \
    --primary-user myadmin \
    --replication-user myrepluser \
    --replica-ip-for-hba 192.168.1.101 \
    --replica-pgdata-path /mnt/pgdata_replica
```

**Example (Synchronous Replication):**
```bash
# export PG_ADMIN_PASSWORD="your_secure_admin_password"
# export REPL_PASSWORD="your_secure_replication_password"

python setup_replication.py \
    --pg-version 16 \
    --primary-user myadmin \
    --replication-user myrepluser \
    --replica-ip-for-hba 192.168.1.101 \
    --replica-pgdata-path /mnt/pgdata_replica \
    --replication-type sync \
    --sync-replica-app-name my_replica_app
```
*(Remember to configure the replica to use `my_replica_app` as its `application_name` in its `primary_conninfo`)*

## Workflow

The script performs the following steps:

1.  **Parses Command-Line Arguments:** Overrides defaults with any provided arguments.
2.  **Logs Effective Configuration:** Prints the configuration being used (excluding passwords).
3.  **Primary Server Setup:**
    *   Creates the specified replication user (if it doesn't exist) with the `REPLICATION` privilege.
    *   Modifies `postgresql.conf` on the primary with necessary settings for replication (e.g., `wal_level`, `max_wal_senders`, `hot_standby`). For synchronous replication, it also sets `synchronous_commit` and `synchronous_standby_names`.
    *   Modifies `pg_hba.conf` on the primary to allow the replication user to connect from the replica's IP address.
    *   Creates a physical replication slot on the primary (if it doesn't exist).
    *   Restarts the PostgreSQL service on the primary to apply these changes.
4.  **Replica Server Setup (Base Backup):**
    *   Performs `pg_basebackup` to copy data from the primary to the replica's data directory (`--replica-pgdata-path`).
    *   The `-R` option is used with `pg_basebackup` to create a `standby.signal` file (or `recovery.signal`) and append connection information to `postgresql.auto.conf` in the replica's data directory.
    *   If synchronous replication is chosen, `application_name` is added to the DSN used by `pg_basebackup`.

5.  **Final Instructions:** The script will output messages guiding you on the final steps needed for the replica (e.g., verifying configuration, starting the replica's PostgreSQL service).

## Important Considerations & Limitations

*   **Permissions:** This script requires significant permissions. Running it as a user with `sudo` capabilities (at least for service restarts) and appropriate PostgreSQL superuser access is often necessary.
*   **Security:**
    *   **Passwords:** Be mindful of how passwords are provided. Using environment variables is generally safer than direct command-line arguments for production systems. For maximum security, consider `~/.pgpass` or other secure authentication methods if your environment supports them for the script's operations.
    *   **pg_hba.conf:** The script adds an entry for the replica. Ensure `replica_ip_address_for_hba` is as specific as possible. Using `0.0.0.0/0` is insecure for production.
*   **Replica Startup:** This script *does not* start the replica PostgreSQL service. This must be done manually on the replica server after the script completes.
*   **Idempotency:** The script attempts to be idempotent where possible:
    *   It checks if the replication user and slot exist before trying to create them.
    *   `pg_hba.conf` and `postgresql.conf` modifications are generally idempotent (it tries not to add duplicate lines or will overwrite existing settings).
    *   `pg_basebackup` requires an empty target directory. The script includes a step to remove the `--replica-pgdata-path` if it exists, for easier re-runs during testing. **Be very careful with this path in production.**
*   **PostgreSQL Versions:** While the script tries to use common settings, there can be differences between PostgreSQL versions (e.g., `wal_keep_size` vs `wal_keep_segments`). It's primarily tested with newer versions (13+).
*   **Error Handling:** The script includes error handling and logging. If a critical step fails, it will log an error and exit. Non-critical modification failures (like `postgresql.conf` changes if the file isn't found but settings might be okay) might issue warnings.
*   **Existing Configurations:** The script will overwrite or comment out existing settings in `postgresql.conf` as specified. Review your existing configurations carefully.

## Troubleshooting

*   **Check Logs:** The script uses Python's `logging` module. Review the script's output for detailed error messages and the steps it performed.
*   **PostgreSQL Logs:** Always check the PostgreSQL server logs on both the primary and replica for more detailed diagnostic information.
*   **Permissions:** Double-check file system permissions for configuration files and the replica data directory. Ensure the PostgreSQL user (e.g., `postgres`) can access its data directory.
*   **`pg_hba.conf`:** Authentication issues are common. Verify that `pg_hba.conf` on the primary correctly allows the `replication_user` to connect from the `replica_ip_address_for_hba` using the `scram-sha-256` method (or md5 if your server is older and passwords are set accordingly).
*   **Firewall:** Ensure no firewalls are blocking connections between the primary and replica on the PostgreSQL port (default 5432).
*   **`pg_basebackup` DSN:** If `pg_basebackup` fails, try to connect to the primary using `psql -d "your_dsn_here"` with the same DSN from a terminal to diagnose connection issues. Remember the DSN needs the replication user.
*   **Synchronous Replication:** If `synchronous_standby_names` is used, the `application_name` in the replica's connection info (`primary_conninfo`) *must* match one of the names listed. `pg_basebackup -R` helps set this up, but verify.

This script provides a solid foundation. Always test thoroughly in a non-production environment before applying to critical systems.
