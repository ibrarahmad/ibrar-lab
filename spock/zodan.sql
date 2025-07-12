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
    [STEP 2] Remote SQL for node creation: %
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

-- Procedure to add a node and create a custom subscription using only the original arguments
CREATE OR REPLACE PROCEDURE add_node(
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

    -- Create the subscription on the new node with hardcoded custom arguments
    PERFORM create_sub(
        new_node_dsn,
        'sub_n2_n3',
        'host=127.0.0.1 dbname=pgedge port=5432 user=pgedge password=spockpass',
        'ARRAY[''default'', ''default_insert_only'', ''ddl_sql'']',
        false,
        false,
        '{}',
        '0'::interval,
        false
    );

    RAISE LOG E'
    [STEP] Subscription "sub_n2_n3" created on node "%" for provider DSN: %
    ', new_node_name, 'host=127.0.0.1 dbname=pgedge port=5432 user=pgedge password=spockpass';

    -- Show all nodes from src_dsn and create replication slot for each
    FOR rec IN
        SELECT * FROM get_spock_nodes(src_dsn)
    LOOP
        IF rec.dsn = src_dsn THEN
            CONTINUE;
        END IF;

        RAISE LOG E'
        Node: %, Location: %, Country: %, DSN: %
        ', rec.node_name, rec.location, rec.country, rec.dsn;

        dbname := substring(rec.dsn from 'dbname=([^\s]+)');
        IF dbname IS NULL THEN
            dbname := 'pgedge';
        END IF;

        slot_name := 'spk_' || dbname || '_' || rec.node_name || '_sub_' || rec.node_name || '_' || new_node_name;

        PERFORM create_replication_slot(
            rec.dsn,
            slot_name,
            'spock_output'
        );
    END LOOP;
END;
$$;