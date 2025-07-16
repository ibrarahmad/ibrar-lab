# zodan.py

This script adds a new node to a Spock cluster using `psql`. It's designed to be run from the command line and performs all the necessary steps to add a new node, including:

-   Creating the new node.
-   Creating subscriptions to and from the new node.
-   Creating replication slots.
-   Synchronizing the new node with the cluster.
-   Enabling the subscriptions.

## Usage

```bash
./zodan.py --src-node-name <source_node> --src-dsn <source_dsn> --new-node-name <new_node> --new-node-dsn <new_node_dsn> [options]
```

### Options

-   `--src-node-name`: The name of an existing node in the cluster.
-   `--src-dsn`: The DSN of the source node.
-   `--new-node-name`: The name of the new node to add.
-   `--new-node-dsn`: The DSN of the new node.
-   `--new-node-location`: The location of the new node (default: "NY").
-   `--new-node-country`: The country of the new node (default: "USA").
-   `--new-node-info`: A JSON string with additional information about the new node (default: "{}").
