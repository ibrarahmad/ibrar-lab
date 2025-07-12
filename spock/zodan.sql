-- Function to retrieve Spock nodes from a remote DSN
CREATE OR REPLACE FUNCTION get_spock_nodes(remote_dsn text)
RETURNS TABLE (
    node_id    integer,
    node_name  text,
    location   text,
    country    text,
    info       text,
    dsn        text
)
AS
$$
BEGIN
    RETURN QUERY
    SELECT *
    FROM dblink(
        remote_dsn,
        'SELECT n.node_id, n.node_name, n.location, n.country, n.info, i.if_dsn
         FROM spock.node n
         JOIN spock.node_interface i ON n.node_id = i.if_nodeid'
    ) AS t(
        node_id integer,
        node_name text,
        location text,
        country text,
        info text,
        dsn text
    );
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION create_sub(
    node_dsn text,
    subscription_name text,
    provider_dsn text,
    replication_sets text,
    synchronize_structure boolean,
    synchronize_data boolean,
    forward_origins text,
    apply_delay interval,
    enabled boolean
)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    sid oid;
    remotesql text;
    exists_count int;
BEGIN
    -- Step 1: Check if subscription already exists on remote
    remotesql := format(
        'SELECT count(*) FROM spock.subscription WHERE sub_name = %L',
        subscription_name
    );

    RAISE INFO E'
    [STEP 1] Remote SQL for check for subscription : %
    ', remotesql;

    SELECT * FROM dblink(node_dsn, remotesql) AS t(count int) INTO exists_count;

    RAISE INFO E'
    [STEP 1] Remote subscription existence check for subscription "%": %
    ', subscription_name, exists_count;

    IF exists_count > 0 THEN
        RAISE INFO E'
        [STEP 1] Subscription "%" already exists remotely. Skipping creation.
        ', subscription_name;
        RETURN;
    END IF;

    -- Step 2: Build remote SQL for subscription creation
    remotesql := format(
        'SELECT spock.sub_create(
            subscription_name := %L,
            provider_dsn := %L,
            replication_sets := %s,
            synchronize_structure := %L,
            synchronize_data := %L,
            forward_origins := %L,
            apply_delay := %L,
            enabled := %L
        )',
        subscription_name,
        provider_dsn,
        replication_sets,
        synchronize_structure::text,
        synchronize_data::text,
        forward_origins,
        apply_delay::text,
        enabled::text
    );

    RAISE INFO E'
    [STEP 2] Remote SQL for subscription creation: %
    ', remotesql;

    -- Step 3: Execute subscription creation on remote node using dblink
    BEGIN
        SELECT * FROM dblink(node_dsn, remotesql) AS t(sid oid) INTO sid;

        RAISE LOG E'
        [STEP 3] Created subscription "%" with id % on remote node.
        ', subscription_name, sid;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE EXCEPTION E'
            [STEP 3] Subscription "%" creation failed remotely! Error: %
            ', subscription_name, SQLERRM;
    END;
END;
$$;

CREATE OR REPLACE FUNCTION create_replication_slot(
    node_dsn text,
    slot_name text,
    plugin text DEFAULT 'spock_output'
)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    remotesql text;
    result RECORD;
    exists_count int;
BEGIN
    -- Check if slot already exists
    remotesql := format(
        'SELECT count(*) FROM pg_replication_slots WHERE slot_name = %L',
        slot_name
    );

    SELECT * FROM dblink(node_dsn, remotesql) AS t(count int) INTO exists_count;

    IF exists_count > 0 THEN
        RAISE INFO E'
        [STEP] Replication slot "%" already exists on remote node. Skipping creation.',
        slot_name;
        RETURN;
    END IF;

    
    remotesql := format(
        'SELECT slot_name, lsn FROM pg_create_logical_replication_slot(%L, %L)',
        slot_name, plugin
    );

    RAISE INFO E'
    [STEP] Remote SQL for slot creation: %
    ', remotesql;

    BEGIN
        SELECT * FROM dblink(node_dsn, remotesql) AS t(slot_name text, lsn pg_lsn) INTO result;
        RAISE LOG E'
        [STEP] Created replication slot "%" with plugin "%" on remote node.',
        slot_name, plugin;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE INFO E'
            [STEP] Replication slot "%" may already exist or creation failed. Error: %
            ', slot_name, SQLERRM;
    END;
END;
$$;

CREATE OR REPLACE FUNCTION sync_event(node_dsn text)
RETURNS pg_lsn
LANGUAGE plpgsql
AS
$$
DECLARE
    sync_rec RECORD;
    remotesql text;
BEGIN
    remotesql := 'SELECT spock.sync_event();';

    RAISE INFO E'[STEP] Remote SQL for sync event: %\n', remotesql;

    SELECT * FROM dblink(node_dsn, remotesql) AS t(lsn pg_lsn) INTO sync_rec;
    RAISE LOG E'[STEP] Sync event triggered on remote node: % with LSN %', node_dsn, sync_rec.lsn;
    RETURN sync_rec.lsn;
END;
$$;

CREATE OR REPLACE FUNCTION wait_for_sync_event(
    node_dsn text,
    wait_for_all boolean,
    provider_node text,
    sync_lsn pg_lsn,
    timeout_ms integer
)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    remotesql text;
    dummy RECORD; -- we need to capture the result
BEGIN
    remotesql := format(
        'CALL spock.wait_for_sync_event(%L, %L, %L::pg_lsn, %s);',
        wait_for_all,
        provider_node,
        sync_lsn::text,
        timeout_ms
    );

    RAISE INFO E'[STEP] Remote SQL for waiting for sync event: %', remotesql;

    -- Assign result to dummy to satisfy dblink's record output
    SELECT * INTO dummy
    FROM dblink(node_dsn, remotesql) AS t(result text);  -- structure must match

    RAISE LOG E'[STEP] Waited for sync event on remote node: %', node_dsn;
END;
$$;

-- Procedure to create a Spock node remotely
CREATE OR REPLACE PROCEDURE create_node(
    node_name text,
    dsn text,
    location text DEFAULT 'NY',
    country text DEFAULT 'USA',
    info jsonb DEFAULT '{}'::jsonb
)
LANGUAGE plpgsql
AS
$$
DECLARE
    joinid oid;
    remotesql text;
    exists_count int;
BEGIN
    -- Step 1: Check if node already exists on remote
    remotesql := format(
        'SELECT count(*) FROM spock.node WHERE node_name = %L',
        node_name
    );

    RAISE INFO E'
    [STEP 2] Remote SQL for check for node : %
    ', remotesql;

    SELECT * FROM dblink(dsn, remotesql) AS t(count int) INTO exists_count;

    raise info E'
    [STEP 1] Remote node existence check for node "%": %
    ', node_name, exists_count;

    IF exists_count > 0 THEN
        RAISE LOG E'
        [STEP 1] Node "%" already exists remotely. Skipping creation.
        ', node_name;
        RETURN;
    END IF;

    -- Step 2: Build the remote SQL for node creation
    remotesql := format(
        'SELECT spock.node_create(
            node_name := %L,
            dsn := %L,
            location := %L,
            country := %L,
            info := %L::jsonb
        )',
        node_name, dsn, location, country, info::text
    );

    RAISE INFO E'
    [STEP 2] Remote SQL for node creation: %\n
    ', remotesql;

    -- Step 3: Execute the node creation on the remote DSN using dblink
    BEGIN
        SELECT * FROM dblink(dsn, remotesql) AS t(joinid oid) INTO joinid;

        IF joinid IS NOT NULL THEN
            RAISE LOG E'
            [STEP 3] Node "%" created remotely with id % and DSN: %
            ', node_name, joinid, dsn;
        ELSE
            RAISE EXCEPTION E'
            [STEP 3] Node "%" creation failed remotely!
            ', node_name;
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE EXCEPTION E'
            [STEP 3] Node "%" creation failed remotely! Error: %
            ', node_name, SQLERRM;
    END;

END;
$$;

CREATE OR REPLACE FUNCTION get_commit_timestamp(node_dsn text, n1 text, n2 text)
RETURNS timestamp
LANGUAGE plpgsql
AS
$$
DECLARE
    ts_rec RECORD;
    remotesql text;
BEGIN
    remotesql := format(
        'SELECT commit_timestamp FROM spock.lag_tracker WHERE origin_name = %L AND receiver_name = %L',
        n1, n2
    );
   
    RAISE INFO E'[STEP] Remote SQL for getting commit timestamp: %\n', remotesql;
    SELECT * FROM dblink(node_dsn, remotesql) AS t(commit_timestamp timestamp) INTO ts_rec;

    RAISE LOG E'[STEP] Commit timestamp for n3 lag: %', ts_rec.commit_timestamp;
    RETURN ts_rec.commit_timestamp;
END;
$$;

CREATE OR REPLACE FUNCTION advance_replication_slot(
    node_dsn text,
    slot_name text,
    sync_timestamp timestamp
)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    remotesql text;
    slot_advance_result RECORD;
BEGIN
    IF sync_timestamp IS NULL THEN
        RAISE INFO E'[STEP] Commit timestamp is NULL, skipping slot advance for slot "%".', slot_name;
        RETURN;
    END IF;

    remotesql := format(
        'WITH lsn_cte AS (
            SELECT spock.get_lsn_from_commit_ts(%L, %L::timestamp) AS lsn
        )
        SELECT pg_replication_slot_advance(%L, lsn) FROM lsn_cte;',
        slot_name, sync_timestamp::text, slot_name
    );

    RAISE INFO E'[STEP] Remote SQL for advancing replication slot: %', remotesql;
    RAISE INFO E'[STEP] Remote node DSN: %', node_dsn;

    -- Capture the result, even if you don't use it
    SELECT * FROM dblink(node_dsn, remotesql) INTO slot_advance_result;
END;
$$;

CREATE OR REPLACE FUNCTION enable_sub(
    node_dsn text,
    sub_name text,
    immediate boolean DEFAULT true
)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    remotesql text;
BEGIN
    remotesql := format(
        'SELECT spock.sub_enable(subscription_name := %L, immediate := %L);',
        sub_name, immediate::text
    );
    
    RAISE INFO E'[STEP] Remote SQL for enabling subscription: %\n', remotesql;

    -- Fix: must provide a dummy column definition
    PERFORM * FROM dblink(node_dsn, remotesql) AS t(result text);

    RAISE LOG E'[STEP] Enabled subscription "%" on remote node: %', sub_name, node_dsn;
END;
$$;


CREATE OR REPLACE FUNCTION monitor_replication_lag(node_dsn text)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    remotesql text;
BEGIN
    remotesql := $sql$
        DO '
        DECLARE
            lag_n1_n4 interval;
            lag_n2_n4 interval;
            lag_n3_n4 interval;
        BEGIN
            LOOP
                SELECT now() - commit_timestamp INTO lag_n1_n4
                FROM spock.lag_tracker
                WHERE origin_name = 'n1' AND receiver_name = 'n4';

                SELECT now() - commit_timestamp INTO lag_n2_n4
                FROM spock.lag_tracker
                WHERE origin_name = 'n2' AND receiver_name = 'n4';

                SELECT now() - commit_timestamp INTO lag_n3_n4
                FROM spock.lag_tracker
                WHERE origin_name = 'n3' AND receiver_name = 'n4';

                RAISE NOTICE 'n1 → n4 lag: %, n2 → n4 lag: %, n3 → n4 lag: %',
                             COALESCE(lag_n1_n4::text, 'NULL'),
                             COALESCE(lag_n2_n4::text, 'NULL'),
                             COALESCE(lag_n3_n4::text, 'NULL');

                EXIT WHEN lag_n1_n4 IS NOT NULL AND lag_n2_n4 IS NOT NULL AND lag_n3_n4 IS NOT NULL
                          AND extract(epoch FROM lag_n1_n4) < 59
                          AND extract(epoch FROM lag_n2_n4) < 59
                          AND extract(epoch FROM lag_n3_n4) < 59;

                PERFORM pg_sleep(1);
            END LOOP;
        END
        ';
    $sql$;
    PERFORM dblink(node_dsn, remotesql);
    RAISE LOG E'[STEP] Monitoring replication lag on remote node: %', node_dsn;
END;
$$;

-- Procedure to add a node and create a custom subscription using only the original arguments
CREATE OR REPLACE PROCEDURE add_node(
    src_node_name text,
    src_dsn text,
    new_node_name text,
    new_node_dsn text,
    new_node_location text DEFAULT 'NY',
    new_node_country text DEFAULT 'USA',
    new_node_info jsonb DEFAULT '{}'::jsonb
)
LANGUAGE plpgsql
AS
$$
DECLARE
    rec RECORD;
    dbname text;
    slot_name text;
    sync_lsn pg_lsn;
    sync_timestamp timestamp;
BEGIN
    -- Create the new node
    CALL create_node(
        new_node_name,
        new_node_dsn,
        new_node_location,
        new_node_country,
        new_node_info
    );

    RAISE LOG E'
    [STEP] New node "%" created with DSN: %
    ', new_node_name, new_node_dsn;

   FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        IF rec.node_name = src_node_name THEN
            CONTINUE;
        END IF;

        PERFORM create_sub(
            new_node_dsn,
            'sub_'|| rec.node_name || '_' || new_node_name,
            rec.dsn,
            'ARRAY[''default'', ''default_insert_only'', ''ddl_sql'']',
            false,
            false,
            '{}',
            '0'::interval,
            false
        );
    END LOOP;

    FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        IF rec.node_name = src_node_name THEN
            CONTINUE;
        END IF;

        RAISE LOG E'
        Node: %, Location: %, Country: %, DSN: %
        ', rec.node_name, rec.location, rec.country, rec.dsn;

        dbname := substring(rec.dsn from 'dbname=([^\s]+)');
        IF dbname IS NULL THEN
            dbname := 'pgedge';
        END IF;

        slot_name := left('spk_' || dbname || '_' || rec.node_name || '_sub_' || rec.node_name || '_' || new_node_name, 64);

        PERFORM create_replication_slot(
            rec.dsn,
            slot_name,
            'spock_output'
        );
    END LOOP;

    FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        IF rec.node_name != src_node_name THEN
            SELECT sync_event(rec.dsn) INTO sync_lsn;
            PERFORM wait_for_sync_event(src_dsn, true, rec.node_name, sync_lsn, 10000);
        END IF;
    END LOOP;

    PERFORM create_sub(
        new_node_dsn,
        'sub_' || src_node_name || '_' || new_node_name,
        src_dsn,
        'ARRAY[''default'', ''default_insert_only'', ''ddl_sql'']',
        true,
        true,
        '{}',
        '0'::interval,
        true
    );

    SELECT sync_event(src_dsn) INTO sync_lsn;
    PERFORM wait_for_sync_event(new_node_dsn, true, src_node_name, sync_lsn, 10000);

    FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        IF rec.node_name != src_node_name THEN
        SELECT get_commit_timestamp(new_node_dsn, src_node_name, rec.node_name) INTO sync_timestamp;
        slot_name := 'spk_' || dbname || '_' || src_node_name || '_sub_' || rec.node_name || '_' || new_node_name;
        
        PERFORM advance_replication_slot(rec.dsn, slot_name, sync_timestamp);
     END IF;
    END LOOP;

   
   FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        PERFORM create_sub(
            rec.dsn,
            'sub_'|| new_node_name || '_' || rec.node_name,
            new_node_dsn,
            'ARRAY[''default'', ''default_insert_only'', ''ddl_sql'']',
            false,
            false,
            '{}',
            '0'::interval,
            true
        );
    END LOOP;

FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        IF rec.node_name = new_node_name THEN
            CONTINUE;
        END IF;

        PERFORM enable_sub(
            new_node_dsn,
            'sub_'|| rec.node_name || '_' || new_node_name);
    END LOOP;
       
END;
$$;