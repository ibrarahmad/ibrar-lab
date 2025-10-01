#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import List
import socket
import time

# Colors kept as a small utility namespace
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


@dataclass
class ClusterConfig:
    # bin_dir will be resolved from pg_config on PATH; default empty until build_cluster fills it
    bin_dir: str = ""
    # lib_dir and share_dir resolved from pg_config for extension checks
    lib_dir: str = ""
    share_dir: str = ""
    # Use current working directory for data directories
    data_base: str = os.getcwd()
    start_port: int = int(os.environ.get("START_PORT", 5540))  # Updated default port to 5540
    default_num_nodes: int = 3
    # Log file in CWD
    log_file: str = "spock_cluster.log"
    step_width: int = 50


class Logger:
    def __init__(self, log_file: str):
        self.log_file = log_file

    def log(self, msg: str, verbose: bool = False) -> None:
        # Colorize status at end of line
        msg_col = msg
        if msg.rstrip().endswith("[OK]"):
            msg_col = msg.replace("[OK]", f"{Colors.GREEN}[OK]{Colors.RESET}")
        elif msg.rstrip().endswith("[FAILED]"):
            msg_col = msg.replace("[FAILED]", f"{Colors.RED}[FAILED]{Colors.RESET}")
        elif msg.rstrip().endswith("[SKIPPED]"):
            msg_col = msg.replace("[SKIPPED]", f"{Colors.BLUE}[SKIPPED]{Colors.RESET}")
        print(msg_col)
        with open(self.log_file, "a") as f:
            f.write(msg + "\n")

    def header(self):
        with open(self.log_file, "a") as f:
            f.write(f"\n==== {datetime.now()} ====\n")


class SpockCluster:
    def __init__(self, cfg: ClusterConfig, logger: Logger):
        self.cfg = cfg
        self.logger = logger

    # ----- helpers -----
    def nodes(self, num_nodes: int) -> List[int]:
        return list(range(1, num_nodes + 1))

    def port(self, node_num: int) -> int:
        # Primary nodes use ports 5431, 5432, 5433
        return 5430 + node_num

    def _port_in_use(self, port: int) -> bool:
        """Return True if TCP port is already bound (simple socket connect test)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def data_dir(self, node_num: int) -> str:
        return f"{self.cfg.data_base}/data{node_num}"

    def step_msg(self, action: str, node_num: int) -> str:
        return f"{action} node {node_num} ...".ljust(self.cfg.step_width)

    def has_spock(self) -> bool:
        # Check for spock library in libdir; consider both .so and .dylib just in case
        candidates = [Path(self.cfg.lib_dir) / "spock.so", Path(self.cfg.lib_dir) / "spock.dylib"]
        return any(p.exists() for p in candidates)

    def node_dsn(self, node_num: int) -> str:
        # Build a DSN for local connections used in spock.node_create and sub_create
        return f"host=127.0.0.1 dbname=pgedge port={self.port(node_num)} user=pgedge password=pgedge"

    def run(self, cmd, verbose: bool = False, **kwargs) -> bool:
        """Run a command, returning True on success. Honors verbose by streaming output.
        If not verbose, stdout/stderr are suppressed unless explicitly provided in kwargs.
        """
        if verbose:
            print(f"\033[93m{cmd}\033[0m")
            proc = subprocess.run(cmd, **kwargs)
        else:
            if "stdout" not in kwargs:
                kwargs["stdout"] = subprocess.DEVNULL
            if "stderr" not in kwargs:
                kwargs["stderr"] = subprocess.DEVNULL
            proc = subprocess.run(cmd, **kwargs)
        return proc.returncode == 0

    # Helper: get postmaster PID from data directory
    def _get_postmaster_pid(self, node_num: int) -> int | None:
        try:
            pid_path = Path(self.data_dir(node_num)) / "postmaster.pid"
            if pid_path.exists():
                with open(pid_path, "r") as f:
                    first = f.readline().strip()
                    if first.isdigit():
                        return int(first)
        except Exception:
            pass
        return None

    # Helper: force kill postgresql if needed
    def _kill_postgres(self, node_num: int, verbose: bool = False) -> bool:
        pid = self._get_postmaster_pid(node_num)
        if pid:
            return self.run(["kill", "-9", str(pid)], verbose=verbose)
        return False

    # ----- operations -----
    def is_running(self, node_num: int, verbose: bool = False) -> bool:
        data_dir = self.data_dir(node_num)
        return self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", data_dir, "status"], verbose=verbose)

    def init_node(self, node_num: int, verbose: bool = False):
        data_dir = self.data_dir(node_num)
        msg = self.step_msg("Initializing", node_num)
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        if not Path(f"{data_dir}/PG_VERSION").exists():
            if self.run([f"{self.cfg.bin_dir}/initdb", "-D", data_dir], verbose=verbose):
                self.logger.log(msg + "[OK]", verbose)
            else:
                self.logger.log(msg + "[FAILED]", verbose)
        else:
            self.logger.log(msg + "[SKIPPED]", verbose)

    def start_node(self, node_num: int, verbose: bool = False):
        data_dir = self.data_dir(node_num)
        port = self.port(node_num)
        msg = self.step_msg("Starting", node_num)
        if not Path(data_dir).is_dir():
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        # Skip if already running
        if self.is_running(node_num, verbose=verbose):
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        # Detect external port conflict early and fail with guidance
        if self._port_in_use(port):
            self.logger.log(msg + f"[FAILED]", verbose)
            guidance = (
                f"Port {port} already in use by another process. Set START_PORT env var or use --start-port to choose a free range."
            )
            if verbose:
                self.logger.log(self.step_msg("Port conflict", node_num) + "[FAILED]", verbose)
            # Also append guidance to main log file
            with open(self.cfg.log_file, "a") as f:
                f.write(guidance + "\n")
            return
        if self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", data_dir, "-o", f"-p {port}", "-l", f"{data_dir}/server.log", "start"], verbose=verbose):
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def create_db(self, node_num: int, dbname: str = "pgedge", owner: str | None = None, verbose: bool = False):
        """Create a database on the given node (requires the node to be running)."""
        port = self.port(node_num)
        msg = self.step_msg(f"Creating DB {dbname}", node_num)
        # Idempotent: skip if DB exists
        try:
            out = subprocess.check_output(
                [f"{self.cfg.bin_dir}/psql", "-d", "postgres", f"-p{port}", "-Atc",
                 f"SELECT 1 FROM pg_database WHERE datname = '{dbname}'"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out == "1":
                self.logger.log(msg + " [SKIPPED]", verbose)
                return
        except subprocess.CalledProcessError:
            pass

        # Retry mechanism for database creation
        retries = 3
        for attempt in range(1, retries + 1):
            cmd = [f"{self.cfg.bin_dir}/createdb", dbname, f"-p{port}"]
            if owner:
                cmd.extend(["-O", owner])
            if self.run(cmd, verbose=verbose):
                self.logger.log(msg + " [OK]", verbose)
                return
            else:
                self.logger.log(msg + f" [FAILED] (Attempt {attempt}/{retries})", verbose)
                time.sleep(2)  # Wait before retrying

        self.logger.log(msg + " [FAILED]: Could not create database after retries", verbose)

    def create_user(self, node_num: int, username: str = "pgedge", verbose: bool = False):
        """Create a login role if it does not exist."""
        port = self.port(node_num)
        msg = self.step_msg(f"Creating user {username}", node_num)
        try:
            out = subprocess.check_output(
                [f"{self.cfg.bin_dir}/psql", "-d", "postgres", f"-p{port}", "-Atc",
                 f"SELECT 1 FROM pg_roles WHERE rolname = '{username}'"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out == "1":
                self.logger.log(msg + "[SKIPPED]", verbose)
                return
        except subprocess.CalledProcessError:
            # Fall through and attempt to create; run() will handle logging
            pass
        created = self.run([f"{self.cfg.bin_dir}/psql", "-d", "postgres", f"-p{port}", "-c",
                             f"CREATE ROLE {username} LOGIN"], verbose=verbose)
        if created:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def stop_node(self, node_num: int, verbose: bool = False):
        data_dir = self.data_dir(node_num)
        msg = self.step_msg("Stopping", node_num)
        if not Path(data_dir).is_dir():
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        # Try fast stop first
        result = self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", data_dir, "stop", "-m", "fast"], verbose=verbose)
        if not result:
            # Try immediate if fast failed
            result = self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", data_dir, "stop", "-m", "immediate"], verbose=verbose)
        # If still running, force kill
        if not result and self.is_running(node_num, verbose=verbose):
            result = self._kill_postgres(node_num, verbose=verbose)
        if result:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def destroy_node(self, node_num: int, verbose: bool = False):
        data_dir = self.data_dir(node_num)
        msg = self.step_msg("Destroying", node_num)
        if Path(data_dir).is_dir():
            # Use common runner so -v prints the command
            ok = self.run(["rm", "-rf", data_dir], verbose=verbose)
            if ok:
                self.logger.log(msg + "[OK]", verbose)
            else:
                self.logger.log(msg + "[FAILED]", verbose)
        else:
            self.logger.log(msg + "[OK]", verbose)

    def cleanup_node(self, node_num: int, verbose: bool = False):
        port = self.port(node_num)
        msg = self.step_msg("Cleaning", node_num)
        cmds = [
            [f"{self.cfg.bin_dir}/dropdb", "--if-exists", "pgedge", f"-p{port}"],
            [f"{self.cfg.bin_dir}/createdb", "pgedge", f"-p{port}"],
            # dblink is optional but harmless if installed
            [f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-c", "create extension if not exists dblink"],
            [f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-t", "-A", "-c",
             "SELECT 'SELECT pg_drop_replication_slot(' || quote_literal(slot_name) || ');' FROM pg_replication_slots WHERE slot_type = 'logical';"],
            [f"{self.cfg.bin_dir}/psql", "-d", "pgedge", f"-p{port}", "-Atc",
             "SELECT 'SELECT pg_replication_origin_drop(' || quote_literal(roname) || ');' FROM pg_replication_origin;"]
        ]
        # Only attempt spock extension management if spock library is present
        if self.has_spock():
            cmds.insert(2, [f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-c", "create extension if not exists spock"])
            cmds.append([f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-c", "drop extension if exists spock; create extension spock"])
        ok = True
        for cmd in cmds:
            # For SQL that outputs SQL, pipe to psql
            joined = " ".join(cmd)
            if "pg_drop_replication_slot" in joined or "pg_replication_origin_drop" in joined:
                try:
                    sql_out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
                    if sql_out.strip():
                        if not self.run([f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}"], input=sql_out, text=True, verbose=verbose):
                            ok = False
                except subprocess.CalledProcessError:
                    ok = False
            else:
                if not self.run(cmd, verbose=verbose):
                    ok = False
        if ok:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def write_auto_conf(self, node_num: int, verbose: bool = False, replica_mode: bool = False, include_spock: bool = True):
        # Build config content; only preload spock if available and requested
        data_dir = self.data_dir(node_num)
        port = self.port(node_num)
        auto_conf = f"{data_dir}/postgresql.auto.conf"
        msg = self.step_msg("Configuring", node_num)
        lines = [f"port = {port}"]
        if self.has_spock() and include_spock:
            lines += [
                "shared_preload_libraries = 'spock'",
                "spock.enable_ddl_replication = 'on'",
                "spock.include_ddl_repset = 'on'",
                "spock.allow_ddl_from_functions = 'on'",
                f"spock.node = 'node{node_num}'",
                "spock.exception_behaviour = 'sub_disable'",
            ]
        else:
            # Skip spock GUCs entirely if library not found to avoid start errors
            if verbose and self.has_spock() and not include_spock:
                self.logger.log(self.step_msg("Delaying spock config", node_num) + "[INFO]", verbose)
            elif verbose:
                self.logger.log(self.step_msg("No spock lib; skipping spock GUCs", node_num) + "[SKIPPED]", verbose)
        lines += [
            "wal_level = logical",
            "max_wal_senders = 20",
            "max_replication_slots = 20",
            "max_worker_processes = 20",
            "track_commit_timestamp = on",
            "wal_sender_timeout = 4s",
            "hot_standby_feedback = on",
            "DateStyle = 'ISO, DMY'",
            "log_line_prefix = '[%m] [%p] [%d] '",
            "fsync = off",
            "client_min_messages = log",
            "log_destination = 'stderr'",
            "logging_collector = on",
            "log_directory = 'log'",
            "log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'",
            "log_truncate_on_rotation = on",
            "log_rotation_age = 1d",
            "log_rotation_size = 0",
        ]
        if replica_mode and self.has_spock():
            lines += [
                f"synchronous_standby_names = 'FIRST 1 (n{node_num}r)'",
                "synchronous_commit = on",
            ]
        content = "\n".join(lines) + "\n"
        try:
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            Path(data_dir, "log").mkdir(parents=True, exist_ok=True)
            with open(auto_conf, "w") as f:
                f.write(content)
            self.logger.log(msg + "[OK]", verbose)
        except Exception:
            self.logger.log(msg + "[FAILED]", verbose)

    def check_spock_extension(self, verbose: bool = False):
        """Check if the spock extension is installed and available."""
        msg = "Checking for spock extension"
        spock_control_path = Path(self.cfg.share_dir) / "extension" / "spock.control"
        if not spock_control_path.exists():
            self.logger.log(msg + " [FAILED]", verbose)
            self.logger.log(f"Spock extension not found at {spock_control_path}. Please install the spock extension.", verbose)
            return False
        self.logger.log(msg + " [OK]", verbose)
        return True

    # ----- spock helpers for cross-wiring -----
    def ensure_extensions(self, node_num: int, verbose: bool = False):
        if not self.check_spock_extension(verbose):
            return
        port = self.port(node_num)
        msg = self.step_msg("Ensuring extensions", node_num)
        sql = "create extension if not exists dblink; create extension if not exists spock;"
        ok = self.run([f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-c", sql], verbose=verbose)
        if ok:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def ensure_spock_node(self, node_num: int, verbose: bool = False):
        name = f"n{node_num}"
        dsn = self.node_dsn(node_num)
        port = self.port(node_num)
        msg = self.step_msg("Registering spock node", node_num)
        try:
            out = subprocess.check_output(
                [f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-Atc",
                 f"select 1 from spock.node where node_name = '{name}'"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out == "1":
                self.logger.log(msg + "[SKIPPED]", verbose)
                return
        except subprocess.CalledProcessError:
            pass
        sql = (
            "select spock.node_create("
            f"node_name := '{name}', "
            f"dsn := '{dsn}', "
            "location := 'local', country := 'USA');"
        )
        ok = self.run([f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{port}", "-c", sql], verbose=verbose)
        if ok:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def ensure_subscription(self, sub_node: int, provider_node: int, verbose: bool = False):
        sub_name = f"sub_n{provider_node}_n{sub_node}"
        sub_port = self.port(sub_node)
        provider_dsn = self.node_dsn(provider_node)
        msg = self.step_msg(f"Subscription {sub_name}", sub_node)
        try:
            out = subprocess.check_output(
                [f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{sub_port}", "-Atc",
                 f"select 1 from spock.subscription where sub_name = '{sub_name}'"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out == "1":
                self.logger.log(msg + "[SKIPPED]", verbose)
                return
        except subprocess.CalledProcessError:
            pass
        sql = (
            "select spock.sub_create("
            f"subscription_name := '{sub_name}', "
            f"provider_dsn := '{provider_dsn}', "
            "replication_sets := ARRAY['default','default_insert_only','ddl_sql'], "
            "synchronize_structure := true, synchronize_data := true, "
            "forward_origins := ARRAY[]::text[], apply_delay := '0', enabled := true);"
        )
        ok = self.run([f"{self.cfg.bin_dir}/psql", "pgedge", f"-p{sub_port}", "-c", sql], verbose=verbose)
        if ok:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def cross_wire(self, num_nodes: int, verbose: bool = False):
        # Make sure nodes are running and prepared
        for i in self.nodes(num_nodes):
            self.start_node(i, verbose)
            self.create_user(i, "pgedge", verbose)
            self.create_db(i, "pgedge", owner="pgedge", verbose=verbose)
            self.ensure_extensions(i, verbose)
            self.ensure_spock_node(i, verbose)
        # Create subscriptions for all pairs i != j
        for i in self.nodes(num_nodes):
            for j in self.nodes(num_nodes):
                if i == j:
                    continue
                self.ensure_subscription(i, j, verbose)
        self.logger.log(f"{'Cross-wiring completed'.ljust(self.cfg.step_width)}[OK]", verbose)

    def all_nodes(self, num_nodes: int, verbose: bool = False):
        for i in self.nodes(num_nodes):
            self.stop_node(i, verbose)
        for i in self.nodes(num_nodes):
            self.destroy_node(i, verbose)
        for i in self.nodes(num_nodes):
            self.init_node(i, verbose)
            self.write_auto_conf(i, verbose, include_spock=False)
        for i in self.nodes(num_nodes):
            self.start_node(i, verbose)
        for i in self.nodes(num_nodes):
            self.cleanup_node(i, verbose)
        # Add spock configuration and restart
        if self.has_spock():
            for i in self.nodes(num_nodes):
                self.stop_node(i, verbose)
                self.write_auto_conf(i, verbose, include_spock=True)
                self.start_node(i, verbose)
        self.logger.log(f"{'All actions completed'.ljust(self.cfg.step_width)}[OK]", verbose)

    def replica_port(self, node_num: int, total_primaries: int) -> int:
        """Port assignment for a replica of primary node_num lives after all primaries.
        Example: primaries ports 5431..543N then replica of node i gets start_port + total_primaries + (i-1)."""
        return 6430 + node_num

    def modify_pg_hba_for_replication(self, node_num: int, verbose: bool = False):
        data_dir = self.data_dir(node_num)
        hba = Path(data_dir) / "pg_hba.conf"
        if not hba.exists():
            return
        lines = [
            "# Added by spock_cluster for replication",\
            "host    replication     pgedge          127.0.0.1/32    trust",\
            "host    replication     pgedge          ::1/128         trust"
        ]
        with open(hba, "a") as f:
            f.write("\n" + "\n".join(lines) + "\n")
        if verbose:
            self.logger.log(self.step_msg("pg_hba replication", node_num) + "[OK]", verbose)

    def ensure_replication_role(self, node_num: int, verbose: bool = False):
        port = self.port(node_num)
        sql = "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='pgedge') THEN CREATE ROLE pgedge LOGIN REPLICATION PASSWORD 'pgedge'; ELSE ALTER ROLE pgedge WITH REPLICATION; END IF; END $$;"
        self.run([f"{self.cfg.bin_dir}/psql", "-d", "postgres", f"-p{port}", "-c", sql], verbose=verbose)

    def create_sync_replica(self, primary_node: int, total_primaries: int, verbose: bool = False):
        primary_port = self.port(primary_node)
        replica_port = self.replica_port(primary_node, total_primaries)
        primary_data = Path(self.data_dir(primary_node))
        replica_num = f"{primary_node}r"  # virtual name for path
        replica_data = Path(f"{self.cfg.data_base}/data{replica_num}")
        slot_name = f"n{primary_node}r_slot"
        msg = self.step_msg(f"Replica for n{primary_node}", primary_node)
        if replica_data.exists() and any(replica_data.iterdir()):
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        replica_data.mkdir(parents=True, exist_ok=True)
        self.ensure_correct_permissions(replica_data, verbose)
        # -C creates replication slot, -S specifies slot name, -R writes recovery config
        cmd = [f"{self.cfg.bin_dir}/pg_basebackup", "-D", str(replica_data), "-p", str(primary_port), 
               "-h", "127.0.0.1", "-U", "pgedge", "-R", "-C", "-S", slot_name, "-Fp", "-Xs"]
        env = os.environ.copy()
        env['PGPASSWORD'] = 'pgedge'
        ok = self.run(cmd, verbose=verbose, env=env)
        if not ok:
            self.logger.log(msg + "[FAILED]", verbose)
            return
        # Rewrite postgresql.auto.conf for replica (don't append, as pg_basebackup copied primary's config)
        recovery_conf = replica_data / "postgresql.auto.conf"
        replica_config_lines = [
            f"primary_conninfo = 'host=127.0.0.1 port={primary_port} user=pgedge password=pgedge application_name=n{primary_node}r'",
            f"primary_slot_name = '{slot_name}'",
            f"port = {replica_port}",
            "hot_standby = on",
            "hot_standby_feedback = on",
            "wal_level = logical",
            "max_wal_senders = 20",
            "max_replication_slots = 20",
            "max_worker_processes = 20",
            "track_commit_timestamp = on",
            "log_line_prefix = '[%m] [%p] [%d] '",
            "fsync = off",
            "log_destination = 'stderr'",
            "logging_collector = on",
            "log_directory = 'log'",
            "log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'",
        ]
        # DO NOT include spock shared_preload_libraries for physical replicas
        with open(recovery_conf, "w") as f:
            f.write("\n".join(replica_config_lines) + "\n")
        self.logger.log(msg + "[OK]", verbose)

    def start_replica(self, primary_node: int, total_primaries: int, verbose: bool = False):
        replica_port = self.replica_port(primary_node, total_primaries)
        replica_data = Path(f"{self.cfg.data_base}/data{primary_node}r")
        msg = self.step_msg(f"Start replica n{primary_node}r", primary_node)
        if not replica_data.is_dir():
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        # Skip if already running
        status = self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", str(replica_data), "status"], verbose=verbose)
        if status:
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        if self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", str(replica_data), "-o", f"-p {replica_port}", "-l", f"{replica_data}/server.log", "start"], verbose=verbose):
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def replica_dirs(self) -> list:
        base = Path(self.cfg.data_base)
        reps = []
        for p in base.glob('data*r'):
            # match pattern data<digit+>r
            name = p.name
            if name.startswith('data') and name[4:-1].isdigit() and name.endswith('r'):
                reps.append(p)
        return reps

    def stop_replica(self, primary_node: int, total_primaries: int, verbose: bool = False):
        replica_data = Path(f"{self.cfg.data_base}/data{primary_node}r")
        msg = self.step_msg(f"Stopping n{primary_node}r", primary_node)
        if not replica_data.is_dir():
            self.logger.log(msg + "[SKIPPED]", verbose)
            return
        res = self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", str(replica_data), "stop", "-m", "fast"], verbose=verbose)
        if not res:
            res = self.run([f"{self.cfg.bin_dir}/pg_ctl", "-D", str(replica_data), "stop", "-m", "immediate"], verbose=verbose)
        # Fallback kill -9
        if not res:
            pid_file = replica_data / 'postmaster.pid'
            if pid_file.exists():
                try:
                    with open(pid_file) as f: pid=int(f.readline().strip())
                    res = self.run(["kill", "-9", str(pid)], verbose=verbose)
                except Exception:
                    pass
        if res:
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

    def destroy_replica(self, primary_node: int, verbose: bool = False):
        replica_data = Path(f"{self.cfg.data_base}/data{primary_node}r")
        msg = self.step_msg(f"Destroy replica n{primary_node}r", primary_node)
        if replica_data.is_dir():
            ok = self.run(["rm", "-rf", str(replica_data)], verbose=verbose)
            if ok:
                self.logger.log(msg + "[OK]", verbose)
            else:
                self.logger.log(msg + "[FAILED]", verbose)
        else:
            self.logger.log(msg + "[SKIPPED]", verbose)

    def ensure_correct_permissions(self, path: str, verbose: bool = False):
        """Ensure the directory has the correct permissions (0700 or 0750)."""
        msg = f"Ensuring permissions for {path}"
        try:
            Path(path).chmod(0o700)
            self.logger.log(msg + " [OK]", verbose)
        except Exception as e:
            self.logger.log(msg + f" [FAILED]: {e}", verbose)

def resolve_pg_bin() -> dict:
    """Find pg_config on PATH, derive bin dir, export PG_BIN, and return it.
    Exit with a clear message if not found.
    """
    pg_config = shutil.which("pg_config")
    if not pg_config:
        print(
            "pg_config not found in PATH. Ensure PostgreSQL is installed and pg_config is in PATH.\n"
            "On macOS (Homebrew): brew install postgresql@17 and add its bin to PATH."
        )
        raise SystemExit(1)
    try:
        bin_dir = subprocess.check_output([pg_config, "--bindir"], text=True).strip()
        lib_dir = subprocess.check_output([pg_config, "--libdir"], text=True).strip()
        share_dir = subprocess.check_output([pg_config, "--sharedir"], text=True).strip()
    except subprocess.CalledProcessError:
        bin_dir = str(Path(pg_config).parent)
        lib_dir = ""
        share_dir = ""
    # Export and prepend to PATH
    os.environ["PG_BIN"] = bin_dir
    os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
    return {"bin_dir": bin_dir, "lib_dir": lib_dir, "share_dir": share_dir}


def build_cluster() -> SpockCluster:
    cfg = ClusterConfig()
    # Resolve binaries based on pg_config in PATH and set PG_BIN
    pg_paths = resolve_pg_bin()
    cfg.bin_dir = pg_paths.get("bin_dir", "")
    cfg.lib_dir = pg_paths.get("lib_dir", "")
    cfg.share_dir = pg_paths.get("share_dir", "")
    # Normalize data_base to absolute CWD path
    cfg.data_base = str(Path(os.getcwd()).resolve())
    logger = Logger(cfg.log_file)
    return SpockCluster(cfg, logger)


def main():
    # Build CLI first so --help doesn't trigger environment checks
    parser = argparse.ArgumentParser(
        description="Spock PostgreSQL cluster manager (Python version)",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Subcommands support
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-n", "--num-nodes", type=int, default=ClusterConfig().default_num_nodes,
                        help="Number of nodes (default: 3)")
    common.add_argument("-v", "--verbose", action="store_true", help="Show output to console as well as log file")
    common.add_argument("-r", "--replica", type=int, choices=[0,1], default=0,
                        help="Enable creation of one synchronous replica per primary (0=off,1=on; default 0)")
    common.add_argument("--start-port", type=int, help="Override base start port (default 5431 or $START_PORT)")

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="COMMAND",
        description="These are COMMANDs",
    )
    subparsers.add_parser("init", parents=[common], help="Initialize all nodes",
                          description="Initialize data directories and write postgresql.auto.conf for all nodes.")
    subparsers.add_parser("stop", parents=[common], help="Stop nodes",
                          description="Stop all nodes (fast mode).")
    subparsers.add_parser("destroy", parents=[common], help="Destroy nodes",
                          description="Stop then remove data directories for all nodes.")
    subparsers.add_parser("cleanup", parents=[common], help="Cleanup databases/extensions on nodes",
                          description="Recreate pgedge DB and reset spock/dblink/replication slots/origins on all nodes.")
    subparsers.add_parser("update-conf", parents=[common], help="Update postgresql.auto.conf for nodes",
                          description="Rewrite postgresql.auto.conf for all nodes with spock-related settings.")
    # New command to idempotently ensure pgedge user and DB exist
    subparsers.add_parser("ensure", parents=[common], help="Ensure pgedge role and DB exist",
                          description="Create pgedge role and DB if missing on all nodes.")
    # New command: cross-wire nodes with spock (extensions, nodes, subscriptions)
    subparsers.add_parser("cross-wire", parents=[common], help="Create spock extension and cross-wire nodes",
                          description="Ensure extensions, register spock nodes, and create cross subscriptions among all nodes.")
    subparsers.add_parser("all", parents=[common], help="Full cycle: stop, cleanup, destroy, init, conf",
                          description="Run: stop -> destroy -> init -> update-conf -> start -> cleanup on all nodes.")

    args = parser.parse_args()
    replica_enabled = bool(getattr(args, 'replica', 0))

    # Determine selected operation from subcommand only
    command = args.command
    if command is None:
        parser.print_help()
        return

    # Now that we know we're doing real work, construct the cluster
    cluster = build_cluster()
    # Override start port from CLI if provided
    if getattr(args, 'start_port', None):
        cluster.cfg.start_port = args.start_port

    # Timestamp header in log
    cluster.logger.header()

    # Execute
    if command == "init":
        # Phase 1: Initialize without spock shared_preload and without sync replication
        for i in cluster.nodes(args.num_nodes):
            cluster.init_node(i, args.verbose)
            cluster.write_auto_conf(i, args.verbose, replica_mode=False, include_spock=False)
            cluster.start_node(i, args.verbose)
            cluster.create_user(i, "pgedge", args.verbose)
            cluster.create_db(i, "pgedge", owner="pgedge", verbose=args.verbose)
            if replica_enabled:
                cluster.ensure_replication_role(i, args.verbose)
                cluster.modify_pg_hba_for_replication(i, args.verbose)
        
        # Phase 2: Add spock to shared_preload_libraries and restart (needed before CREATE EXTENSION spock)
        if cluster.has_spock():
            for i in cluster.nodes(args.num_nodes):
                cluster.stop_node(i, args.verbose)
                cluster.write_auto_conf(i, args.verbose, replica_mode=False, include_spock=True)
                cluster.start_node(i, args.verbose)
                # NOW create extensions after spock is in shared_preload_libraries
                cluster.ensure_extensions(i, args.verbose)
        
        if replica_enabled:
            # Reload primaries after hba changes
            for i in cluster.nodes(args.num_nodes):
                cluster.run([f"{cluster.cfg.bin_dir}/pg_ctl", "-D", cluster.data_dir(i), "reload"], verbose=args.verbose)
            # Create replicas (they will copy the database with extensions)
            for i in cluster.nodes(args.num_nodes):
                cluster.create_sync_replica(i, args.num_nodes, args.verbose)
            # Start replicas
            for i in cluster.nodes(args.num_nodes):
                cluster.start_replica(i, args.num_nodes, args.verbose)
            # Phase 3: Add synchronous replication config now that replicas exist
            for i in cluster.nodes(args.num_nodes):
                cluster.stop_node(i, args.verbose)
                cluster.write_auto_conf(i, args.verbose, replica_mode=True, include_spock=cluster.has_spock())
                cluster.start_node(i, args.verbose)
    elif command == "stop":
        for i in cluster.nodes(args.num_nodes):
            cluster.stop_node(i, args.verbose)
    elif command == "destroy":
        # Stop postgres first, then destroy data directories including replicas
        for i in cluster.nodes(args.num_nodes):
            cluster.stop_node(i, args.verbose)
        # Stop replicas if present
        for i in cluster.nodes(args.num_nodes):
            cluster.stop_replica(i, args.num_nodes, args.verbose)
        for i in cluster.nodes(args.num_nodes):
            cluster.destroy_replica(i, args.verbose)
        for i in cluster.nodes(args.num_nodes):
            cluster.destroy_node(i, args.verbose)
    elif command == "cleanup":
        for i in cluster.nodes(args.num_nodes):
            cluster.cleanup_node(i, args.verbose)
    elif command == "update-conf":
        for i in cluster.nodes(args.num_nodes):
            cluster.write_auto_conf(i, args.verbose)
    elif command == "ensure":
        for i in cluster.nodes(args.num_nodes):
            cluster.create_user(i, "pgedge", args.verbose)
            cluster.create_db(i, "pgedge", owner="pgedge", verbose=args.verbose)
    elif command == "cross-wire":
        cluster.cross_wire(args.num_nodes, args.verbose)
    elif command == "all":
        cluster.all_nodes(args.num_nodes, args.verbose)
        if replica_enabled:
            for i in cluster.nodes(args.num_nodes):
                cluster.ensure_replication_role(i, args.verbose)
                cluster.modify_pg_hba_for_replication(i, args.verbose)
            for i in cluster.nodes(args.num_nodes):
                cluster.create_sync_replica(i, args.num_nodes, args.verbose)
            for i in cluster.nodes(args.num_nodes):
                cluster.start_replica(i, args.num_nodes, args.verbose)


if __name__ == "__main__":
    main()

