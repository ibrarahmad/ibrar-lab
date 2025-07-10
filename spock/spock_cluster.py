#!/usr/bin/env python3

import argparse
import os
import subprocess
from pathlib import Path
from datetime import datetime

BIN_DIR = "/usr/local/pgsql.17/bin"
DATA_BASE = "/home/pgedge/pg_data"
START_PORT = 5431
DEFAULT_NUM_NODES = 3
LOG_FILE = "/home/pgedge/pg_data/spock_cluster.log"
STEP_WIDTH = 50

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

def run(cmd, **kwargs):
    """Run a shell command, return True if success, False otherwise."""
    with open(LOG_FILE, "a") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=f, **kwargs)
        return proc.returncode == 0

def step_msg(action, node_num):
    return f"{action} node {node_num} ...".ljust(STEP_WIDTH)

def init_node(node_num):
    data_dir = f"{DATA_BASE}/data{node_num}"
    port = START_PORT + node_num - 1
    msg = step_msg("Initializing", node_num)
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    if not Path(f"{data_dir}/PG_VERSION").exists():
        if not run([f"{BIN_DIR}/initdb", "-D", data_dir]):
            log(msg + "[FAILED]")
            return
    if run([f"{BIN_DIR}/pg_ctl", "-D", data_dir, "-o", f"-p {port}", "-l", f"{data_dir}/server.log", "start"]):
        log(msg + "[OK]")
    else:
        log(msg + "[FAILED]")

def stop_node(node_num):
    data_dir = f"{DATA_BASE}/data{node_num}"
    msg = step_msg("Stopping", node_num)
    if not Path(data_dir).is_dir():
        log(msg + "[SKIPPED]")
        return
    result = run([f"{BIN_DIR}/pg_ctl", "-D", data_dir, "stop", "-m", "fast"])
    if result:
        log(msg + "[OK]")
    else:
        log(msg + "[FAILED]")

def destroy_node(node_num):
    data_dir = f"{DATA_BASE}/data{node_num}"
    msg = step_msg("Destroying", node_num)
    stop_node(node_num)
    if Path(data_dir).is_dir():
        try:
            subprocess.run(["rm", "-rf", data_dir], check=True)
            log(msg + "[OK]")
        except Exception:
            log(msg + "[FAILED]")
    else:
        log(msg + "[OK]")

def cleanup_node(node_num):
    port = START_PORT + node_num - 1
    msg = step_msg("Cleaning", node_num)
    cmds = [
        [f"{BIN_DIR}/dropdb", "pgedge", f"-p{port}"],
        [f"{BIN_DIR}/createdb", "pgedge", f"-p{port}"],
        [f"{BIN_DIR}/psql", "pgedge", f"-p{port}", "-c", "create extension if not exists spock"],
        [f"{BIN_DIR}/psql", "pgedge", f"-p{port}", "-c", "create extension if not exists dblink"],
        [f"{BIN_DIR}/psql", "pgedge", f"-p{port}", "-t", "-A", "-c",
         "SELECT 'SELECT pg_drop_replication_slot(' || quote_literal(slot_name) || ');' FROM pg_replication_slots WHERE slot_type = 'logical';"],
        [f"{BIN_DIR}/psql", "-d", "pgedge", f"-p{port}", "-Atc",
         "SELECT 'SELECT pg_replication_origin_drop(' || quote_literal(roname) || ');' FROM pg_replication_origin;"],
        [f"{BIN_DIR}/psql", "pgedge", f"-p{port}", "-c", "drop extension if exists spock; create extension spock"]
    ]
    ok = True
    for cmd in cmds:
        # For SQL that outputs SQL, pipe to psql
        if "pg_drop_replication_slot" in " ".join(cmd) or "pg_replication_origin_drop" in " ".join(cmd):
            try:
                sql_out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
                if sql_out.strip():
                    if not run([f"{BIN_DIR}/psql", "pgedge", f"-p{port}"], input=sql_out, text=True):
                        ok = False
            except subprocess.CalledProcessError:
                ok = False
        else:
            if not run(cmd):
                ok = False
    if ok:
        log(msg + "[OK]")
    else:
        log(msg + "[FAILED]")

def write_auto_conf(node_num):
    data_dir = f"{DATA_BASE}/data{node_num}"
    port = START_PORT + node_num - 1
    auto_conf = f"{data_dir}/postgresql.auto.conf"
    msg = step_msg("Configuring", node_num)
    content = f"""spock.enable_ddl_replication = 'on'
spock.include_ddl_repset = 'on'
spock.allow_ddl_from_functions = 'on'
spock.node = 'node{node_num}'
port = {port}
shared_preload_libraries = 'spock'
wal_level = logical
max_wal_senders = 20
max_replication_slots = 20
max_worker_processes = 20
track_commit_timestamp = on
wal_sender_timeout = 4s
DateStyle = 'ISO, DMY'
log_line_prefix = '[%m] [%p] [%d] '
fsync = off
spock.exception_behaviour = 'sub_disable'
client_min_messages = log
"""
    try:
        with open(auto_conf, "w") as f:
            f.write(content)
        log(msg + "[OK]")
    except Exception:
        log(msg + "[FAILED]")

def all_nodes(num_nodes):
    for i in range(1, num_nodes+1):
        stop_node(i)
    for i in range(1, num_nodes+1):
        cleanup_node(i)
    for i in range(1, num_nodes+1):
        destroy_node(i)
    for i in range(1, num_nodes+1):
        init_node(i)
        write_auto_conf(i)
    log(f"{'All actions completed'.ljust(STEP_WIDTH)}[OK]")

def main():
    parser = argparse.ArgumentParser(description="Spock PostgreSQL cluster manager (Python version)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-i", "--init", action="store_true", help="Initialize and start nodes")
    group.add_argument("-s", "--stop", action="store_true", help="Stop nodes")
    group.add_argument("-d", "--destroy", action="store_true", help="Destroy nodes")
    group.add_argument("-c", "--cleanup", action="store_true", help="Cleanup databases/extensions on nodes")
    group.add_argument("-u", "--update-conf", action="store_true", help="Update postgresql.auto.conf for nodes")
    group.add_argument("-a", "--all", action="store_true", help="Full cycle: stop, cleanup, destroy, init, conf")
    parser.add_argument("-n", "--num-nodes", type=int, default=DEFAULT_NUM_NODES, help="Number of nodes (default: 3)")
    args = parser.parse_args()

    # Timestamp header in log
    with open(LOG_FILE, "a") as f:
        f.write(f"\n==== {datetime.now()} ====\n")

    if args.init:
        for i in range(1, args.num_nodes+1):
            init_node(i)
            write_auto_conf(i)
    elif args.stop:
        for i in range(1, args.num_nodes+1):
            stop_node(i)
    elif args.destroy:
        for i in range(1, args.num_nodes+1):
            destroy_node(i)
    elif args.cleanup:
        for i in range(1, args.num_nodes+1):
            cleanup_node(i)
    elif args.update_conf:
        for i in range(1, args.num_nodes+1):
            write_auto_conf(i)
    elif args.all:
        all_nodes(args.num_nodes)

if __name__ == "__main__":
    main()