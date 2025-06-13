import argparse
import configparser
import os
import sys
import subprocess
import logging
import shutil
from datetime import datetime

# --- Configuration ---
CONFIG_FILE = "pg.conf"
LOG_DIR = "logs"

# --- Color Codes for Output ---
GREEN_TICK = "\033[92m✔\033[0m"
RED_X = "\033[91m✘\033[0m"

# --- Global Logger ---
script_logger = logging.getLogger("pg_script")
script_log_file = os.path.join(LOG_DIR, "pg_script.log")

# Yellow color for warnings (though print_warning will handle specifics)
YELLOW_WARN = "\033[93m"
RESET_COLOR = "\033[0m"

def setup_script_logging():
    """Sets up logging for the script itself."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    if not script_logger.handlers:
        handler = logging.FileHandler(script_log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        script_logger.addHandler(handler)
        script_logger.setLevel(logging.INFO)
        script_logger.propagate = False

def print_success(message):
    print(f"{GREEN_TICK} {message}")
    script_logger.info(f"SUCCESS: {message}")

def print_failure(message, exit_script=False):
    print(f"{RED_X} {message}")
    script_logger.error(f"FAILURE: {message}")
    if exit_script:
        sys.exit(1)

def print_info(message):
    print(message)
    script_logger.info(message)

def print_warning(message):
    """Prints a warning message."""
    print(f"{YELLOW_WARN}WARN:{RESET_COLOR} {message}")
    script_logger.warning(message)

def load_config(config_file_path):
    """Loads the configuration from the given INI file."""
    config = configparser.ConfigParser(defaults={'bindir': '', 'postgres_options': ''}) # Changed None to ''
    if not os.path.exists(config_file_path):
        print_failure(f"Configuration file '{config_file_path}' not found.")
        script_logger.error(f"Configuration file '{config_file_path}' not found.")
        return None
    try:
        config.read(config_file_path)
        # Validate that LOG_DIR is accessible from config for script's own logging
        # This is a bit of a chicken-and-egg, setup_script_logging runs before config is loaded.
        # For now, we assume LOG_DIR global is used by setup_script_logging,
        # and pg.conf can override it for *other* purposes if needed.
        # Or, we could re-initialize logging if config specifies a different log_dir.
        # For now, let's keep it simple: script logs go to global LOG_DIR.
        # PostgreSQL instance logs will use log_dir from config.

        # Check for default essential paths
        if not config.has_option('DEFAULT', 'source_path') or not config.get('DEFAULT', 'source_path'):
            print_warning("DEFAULT 'source_path' is not defined in config. Compilation may fail.")
            # Not a fatal error for all commands, so just warn.
        if not config.has_option('DEFAULT', 'log_dir') or not config.get('DEFAULT', 'log_dir'):
            print_failure("DEFAULT 'log_dir' is not defined in config. This is required for operation logs.", exit_script=False) # Let it return None
            return None # Critical for node logging

        return config
    except configparser.Error as e:
        print_failure(f"Error parsing configuration file '{config_file_path}': {e}")
        script_logger.error(f"Error parsing configuration file '{config_file_path}': {e}")
        return None

def run_command(command, cwd=None, env=None, capture_output=True, text=True, check=False):
    if isinstance(command, list):
        command_str = " ".join(command)
    else:
        command_str = command
    script_logger.debug(f"Running command: {command_str} (cwd: {cwd})")
    print_info(f"Executing: {command_str}")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE if capture_output else sys.stdout,
            stderr=subprocess.PIPE if capture_output else sys.stderr,
            text=text,
            cwd=cwd,
            env=env,
            bufsize=1,
            universal_newlines=True if text else False,
            shell=isinstance(command, str)
        )
        stdout_lines, stderr_lines = [], []
        if capture_output:
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    if line:
                        script_logger.debug(f"STDOUT: {line}")
                        stdout_lines.append(line)
                        print(f"  {line}")
            if process.stderr:
                for line in iter(process.stderr.readline, ''):
                    line = line.strip()
                    if line:
                        script_logger.error(f"STDERR: {line}")
                        stderr_lines.append(line)
                        print(f"  \033[91m{line}\033[0m")
            if process.stdout: process.stdout.close()
            if process.stderr: process.stderr.close()
            return_code = process.wait()
            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)
        else:
            return_code = process.wait()
            stdout, stderr = "", ""
        script_logger.debug(f"Command '{command_str}' finished with exit code {return_code}.")
        if check and return_code != 0:
            error_message = f"Command '{command_str}' failed. Stderr:\n{stderr}"
            script_logger.error(error_message.replace('%', '%%'))
            raise subprocess.CalledProcessError(return_code, command, output=stdout, stderr=stderr)
        return stdout, stderr, return_code
    except FileNotFoundError:
        msg = f"Command not found: {command[0] if isinstance(command, list) else command.split()[0]}"
        script_logger.error(msg)
        if check: raise FileNotFoundError(msg)
        return "", msg, -1
    except Exception as e:
        error_message = str(e).replace('%', '%%')
        script_logger.error(f"Exception running command '{command_str}': {error_message}")
        if check: raise
        return "", str(e), -2

def handle_compile(args, config):
    """Handles the 'compile' command: extracts source, configures, builds, and installs PostgreSQL."""
    node_name = args.node_name  # For logging and context
    pg_version = args.pg

    print_info(f"Attempting to compile PostgreSQL {pg_version} (context: node '{node_name}').")
    script_logger.info(f"Compile command initiated for PG {pg_version}, context node: {node_name}")

    source_path_str = config.get('DEFAULT', 'source_path', fallback=None)
    if not source_path_str:
        print_failure("DEFAULT 'source_path' is not defined in the configuration file.", exit_script=True)
        # exit_script=True should terminate, but return for safety if it were changed
        return

    if not os.path.isdir(source_path_str):
        print_failure(f"Configured source_path '{source_path_str}' does not exist or is not a directory.", exit_script=True)
        return

    # Derived paths
    pg_source_dir_name = f"postgresql-{pg_version}"
    pg_source_abs_path = os.path.join(source_path_str, pg_source_dir_name)

    pg_tarball_name = f"{pg_source_dir_name}.tar.gz"
    pg_tarball_abs_path = os.path.join(source_path_str, pg_tarball_name)

    install_prefix = os.path.join(source_path_str, f"pgsql-{pg_version}")
    final_bindir = os.path.join(install_prefix, 'bin')

    script_logger.info(f"PostgreSQL version: {pg_version}")
    script_logger.info(f"Base source path from config: {source_path_str}")
    script_logger.info(f"Expected source directory for PG {pg_version}: {pg_source_abs_path}")
    script_logger.info(f"Expected tarball for extraction: {pg_tarball_abs_path}")
    script_logger.info(f"Installation prefix for this version: {install_prefix}")
    script_logger.info(f"Final binaries directory (bindir) will be: {final_bindir}")

    # Step 1: Check for existing source directory or extract tarball
    if not os.path.isdir(pg_source_abs_path):
        print_info(f"Source directory '{pg_source_abs_path}' not found for PostgreSQL {pg_version}.")
        if os.path.isfile(pg_tarball_abs_path):
            print_info(f"Found tarball '{pg_tarball_abs_path}'. Attempting to extract to '{source_path_str}'...")
            # tar -xzf {tarball} -C {destination_directory}
            extract_command = ["tar", "-xzf", pg_tarball_abs_path, "-C", source_path_str]
            # Execute in source_path_str to ensure correct extraction path if tarball contains relative paths
            _, stderr, retcode = run_command(extract_command, cwd=source_path_str)
            if retcode != 0:
                print_failure(f"Failed to extract tarball '{pg_tarball_abs_path}'. Error: {stderr}")
                return
            print_success(f"Successfully extracted '{pg_tarball_name}'.")
            # Verify that the expected directory was created by the extraction
            if not os.path.isdir(pg_source_abs_path):
                print_failure(f"Extraction of '{pg_tarball_name}' seemed to succeed, but the expected source directory '{pg_source_abs_path}' was not found. Check tarball contents.")
                return
        else:
            print_failure(f"Tarball '{pg_tarball_abs_path}' not found. Please download it to '{source_path_str}' for PostgreSQL version {pg_version} and try again.")
            return
    else:
        print_info(f"Using existing source directory for PostgreSQL {pg_version}: '{pg_source_abs_path}'")

    # Step 2: Configure
    print_info(f"Configuring PostgreSQL {pg_version} in '{pg_source_abs_path}' (prefix: '{install_prefix}')...")
    configure_env = os.environ.copy()
    configure_env['CFLAGS'] = "-g3 -O0" # Debug symbols, no optimization
    configure_env['LDFLAGS'] = f"-Wl,-rpath,{os.path.join(install_prefix, 'lib')}" # Embed rpath for lib discovery

    # Command: ./configure --prefix=/path/to/install --enable-cassert CFLAGS='-g3 -O0' LDFLAGS='-Wl,-rpath,...'
    # We pass CFLAGS and LDFLAGS via env, which is standard.
    configure_command = ["./configure", f"--prefix={install_prefix}", "--enable-cassert"]
    _, stderr, retcode = run_command(configure_command, cwd=pg_source_abs_path, env=configure_env)
    if retcode != 0:
        print_failure(f"Configuration step failed for PostgreSQL {pg_version}. Error: {stderr}")
        return
    print_success(f"Configuration of PostgreSQL {pg_version} complete.")

    # Step 3: Make
    num_cores = os.cpu_count() or 1 # Default to 1 if os.cpu_count() is None or 0
    print_info(f"Building PostgreSQL {pg_version} using {num_cores} core(s)... (This may take a while)")
    make_command = ["make", "-j", str(num_cores)]
    _, stderr, retcode = run_command(make_command, cwd=pg_source_abs_path)
    if retcode != 0:
        print_failure(f"Build (make) step failed for PostgreSQL {pg_version}. Error: {stderr}")
        return
    print_success(f"Build (make) of PostgreSQL {pg_version} complete.")

    # Step 4: Make Install
    print_info(f"Installing PostgreSQL {pg_version} to '{install_prefix}' using {num_cores} core(s)...")
    make_install_command = ["make", "install", "-j", str(num_cores)]
    _, stderr, retcode = run_command(make_install_command, cwd=pg_source_abs_path)
    if retcode != 0:
        print_failure(f"Installation (make install) step failed for PostgreSQL {pg_version}. Error: {stderr}")
        return

    print_success(f"Installation of PostgreSQL {pg_version} to '{install_prefix}' complete.")
    print_success(f"Binaries are now available in: {final_bindir}")
    print_info(f"To use this version for a node, update 'bindir = {final_bindir}' in your '{CONFIG_FILE}' for that node's section.")
    print_warning("Ensure that system dependencies for building PostgreSQL (e.g., readline-devel, zlib-devel, gcc, make) are installed on your system.")

def handle_initdb(args, config):
    """Handles the 'initdb' command for a specified node."""
    node_name = args.node_name
    print_info(f"Initializing PostgreSQL cluster for node '{node_name}'...")
    script_logger.info(f"Initdb command initiated for node: {node_name}")

    if not config.has_section(node_name):
        print_failure(f"Node '{node_name}' not found in configuration file '{CONFIG_FILE}'.", exit_script=True)
        return

    # Get node-specific configurations
    datadir = config.get(node_name, 'datadir', fallback=None)
    bindir = config.get(node_name, 'bindir', fallback=None) # Must be set, e.g., from compile step or manually
    port = config.getint(node_name, 'port', fallback=None) # Ensure port is integer
    # postgres_options is a string like "max_connections=100,shared_buffers=128MB"
    # Or it could be a list of options if config stores it differently. Assume comma-separated string.
    postgres_options_str = config.get(node_name, 'postgres_options', fallback='')

    if not datadir:
        print_failure(f"'datadir' is not configured for node '{node_name}'.", exit_script=True)
        return
    if not bindir:
        print_failure(f"'bindir' is not configured for node '{node_name}'. This path should point to PostgreSQL binaries (e.g., from a compile step).", exit_script=True)
        return
    if port is None: # Port can be 0, so check for None explicitly
        print_failure(f"'port' is not configured for node '{node_name}'.", exit_script=True)
        return

    # Resolve paths to be absolute for clarity and safety
    datadir = os.path.abspath(datadir)
    bindir = os.path.abspath(bindir)

    initdb_path = os.path.join(bindir, 'initdb')
    if not os.path.isfile(initdb_path):
        print_failure(f"initdb executable not found at '{initdb_path}'. Check 'bindir' for node '{node_name}'.", exit_script=True)
        return

    script_logger.info(f"Node '{node_name}': Data directory: {datadir}")
    script_logger.info(f"Node '{node_name}': Binaries directory: {bindir}")
    script_logger.info(f"Node '{node_name}': Port: {port}")
    script_logger.info(f"Node '{node_name}': Initdb path: {initdb_path}")

    # Check data directory status
    if os.path.exists(datadir):
        if os.listdir(datadir): # Check if directory is not empty
            print_failure(f"Data directory '{datadir}' exists and is not empty. initdb requires an empty or non-existent directory.", exit_script=True)
            return
    else:
        try:
            os.makedirs(datadir, exist_ok=True) # Create datadir if it doesn't exist
            print_info(f"Created data directory: {datadir}")
        except OSError as e:
            print_failure(f"Failed to create data directory '{datadir}'. Error: {e}", exit_script=True)
            return

    # Run initdb command
    # Using a default username 'postgres'. Could be made configurable.
    # --auth=trust for local development setup ease. Consider other auth methods for production.
    # For now, let's keep it simple and rely on initdb defaults for auth, or pg_hba.conf later.
    # Default is often 'trust' for local connections if no auth options are specified.
    print_info(f"Running initdb for node '{node_name}' in '{datadir}'...")
    # initdb_command = [initdb_path, "-D", datadir, "--username=postgres", "--auth=trust"]
    initdb_command = [initdb_path, "-D", datadir, "--username=postgres"]
    stdout, stderr, retcode = run_command(initdb_command)
    if retcode != 0:
        print_failure(f"initdb failed for node '{node_name}'. Error: {stderr}\nOutput: {stdout}")
        # Consider cleaning up datadir if initdb fails partially, but this can be risky.
        # For now, leave as is.
        return
    print_success(f"initdb successfully completed for node '{node_name}'.")

    # Append settings to postgresql.auto.conf
    pg_auto_conf_path = os.path.join(datadir, "postgresql.auto.conf")
    print_info(f"Appending configuration to '{pg_auto_conf_path}'...")
    try:
        with open(pg_auto_conf_path, 'a') as f: # Append mode
            f.write(f"\n# Settings added by pg_script.py initdb for node {node_name}\n")
            f.write(f"port = {port}\n")

            # Process postgres_options from config
            if postgres_options_str:
                options = [opt.strip() for opt in postgres_options_str.split(',') if opt.strip()]
                for option in options:
                    if '=' in option: # Ensure it's a key=value pair
                        f.write(f"{option}\n")
                    else:
                        print_warning(f"Ignoring invalid format option '{option}' from postgres_options for node '{node_name}'. Expected 'key=value'.")
                        script_logger.warning(f"Node {node_name}: Invalid postgres_option format: {option}")

        print_success(f"Successfully updated '{pg_auto_conf_path}'.")
    except IOError as e:
        print_failure(f"Failed to write to '{pg_auto_conf_path}'. Error: {e}")
        # This is problematic as initdb succeeded but config is partial.
        # Manual intervention might be needed.
        return

    print_info(f"Node '{node_name}' initialized. Use 'pg_script.py start {node_name}' to start the server.")

def get_node_config_for_control(node_name, config):
    """Retrieves and validates essential configuration for controlling a node (start, stop, restart)."""
    if not config.has_section(node_name):
        print_failure(f"Node '{node_name}' not found in configuration file '{CONFIG_FILE}'.", exit_script=True)
        return None # Should not be reached if exit_script=True

    datadir = config.get(node_name, 'datadir', fallback=None)
    bindir = config.get(node_name, 'bindir', fallback=None)

    if not datadir:
        print_failure(f"'datadir' is not configured for node '{node_name}'.", exit_script=True)
        return None
    if not bindir:
        print_failure(f"'bindir' is not configured for node '{node_name}'.", exit_script=True)
        return None

    datadir = os.path.abspath(datadir)
    bindir = os.path.abspath(bindir)

    pg_ctl_path = os.path.join(bindir, 'pg_ctl')
    if not os.path.isfile(pg_ctl_path):
        print_failure(f"pg_ctl executable not found at '{pg_ctl_path}'. Check 'bindir' for node '{node_name}'.", exit_script=True)
        return None

    default_log_dir = config.get('DEFAULT', 'log_dir', fallback=LOG_DIR) # Use global LOG_DIR if not in DEFAULT
    node_log_file = os.path.join(default_log_dir, f"{node_name}.log")
    # Ensure the directory for node-specific log files exists
    os.makedirs(os.path.dirname(node_log_file), exist_ok=True)


    return {
        "datadir": datadir,
        "bindir": bindir,
        "pg_ctl_path": pg_ctl_path,
        "log_file": node_log_file
    }

def handle_start(args, config):
    """Handles the 'start' command for a PostgreSQL node."""
    node_name = args.node_name
    print_info(f"Attempting to start PostgreSQL server for node '{node_name}'...")

    node_ctl_config = get_node_config_for_control(node_name, config)
    if not node_ctl_config: return # Error already printed by helper

    pg_ctl_path = node_ctl_config['pg_ctl_path']
    datadir = node_ctl_config['datadir']
    log_file = node_ctl_config['log_file']

    # pg_ctl start -D /data/directory -l /path/to/logfile.log
    start_command = [pg_ctl_path, "-D", datadir, "-l", log_file, "start"]
    stdout, stderr, retcode = run_command(start_command)

    if retcode == 0:
        # pg_ctl often returns 0 even if server fails to start but command was valid.
        # A better check involves querying status or checking logs, but for now, trust pg_ctl's output.
        print_success(f"PostgreSQL server for node '{node_name}' start command issued. Check log '{log_file}'. Output:\n{stdout}")
        if stderr:
            print_warning(f"Stderr from start command: {stderr}")
    else:
        print_failure(f"Failed to start PostgreSQL server for node '{node_name}'. Error: {stderr}\nOutput: {stdout}")

def handle_stop(args, config):
    """Handles the 'stop' command for a PostgreSQL node."""
    node_name = args.node_name
    stop_mode = args.mode # 'smart', 'fast', or 'immediate'
    print_info(f"Attempting to stop PostgreSQL server for node '{node_name}' (mode: {stop_mode})...")

    node_ctl_config = get_node_config_for_control(node_name, config)
    if not node_ctl_config: return

    pg_ctl_path = node_ctl_config['pg_ctl_path']
    datadir = node_ctl_config['datadir']

    # pg_ctl stop -D /data/directory -m <mode>
    stop_command = [pg_ctl_path, "-D", datadir, "-m", stop_mode, "stop"]
    stdout, stderr, retcode = run_command(stop_command)

    if retcode == 0:
        print_success(f"PostgreSQL server for node '{node_name}' stop command issued (mode: {stop_mode}). Output:\n{stdout}")
        if stderr:
            print_warning(f"Stderr from stop command: {stderr}")
    else:
        print_failure(f"Failed to stop PostgreSQL server for node '{node_name}'. Error: {stderr}\nOutput: {stdout}")

def handle_restart(args, config):
    """Handles the 'restart' command for a PostgreSQL node."""
    node_name = args.node_name
    print_info(f"Attempting to restart PostgreSQL server for node '{node_name}'...")

    node_ctl_config = get_node_config_for_control(node_name, config)
    if not node_ctl_config: return

    pg_ctl_path = node_ctl_config['pg_ctl_path']
    datadir = node_ctl_config['datadir']
    log_file = node_ctl_config['log_file']

    # pg_ctl restart -D /data/directory -l /path/to/logfile.log
    restart_command = [pg_ctl_path, "-D", datadir, "-l", log_file, "restart"]
    stdout, stderr, retcode = run_command(restart_command)

    if retcode == 0:
        print_success(f"PostgreSQL server for node '{node_name}' restart command issued. Check log '{log_file}'. Output:\n{stdout}")
        if stderr:
            print_warning(f"Stderr from restart command: {stderr}")
    else:
        print_failure(f"Failed to restart PostgreSQL server for node '{node_name}'. Error: {stderr}\nOutput: {stdout}")

def main():
    setup_script_logging() # Initial logging setup
    parser = argparse.ArgumentParser(
        description="PostgreSQL Management Script (pg_script)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--config', default=CONFIG_FILE, help=f"Path to the configuration file (default: {CONFIG_FILE})")

    subparsers = parser.add_subparsers(dest='command', title='Available commands', required=True)

    # Placeholder for future commands
    # initdb_parser = subparsers.add_parser('initdb', help='Initialize a new PostgreSQL cluster')
    # ...
    compile_parser = subparsers.add_parser('compile',
                                         help='Compile PostgreSQL from source. Assumes tarball exists in source_path.',
                                         description='Downloads (if not present) and compiles a specific version of PostgreSQL. The compiled binaries will be placed in a version-specific subdirectory within the source_path.')
    compile_parser.add_argument('node_name',
                                help="Context node name (primarily for logging and future integration). Compile options are generally global per version.")
    compile_parser.add_argument('--pg',
                                default='17',
                                help='PostgreSQL version to compile (e.g., 16, 17, 18). Default: 17. The script expects a tarball named postgresql-{version}.tar.gz to be present in the DEFAULT source_path defined in pg.conf.')
    compile_parser.set_defaults(func=handle_compile)

    initdb_parser = subparsers.add_parser('initdb',
                                          help='Initialize a new PostgreSQL cluster for a configured node.',
                                          description='Initializes a new PostgreSQL database cluster (using initdb) for a specified node. Requires datadir and bindir to be set in pg.conf for the node.')
    initdb_parser.add_argument('node_name',
                               help='The name of the node section in pg.conf to initialize (e.g., n1).')
    initdb_parser.set_defaults(func=handle_initdb)

    start_parser = subparsers.add_parser('start',
                                         help='Start a PostgreSQL server for a configured node.',
                                         description='Starts the PostgreSQL server for the specified node using pg_ctl.')
    start_parser.add_argument('node_name',
                              help='The name of the node (defined in pg.conf) to start.')
    start_parser.set_defaults(func=handle_start)

    stop_parser = subparsers.add_parser('stop',
                                        help='Stop a PostgreSQL server for a configured node.',
                                        description='Stops the PostgreSQL server for the specified node using pg_ctl.')
    stop_parser.add_argument('node_name',
                             help='The name of the node (defined in pg.conf) to stop.')
    # Add optional stop mode argument
    stop_parser.add_argument('-m', '--mode', choices=['smart', 'fast', 'immediate'], default='smart',
                             help='Stop mode (smart, fast, immediate). Default: smart.')
    stop_parser.set_defaults(func=handle_stop)

    restart_parser = subparsers.add_parser('restart',
                                           help='Restart a PostgreSQL server for a configured node.',
                                           description='Restarts the PostgreSQL server for the specified node using pg_ctl.')
    restart_parser.add_argument('node_name',
                                help='The name of the node (defined in pg.conf) to restart.')
    restart_parser.set_defaults(func=handle_restart)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        # load_config function already prints the error message.
        script_logger.critical("Configuration loading failed. Exiting.") # Use critical for this
        sys.exit(1) # Exit if config is essential

    print_success(f"Configuration loaded successfully from '{args.config}'.")
    print_info("Available sections in config: " + ", ".join(config.sections()))

    # Dispatch to the appropriate command handler
    if hasattr(args, 'func'):
        args.func(args, config) # Pass parsed args and loaded config to the handler
    else:
        # This case should ideally not be reached if commands are required and correctly set up.
        print_failure("No command function associated with the command. This is a script error.", exit_script=True)
        parser.print_help(sys.stderr)
        sys.exit(1)

    # The following is placeholder logic and should be removed or refactored if actual commands are handled by args.func
    # print_info(f"Command '{args.command}' received.")
    # # For testing, let's try to get a value from config if a node is specified
    # # This part is just for temporary testing of config loading with a hypothetical command.
    # # It will be replaced by actual command handlers.
    # if hasattr(args, 'node_name') and args.node_name and args.command != 'compile': # Avoid double processing for compile
    #     if config.has_section(args.node_name):
    #         print_info(f"Config for node '{args.node_name}':")
    #         for key, value in config.items(args.node_name):
    #             print(f"  {key} = {value}")
    #     else:
    #         print_warning(f"Node '{args.node_name}' not found in configuration.")
    # else:
    #     if args.command != 'compile':
    #        print_info("No specific node targeted by the current (placeholder) command logic.")


if __name__ == "__main__":
    main()
