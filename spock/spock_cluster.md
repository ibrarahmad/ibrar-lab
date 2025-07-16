# spock_cluster.py

This script is a Python-based command-line tool for managing a local Spock PostgreSQL cluster. It simplifies the process of setting up and tearing down a multi-node cluster for development and testing.

## Usage

```bash
./spock_cluster.py [options]
```

### Options

-   `-i`, `--init`: Initialize all nodes.
-   `-s`, `--stop`: Stop nodes.
-   `-d`, `--destroy`: Destroy nodes.
-   `-c`, `--cleanup`: Cleanup databases and extensions on nodes.
-   `-u`, `--update-conf`: Update `postgresql.auto.conf` for nodes.
-   `-a`, `--all`: Perform a full cycle: stop, cleanup, destroy, init, and configure.
-   `-n`, `--num-nodes`: Number of nodes to manage (default: 3).
-   `-v`, `--verbose`: Show output to the console as well as the log file.

### Configuration

The script uses several constants defined at the beginning of the file to configure the cluster:

-   `BIN_DIR`: The directory where the PostgreSQL binaries are located.
-   `DATA_BASE`: The base directory for the node data directories.
-   `START_PORT`: The starting port number for the nodes.
-   `DEFAULT_NUM_NODES`: The default number of nodes to manage.
-   `LOG_FILE`: The path to the log file.
