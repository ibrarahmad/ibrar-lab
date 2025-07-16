# cross_nodes.py

This script is used to "cross-wire" or "uncross-wire" Spock nodes.

-   **Cross-wiring**: Sets up a mesh by creating Spock nodes and subscriptions between all nodes.
-   **Uncross-wiring**: Tears down the mesh by dropping the Spock nodes and subscriptions.

## Usage

```bash
./cross_nodes.py [options]
```

### Options

-   `-c`, `--cross`: Cross-wire nodes (default action).
-   `-r`, `--uncross`: Uncross-wire nodes.
-   `-v`, `--verbose`: Show SQL output and errors.
-   `-n`, `--num-nodes`: Number of nodes to use (default: 3).

### Node Configuration

The script uses a default configuration for the nodes, defined in the `DEFAULT_NODES` variable in the script. You can modify this variable to change the node connection details.
