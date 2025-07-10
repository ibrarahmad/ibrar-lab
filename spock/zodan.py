#!/usr/bin/env python3

import subprocess
import sys
from datetime import datetime
import argparse
import os

# Set PostgreSQL bin path
PG_PATH = "/usr/local/pgsql.17/bin"

# Update PATH environment variable to include PostgreSQL bin path
os.environ["PATH"] = f"{PG_PATH}:{os.environ.get('PATH', '')}"


SRC_NODE = [
    {
        "name": "n1",
        "dsn": "host=127.0.0.1 dbname=pgedge port=5431 user=pgedge password=pgedge",
        "location": "Los Angeles",
        "country": "USA"
    }
]

NEW_NODE = [
    {
        "name": "n3",
        "dsn": "host=127.0.0.1 dbname=pgedge port=5433 user=pgedge password=pgedge",
        "location": "Los Angeles",
        "country": "USA"
    }
]

def get_nodes():
    """
    Fetches the list of nodes from the PostgreSQL cluster using the DSN of SRC_NODE.
    Returns a list of dictionaries with node details.
    """
    sql = """
        SELECT node_name, dsn, location, country
        FROM spock.node;
    """
    rc, stdout, stderr = execute_sql(sql, SRC_NODE[0]['dsn'])
    if rc != 0:
        print(f"Error fetching nodes: {stderr}")
        return []
    nodes = []
    lines = stdout.strip().splitlines()
    # Skip header and separator lines
    for line in lines[2:]:
        if not line.strip() or line.startswith('('):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) == 4:
            nodes.append({
                "name": parts[0],
                "dsn": parts[1],
                "location": parts[2],
                "country": parts[3]
            })
    return nodes

NODES = get_nodes()

# Generate replication slots for all disabled subscriptions
REPLICATION_SLOTS = [
    f"spk_pgedge_{node['name']}_sub_{node['name']}_{NEW_NODE[0]['name']}"
    for node in NODES
]

SYNC_EVENT_TIMEOUT = 1200000
APPLY_WORKER_TIMEOUT = 1000

def log_step(step_number, description, status, node_name=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    node_info = f"[{node_name}]" if node_name else ""
    aligned_description = f"{description:<50}"  # Align description to a fixed width
    aligned_status = f"[{status}]"  # Align status to ensure consistent formatting
    print(f"[{timestamp}] [Step - {step_number:02}]: {node_info} - {aligned_description} {aligned_status}")


# Function to execute SQL commands on a specific DSN
def execute_sql(sql, conn_info):
    conn_command = f"psql '{conn_info}' -v ON_ERROR_STOP=1 <<'EOF'\n{sql}\nEOF"
    result = subprocess.run(conn_command, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

# Function to generate SQL for `node_create`
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

# Function to generate SQL for `sub_create`
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

# Function to generate SQL for `sub_drop`
def sub_drop(sub_name):
    sql = f"SELECT spock.sub_drop(subscription_name => '{sub_name}');"
    return sql

# Function to generate SQL for `node_drop`
def node_drop(node_name):
    sql = f"SELECT spock.node_drop(node_name => '{node_name}');"
    return sql

def add_node_workflow(verbose):
    steps = []

    # Step 1: Create the new node
    steps.append({
        "description": f"Create node {NEW_NODE[0]['name']} in the cluster",
        "sql": node_create(NEW_NODE[0]['name'], NEW_NODE[0]['dsn'], NEW_NODE[0]['location'], NEW_NODE[0]['country']),
        "conn_info": NEW_NODE[0]['dsn'],
        "node_name": NEW_NODE[0]['name']
    })

    # Step 2-3: Create subscriptions from the new node to existing nodes
    for node in NODES:
        steps.append({
            "description": f"Create a subscription (sub_{NEW_NODE[0]['name']}_{node['name']})",
            "sql": sub_create(
                sub_name=f"sub_{NEW_NODE[0]['name']}_{node['name']}",
                provider_dsn=NEW_NODE[0]['dsn']
            ),
            "conn_info": node['dsn'],
            "node_name": node['name']
        })

    # Step 4: Wait for the apply worker to complete on the last node
    steps.append({
        "description": f"Wait for the apply worker",
        "sql": f"SELECT spock.wait_for_apply_worker(${2}, {APPLY_WORKER_TIMEOUT});",
        "conn_info": NODES[1]['dsn'],
        "ignore_error": True,
        "node_name": NODES[1]['name']
    })

    # Step 5: Create subscriptions from existing nodes to the new node
    for node in NODES:
        steps.append({
            "description": f"Create Subscription (sub_{node['name']}_{NEW_NODE[0]['name']}) [disabled]",
            "sql": sub_create(
                sub_name=f"sub_{node['name']}_{NEW_NODE[0]['name']}",
                provider_dsn=node['dsn'],
                synchronize_structure=False,
                synchronize_data=False,
                enabled=False
            ),
            "conn_info": NEW_NODE[0]['dsn'],
            "node_name": NEW_NODE[0]['name']
        })

    # Step 6: Create replication slots for disabled subscriptions
    for node in NODES:
        if not node.get("source", False):
            slot_name = f"spk_{NEW_NODE[0]['dsn'].split(' ')[1].split('=')[1]}_{node['name']}_sub_{node['name']}_{NEW_NODE[0]['name']}"
            steps.append({
                "description": f"Create replication slot {slot_name}",
                "sql": f"SELECT pg_create_logical_replication_slot('{slot_name}', 'spock_output');",
                "conn_info": NEW_NODE[0]['dsn'],
                "node_name": NEW_NODE[0]['name']
            })

    # Step 7: Trigger synchronization events and wait for them
    for i, node in enumerate(NODES):
        if node.get("source", False):
            steps.append({
                "description": f"Trigger a synchronization event on {node['name']}",
                "sql": "SELECT spock.sync_event();",
                "conn_info": node['dsn'],
                "node_name": node['name']
            })
            steps.append({
                "description": f"Wait for the synchronization event triggered by {node['name']} to complete",
                "sql": f"CALL spock.wait_for_sync_event(true, '{node['name']}', ${len(steps)}::pg_lsn, {SYNC_EVENT_TIMEOUT});",
                "conn_info": NEW_NODE[0]['dsn'],
                "ignore_error": True,
                "node_name": NEW_NODE[0]['name']
            })

    # Step 8: Check replication lags
    steps.append({
        "description": "Check the replication lags between nodes",
        "sql": """
        DO $$ 
        DECLARE
            lag_n1_n3 interval;
            lag_n2_n3 interval;
        BEGIN
            LOOP
                SELECT now() - commit_timestamp INTO lag_n1_n3
                FROM spock.lag_tracker
                WHERE origin_name = 'n1' AND receiver_name = 'n3';

                SELECT now() - commit_timestamp INTO lag_n2_n3
                FROM spock.lag_tracker
                WHERE origin_name = 'n2' AND receiver_name = 'n3';

                RAISE NOTICE 'n1 → n3 lag: %, n2 → n3 lag: %',
                             COALESCE(lag_n1_n3::text, 'NULL'),
                             COALESCE(lag_n2_n3::text, 'NULL');

                EXIT WHEN lag_n1_n3 IS NOT NULL AND lag_n2_n3 IS NOT NULL
                          AND extract(epoch FROM lag_n1_n3) < 59
                          AND extract(epoch FROM lag_n2_n3) < 59;

                PERFORM pg_sleep(1);
            END LOOP;
        END
        $$;
        """.strip(),
        "conn_info": NEW_NODE[0]['dsn'],
        "node_name": NEW_NODE[0]['name']
    })

    outputs = execute_steps(steps, verbose)

def remove_node_workflow(verbose):
    steps = []

    # Drop subscriptions on the new node
    for node in NODES:
        steps.append({
            "description": f"Drop subscription (sub_{node['name']}_{NEW_NODE[0]['name']})",
            "sql": sub_drop(f"sub_{node['name']}_{NEW_NODE[0]['name']}"),
            "conn_info": NEW_NODE[0]['dsn'],
            "ignore_error": True,
            "node_name": NEW_NODE[0]['name']
        })

    # Drop subscriptions on existing nodes
    for node in NODES:
        steps.append({
            "description": f"Drop subscription (sub_{NEW_NODE[0]['name']}_{node['name']})",
            "sql": sub_drop(f"sub_{NEW_NODE[0]['name']}_{node['name']}"),
            "conn_info": node['dsn'],
            "ignore_error": True,
            "node_name": node['name']
        })

    # Drop the new node
    steps.append({
        "description": f"Drop node {NEW_NODE[0]['name']}",
        "sql": node_drop(NEW_NODE[0]['name']),
        "conn_info": NEW_NODE[0]['dsn'],
        "ignore_error": True,
        "node_name": NEW_NODE[0]['name']
    })

    execute_steps(steps, verbose)

def execute_steps(steps, verbose=0):
    step_outputs = {}

    for i, step in enumerate(steps, start=1):
        desc = step["description"]
        sql = step["sql"]
        conn_info = step.get("conn_info")
        ignore_error = step.get("ignore_error", False)
        node_name = step.get("node_name")  # Extract node name for logging

        for key in sorted(step_outputs.keys(), key=lambda x: -len(str(x))):
            placeholder = f"${key}"
            sql = sql.replace(placeholder, step_outputs[key])

        if verbose >= 1:
            print(f"Executing on: {conn_info}")
        if verbose == 2:
            print(f"SQL Query:\n{sql}\n")

        rc, stdout, stderr = execute_sql(sql, conn_info)

        if rc == 0:
            output_lines = stdout.strip().splitlines()
            extracted = ""
            for line in reversed(output_lines):
                line = line.strip()
                if line and not line.startswith("(") and not line.startswith("sub_create") and not line.startswith("node_create"):
                    extracted = line
                    break

            if "/" in extracted:
                step_outputs[i] = f"'{extracted}'"
            else:
                step_outputs[i] = extracted

            if verbose >= 1:
                print(stdout)
            log_step(i, desc, "OK", node_name)
        elif ignore_error:
            step_outputs[i] = ""
            if verbose >= 1:
                print(f"\033[93m{stderr}\033[0m")
            log_step(i, desc, "IGNORED", node_name)
        else:
            if verbose >= 1:
                print(f"\033[91m{stderr}\033[0m")
            log_step(i, desc, "FAILED", node_name)
            sys.exit(f"\033[91mStep failed: {desc}\033[0m")

    return step_outputs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spock Node Management")
    parser.add_argument("-a", "--add-node", action="store_true", help="Add a new node (default)")
    parser.add_argument("-r", "--remove-node", action="store_true", help="Remove an existing node")
    parser.add_argument("-v", "--verbose", type=int, choices=[0, 1, 2], default=0, help="Set verbosity level (0: steps only, 1: steps and output, 2: steps, query, and output)")
    args = parser.parse_args()

    if args.remove_node:
        remove_node_workflow(args.verbose)
    else:
        add_node_workflow(args.verbose)