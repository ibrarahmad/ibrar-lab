#!/bin/bash

# filepath: /Users/pgedge/pg_scripts/spock/spock_cluster.sh

# Set the library path
export DYLD_LIBRARY_PATH=/usr/local/pgsql.16/lib:$DYLD_LIBRARY_PATH

# Default values
NUM_NODES=3
ACTION=""
DATA=~/pg_data  # Main directory for data
LOG=~/pg_logs   # Main directory for logs

# Create main directories if they don't exist
mkdir -p $DATA
mkdir -p $LOG

# Usage function
usage() {
    echo "Usage: $0 [-n <number_of_nodes>] [-c | -i]"
    echo "  -n <number_of_nodes>  Specify the number of nodes (default: 3)"
    echo "  -c                    Cleanup nodes"
    echo "  -i                    Initialize nodes"
    exit 1
}

# Parse options
while getopts "n:ci" opt; do
    case $opt in
        n) NUM_NODES=$OPTARG ;;
        c) ACTION="cleanup" ;;
        i) ACTION="initialize" ;;
        *) usage ;;
    esac
done

# Validate action
if [[ -z $ACTION ]]; then
    usage
fi

# Generate postgresql.auto.conf for a node
generate_auto_conf() {
    local node=$1
    local port=$((5430 + node))
    local data_dir=$DATA/data$node
    cat > $data_dir/postgresql.auto.conf <<EOF
spock.enable_ddl_replication = 'on'
spock.include_ddl_repset = 'on'
spock.allow_ddl_from_functions = 'on'
snowflake.node = '$node'
port = $port
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
EOF
}

# Cleanup function
cleanup_node() {
    local node=$1
    local port=$((5430 + node))
    echo -n "Cleaning up node $node on port $port... "
    if dropdb pgedge -p$port && createdb pgedge -p$port && \
       psql pgedge -p$port -c "create extension spock" && \
       psql pgedge -p$port -c "create extension dblink" && \
       psql pgedge -p$port -t -A -c \
       "SELECT 'SELECT pg_drop_replication_slot(' || quote_literal(slot_name) || ');' FROM pg_replication_slots WHERE slot_type = 'logical';" | \
       psql pgedge -p$port && \
       psql -d pgedge -p$port -Atc \
       "SELECT 'SELECT pg_replication_origin_drop(' || quote_literal(roname) || ');' FROM pg_replication_origin;" | \
       psql -d pgedge -p$port && \
       psql pgedge -p$port -c "drop extension spock; create extension spock"; then
        printf "%-10s\n" "OK"
    else
        printf "%-10s\n" "FAILED"
    fi
}

# Initialization function
initialize_node() {
    local node=$1
    local port=$((5430 + node))
    local data_dir=$DATA/data$node
    local log_file=$LOG/log$node
    echo -n "Initializing node $node on port $port... "
    if /usr/local/pgsql.16/bin/pg_ctl -D $data_dir stop && \
       rm -rf $data_dir && \
       /usr/local/pgsql.16/bin/initdb $data_dir && \
       generate_auto_conf $node && \
       /usr/local/pgsql.16/bin/pg_ctl -D $data_dir start -l $log_file; then
        printf "%-10s\n" "OK"
    else
        printf "%-10s\n" "FAILED"
    fi
}

# Perform the action for all nodes
for ((node=1; node<=NUM_NODES; node++)); do
    if [[ $ACTION == "cleanup" ]]; then
        cleanup_node $node
    elif [[ $ACTION == "initialize" ]]; then
        initialize_node $node
    fi
done

echo "$ACTION completed for $NUM_NODES nodes."