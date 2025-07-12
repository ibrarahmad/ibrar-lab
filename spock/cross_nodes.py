#!/usr/bin/env python3

import subprocess
import sys
from datetime import datetime
import argparse
import os

PG_PATH = "/usr/local/pgsql.17/bin"
os.environ["PATH"] = f"{PG_PATH}:{os.environ.get('PATH', '')}"

DEFAULT_NODES = [
    {
        "name": "n1",
        "dsn": "host=127.0.0.1 dbname=pgedge port=5431 user=pgedge password=pgedge",
        "location": "Los Angeles",
        "country": "USA"
    },
    {
        "name": "n2",
        "dsn": "host=127.0.0.1 dbname=pgedge port=5432 user=pgedge password=pgedge",
        "location": "Los Angeles",
        "country": "USA"
    }
]

def log_step(step_number, description, status, node_name=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    node_info = f"[{node_name}]" if node_name else ""
    aligned_description = f"{description:<50}"
    aligned_status = f"[{status}]"
    print(f"\n[{timestamp}] Step {step_number:02}: {node_info} {aligned_description} {aligned_status}")

def execute_sql(sql, conn_info):
    conn_command = f"psql '{conn_info}' -v ON_ERROR_STOP=1 <<'EOF'\n{sql}\nEOF"
    result = subprocess.run(conn_command, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def node_create(node_name, dsn, location, country):
    sql = f"""
    SELECT spock.node_create(
        node_name => '{node_name}',
        dsn => '{dsn}',
        location => '{location}',
        country => '{country}'
    );
    """
    return sql.strip()

def sub_create(sub_name, provider_dsn, replication_sets=None, synchronize_structure=True, synchronize_data=True, enabled=True):
    if replication_sets is None:
        replication_sets = "['default', 'default_insert_only', 'ddl_sql']"
    sql = f"""
    SELECT spock.sub_create(
        subscription_name => '{sub_name}',
        provider_dsn => '{provider_dsn}',
        replication_sets => ARRAY{replication_sets},
        synchronize_structure => {str(synchronize_structure).lower()},
        synchronize_data => {str(synchronize_data).lower()},
        forward_origins => ARRAY[]::text[],
        apply_delay => '0'::interval,
        force_text_transfer => false,
        enabled => {str(enabled).lower()}
    );
    """
    return sql.strip()

def sub_drop(sub_name):
    sql = f"SELECT spock.sub_drop(subscription_name => '{sub_name}');"
    return sql

def node_drop(node_name):
    sql = f"SELECT spock.node_drop(node_name => '{node_name}');"
    return sql

def repset_create(set_name):
    sql = f"""
    SELECT spock.repset_create(
        set_name => '{set_name}',
        replicate_insert => true,
        replicate_update => true,
        replicate_delete => true,
        replicate_truncate => true
    );
    """
    return sql.strip()

def cross_node_workflow(nodes, verbose):
    steps = []
    step_num = 1

    # Create all nodes
    for node in nodes:
        steps.append({
            "description": f"Create spock node {node['name']}",
            "sql": node_create(node['name'], node['dsn'], node['location'], node['country']),
            "conn_info": node['dsn'],
            "node_name": node['name'],
            "step_num": step_num
        })
        step_num += 1

    # Create subscriptions: each node subscribes to every other node
    for i, node in enumerate(nodes):
        for j, provider in enumerate(nodes):
            if i != j:
                sub_name = f"sub_{provider['name']}_{node['name']}"
                steps.append({
                    "description": f"Create subscription {sub_name} for {node['name']} ({provider['name']}->{node['name']})",
                    "sql": sub_create(
                        sub_name=sub_name,
                        provider_dsn=provider['dsn']
                    ),
                    "conn_info": node['dsn'],
                    "node_name": node['name'],
                    "step_num": step_num
                })
                step_num += 1

    # Create replication set for each node
    for node in nodes:
        repset_name = f"{node['name']}r"
        steps.append({
            "description": f"Create replication set {repset_name} for {node['name']}",
            "sql": repset_create(repset_name),
            "conn_info": node['dsn'],
            "node_name": node['name'],
            "step_num": step_num
        })
        step_num += 1

    execute_steps(steps, verbose)

def uncross_node_workflow(nodes, verbose):
    steps = []
    step_num = 1

    # Drop all subscriptions
    for i, node in enumerate(nodes):
        for j, provider in enumerate(nodes):
            if i != j:
                sub_name = f"sub_{provider['name']}_{node['name']}"
                steps.append({
                    "description": f"Drop subscription {sub_name} from {node['name']}",
                    "sql": sub_drop(sub_name),
                    "conn_info": node['dsn'],
                    "node_name": node['name'],
                    "step_num": step_num
                })
                step_num += 1

    # Drop all nodes
    for node in nodes:
        steps.append({
            "description": f"Drop node {node['name']}",
            "sql": node_drop(node['name']),
            "conn_info": node['dsn'],
            "node_name": node['name'],
            "step_num": step_num
        })
        step_num += 1

    execute_steps(steps, verbose)

def execute_steps(steps, verbose=0):
    for step in steps:
        desc = step["description"]
        sql = step["sql"]
        conn_info = step.get("conn_info")
        node_name = step.get("node_name")
        step_number = step.get("step_num", 0)
        rc, stdout, stderr = execute_sql(sql, conn_info)
        status = "OK" if rc == 0 else "FAILED"
        log_step(step_number, desc, status, node_name)
        if verbose and rc != 0:
            print(stderr)
        elif verbose and rc == 0 and verbose:
            print(stdout)

def parse_nodes_from_args(args):
    # You can extend this to read from a config file or arguments
    # For now, use DEFAULT_NODES and --num-nodes to slice
    num_nodes = args.num_nodes if hasattr(args, "num_nodes") else len(DEFAULT_NODES)
    return DEFAULT_NODES[:num_nodes]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross-wire or uncross-wire Spock nodes.")
    parser.add_argument("-c", "--cross", action="store_true", help="Cross-wire nodes (default)")
    parser.add_argument("-r", "--uncross", action="store_true", help="Uncross-wire nodes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show SQL output and errors")
    parser.add_argument("-n", "--num-nodes", type=int, default=len(DEFAULT_NODES),
                        help="Number of nodes (default: 3)")
    args = parser.parse_args()

    nodes = parse_nodes_from_args(args)

    if args.uncross:
        uncross_node_workflow(nodes, args.verbose)
    else:
        cross_node_workflow(nodes, args.verbose)