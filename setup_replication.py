"""
PostgreSQL Streaming Replication Setup Script

This script automates the setup of PostgreSQL streaming replication (both asynchronous
and synchronous). It configures the primary server, performs a base backup to
initialize a replica, and provides guidance for replica server startup.

Key Features:
- Configures primary server's postgresql.conf and pg_hba.conf.
- Creates a dedicated replication user and a replication slot.
- Supports both asynchronous and synchronous replication modes.
- Performs a base backup to the replica's data directory using pg_basebackup.
- Configurable via command-line arguments, environment variables, or defaults.
- Uses logging for operational traceability and error reporting.

Prerequisites:
- Python 3.x
- psycopg2-binary library (`pip install psycopg2-binary`)
- PostgreSQL installed on the primary server.
- pg_basebackup utility available (usually part of PostgreSQL client tools).
- Sufficient permissions to:
    - Connect to the primary PostgreSQL instance as an admin user.
    - Modify PostgreSQL configuration files (postgresql.conf, pg_hba.conf).
    - Restart the PostgreSQL service on the primary.
    - Create directories and write data for the replica (e.g., in /var/lib/postgresql).
    - Run sudo for service restarts.
"""
import psycopg2
from psycopg2 import sql
import subprocess
import re
import os
import shutil
import logging
import sys
import argparse

# --- Database Interaction Functions ---
def connect_to_postgresql(db_name: str, user: str, password: str | None, host: str = "localhost", port: str = "5432") -> psycopg2.extensions.connection | None:
    """
    Connects to a PostgreSQL database using the provided parameters.

    Args:
        db_name (str): The name of the database to connect to.
        user (str): The username for the connection.
        password (str | None): The password for the user. Can be None if using other auth methods.
        host (str, optional): The database server host. Defaults to "localhost".
        port (str, optional): The database server port. Defaults to "5432".

    Returns:
        psycopg2.extensions.connection | None: A connection object if successful, None otherwise.
    """
    try:
        # Attempt to connect to the database
        conn = psycopg2.connect(dbname=db_name, user=user, password=password, host=host, port=port)
        logging.info(f"Successfully connected to PostgreSQL database: {db_name} on {host}")
        return conn
    except psycopg2.OperationalError as e:
        # Specific error for connection issues (e.g., host not found, port not open, auth failure)
        logging.error(f"Error connecting to PostgreSQL database {db_name} on {host}: {e}")
        return None
    except psycopg2.Error as e:
        # Catch other psycopg2 errors that might occur during connection setup
        logging.error(f"A psycopg2 error occurred while connecting to {db_name} on {host}: {e}")
        return None

# --- Shell Command Execution Functions ---
def execute_shell_command(command: list | str) -> tuple[str | None, str | None, int]:
    """
    Executes a shell command and returns its standard output, standard error, and return code.

    Args:
        command (list | str): The command to execute. Can be a list of arguments (recommended for security
                              and clarity) or a single string. If a string is provided and it contains
                              shell metacharacters (e.g., '*', '|', ';'), it will be executed with `shell=True`.

    Returns:
        tuple[str | None, str | None, int]: A tuple containing (stdout_str, stderr_str, return_code).
                                            On Python exceptions (e.g., command not found, subprocess error),
                                            it returns (None, error_message_str, -1).
    """
    cmd_str_for_print = ' '.join(command) if isinstance(command, list) else command
    try:
        logging.info(f"Executing command: {cmd_str_for_print}")
        # Determine shell usage: if command is a string and contains shell-specific characters.
        # Using shell=True can be a security hazard if command strings are built from untrusted input.
        use_shell = isinstance(command, str) and any(c in command for c in ['*', '?', '|', '<', '>', '&', ';'])

        process = subprocess.Popen(
            command if use_shell or isinstance(command, list) else command.split(), # Split string command if not using shell
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True # Ensures stdout/stderr are decoded as strings
        )
        stdout, stderr = process.communicate() # Wait for command to complete

        if process.returncode == 0:
            logging.info(f"Command '{cmd_str_for_print}' executed successfully.")
            if stdout: logging.debug(f"Stdout from '{cmd_str_for_print}':\n{stdout.strip()}")
        else:
            logging.error(f"Command '{cmd_str_for_print}' failed with code {process.returncode}. Error:\n{stderr.strip()}")
        return stdout, stderr, process.returncode
    except subprocess.SubprocessError as e:
        logging.error(f"Subprocess error while executing command '{cmd_str_for_print}': {e}")
        return None, str(e), -1
    except OSError as e:
        # This can happen if the command is not found or if there's a permission issue.
        logging.error(f"OS error (e.g., command not found or permissions issue) while executing command '{cmd_str_for_print}': {e}")
        return None, str(e), -1
    except Exception as e:
        logging.error(f"An unexpected exception occurred while executing command '{cmd_str_for_print}': {e}", exc_info=True)
        return None, str(e), -1

# --- Configuration File Management Functions ---
def modify_postgresql_conf(config_path: str, settings: dict, unset_keys: list = None) -> bool:
    """
    Modifies settings in a postgresql.conf file.

    The function first processes `unset_keys` by commenting out any existing lines
    matching these keys. Then, it processes `settings`: if a key exists (even if
    commented out by the previous step or already in the file), its value is updated
    (and the line is uncommented if necessary). If a key from `settings` does not
    exist, it's appended to the file.

    Args:
        config_path (str): The full path to the postgresql.conf file.
        settings (dict): A dictionary of settings to apply (e.g., {"wal_level": "replica"}).
                         Values are formatted appropriately (e.g., strings quoted if needed).
        unset_keys (list, optional): A list of keys to ensure are commented out. Defaults to None.

    Returns:
        bool: True if any changes were made to the file (or if the desired state was already met
              without errors). False if file not found or an I/O error occurred.
    """
    if not os.path.exists(config_path):
        logging.error(f"Configuration file {config_path} not found.")
        return False

    changes_made_to_content = False # Tracks if the content of the file actually changes
    lines = []
    try:
        with open(config_path, 'r') as f:
            lines = f.readlines()
    except IOError as e:
        logging.error(f"Error reading file {config_path}: {e}")
        return False

    # Process unset_keys first: comment them out
    if unset_keys:
        temp_lines_after_unset = []
        for line_content in lines:
            stripped_line = line_content.strip()
            modified_this_line = False
            for unset_key in unset_keys:
                # Regex to match 'key = value' or '#key = value'
                pattern = re.compile(r"^\s*(#\s*)?(" + re.escape(unset_key) + r")\s*=\s*(.*)$")
                if pattern.match(stripped_line):
                    if not stripped_line.startswith("#"): # Only comment if not already commented
                        temp_lines_after_unset.append(f"# {stripped_line}\n")
                        logging.info(f"Commented out setting in {config_path} for key '{unset_key}': {stripped_line}")
                        changes_made_to_content = True
                    else: # Already commented
                        temp_lines_after_unset.append(line_content)
                    modified_this_line = True
                    break # Key found, no need to check other unset_keys for this line
            if not modified_this_line:
                temp_lines_after_unset.append(line_content)
        lines = temp_lines_after_unset # Use these potentially modified lines for the next step

    # Process settings: modify or append
    settings_to_process = settings.copy() # To track which settings are appended vs modified
    final_lines = []
    for line_content in lines:
        stripped_line = line_content.strip()
        appended_for_setting = False # Flag to check if this line was replaced by a setting
        for key, value in list(settings_to_process.items()):
            pattern = re.compile(r"^\s*(#\s*)?(" + re.escape(key) + r")\s*=\s*(.*)$")
            match = pattern.match(stripped_line)
            if match:
                current_prefix = match.group(1) or ""  # e.g., "# " or ""
                current_value_str = match.group(3)   # The value part as found in file

                # Determine correct formatting for the new value
                # Strings are quoted unless they are known keywords or already seem quoted.
                # Numbers and specific keywords (on, off, true, false, etc.) are not quoted.
                if isinstance(value, str) and not (value.isdigit() or value.lower() in ['on', 'off', 'true', 'false', 'replica', 'logical', 'minimal', 'hot_standby', 'md5', 'scram-sha-256', 'trust', 'local', 'remote_write', 'remote_apply'] or (value.startswith("'") and value.endswith("'"))):
                    formatted_value = f"'{value}'"
                else:
                    formatted_value = str(value)

                # Modify if the line was commented OR the value is different
                if current_prefix.strip() == "#" or current_value_str != formatted_value:
                    final_lines.append(f"{key} = {formatted_value}\n")
                    logging.info(f"Set setting in {config_path}: {key} = {formatted_value} (original line: '{stripped_line}')")
                    changes_made_to_content = True
                else: # Already correctly set and uncommented
                    final_lines.append(line_content)

                if key in settings_to_process: # Mark as processed
                    del settings_to_process[key]
                appended_for_setting = True
                break # Key found and processed for this line
        if not appended_for_setting: # If line was not a match for any setting key
            final_lines.append(line_content)

    # Append any settings that were not found and processed in the file
    for key, value in settings_to_process.items():
        if isinstance(value, str) and not (value.isdigit() or value.lower() in ['on', 'off', 'true', 'false', 'replica', 'logical', 'minimal', 'hot_standby', 'md5', 'scram-sha-256', 'trust', 'local', 'remote_write', 'remote_apply'] or (value.startswith("'") and value.endswith("'"))):
            formatted_value = f"'{value}'"
        else:
            formatted_value = str(value)
        final_lines.append(f"{key} = {formatted_value}\n")
        logging.info(f"Appended setting to {config_path}: {key} = {formatted_value}")
        changes_made_to_content = True

    if changes_made_to_content:
        try:
            with open(config_path, 'w') as f:
                f.writelines(final_lines)
            logging.info(f"Successfully updated {config_path}")
        except IOError as e:
            logging.error(f"Error writing file {config_path}: {e}")
            return False # Failure to write changes
    else:
        logging.info(f"No content changes required in {config_path} for the given settings/unset_keys.")

    return True # Success, even if no content changes were strictly needed but file ops were okay.

def configure_pg_hba_for_replication(pg_hba_path: str, replication_user: str, replica_address: str, database: str = "replication") -> bool:
    """
    Adds a replication entry to pg_hba.conf if a suitable one doesn't already exist.

    The entry allows the specified replication user to connect from the replica_address
    for the purpose of replication (typically 'replication' database name).
    Uses scram-sha-256 authentication method.

    Args:
        pg_hba_path (str): Full path to the pg_hba.conf file.
        replication_user (str): The username for replication.
        replica_address (str): The IP address or subnet of the replica server (e.g., '192.168.1.101/32').
        database (str, optional): The database name for replication connections. Defaults to "replication".

    Returns:
        bool: True if the entry was added or a suitable one already existed. False on error.
    """
    if not os.path.exists(pg_hba_path):
        logging.error(f"Configuration file {pg_hba_path} not found.")
        return False

    auth_method = "scram-sha-256" # Recommended auth method
    hba_entry_to_add = f"host    {database}     {replication_user}    {replica_address}     {auth_method}\n"

    try:
        with open(pg_hba_path, 'r') as f:
            lines = f.readlines()

        entry_exists = False
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith("#") or not stripped_line: # Skip comments and empty lines
                continue

            # Simple check for exact line match first
            if stripped_line == hba_entry_to_add.strip():
                entry_exists = True
                break

            # Check for more permissive entries that might cover this specific need
            parts = re.split(r'\s+', stripped_line) # Split by one or more whitespace
            if len(parts) >= 5:
                p_type, p_db, p_user, p_address, p_method = parts[0], parts[1], parts[2], parts[3], parts[4]

                is_host_type = (p_type == "host")
                is_correct_db = (p_db == database or p_db == "all") # 'all' db covers 'replication'
                is_correct_user = (p_user == replication_user or p_user == "all") # 'all' user covers specific user
                # Address check: exact match, or 'all' (careful with this), or common wildcards
                is_correct_address = (p_address == replica_address or p_address == "all" or p_address == "0.0.0.0/0" or p_address == "::/0")
                # Method check: target method or a more permissive one (e.g. trust)
                is_sufficient_method = (p_method in [auth_method, "md5", "trust"]) # md5 might exist from older setups

                if is_host_type and is_correct_db and is_correct_user and is_correct_address and is_sufficient_method:
                    logging.info(f"Found existing or similar HBA entry in {pg_hba_path} that covers the requirement: '{stripped_line}'")
                    entry_exists = True
                    break

        if not entry_exists:
            logging.info(f"Adding HBA entry to {pg_hba_path}: {hba_entry_to_add.strip()}")
            # Ensure there's a newline before appending if the last line didn't have one
            if lines and not lines[-1].endswith('\n'):
                lines.append('\n')
            lines.append(hba_entry_to_add)

            with open(pg_hba_path, 'w') as f:
                f.writelines(lines)
            logging.info(f"Successfully updated {pg_hba_path} with new HBA entry.")
        else:
            logging.info(f"No changes required in {pg_hba_path}, suitable HBA entry already exists.")

        return True # True because the desired state (entry exists or was added) is achieved
    except IOError as e:
        logging.error(f"IOError processing file {pg_hba_path}: {e}")
        return False
    except Exception as e: # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred while configuring {pg_hba_path}: {e}", exc_info=True)
        return False

# --- Service Management Functions ---
def restart_postgresql_service(service_name: str = "postgresql") -> bool:
    """
    Restarts the PostgreSQL service using systemctl.

    Args:
        service_name (str, optional): The name of the PostgreSQL service.
                                      Defaults to "postgresql". Varies by distribution/version
                                      (e.g., "postgresql-14", "postgresql@14-main").

    Returns:
        bool: True if the service was restarted successfully, False otherwise.
    """
    # Basic validation for service name format
    if not re.match(r"^[a-zA-Z0-9._@-]+$", service_name):
        logging.error(f"Invalid service name format: {service_name}")
        return False

    command = ["sudo", "systemctl", "restart", service_name]
    # execute_shell_command handles its own logging for command execution details
    _stdout, _stderr, returncode = execute_shell_command(command)

    if returncode == 0:
        # Already logged by execute_shell_command, but an explicit info here is good.
        logging.info(f"PostgreSQL service '{service_name}' restart command issued successfully.")
        return True
    else:
        # Error details already logged by execute_shell_command
        logging.error(f"Attempt to restart PostgreSQL service '{service_name}' failed.")
        return False

# --- Replication Setup Functions ---
def create_replication_user(conn_params: dict, replication_user: str, replication_password: str) -> bool:
    """
    Creates a replication user in PostgreSQL if it doesn't already exist.

    Args:
        conn_params (dict): Connection parameters for the PostgreSQL server
                            (keys: 'host', 'port', 'dbname', 'user', 'password').
                            The user in conn_params should have rights to create roles.
        replication_user (str): The username for the new replication user.
        replication_password (str): The password for the new replication user. Can be None if password
                                    auth is not intended immediately for this user (e.g. peer auth).

    Returns:
        bool: True if the user was created or already existed, False on error.
    """
    conn = None
    try:
        logging.info(f"Attempting to connect to DB (user: {conn_params.get('user')}) to check/create replication user '{replication_user}'...");
        conn = connect_to_postgresql(**conn_params)
        if not conn:
            return False # connect_to_postgresql already logs the error

        conn.autocommit = True # CREATE USER cannot run inside a transaction block unless it's the first command
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute(sql.SQL("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s"), [replication_user])
            if cur.fetchone():
                logging.info(f"Replication user '{replication_user}' already exists.")
                # Consider verifying if existing user has REPLICATION attribute if script needs to be very robust.
                # e.g. cur.execute("SELECT rolreplication FROM pg_catalog.pg_roles WHERE rolname = %s", [replication_user])
                #      if not cur.fetchone()[0]: logging.warning(...) / attempt ALTER USER
                return True
            else:
                # Create user with replication privilege
                logging.info(f"Creating replication user '{replication_user}'...")
                if not replication_password:
                    logging.warning(f"Creating replication user '{replication_user}' without a password. Ensure alternative auth is configured.")
                    create_user_query = sql.SQL("CREATE USER {} WITH REPLICATION").format(sql.Identifier(replication_user))
                    cur.execute(create_user_query)
                else:
                    create_user_query = sql.SQL("CREATE USER {} WITH REPLICATION PASSWORD %s").format(sql.Identifier(replication_user))
                    cur.execute(create_user_query, [replication_password])
                logging.info(f"Successfully created replication user '{replication_user}'.")
                return True
    except psycopg2.Error as e: # Catch specific database errors
        logging.error(f"Database error concerning replication user '{replication_user}': {e}")
        return False
    except Exception as e: # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred concerning replication user '{replication_user}': {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()
            logging.debug(f"Database connection closed for create_replication_user (user: {replication_user}).")

def create_replication_slot(conn_params: dict, slot_name: str, slot_type: str = "physical", temporarily: bool = False) -> bool:
    """
    Creates a replication slot on the primary server if it doesn't already exist.

    Args:
        conn_params (dict): Connection parameters for the PostgreSQL server.
                            The user typically needs superuser or REPLICATION privileges.
        slot_name (str): The name for the replication slot.
        slot_type (str, optional): Type of slot ('physical' or 'logical'). Defaults to "physical".
        temporarily (bool, optional): If True, creates a temporary slot. Defaults to False.
                                     Note: temporary physical slots are session-bound and not typically used for persistent replication.

    Returns:
        bool: True if the slot was created or already existed, False on error.
    """
    conn = None
    try:
        logging.info(f"Attempting to connect to database (user: {conn_params.get('user')}) to check/create replication slot '{slot_name}'...");
        conn = connect_to_postgresql(**conn_params)
        if not conn:
            return False # Error logged by connect_to_postgresql

        conn.autocommit = True
        with conn.cursor() as cur:
            # Check if slot exists
            cur.execute(sql.SQL("SELECT 1 FROM pg_catalog.pg_replication_slots WHERE slot_name = %s"), [slot_name])
            if cur.fetchone():
                logging.info(f"Replication slot '{slot_name}' already exists.")
                return True
            else:
                logging.info(f"Creating {slot_type} replication slot '{slot_name}' (temporary={temporarily})...")
                if slot_type.lower() not in ["physical", "logical"]:
                    logging.error(f"Invalid slot_type '{slot_type}'. Must be 'physical' or 'logical'.")
                    return False

                params = [slot_name]
                if slot_type.lower() == "physical":
                    # pg_create_physical_replication_slot(slot_name name, immediately_reserve boolean DEFAULT false, temporary boolean DEFAULT false, two_phase boolean DEFAULT false)
                    # Setting immediately_reserve and two_phase to false for simplicity.
                    create_slot_query = sql.SQL("SELECT pg_catalog.pg_create_physical_replication_slot(%s, false, %s)")
                    params.append(temporarily)
                else: # logical
                    # pg_create_logical_replication_slot(slot_name name, plugin name, temporary boolean DEFAULT false, two_phase boolean DEFAULT false)
                    output_plugin = "test_decoding" # This should ideally be a parameter or a script constant
                    logging.warning(f"Logical slot creation requires an output_plugin. Defaulting to '{output_plugin}'. Ensure this plugin is available and suitable.")
                    create_slot_query = sql.SQL("SELECT pg_catalog.pg_create_logical_replication_slot(%s, %s, %s)")
                    params.insert(1, output_plugin) # Insert plugin name after slot_name
                    params.append(temporarily) # Add the temporary flag

                cur.execute(create_slot_query, params)
                logging.info(f"Successfully created {slot_type} replication slot '{slot_name}'.")
                return True
    except psycopg2.Error as e:
        logging.error(f"Database error while creating {slot_type} slot '{slot_name}': {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred while creating {slot_type} slot '{slot_name}': {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()
            logging.debug(f"Database connection closed for create_replication_slot (slot: {slot_name}).")

def perform_pg_basebackup(primary_conn_dsn: str, pgdata_replica: str, replication_password_for_log: str | None, backup_label: str = "pg_basebackup_replica") -> bool:
    """
    Performs pg_basebackup from the primary to initialize the replica's data directory.

    Args:
        primary_conn_dsn (str): DSN string for connecting to the primary server.
        pgdata_replica (str): Path to the replica's PostgreSQL data directory.
        replication_password_for_log (str | None): The replication password, used ONLY for masking in logs.
                                                   The actual password should be part of the DSN.
        backup_label (str, optional): Label for the backup. Defaults to "pg_basebackup_replica".

    Returns:
        bool: True if pg_basebackup completed successfully, False otherwise.
    """
    try:
        # Pre-check for replica data directory
        if os.path.exists(pgdata_replica):
            # Check if directory is not empty. os.listdir() will raise an error if path is not a dir.
            if not os.path.isdir(pgdata_replica):
                 logging.error(f"Path '{pgdata_replica}' for replica data exists but is not a directory. Aborting.")
                 return False
            if os.listdir(pgdata_replica):
                logging.error(f"Replica data directory '{pgdata_replica}' exists and is not empty. Aborting pg_basebackup to prevent data loss.")
                return False
            logging.info(f"Replica data directory '{pgdata_replica}' exists and is empty. Proceeding with backup.")
        else:
            logging.info(f"Replica data directory '{pgdata_replica}' does not exist. Creating it...")
            os.makedirs(pgdata_replica, exist_ok=True)
            os.chmod(pgdata_replica, 0o700)
            logging.info(f"Created directory '{pgdata_replica}' with restrictive permissions (0700).")

        command = [
            "pg_basebackup", "-d", primary_conn_dsn, "-D", pgdata_replica,
            "-X", "stream", "-P", "-R", "-l", backup_label
        ]

        # Mask password in DSN for logging
        dsn_for_log = primary_conn_dsn
        if replication_password_for_log: # Check if password was provided to mask
            dsn_for_log = primary_conn_dsn.replace(replication_password_for_log, '********')
        logging.info(f"Attempting to perform pg_basebackup to '{pgdata_replica}' using DSN: '{dsn_for_log}'")

        _stdout, _stderr, returncode = execute_shell_command(command)

        if returncode == 0:
            logging.info(f"pg_basebackup completed successfully to '{pgdata_replica}'.")
            return True
        else:
            # Error already logged by execute_shell_command
            logging.error(f"pg_basebackup failed for '{pgdata_replica}'.")
            return False
    except OSError as e:
        logging.error(f"OS error during pg_basebackup setup for '{pgdata_replica}': {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected exception occurred during pg_basebackup to '{pgdata_replica}': {e}", exc_info=True)
        return False

# --- Main Orchestration ---
def main():
    """
    Main function to orchestrate the PostgreSQL replication setup.
    Parses command-line arguments, configures logging, and executes setup steps.
    """
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(funcName)s - L%(lineno)d - %(message)s', # Added module, funcName, lineno
                        datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        description="Automate PostgreSQL streaming replication setup.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    pg_common_group = parser.add_argument_group('PostgreSQL Common Settings')
    pg_common_group.add_argument('--pg-version', default=os.environ.get("PG_VERSION", "16"), help="PostgreSQL version (e.g., '16'). ENV: PG_VERSION")
    pg_common_group.add_argument('--pg-cluster-name', default=os.environ.get("PG_CLUSTER_NAME", "main"), help="PostgreSQL cluster name (e.g., 'main'). ENV: PG_CLUSTER_NAME")

    primary_group = parser.add_argument_group('Primary Server Settings')
    primary_group.add_argument('--primary-host', default=os.environ.get("PG_PRIMARY_HOST", "localhost"), help="Primary server host. ENV: PG_PRIMARY_HOST")
    primary_group.add_argument('--primary-port', type=int, default=int(os.environ.get("PG_PRIMARY_PORT", "5432")), help="Primary server port. ENV: PG_PRIMARY_PORT")
    primary_group.add_argument('--primary-db', default=os.environ.get("PG_DB_NAME", "postgres"), help="Database name on primary for admin tasks. ENV: PG_DB_NAME")
    primary_group.add_argument('--primary-user', default=os.environ.get("PG_ADMIN_USER", "postgres"), help="Admin user on primary. ENV: PG_ADMIN_USER")
    primary_group.add_argument('--primary-password', default=os.environ.get("PG_ADMIN_PASSWORD"), help="Password for admin user on primary. ENV: PG_ADMIN_PASSWORD")
    primary_group.add_argument('--primary-psql-conf-path', help="Path to primary postgresql.conf. If not set, derived from version/cluster.")
    primary_group.add_argument('--primary-pg-hba-path', help="Path to primary pg_hba.conf. If not set, derived from version/cluster.")
    primary_group.add_argument('--primary-service-name', help="Name of primary PostgreSQL service. If not set, derived (e.g., postgresql@<ver>-<cluster>).")

    replica_group = parser.add_argument_group('Replica Server Settings')
    replica_group.add_argument('--replica-pgdata-path', help="Path for replica's data directory. Default derived from PG_VERSION and CLUSTER_NAME.")
    replica_group.add_argument('--replica-ip-for-hba', default=os.environ.get("REPLICA_IP", "127.0.0.1"), help="Replica IP address for pg_hba.conf on primary. ENV: REPLICA_IP")

    replication_group = parser.add_argument_group('Replication Specific Settings')
    replication_group.add_argument('--replication-user', default=os.environ.get("REPL_USER", "repl_user"), help="Replication username. ENV: REPL_USER")
    replication_group.add_argument('--replication-password', default=os.environ.get("REPL_PASSWORD"), help="Password for replication user. ENV: REPL_PASSWORD")
    replication_group.add_argument('--replication-slot-name', help="Name for replication slot. Default: {replication_user}_slot_physical.")
    replication_group.add_argument('--replication-type', choices=['async', 'sync'], default=os.environ.get('REPLICATION_TYPE', 'async').lower(), help="Replication type. ENV: REPLICATION_TYPE")
    replication_group.add_argument('--sync-replica-app-name', default=os.environ.get('SYNC_REPLICA_NAME', 'replica1_app_name'), help="Application name for synchronous replica. ENV: SYNC_REPLICA_NAME")

    args = parser.parse_args()

    pg_version = args.pg_version
    pg_cluster_name = args.pg_cluster_name
    primary_base_path = f"/etc/postgresql/{pg_version}/{pg_cluster_name}"

    primary_host = args.primary_host
    primary_port = args.primary_port
    primary_admin_user = args.primary_user
    primary_admin_password = args.primary_password
    primary_db_name = args.primary_db

    primary_psql_conf_path = args.primary_psql_conf_path or f"{primary_base_path}/postgresql.conf"
    primary_pg_hba_path = args.primary_pg_hba_path or f"{primary_base_path}/pg_hba.conf"
    primary_service_name = args.primary_service_name or f"postgresql@{pg_version}-{pg_cluster_name}"

    replica_pgdata_path = args.replica_pgdata_path or f"/var/lib/postgresql/{pg_version}/{pg_cluster_name}_replica_data"
    replica_service_name = f"postgresql@{pg_version}-{pg_cluster_name}-replica"

    replication_user = args.replication_user
    replication_password = args.replication_password # This can be None, functions should handle it or warn
    replication_slot_name = args.replication_slot_name or f"{replication_user}_slot_physical"
    replica_ip_address_for_hba = args.replica_ip_for_hba

    replication_type = args.replication_type
    synchronous_standby_application_name = args.sync_replica_app_name

    effective_config_logging = {
        'PostgreSQL Version': pg_version, 'PostgreSQL Cluster Name': pg_cluster_name,
        'Primary Host': primary_host, 'Primary Port': primary_port, 'Primary Admin User': primary_admin_user,
        'Primary DB Name': primary_db_name, 'Primary postgresql.conf Path': primary_psql_conf_path,
        'Primary pg_hba.conf Path': primary_pg_hba_path, 'Primary Service Name': primary_service_name,
        'Replica Data Path': replica_pgdata_path, 'Replica IP for HBA': replica_ip_address_for_hba,
        'Replication User': replication_user, 'Replication Slot Name': replication_slot_name,
        'Replication Type': replication_type,
    }
    if replication_type == 'sync': effective_config_logging['Synchronous Replica App Name'] = synchronous_standby_application_name

    logging.info("--- Effective Script Configuration (Passwords Masked/Omitted) ---")
    for key, value in effective_config_logging.items(): logging.info(f"{key}: {value}")
    logging.info("--- End of Effective Script Configuration ---")

    logging.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    logging.warning("!!! WARNING: This script performs actual system and database modifications !!!")
    # ... (rest of warning)
    logging.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")

    if not primary_admin_password:
        logging.warning("Primary admin password not provided. Operations may fail if other auth methods are not configured.")
    if not replication_password: # For create_replication_user and DSN for pg_basebackup
        logging.warning("Replication password not provided. User creation or pg_basebackup may fail if other auth methods are not configured for the replication user.")

    primary_conn_params = {
        "host": primary_host, "port": str(primary_port), "dbname": primary_db_name,
        "user": primary_admin_user, "password": primary_admin_password
    }

    logging.info(f"--- Configuring for {replication_type.upper()} REPLICATION ---")
    logging.info("--- Starting Primary Server Setup ---")

    logging.info("Step 1: Creating/Verifying replication user...")
    if not create_replication_user(primary_conn_params, replication_user, replication_password):
        logging.error(f"CRITICAL: Failed to create or verify replication user '{replication_user}'. Aborting setup.")
        sys.exit(1)

    logging.info("Step 2: Modifying primary postgresql.conf...")
    primary_conf_settings = {
        "listen_addresses": "*", "wal_level": "replica", "max_wal_senders": "10",
        "wal_keep_size": "512MB", "hot_standby": "on"
    }
    keys_to_unset_for_async = []
    if replication_type == 'sync':
        logging.info(f"Configuring for SYNCHRONOUS replication. Standby application name: '{synchronous_standby_application_name}'")
        primary_conf_settings["synchronous_commit"] = "on"
        primary_conf_settings["synchronous_standby_names"] = synchronous_standby_application_name
    else:
        logging.info("Configuring for ASYNCHRONOUS replication.")
        primary_conf_settings["synchronous_commit"] = "local"
        keys_to_unset_for_async.append("synchronous_standby_names")

    if not modify_postgresql_conf(primary_psql_conf_path, primary_conf_settings, unset_keys=keys_to_unset_for_async if keys_to_unset_for_async else None):
        logging.warning(f"Modification of {primary_psql_conf_path} reported issues or made no changes. Please check logs and configuration manually if script proceeds.")

    logging.info("Step 3: Configuring primary pg_hba.conf...")
    if not configure_pg_hba_for_replication(primary_pg_hba_path, replication_user, replica_ip_address_for_hba):
        logging.error(f"CRITICAL: Failed to configure {primary_pg_hba_path} for replication. Aborting setup.")
        sys.exit(1)

    logging.info("Step 4: Creating/Verifying replication slot...")
    if not create_replication_slot(primary_conn_params, replication_slot_name, slot_type="physical"):
        logging.error(f"CRITICAL: Failed to create or verify physical replication slot '{replication_slot_name}'. Aborting setup.")
        sys.exit(1)

    logging.info("Step 5: Restarting primary PostgreSQL service...")
    if not restart_postgresql_service(primary_service_name):
        logging.error(f"CRITICAL: Failed to restart primary PostgreSQL service '{primary_service_name}'. Manual restart and log check required. Aborting setup.")
        sys.exit(1)

    logging.info("--- Primary Server Setup Complete ---")
    logging.info("--- Starting Replica Server Setup (pg_basebackup) ---")

    logging.info("Step 6: Performing pg_basebackup...")
    if os.path.exists(replica_pgdata_path):
        logging.info(f"Found existing replica data directory at '{replica_pgdata_path}'. Removing it for a clean backup...")
        try: shutil.rmtree(replica_pgdata_path)
        except Exception as e:
            logging.error(f"CRITICAL: Error removing existing replica data directory '{replica_pgdata_path}': {e}. Aborting setup.")
            sys.exit(1)

    primary_conn_dsn_for_backup = f"host={primary_host} port={primary_port} user={replication_user} password={replication_password} dbname={primary_db_name}"
    if replication_type == 'sync':
        primary_conn_dsn_for_backup += f" application_name={synchronous_standby_application_name}"

    # Pass replication_password for logging purposes only (it will be masked)
    if not perform_pg_basebackup(primary_conn_dsn_for_backup, replica_pgdata_path, replication_password):
        logging.error(f"CRITICAL: pg_basebackup to '{replica_pgdata_path}' failed. Check logs. Aborting setup.")
        sys.exit(1)

    logging.info(f"pg_basebackup with -R option should have created standby.signal (or recovery.signal) and updated postgresql.auto.conf with primary_conninfo.")
    if replication_type == 'sync':
        logging.info(f"IMPORTANT FOR SYNC REPLICA: Ensure the replica's postgresql.auto.conf (or equivalent for your PG version) has primary_conninfo including 'application_name={synchronous_standby_application_name}'.")
        logging.info(f"Alternatively, set PGAPPNAME env var for the replica's PostgreSQL process or in its connection string within primary_conninfo.")

    logging.info("--- Replica Server Setup (pg_basebackup) Complete ---")

    logging.info("--- Final Instructions ---")
    # ... (rest of final instructions)

    logging.info("PostgreSQL replication setup script orchestration finished successfully.")

if __name__ == "__main__":
    main()
