#!/usr/bin/env python3

import argparse
import configparser
import subprocess
import os
import sys
import logging
import shutil

CONFIG_FILE = "pg.conf"
DEFAULT_PG_VERSION = "17"
GREEN, RED, RESET = '\033[92m', '\033[91m', '\033[0m'
LINE_WIDTH = 90

def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")
    sys.exit(1)

def print_info(msg):
    print(msg)

def wrap_text(text, width=LINE_WIDTH):
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current += " " + word if current else word
    if current:
        lines.append(current)
    return "\n".join(lines)

def load_config(config_file=None):
    config = configparser.ConfigParser()
    cfg_file = config_file or CONFIG_FILE
    if not os.path.exists(cfg_file):
        print_error(f"Configuration file '{cfg_file}' not found.")
    config.read(cfg_file)
    return config

def get_node_config(config, node):
    if node not in config:
        print_error(f"Node '{node}' not found in config.")
    node_cfg = dict(config['DEFAULT'])
    node_cfg.update(config[node])
    for key in ['source_path', 'base_data_directory',
                'base_log_directory', 'base_bin_directory', 'port']:
        if key not in node_cfg:
            print_error(f"Missing key '{key}' for node '{node}'.")
    node_cfg['data_directory'] = os.path.join(node_cfg['base_data_directory'], node)
    node_cfg['log_file'] = os.path.join(node_cfg['base_log_directory'], f"{node}.log")
    node_cfg['bin_directory'] = os.path.join(
        node_cfg['base_bin_directory'], f"pgsql-{node_cfg.get('pg_version', DEFAULT_PG_VERSION)}", "bin")
    return node_cfg

def setup_logging(logfile, verbose):
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    handlers = [logging.FileHandler(logfile)]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers
    )

def run_command(cmd, cwd=None, env=None,
                log_output=True, node_log="", verbose=False, ignore_error=False):
    if verbose:
        print_info(f"[{node_log}] Running: {' '.join(cmd)}")
    logging.info(f"[{node_log}] {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                cwd=cwd, env=env)
        out, err = proc.communicate()
        if log_output:
            if out:
                logging.info(f"Stdout: {out.strip()}")
                if verbose:
                    print(out.strip())
            if err:
                logging.error(f"Stderr: {err.strip()}")
                if verbose:
                    print(err.strip())
        if proc.returncode != 0:
            if ignore_error:
                if verbose:
                    print_info(f"[WARN] Ignored failure: {' '.join(cmd)}")
                return out, err, proc.returncode
            print_error(f"[{node_log}] Command failed. Check logs.")
        if verbose:
            print_success(f"[{node_log}] OK: {' '.join(cmd)}")
        return out, err, proc.returncode
    except Exception as e:
        logging.error(f"Exception: {e}")
        if not ignore_error:
            print_error(f"[{node_log}] Exception occurred.")
        return None, str(e), -1

def status_node(args):
    cfg = get_node_config(load_config(args.config_file), args.node_name)
    setup_logging(cfg['log_file'], args.verbose)
    pg_ctl = os.path.join(cfg['bin_directory'], "pg_ctl")
    cmd = [pg_ctl, "-D", cfg['data_directory'], "status"]
    try:
        out, err, code = run_command(cmd, node_log=args.node_name,
                                     verbose=args.verbose, ignore_error=True)
        if code == 0:
            print_success(f"[{args.node_name}] PostgreSQL is running.")
        else:
            print_info(f"[{args.node_name}] PostgreSQL is NOT running.")
    except Exception:
        print_info(f"[{args.node_name}] Unable to determine status.")

def start_node(args):
    cfg = get_node_config(load_config(args.config_file), args.node_name)
    setup_logging(cfg['log_file'], args.verbose)
    pg_ctl = os.path.join(cfg['bin_directory'], "pg_ctl")
    cmd = [pg_ctl, "-D", cfg['data_directory'], "-l", cfg['log_file'], "start", "-w", "-t", "10"]
    out, err, code = run_command(cmd, node_log=args.node_name, verbose=args.verbose, ignore_error=True)
    if code == 0:
        print_success(f"[{args.node_name}] PostgreSQL started.")
    else:
        print_error(f"[{args.node_name}] PostgreSQL failed to start. Check log: {cfg['log_file']}")

def stop_node(args):
    cfg = get_node_config(load_config(args.config_file), args.node_name)
    setup_logging(cfg['log_file'], args.verbose)
    pg_ctl = os.path.join(cfg['bin_directory'], "pg_ctl")
    run_command([pg_ctl, "-D", cfg['data_directory'], "stop", "-m", "fast"],
                node_log=args.node_name, verbose=args.verbose,
                ignore_error=True)

def write_auto_conf(config, node_name):
    auto_conf_path = os.path.join(config["DEFAULT"]['base_data_directory'], node_name, "postgresql.auto.conf")
    auto_conf_section = f"postgresql.auto.conf.{node_name}"
    if not config.has_section(auto_conf_section):
        print_error(f"Section '{auto_conf_section}' not found in configuration.")
    excluded_keys = {'source_path', 'base_log_directory', 'base_bin_directory', 'base_data_directory', 'postgres_options'}
    with open(auto_conf_path, "w") as f:
        for key, value in config.items(auto_conf_section):
            if key not in excluded_keys:
                f.write(f"{key} = {value}\n")
        # Add primary_slot_name for replica nodes
        if "replica" in node_name:
            f.write(f"primary_slot_name = '{node_name}_slot'\n")

def modify_pg_hba_conf(cfg):
    """
    Modify pg_hba.conf to trust local connections for all users and allow replication for replicator.
    """
    pg_hba_path = os.path.join(cfg['data_directory'], "pg_hba.conf")
    with open(pg_hba_path, "a") as hba:
        hba.write("\n# Allow replication for replicator user\n")
        hba.write("host    replication     replicator      127.0.0.1/32    trust\n")
        hba.write("host    replication     replicator      ::1/128         trust\n")
        hba.write("# Allow all local connections (for dev)\n")
        hba.write("host    all             all             127.0.0.1/32    trust\n")
        hba.write("host    all             all             ::1/128         trust\n")

def initdb_node(args):
    config = load_config(args.config_file)  # Load the full ConfigParser object
    cfg = get_node_config(config, args.node_name)  # Get the node-specific dictionary
    setup_logging(cfg['log_file'], args.verbose)
    if os.path.exists(cfg['data_directory']) and os.listdir(cfg['data_directory']):
        print_error(f"[{args.node_name}] Data dir is not empty.")
    os.makedirs(cfg['data_directory'], exist_ok=True)
    initdb = os.path.join(cfg['bin_directory'], "initdb")
    run_command([initdb, "-D", cfg['data_directory']],
                node_log=args.node_name, verbose=args.verbose)
    write_auto_conf(config, args.node_name)  # Pass the ConfigParser object
    modify_pg_hba_conf(cfg)
def compile_node(args):
    cfg = get_node_config(load_config(args.config_file), args.node_name)
    setup_logging(cfg['log_file'], args.verbose)
    src_base = cfg['source_path']
    pg_version = args.pg
    version_dirs = [f"postgresql-{pg_version}",
                    f"postgresql-{pg_version.split('.')[0]}"]
    pg_src = next((os.path.join(src_base, d)
                   for d in version_dirs
                   if os.path.isdir(os.path.join(src_base, d))), None)
    if not pg_src:
        print_error(f"Source not found for version {pg_version}")
    install_dir = os.path.join(cfg['base_bin_directory'], f"pgsql-{pg_version}")
    os.makedirs(install_dir, exist_ok=True)
    run_command(["make", "distclean"], cwd=pg_src,
                node_log=args.node_name, verbose=args.verbose, ignore_error=True)
    run_command(["./configure", f"--prefix={install_dir}",
                 "--enable-cassert", "CFLAGS=-g3 -O0"],
                cwd=pg_src, node_log=args.node_name, verbose=args.verbose)
    run_command(["make", f"-j{os.cpu_count() or 2}"],
                cwd=pg_src, node_log=args.node_name, verbose=args.verbose)
    run_command(["make", "install"], cwd=pg_src,
                node_log=args.node_name, verbose=args.verbose)
    print_success(f"[{args.node_name}] PostgreSQL {pg_version} compiled.")

def destroy_node(args):
    cfg = get_node_config(load_config(args.config_file), args.node_name)
    setup_logging(cfg['log_file'], args.verbose)
    stop_node(args)
    if os.path.exists(cfg['data_directory']):
        shutil.rmtree(cfg['data_directory'])
        print_success(f"[{args.node_name}] Node destroyed.")

def cleanup_node(args):
    destroy_node(args)
    initdb_node(args)

def replica_node(args):
    import getpass
    config = load_config(args.config_file)
    primary_cfg = get_node_config(config, args.primary_node)
    replica_cfg = get_node_config(config, args.replica_node)
    setup_logging(replica_cfg['log_file'], args.verbose)

    primary_port = str(primary_cfg.get('port', '5432'))
    primary_ip = primary_cfg.get('ip', '127.0.0.1')
    primary_user = primary_cfg.get('user', 'postgres')
    primary_db = primary_cfg.get('db', 'postgres')
    replica_port = str(replica_cfg.get('port', '5432'))

    psql = os.path.join(primary_cfg['bin_directory'], "psql")
    for role in ["postgres", "replicator"]:
        create_role_cmd = [
            psql, "-p", primary_port, "-h", primary_ip,
            "-U", primary_user, "-d", primary_db,
            "-c", f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
                  f"THEN CREATE ROLE {role} WITH LOGIN{' REPLICATION' if role == 'replicator' else ''} PASSWORD '{role}'; "
                  f"END IF; END $$;"
        ]
        run_command(create_role_cmd, node_log=args.primary_node, verbose=args.verbose, ignore_error=True)

    if os.path.exists(replica_cfg['data_directory']):
        if os.listdir(replica_cfg['data_directory']):
            print_error(f"[{args.replica_node}] Data dir not empty.")
    else:
        os.makedirs(replica_cfg['data_directory'], exist_ok=True)
        os.chmod(replica_cfg['data_directory'], 0o700)
        try:
            shutil.chown(replica_cfg['data_directory'], user=getpass.getuser())
        except Exception:
            pass

    pg_ctl = os.path.join(primary_cfg['bin_directory'], "pg_ctl")
    run_command([pg_ctl, "-D", primary_cfg['data_directory'], "reload"],
                node_log=args.primary_node, verbose=args.verbose)

    basebackup = os.path.join(replica_cfg['bin_directory'], "pg_basebackup")
    env = os.environ.copy()
    env['PGPASSWORD'] = primary_cfg.get('replicator_password', 'replicator')
    run_command([
        basebackup, "-D", replica_cfg['data_directory'], "-h",
        primary_ip, "-p", primary_port,
        "-U", "replicator", "-R", "-Fp", "-Xs", "-P"
    ], env=env, node_log=args.replica_node, verbose=args.verbose)

    auto_conf_path = os.path.join(replica_cfg['data_directory'], "postgresql.auto.conf")
    write_auto_conf(config, args.replica_node)  # Write all other settings first

    # Append primary_conninfo at the end of postgresql.auto.conf
    with open(auto_conf_path, "a") as f:
        f.write(f"primary_conninfo = 'host={primary_ip} application_name=test port={primary_port} "
                f"user=replicator password=replicator sslmode=prefer'\n")

    print_success(f"[{args.replica_node}] Replica created.")
    if args.sync:
        print_info(f"[{args.replica_node}] Configure synchronous_standby_names manually.")
def main():
    parser = argparse.ArgumentParser(
        description=wrap_text(
            "Manage multi-node PostgreSQL clusters for testing or dev. \
             Each node is defined in pg.conf and has its own port/data/log/bin settings."))

    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output.")
    parser.add_argument("-c", "--config", default="pg.conf",
                        help="Path to config file (default: pg.conf)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Check if a node is running.")
    status.add_argument("node_name", help="Node name from pg.conf")
    status.set_defaults(func=status_node)

    start = subparsers.add_parser("start", help="Start PostgreSQL for a node.")
    start.add_argument("node_name", help="Node name from pg.conf")
    start.set_defaults(func=start_node)

    stop = subparsers.add_parser("stop", help="Stop PostgreSQL for a node.")
    stop.add_argument("node_name", help="Node name from pg.conf")
    stop.set_defaults(func=stop_node)

    initdb = subparsers.add_parser("initdb", help="Initialize a PostgreSQL cluster.")
    initdb.add_argument("node_name", help="Node name from pg.conf")
    initdb.set_defaults(func=initdb_node)

    compile = subparsers.add_parser("compile", help="Compile PostgreSQL from source.")
    compile.add_argument("node_name", help="Node name from pg.conf")
    compile.add_argument("--pg", default=DEFAULT_PG_VERSION,
                         help="PostgreSQL version (default: 17)")
    compile.set_defaults(func=compile_node)

    destroy = subparsers.add_parser("destroy", help="Stop and delete a node.")
    destroy.add_argument("node_name", help="Node name from pg.conf")
    destroy.set_defaults(func=destroy_node)

    cleanup = subparsers.add_parser("cleanup", help="Destroy and re-init a node.")
    cleanup.add_argument("node_name", help="Node name from pg.conf")
    cleanup.set_defaults(func=cleanup_node)

    replica = subparsers.add_parser("replica",
        help="Create a streaming replica from a primary node.")
    replica.add_argument("primary_node", help="Primary node name")
    replica.add_argument("replica_node", help="Replica node name")
    replica.add_argument("--sync", action="store_true",
        help="Print notice to configure synchronous replication")
    replica.set_defaults(func=replica_node)

    args = parser.parse_args()
    args.config_file = args.config
    args.func(args)

if __name__ == "__main__":
    main()
