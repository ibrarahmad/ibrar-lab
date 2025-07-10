-- Helper Function: get_nodes_from_dsn
CREATE OR REPLACE FUNCTION get_nodes(target_dsn text)
RETURNS TABLE (node_id oid, node_name text)
AS
$$
BEGIN
    RETURN QUERY
    SELECT *
    FROM dblink(target_dsn, 'SELECT node_id, node_name FROM spock.node', true)
         AS results(node_id oid, node_name text);
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE PROCEDURE join_node_group(
    join_target_dsn text,
    node_group_name text,
    pjoin_phase int DEFAULT 1
)
LANGUAGE plpgsql
AS
$$
DECLARE
    join_record record;
    member_record record;
    joinid oid;
    joinname text;
    joindsn text;
    memberid oid;
    membername text;
    joinsubname name;
    membersubname name;
BEGIN
    RAISE LOG '/CDR/ Starting join_node_group with DSN: %, node_group_name: %', join_target_dsn, node_group_name;

    -- Phase 1: Create or fetch the local node
    join_record := create_or_fetch_local_node('n3');
    joinid := join_record.joinid;
    joinname := join_record.joinname;
    joindsn := join_record.joindsn;

    RAISE LOG E'/CDR/ Local node details: id: %, name: %, dsn: %\n', joinid, joinname, joindsn;

    -- Phase 2: Fetch member node details
    member_record := fetch_member_node_details(join_target_dsn);

    -- Check if member_record is NULL
    IF member_record IS NULL THEN
        RAISE EXCEPTION '/CDR/ No member node found for DSN: %', join_target_dsn;
    END IF;

    memberid := member_record.memberid;
    membername := member_record.membername;

    joinsubname := joinname || '_' || membername;
    membersubname := membername || '_' || joinname;

    RAISE LOG '/CDR/ join sub name: %, member sub name: %', COALESCE(joinsubname, '<NULL>'), COALESCE(membersubname, '<NULL>');

    -- Phase 3: Setup subscriptions for existing nodes
    RAISE LOG E'/CDR/ Phase 2: Setting up subscriptions for existing nodes\n';
    PERFORM setup_subscriptions(join_target_dsn, joinid, joindsn, joinname);

    -- Phase 4: Setup disabled subscriptions for the new node
    RAISE LOG E'/CDR/ Phase 3: Setting up disbale subscriptions for nodes other than the source node\n';
    PERFORM setup_disabled_subscriptions(join_target_dsn, joinid, memberid, joinname);

    RAISE LOG '/CDR/ Completed join_node_group successfully.';
END;
$$;


-- Helper Function: check_commit_timestamp_for_n3_lag
CREATE OR REPLACE FUNCTION check_commit_timestamp_for_n3_lag()
RETURNS timestamp
AS
$$
DECLARE
    commit_ts timestamp;
BEGIN
    SELECT commit_timestamp INTO commit_ts
    FROM spock.lag_tracker
    WHERE origin_name = 'n2' AND receiver_name = 'n3';

    IF commit_ts IS NULL THEN
        RAISE LOG '/CDR/ No commit timestamp found for n2 → n3 lag.';
        RETURN NULL;
    ELSE
        RAISE LOG '/CDR/ Commit timestamp for n2 → n3 lag: %', commit_ts;
        RETURN commit_ts;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION create_or_fetch_local_node(
    node_name text
)
RETURNS TABLE (joinid oid, joinname text, joindsn text)
AS
$$
BEGIN
    SELECT node_id INTO joinid FROM spock.local_node;

    IF joinid IS NULL THEN
        RAISE LOG '/CDR/ Local node not found. Creating node: %', node_name;
        SELECT spock.node_create(
            node_name := node_name,
            dsn := 'host=127.0.0.1 dbname=pgedge port=5433 user=pgedge password=pgedge',
            location := 'Los Angeles',
            country := 'USA',
            info := '{"key": "value"}'::jsonb
        ) INTO joinid;
    END IF;

    SELECT n.node_name INTO joinname FROM spock.node AS n WHERE n.node_id = joinid;
    SELECT ni.if_dsn INTO joindsn FROM spock.node_interface AS ni WHERE ni.if_nodeid = joinid;

    IF joinname IS NULL OR joindsn IS NULL THEN
        RAISE EXCEPTION '/CDR/ Failed to fetch local node details for node_id: %', joinid;
    END IF;

    RETURN QUERY SELECT joinid, joinname, joindsn;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: fetch_member_node_details
CREATE OR REPLACE FUNCTION fetch_member_node_details(
    join_target_dsn text
)
RETURNS TABLE (memberid oid, membername text)
AS
$$
DECLARE
    remotesql text; -- Declare the variable
BEGIN
    remotesql := 'SELECT node_id, node_name::text FROM spock.node WHERE node_id = (SELECT if_nodeid FROM spock.node_interface WHERE if_dsn ~ $x$host=127.0.0.1$x$ AND if_dsn ~ $x$port=5431$x$)';
    RAISE LOG '/CDR/ Executing dblink query: %', remotesql;

    RETURN QUERY SELECT * FROM dblink(join_target_dsn, remotesql, true) AS results(id oid, nm text);

    -- Log if no rows are returned
    IF NOT FOUND THEN
        RAISE LOG '/CDR/ No rows returned from dblink query: %', remotesql;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: create_subscription_for_node
CREATE OR REPLACE FUNCTION create_subscription_for_node(
    subscription_name text
)
RETURNS void
AS
$$
DECLARE
    sid oid;
    dsn text;
    subname text := subscription_name; -- Declare and initialize subname
BEGIN
    -- Create the subscription directly on n3 from n1
    dsn := 'host=127.0.0.1 dbname=pgedge port=5431 user=pgedge password=pgedge';
    
    SELECT spock.sub_create(
                subscription_name := subname,
                provider_dsn := dsn,
                replication_sets := '{default,default_insert_only,ddl_sql}',
                synchronize_structure := true,
                synchronize_data := true,
                forward_origins := '{}',
                apply_delay := '0'::interval,
                enabled := true
            ) INTO sid;

    EXECUTE format('SELECT * FROM spock.subscription WHERE sub_id = %L', sid); -- Correct EXECUTE statement

    RAISE LOG '/CDR/ Created subscription %/% on n3 from n1', subscription_name, sid;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: get_provider_dsn_for_node
CREATE OR REPLACE FUNCTION get_provider_dsn_for_node(
    node_name text
)
RETURNS text
AS
$$
DECLARE
    provider_dsn text;
BEGIN
    -- Fetch the DSN of the specified node
    SELECT ni.if_dsn INTO provider_dsn
    FROM spock.node_interface AS ni
    JOIN spock.node AS n ON ni.if_nodeid = n.node_id
    WHERE n.node_name = node_name;

    IF provider_dsn IS NULL THEN
        RAISE EXCEPTION '/CDR/ Failed to fetch provider DSN for the node: %', node_name;
    END IF;

    RETURN provider_dsn;
END;
$$ LANGUAGE plpgsql;


-- Helper Function: setup_subscriptions
CREATE OR REPLACE FUNCTION setup_subscriptions(
    join_target_dsn text,
    joinid oid,
    joindsn text,
    joinname text
)
RETURNS void
AS
$$
DECLARE
    id oid;
    name text;
    dsn text;
    subname name;
    remotesql text;
    sid oid;
BEGIN

    RAISE LOG E'/CDR/ Starting setup_subscriptions with join_target_dsn: %, joinid: %, joindsn: %, joinname: %\n', join_target_dsn, joinid, joindsn, joinname;

    FOR id IN SELECT * FROM dblink(join_target_dsn, $x$SELECT node_id FROM spock.node$x$, true) AS results(id oid) LOOP
        IF id = joinid THEN
            RAISE LOG '/CDR/ Skipping node % as it matches the joinid.', id;
            CONTINUE;
        END IF;

        BEGIN
            remotesql := 'SELECT node_name FROM spock.node WHERE node_id = ' || id;
            RAISE LOG '/CDR/ Executing query to fetch node_name: %', remotesql;
            SELECT * FROM dblink(join_target_dsn, remotesql, true) AS results(name text) INTO name;

            remotesql := 'SELECT if_dsn FROM spock.node_interface WHERE if_nodeid = ' || id;
            RAISE LOG '/CDR/ Executing query to fetch dsn: %', remotesql;
            SELECT * FROM dblink(join_target_dsn, remotesql, true) AS results(dsn text) INTO dsn;

            -- Validate the dsn before proceeding
            IF dsn IS NULL OR dsn = '' THEN
                RAISE LOG '/CDR/ Skipping node % due to invalid or empty dsn: %', id, dsn;
                CONTINUE;
            END IF;

            subname := joinname || '_' || name;

            IF subname IS NULL OR joindsn IS NULL THEN
                RAISE LOG '/CDR/ Skipping subscription creation due to invalid subname or provider_dsn.';
                CONTINUE;
            END IF;

            RAISE LOG '/CDR/ Creating subscription with subname: %, provider_dsn: %', subname, joindsn;

            SELECT format(
                'SELECT spock.sub_create(subscription_name := $x$%s$x$, provider_dsn := $x$%s$x$, replication_sets := ''{default,default_insert_only,ddl_sql}'', synchronize_structure := false, synchronize_data := true, forward_origins := ''{}'', apply_delay := ''0''::interval)',
                subname, joindsn
            ) INTO remotesql;

            RAISE LOG E'/CDR/ Executing subscription creation query: %\n', remotesql;

            -- Execute the subscription creation query
            SELECT * FROM dblink(dsn, remotesql, true) AS results(id oid) INTO sid;
            RAISE LOG '/CDR/ Created subscription %/% (from % to %) on target: %', subname, sid, joinname, name, dsn;
        EXCEPTION WHEN OTHERS THEN
            RAISE LOG '/CDR/ Error occurred while processing node %: %', id, SQLERRM;
            CONTINUE;
        END;
    END LOOP;

    RAISE LOG E'/CDR/ Completed setup_subscriptions\n.';
END;
$$ LANGUAGE plpgsql;

-- Helper Function: setup_disabled_subscriptions
CREATE OR REPLACE FUNCTION setup_disabled_subscriptions(
    join_target_dsn text,
    joinid oid,
    memberid oid,
    joinname text
)
RETURNS void
AS
$$
DECLARE
    id oid;
    name text;
    dsn text;
    subname name;
    remotesql text;
    sid oid;
BEGIN
    FOR id IN SELECT * FROM dblink(join_target_dsn, $x$SELECT node_id FROM spock.node$x$, true) AS results(id oid) LOOP
        IF id = joinid OR id = memberid THEN
            CONTINUE;
        END IF;

        BEGIN
            remotesql := 'SELECT node_name FROM spock.node WHERE node_id = ' || id;
            SELECT * FROM dblink(join_target_dsn, remotesql, true) AS results(name text) INTO name;

            remotesql := 'SELECT if_dsn FROM spock.node_interface WHERE if_nodeid = ' || id;
            SELECT * FROM dblink(join_target_dsn, remotesql, true) AS results(dsn text) INTO dsn;

            subname := name || '_' || joinname;

            -- Check if the subscription already exists
            remotesql := format(
                'SELECT EXISTS (SELECT 1 FROM spock.subscription WHERE sub_name = %L)',
                subname
            );
            IF EXISTS (SELECT * FROM dblink(join_target_dsn, remotesql, true) AS results(exists boolean) WHERE exists) THEN
                RAISE LOG '/CDR/ Subscription % already exists. Skipping creation.', subname;
                CONTINUE;
            END IF;

            SELECT spock.sub_create(
                subscription_name := subname,
                provider_dsn := dsn,
                replication_sets := '{default,default_insert_only,ddl_sql}',
                synchronize_structure := false,
                synchronize_data := false,
                forward_origins := '{}',
                apply_delay := '0'::interval,
                enabled := false
            ) INTO sid;

            RAISE LOG '/CDR/ Created disabled subscription %/% (from % to %) provider_dsn %', sid, subname, joinname, name, dsn;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: trigger_sync_event
CREATE OR REPLACE FUNCTION trigger_sync_event(nn text)
RETURNS pg_lsn
AS
$$
DECLARE
    local_dsn text;
    sync_event_result pg_lsn;
BEGIN
    -- Fetch the DSN of the specified node
    SELECT ni.if_dsn INTO local_dsn
    FROM spock.node_interface AS ni
    JOIN spock.node AS n ON ni.if_nodeid = n.node_id
    WHERE n.node_name = nn;

    RAISE NOTICE E'/CDR/ Triggering sync event for node: % with DSN: %\n', nn, local_dsn;

    IF local_dsn IS NULL THEN
        RAISE EXCEPTION '/CDR/ Failed to fetch DSN for the node: %', nn;
    END IF;

    -- Trigger sync event using the node's DSN
    EXECUTE format('SELECT * FROM dblink(%L, ''SELECT spock.sync_event();'') AS result(sync_event pg_lsn);', local_dsn)
    INTO sync_event_result;

    IF sync_event_result IS NULL THEN
        RAISE EXCEPTION '/CDR/ Failed to trigger sync event for node: %', nn;
    END IF;

    RAISE NOTICE E'/CDR/ Sync event triggered successfully for node: % with LSN: %\n', nn, sync_event_result;

    RETURN sync_event_result;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: wait_for_sync_event
CREATE OR REPLACE FUNCTION wait_for_sync_event(
    origin_name text,
    lsn pg_lsn,
    timeout int
)
RETURNS void
AS
$$
DECLARE
    origin_dsn text;
BEGIN
    -- Fetch the DSN of the specified origin node
    SELECT ni.if_dsn INTO origin_dsn
    FROM spock.node_interface AS ni
    JOIN spock.node AS n ON ni.if_nodeid = n.node_id
    WHERE n.node_name = origin_name;

    RAISE NOTICE E'Wait for sync event for origin: %, LSN: %, timeout: %\n', origin_name, lsn, timeout;
    RAISE NOTICE E'/CDR/ Origin DSN: %\n', origin_dsn;
    
    IF origin_dsn IS NULL THEN
        RAISE EXCEPTION '/CDR/ Failed to fetch DSN for the origin node: %', origin_name;
    END IF;

    -- Wait for sync event using the origin node's DSN
    EXECUTE format(
        'SELECT * FROM dblink(%L, ''CALL spock.wait_for_sync_event(true, %L, %s);'')',
        origin_dsn, lsn, timeout
    );
END;
$$ LANGUAGE plpgsql;

-- Helper Function: check_replication_lags
CREATE OR REPLACE FUNCTION check_replication_lags()
RETURNS void
AS
$$
DECLARE
    lag_n1_n3 interval;
    lag_n2_n3 interval;
    start_time timestamp := clock_timestamp();
    elapsed_time interval;
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

        -- Calculate elapsed time
        elapsed_time := clock_timestamp() - start_time;

        -- Exit if timeout is reached
        IF extract(epoch FROM elapsed_time) > 300 THEN
            RAISE NOTICE 'Timeout reached while waiting for replication lags.';
            EXIT;
        END IF;

        PERFORM pg_sleep(1);
    END LOOP;
END;
$$ LANGUAGE plpgsql;-- Helper Function: enable_subscription


CREATE OR REPLACE FUNCTION enable_subscription(
    subscription_name text,
    immediate boolean DEFAULT true
)
RETURNS void
AS
$$
BEGIN
    EXECUTE format('ALTER SUBSCRIPTION %I ENABLE %s;', subscription_name, CASE WHEN immediate THEN 'IMMEDIATE' ELSE '' END);
    RAISE LOG '/CDR/ Enabled subscription % with immediate: %', subscription_name, immediate;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: create_replication_slot
CREATE OR REPLACE FUNCTION create_replication_slot(
    slot_name text,
    plugin text DEFAULT 'spock_output'
)
RETURNS void
AS
$$
BEGIN
    EXECUTE format('SELECT pg_create_logical_replication_slot(%L, %L);', slot_name, plugin);
    RAISE LOG '/CDR/ Created replication slot % with plugin %', slot_name, plugin;
END;
$$ LANGUAGE plpgsql;

-- Helper Function: advance_replication_slot
CREATE OR REPLACE FUNCTION advance_replication_slot(
    slot_name text,
    commit_timestamp text,
    n2_dsn text
)
RETURNS void
AS
$$
DECLARE
    remotesql text;
BEGIN
    remotesql := format(
        'WITH lsn_cte AS (SELECT spock.get_lsn_from_commit_ts(%L, %L::timestamp) AS lsn) SELECT pg_replication_slot_advance(%L, lsn) FROM lsn_cte;',
        slot_name, commit_timestamp, slot_name
    );

    RAISE LOG '/CDR/ Executing advance replication slot query on n2: %', remotesql;

    PERFORM dblink_exec(n2_dsn, remotesql);

    RAISE LOG '/CDR/ Advanced replication slot % to commit timestamp % on n2', slot_name, commit_timestamp;
END;
$$ LANGUAGE plpgsql;


SELECT create_or_fetch_local_node('n3');

SELECT join_node_group('host=127.0.0.1 dbname=pgedge port=5431 user=pgedge password=pgedge', 'n3');

SELECT create_replication_slot('spk_pgedge_n2_sub_n2_n3', 'spock_output');

\set AUTOCOMMIT on


SELECT create_subscription_for_node(
    subscription_name := 'sub_n1_n3');


-- Phase 5: Trigger sync_event on n2 and wait on n1
CALL spock.wait_for_sync_event(true, 'n1', trigger_sync_event('n2'), 1200000);

-- Phase 6: Trigger sync_event on n1 and wait on n3
CALL spock.wait_for_sync_event(true, 'n3', trigger_sync_event('n1'), 1200000);

-- Phase 9: Advance Replication Slot
SELECT advance_replication_slot('spk_pgedge_n2_sub_n2_n3', check_commit_timestamp_for_n3_lag()::text);

-- Phase 10: Enable Subscription sub_n2_n3
SELECT enable_subscription('sub_n2_n3', true);

-- Phase 11: Check Replication Lags
SELECT check_replication_lags();