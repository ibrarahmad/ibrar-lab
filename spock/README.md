# Spock

This directory contains scripts related to the [Spock](https://www.2ndquadrant.com/en/resources/postgresql-spock/) extension for PostgreSQL, focusing on multi-node logical replication and cluster management.

## Files

- [`cross_nodes.py`](cross_nodes.py)  
  A Python script for executing shell or SQL commands across multiple Spock nodes via SSH or direct connections. Useful for automation and cluster-wide diagnostics.

- [`spock_cluster.py`](spock_cluster.py)  
  A Python utility to initialize, configure, and manage a full Spock cluster. Supports adding nodes, setting up subscriptions, and orchestrating replication topologies.

- [`zodan.py`](zodan.py)  
  A Python script designed to simplify advanced cluster operations such as adding nodes with custom configurations, syncing replication slots, and zero-downtime workflows.

- [`zodan.sql`](zodan.sql)  
  A comprehensive SQL-based workflow using `dblink` to add a new Spock node with zero downtime. Useful for PostgreSQL-native deployments without external tooling.

---

Each script is modular and designed to support high-availability Spock deployments with minimal manual effort.
