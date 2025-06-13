#!/usr/bin/env python3

import argparse
import configparser
import subprocess
import os
import sys
import logging
import shutil

# --- Configuration ---
CONFIG_FILE = "pg.conf"
DEFAULT_PG_VERSION = "17"
# ANSI escape codes for colors
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

# --- Helper Functions ---
def print_success(message):
    """Prints a success message with a green tick."""
    print(f"{GREEN}✓ {message}{RESET}")

def print_error(message):
    """Prints an error message with a red cross."""
    print(f"{RED}✗ {message}{RESET}")
    sys.exit(1) # Exit on error

def print_info(message):
    """Prints an informational message."""
    print(message)

def load_config():
    """Loads configurations from pg.conf."""
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        print_error(f"Configuration file '{CONFIG_FILE}' not found.")
    config.read(CONFIG_FILE)
    return config

def get_node_config(config, node_name):
    """Retrieves configuration for a specific node, falling back to DEFAULTs."""
    if node_name not in config:
        print_error(f"Node '{node_name}' not found in {CONFIG_FILE}.")

    node_cfg = {}
    # Start with DEFAULT values
    if 'DEFAULT' in config:
        for key, value in config['DEFAULT'].items():
            node_cfg[key] = value
    # Override with node-specific values
    for key, value in config[node_name].items():
        node_cfg[key] = value

    # Ensure essential paths are defined
    for essential_key in ['source_path', 'base_data_directory', 'base_log_directory', 'base_bin_directory', 'port']:
        if essential_key not in node_cfg:
            print_error(f"Essential configuration '{essential_key}' not found for node '{node_name}' or in DEFAULTs.")

    # Construct node-specific paths
    node_cfg['data_directory'] = os.path.join(node_cfg['base_data_directory'], node_name)
    node_cfg['log_file'] = os.path.join(node_cfg['base_log_directory'], f"{node_name}.log")
    node_cfg['bin_directory'] = os.path.join(node_cfg['base_bin_directory'], f"pgsql-{node_cfg.get('pg_version', DEFAULT_PG_VERSION)}", "bin") # Path if compiling specific versions

    return node_cfg

def setup_logging(log_file_path):
    """Sets up logging to file and console."""
    log_dir = os.path.dirname(log_file_path)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
            print_info(f"Created log directory: {log_dir}")
        except OSError as e:
            print_error(f"Could not create log directory {log_dir}: {e}")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path),
            # logging.StreamHandler(sys.stdout) # Optionally log to console as well
        ]
    )
    # Add a handler for console output for our print_success/error/info
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s")) # Keep it clean
    # logging.getLogger().addHandler(console_handler) # This would duplicate messages if also using print

def run_command(command, cwd=None, env=None, log_output=True, node_name_for_log=""):
    """Runs a shell command and logs its output."""
    if node_name_for_log:
        logging.info(f"[{node_name_for_log}] Executing command: {' '.join(command)}")
    else:
        logging.info(f"Executing command: {' '.join(command)}")

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=env)
        stdout, stderr = process.communicate()

        if log_output:
            if stdout:
                logging.info(f"Stdout: {stdout.strip()}")
            if stderr:
                logging.error(f"Stderr: {stderr.strip()}")

        if process.returncode != 0:
            if node_name_for_log:
                print_error(f"[{node_name_for_log}] Command failed: {' '.join(command)}. Check log for details.")
            else:
                print_error(f"Command failed: {' '.join(command)}. Check log for details.")
        return stdout, stderr, process.returncode
    except Exception as e:
        logging.error(f"Exception running command {' '.join(command)}: {e}")
        if node_name_for_log:
            print_error(f"[{node_name_for_log}] Exception during command execution: {' '.join(command)}. Check log.")
        else:
            print_error(f"Exception during command execution: {' '.join(command)}. Check log.")
        return None, str(e), -1


# --- Command Functions ---
def compile_postgres(node_name, pg_version):
    """Compiles PostgreSQL for a given node and version."""
    config = load_config()
    # Use node_name to get general paths like source_path, base_bin_directory
    # The pg_version from config isn't strictly used for compilation paths here, pg_version arg is king.
    node_cfg_for_paths = get_node_config(config, node_name)
    setup_logging(node_cfg_for_paths['log_file']) # Log pg_script operations

    source_path_base = node_cfg_for_paths['source_path'] # Base directory for PG sources

    # Logic to determine actual source directory (e.g., source_path_base/postgresql-17.1)
    pg_source_dir_found = None
    exact_match_path = os.path.join(source_path_base, f"postgresql-{pg_version}")
    if os.path.isdir(exact_match_path):
        pg_source_dir_found = exact_match_path
    else:
        # Try finding by major version if a specific patch isn't found (e.g., pg_version "17.1" for "postgresql-17")
        try:
            major_version_str = pg_version.split('.')[0]
            # If pg_version was "17.1", try "postgresql-17"
            if pg_version != major_version_str:
                 major_match_path = os.path.join(source_path_base, f"postgresql-{major_version_str}")
                 if os.path.isdir(major_match_path):
                    pg_source_dir_found = major_match_path
                    print_info(f"[{node_name}] Exact version source 'postgresql-{pg_version}' not found, using 'postgresql-{major_version_str}' at {pg_source_dir_found}.")

            # If still not found (e.g. pg_version was "17", or "17.1" and "postgresql-17" also not found),
            # try to find any directory starting with postgresql-<major_version> (e.g. postgresql-17-beta1)
            if not pg_source_dir_found:
                found_longer_match = False
                for item in os.listdir(source_path_base):
                    if item.startswith(f"postgresql-{major_version_str}") and os.path.isdir(os.path.join(source_path_base, item)):
                        pg_source_dir_found = os.path.join(source_path_base, item)
                        print_info(f"[{node_name}] Source for version/variant '{pg_version}' not found directly, using discovered directory: {pg_source_dir_found}.")
                        found_longer_match = True
                        break
                if not found_longer_match: # Only error if no such major version directory at all
                    print_error(f"[{node_name}] PostgreSQL source directory for version {pg_version} (or major {major_version_str}) not found in {source_path_base}.")
                    return
        except FileNotFoundError:
            print_error(f"[{node_name}] Source path base directory '{source_path_base}' not found.")
            return
        except Exception as e:
             print_error(f"[{node_name}] Error finding PostgreSQL source directory for version {pg_version}: {e}")
             return

    if not pg_source_dir_found:
        print_error(f"[{node_name}] Failed to identify PostgreSQL source directory for version {pg_version} in {source_path_base}.")
        return

    # install_dir is where this specific version will be installed
    # It's based on the pg_version argument, not what's in node_cfg_for_paths['pg_version']
    install_dir = os.path.join(node_cfg_for_paths['base_bin_directory'], f"pgsql-{pg_version}")

    logging.info(f"[{node_name}] Starting compilation of PostgreSQL {pg_version} from {pg_source_dir_found} into {install_dir}")
    print_info(f"[{node_name}] Compiling PostgreSQL {pg_version} from source: {pg_source_dir_found}")
    print_info(f"[{node_name}] Installation prefix: {install_dir}")
    print_info(f"[{node_name}] This may take a significant amount of time...")

    if not os.path.exists(install_dir):
        os.makedirs(install_dir, exist_ok=True)
        logging.info(f"[{node_name}] Created installation directory: {install_dir}")

    # Configure command - run from within the source directory
    configure_cmd = [
        os.path.join(pg_source_dir_found, "configure"),
        f"--prefix={install_dir}",
        "--enable-cassert",        # Enable assertion checks
        "CFLAGS=-g3 -O0"         # Debug symbols, no optimization
    ]
    logging.info(f"[{node_name}] Running configure: {' '.join(configure_cmd)}")
    # Pass pg_source_dir_found as cwd, so "./configure" would also work if the script itself is in pg_source_dir_found
    # However, it's safer to use the absolute path to configure, or rely on cwd for ./configure
    # The existing script does: run_command(["./configure", ...], cwd=pg_source_dir_found, ...) which is fine.
    # Let's stick to "./configure" and ensure cwd is set.
    run_command(["./configure"] + configure_cmd[1:], cwd=pg_source_dir_found, node_name_for_log=node_name)


    cpu_count = os.cpu_count() or 2 # Default to 2 if cpu_count is None or 0, for -j flag
    make_cmd = ["make", f"-j{cpu_count}"]
    logging.info(f"[{node_name}] Running make: {' '.join(make_cmd)}")
    run_command(make_cmd, cwd=pg_source_dir_found, node_name_for_log=node_name)

    make_install_cmd = ["make", "install"]
    logging.info(f"[{node_name}] Running make install: {' '.join(make_install_cmd)}")
    run_command(make_install_cmd, cwd=pg_source_dir_found, node_name_for_log=node_name)

    # Informational message after successful installation
    print_info(f"[{node_name}] To use this compiled version ({pg_version}) for node '{node_name}' with other pg_script.py commands (like initdb, start), ensure 'pg_version = {pg_version}' is set under the '[{node_name}]' section in your {CONFIG_FILE}.")

    print_success(f"[{node_name}] PostgreSQL {pg_version} compiled and installed successfully in {install_dir}.")
    logging.info(f"[{node_name}] PostgreSQL {pg_version} compiled and installed successfully in {install_dir}.")


# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser(
        description="A Python script to manage PostgreSQL instances, including compilation, initialization, replication, and operational control.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available actions. Use 'pg_script.py <command> --help' for more details on a specific command.",
        title="Commands" # Title for the subparsers group in help
    )
    subparsers.required = True # Make sure a subcommand is provided

    # --- Compile Command ---
    parser_compile = subparsers.add_parser("compile", help="Compile a specific PostgreSQL version from source.")
    parser_compile.add_argument(
        "node_name",
        help="Node identifier (e.g., n1 from pg.conf) for logging context and to fetch default paths like 'source_path' and 'base_bin_directory'. This does not permanently tie the compiled binaries to this node; any node can be configured to use them later via its 'pg_version' setting in pg.conf."
    )
    parser_compile.add_argument(
        "--pg",
        default=DEFAULT_PG_VERSION,
        help=f"PostgreSQL version to compile (e.g., '17', '16.3'). Default: {DEFAULT_PG_VERSION}. The script will look for a source directory like 'postgresql-{{version}}' under the 'source_path' defined in pg.conf."
    )
    parser_compile.set_defaults(func=lambda args: compile_postgres(args.node_name, args.pg))

    # --- InitDB Command ---
    parser_initdb = subparsers.add_parser("initdb", help="Initialize a new PostgreSQL cluster for a configured node.")
    parser_initdb.add_argument(
        "node_name",
        help="Identifier of the target node (a section in pg.conf) to initialize. The node's 'data_directory', 'port', and any 'pgsetting_*' values from pg.conf will be used. Ensure 'pg_version' in pg.conf for this node points to the desired (potentially compiled) PostgreSQL version binaries."
    )
    parser_initdb.set_defaults(func=initdb_node)

    # --- Replica Command ---
    parser_replica = subparsers.add_parser("replica", help="Configure a new node as a streaming read replica of an existing primary node.")
    parser_replica.add_argument(
        "primary_node",
        help="Identifier of the primary node (section in pg.conf) to replicate from. This node must be initialized and running. Its 'port' and 'host' (defaulting to localhost) from pg.conf will be used for connection. Ensure it's configured for replication (wal_level, max_wal_senders, pg_hba.conf)."
    )
    parser_replica.add_argument(
        "replica_node",
        help="Identifier of the new node (section in pg.conf) to be configured as a replica. Its 'data_directory', 'port', and 'pg_version' (for pg_basebackup path) from pg.conf will be used. The data directory must be empty or non-existent."
    )
    parser_replica.add_argument(
        "--sync",
        action="store_true",
        help="If specified, provides guidance for manual configuration of synchronous replication. Note: Actual synchronous setup requires manual changes on the primary's postgresql.conf (e.g., 'synchronous_standby_names') and a primary restart/reload."
    )
    parser_replica.add_argument("--async", action="store_false", dest="sync", help="Use asynchronous replication (default).")
    parser_replica.set_defaults(sync=False) # Default to async
    parser_replica.set_defaults(func=create_replica)

    # --- Start Command ---
    parser_start = subparsers.add_parser("start", help="Start the PostgreSQL server for a specified, initialized node.")
    parser_start.add_argument(
        "node_name",
        help="Identifier of the target node (section in pg.conf) whose PostgreSQL server is to be started. The node must have been previously initialized (e.g., via 'initdb' or 'replica' commands)."
    )
    parser_start.set_defaults(func=start_node)

    # --- Stop Command ---
    parser_stop = subparsers.add_parser("stop", help="Stop the PostgreSQL server for a specified node.")
    parser_stop.add_argument(
        "node_name",
        help="Identifier of the target node (section in pg.conf) whose PostgreSQL server is to be stopped. Uses 'fast' mode by default."
    )
    parser_stop.set_defaults(func=stop_node)

    # --- Restart Command ---
    parser_restart = subparsers.add_parser("restart", help="Restart the PostgreSQL server for a specified node.")
    parser_restart.add_argument(
        "node_name",
        help="Identifier of the target node (section in pg.conf) whose PostgreSQL server is to be restarted. Uses 'fast' mode for shutdown. If the server is not running, it will attempt to start it."
    )
    parser_restart.set_defaults(func=restart_node)

    # --- Cleanup Command ---
    parser_cleanup = subparsers.add_parser("cleanup", help="Reset a node: stop server, remove its data directory, and re-initialize it.")
    parser_cleanup.add_argument(
        "node_name",
        help="Identifier of the target node (section in pg.conf) to be cleaned up. This is a destructive operation that involves data loss for the node, followed by re-initialization based on its pg.conf settings."
    )
    parser_cleanup.set_defaults(func=cleanup_node)

    # --- Destroy Command ---
    parser_destroy = subparsers.add_parser("destroy", help="Permanently remove a node: stop server and delete its data directory.")
    parser_destroy.add_argument(
        "node_name",
        help="Identifier of the target node (section in pg.conf) to be destroyed. This is a destructive operation that involves stopping the server and completely removing its data directory."
    )
    parser_destroy.set_defaults(func=destroy_node)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # Ensure logs directory exists from config, even if node-specific log isn't immediately set up by a command
    # This is a general place for logs; specific commands will set up their node logs.
    # However, some early errors (like config loading) might not have a node_name yet.
    # So, we ensure the base_log_directory exists.
    temp_config_for_log_dir = load_config()
    base_log_dir = temp_config_for_log_dir.get('DEFAULT', 'base_log_directory', fallback='logs') # Use 'logs' as a last resort
    if not os.path.exists(base_log_dir):
        try:
            os.makedirs(base_log_dir)
            print_info(f"Created base log directory: {base_log_dir}")
        except OSError as e:
            # Not using print_error here as it exits; this is a soft setup step.
            print(f"{RED}Warning: Could not create base log directory {base_log_dir}: {e}{RESET}")


    if hasattr(args, 'func'):
        args.func(args)
    else:
        # This case should ideally not be reached if subparsers.required = True
        # and all subparsers have set_defaults(func=...).
        # However, if a new subparser is added without a func, it would end up here.
        parser.print_help(sys.stderr)
        print_error("No function associated with the chosen command.")


if __name__ == "__main__":
    main()
