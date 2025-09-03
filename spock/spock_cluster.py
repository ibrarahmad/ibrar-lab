#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import List

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
    start_port: int = int(os.environ.get("START_PORT", 5431))
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
        return self.cfg.start_port + node_num - 1

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
                self.logger.log(msg + "[SKIPPED]", verbose)
                return
        except subprocess.CalledProcessError:
            pass
        cmd = [f"{self.cfg.bin_dir}/createdb", dbname, f"-p{port}"]
        if owner:
            cmd.extend(["-O", owner])
        if self.run(cmd, verbose=verbose):
            self.logger.log(msg + "[OK]", verbose)
        else:
            self.logger.log(msg + "[FAILED]", verbose)

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

    def write_auto_conf(self, node_num: int, verbose: bool = False):
        data_dir = self.data_dir(node_num)
        port = self.port(node_num)
        auto_conf = f"{data_dir}/postgresql.auto.conf"
        msg = self.step_msg("Configuring", node_num)
        # Build config content; only preload spock if available
        lines = [
            "spock.enable_ddl_replication = 'on'",
            "spock.include_ddl_repset = 'on'",
            "spock.allow_ddl_from_functions = 'on'",
            f"spock.node = 'node{node_num}'",
            f"port = {port}",
        ]
        if self.has_spock():
            lines.append("shared_preload_libraries = 'spock'")
        lines += [
            "wal_level = logical",
            "max_wal_senders = 20",
            "max_replication_slots = 20",
            "max_worker_processes = 20",
            "track_commit_timestamp = on",
            "wal_sender_timeout = 4s",
            "DateStyle = 'ISO, DMY'",
            "log_line_prefix = '[%m] [%p] [%d] '",
            "fsync = off",
            "spock.exception_behaviour = 'sub_disable'",
            "client_min_messages = log",
            # --- Enable PostgreSQL server logging to dataN/log ---
            "log_destination = 'stderr'",
            "logging_collector = on",
            "log_directory = 'log'",
            "log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'",
            "log_truncate_on_rotation = on",
            "log_rotation_age = 1d",
            "log_rotation_size = 0",
        ]
        content = "\n".join(lines) + "\n"
        try:
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            # Ensure the log directory exists for logging_collector
            Path(data_dir, "log").mkdir(parents=True, exist_ok=True)
            with open(auto_conf, "w") as f:
                f.write(content)
            self.logger.log(msg + "[OK]", verbose)
        except Exception:
            self.logger.log(msg + "[FAILED]", verbose)

    # ----- spock helpers for cross-wiring -----
    def ensure_extensions(self, node_num: int, verbose: bool = False):
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
            self.write_auto_conf(i, verbose)
        for i in self.nodes(num_nodes):
            self.start_node(i, verbose)
        for i in self.nodes(num_nodes):
            self.cleanup_node(i, verbose)
        self.logger.log(f"{'All actions completed'.ljust(self.cfg.step_width)}[OK]", verbose)


# ----- binary check -----

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

    # Determine selected operation from subcommand only
    command = args.command
    if command is None:
        parser.print_help()
        return

    # Now that we know we're doing real work, construct the cluster
    cluster = build_cluster()

    # Timestamp header in log
    cluster.logger.header()

    # Execute
    if command == "init":
        for i in cluster.nodes(args.num_nodes):
            cluster.init_node(i, args.verbose)
            cluster.write_auto_conf(i, args.verbose)
            cluster.start_node(i, args.verbose)
            cluster.create_user(i, "pgedge", args.verbose)
            cluster.create_db(i, "pgedge", owner="pgedge", verbose=args.verbose)
    elif command == "stop":
        for i in cluster.nodes(args.num_nodes):
            cluster.stop_node(i, args.verbose)
    elif command == "destroy":
        # Stop postgres first, then destroy data directories
        for i in cluster.nodes(args.num_nodes):
            cluster.stop_node(i, args.verbose)
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


if __name__ == "__main__":
    main()

