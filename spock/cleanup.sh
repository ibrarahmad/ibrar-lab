export DYLD_LIBRARY_PATH=/usr/local/pgsql.16/lib:$DYLD_LIBRARY_PATH

dropdb pgedge -p5431
createdb pgedge -p5431
dropdb pgedge -p5432
createdb pgedge -p5432
dropdb pgedge -p5433
createdb pgedge -p5433

psql pgedge -p5431 -c "create extension spock";
psql pgedge -p5432 -c "create extension spock";
psql pgedge -p5433 -c "create extension spock";

psql pgedge -p5431 -c "create extension dblink";
psql pgedge -p5432 -c "create extension dblink";
psql pgedge -p5433 -c "create extension dblink";

psql pgedge -p5431 -t -A -c \
"SELECT 'SELECT pg_drop_replication_slot(' || quote_literal(slot_name) || ');' FROM pg_replication_slots WHERE slot_type = 'logical';" \
| psql pgedge -p5431


psql pgedge -p5432 -t -A -c \
"SELECT 'SELECT pg_drop_replication_slot(' || quote_literal(slot_name) || ');' FROM pg_replication_slots WHERE slot_type = 'logical';" \
| psql pgedge -p5432

psql pgedge -p5433 -t -A -c \
"SELECT 'SELECT pg_drop_replication_slot(' || quote_literal(slot_name) || ');' FROM pg_replication_slots WHERE slot_type = 'logical';" \
| psql pgedge -p5433


psql -d pgedge -p5431 -Atc \
"SELECT 'SELECT pg_replication_origin_drop(' || quote_literal(roname) || ');' FROM pg_replication_origin;" \
| psql -d pgedge -p5431


psql -d pgedge -p5432 -Atc \
"SELECT 'SELECT pg_replication_origin_drop(' || quote_literal(roname) || ');' FROM pg_replication_origin;" \
| psql -d pgedge -p5432


psql -d pgedge -p5433 -Atc \
"SELECT 'SELECT pg_replication_origin_drop(' || quote_literal(roname) || ');' FROM pg_replication_origin;" \
| psql -d pgedge -p5433

psql pgedge -p5433 -c "drop extension spock; create extension spock";
psql pgedge -p5432 -c "drop extension spock; create extension spock";
psql pgedge -p5431 -c "drop extension spock; create extension spock"
