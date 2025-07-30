-- =================================
-- PARTITION CREATION FOR DOORLOCK SYSTEM
-- Monthly partitions for access_logs, Hash partitions for system_logs
-- =================================

-- =================================
-- ACCESS LOGS MONTHLY PARTITIONS
-- =================================

-- Create partitions for 2025 (current year + future months)
CREATE TABLE access_logs_202507 PARTITION OF access_logs
    FOR VALUES FROM ('2025-07-01 00:00:00+07') TO ('2025-08-01 00:00:00+07');

CREATE TABLE access_logs_202508 PARTITION OF access_logs
    FOR VALUES FROM ('2025-08-01 00:00:00+07') TO ('2025-09-01 00:00:00+07');

CREATE TABLE access_logs_202509 PARTITION OF access_logs
    FOR VALUES FROM ('2025-09-01 00:00:00+07') TO ('2025-10-01 00:00:00+07');

CREATE TABLE access_logs_202510 PARTITION OF access_logs
    FOR VALUES FROM ('2025-10-01 00:00:00+07') TO ('2025-11-01 00:00:00+07');

CREATE TABLE access_logs_202511 PARTITION OF access_logs
    FOR VALUES FROM ('2025-11-01 00:00:00+07') TO ('2025-12-01 00:00:00+07');

CREATE TABLE access_logs_202512 PARTITION OF access_logs
    FOR VALUES FROM ('2025-12-01 00:00:00+07') TO ('2026-01-01 00:00:00+07');

-- Create partitions for 2026 (future planning)
CREATE TABLE access_logs_202601 PARTITION OF access_logs
    FOR VALUES FROM ('2026-01-01 00:00:00+07') TO ('2026-02-01 00:00:00+07');

CREATE TABLE access_logs_202602 PARTITION OF access_logs
    FOR VALUES FROM ('2026-02-01 00:00:00+07') TO ('2026-03-01 00:00:00+07');

CREATE TABLE access_logs_202603 PARTITION OF access_logs
    FOR VALUES FROM ('2026-03-01 00:00:00+07') TO ('2026-04-01 00:00:00+07');

CREATE TABLE access_logs_202604 PARTITION OF access_logs
    FOR VALUES FROM ('2026-04-01 00:00:00+07') TO ('2026-05-01 00:00:00+07');

CREATE TABLE access_logs_202605 PARTITION OF access_logs
    FOR VALUES FROM ('2026-05-01 00:00:00+07') TO ('2026-06-01 00:00:00+07');

CREATE TABLE access_logs_202606 PARTITION OF access_logs
    FOR VALUES FROM ('2026-06-01 00:00:00+07') TO ('2026-07-01 00:00:00+07');

-- =================================
-- SYSTEM LOGS HASH PARTITIONS (12 partitions for balanced distribution)
-- =================================

CREATE TABLE system_logs_0 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 0);

CREATE TABLE system_logs_1 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 1);

CREATE TABLE system_logs_2 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 2);

CREATE TABLE system_logs_3 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 3);

CREATE TABLE system_logs_4 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 4);

CREATE TABLE system_logs_5 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 5);

CREATE TABLE system_logs_6 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 6);

CREATE TABLE system_logs_7 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 7);

CREATE TABLE system_logs_8 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 8);

CREATE TABLE system_logs_9 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 9);

CREATE TABLE system_logs_10 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 10);

CREATE TABLE system_logs_11 PARTITION OF system_logs
    FOR VALUES WITH (modulus 12, remainder 11);

-- =================================
-- PARTITION MANAGEMENT FUNCTIONS
-- =================================

-- Function to create next month partition for access_logs
CREATE OR REPLACE FUNCTION create_monthly_partition(target_date DATE)
RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    start_date TEXT;
    end_date TEXT;
    sql_cmd TEXT;
BEGIN
    -- Generate partition name (format: access_logs_YYYYMM)
    partition_name := 'access_logs_' || to_char(target_date, 'YYYYMM');
    
    -- Calculate date ranges (Indonesia timezone)
    start_date := to_char(date_trunc('month', target_date), 'YYYY-MM-DD') || ' 00:00:00+07';
    end_date := to_char(date_trunc('month', target_date) + interval '1 month', 'YYYY-MM-DD') || ' 00:00:00+07';
    
    -- Build CREATE TABLE command
    sql_cmd := format('CREATE TABLE IF NOT EXISTS %I PARTITION OF access_logs FOR VALUES FROM (%L) TO (%L)',
                     partition_name, start_date, end_date);
    
    -- Execute the command
    EXECUTE sql_cmd;
    
    -- Return info
    RETURN format('Created partition %s for range %s to %s', partition_name, start_date, end_date);
END;
$$ LANGUAGE plpgsql;

-- Function to drop old partitions (data retention)
CREATE OR REPLACE FUNCTION drop_old_partitions(retention_months INTEGER DEFAULT 12)
RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    cutoff_date DATE;
    dropped_partitions TEXT[] := '{}';
    partition_record RECORD;
BEGIN
    -- Calculate cutoff date
    cutoff_date := date_trunc('month', CURRENT_DATE) - (retention_months || ' months')::interval;
    
    -- Find partitions older than cutoff date
    FOR partition_record IN
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE tablename LIKE 'access_logs_%'
        AND tablename ~ '^access_logs_[0-9]{6}$'
        AND to_date(substring(tablename from 13), 'YYYYMM') < cutoff_date
    LOOP
        partition_name := partition_record.tablename;
        
        -- Drop the partition
        EXECUTE format('DROP TABLE IF EXISTS %I', partition_name);
        
        -- Add to dropped list
        dropped_partitions := array_append(dropped_partitions, partition_name);
    END LOOP;
    
    -- Return result
    IF array_length(dropped_partitions, 1) > 0 THEN
        RETURN format('Dropped %s old partitions: %s', 
                     array_length(dropped_partitions, 1), 
                     array_to_string(dropped_partitions, ', '));
    ELSE
        RETURN 'No old partitions found to drop';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to automatically create future partitions
CREATE OR REPLACE FUNCTION auto_create_partitions()
RETURNS TEXT AS $$
DECLARE
    result TEXT[];
    future_month DATE;
    i INTEGER;
BEGIN
    -- Create partitions for next 6 months
    FOR i IN 0..5 LOOP
        future_month := date_trunc('month', CURRENT_DATE) + (i || ' months')::interval;
        result := array_append(result, create_monthly_partition(future_month));
    END LOOP;
    
    RETURN array_to_string(result, E'\n');
END;
$$ LANGUAGE plpgsql;

-- =================================
-- PARTITION MAINTENANCE SCHEDULING
-- =================================

-- Note: This requires pg_cron extension (available in production)
-- For now, we'll create the structure and run manually

-- Create maintenance log table
CREATE TABLE partition_maintenance_log (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(50) NOT NULL,
    result TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Function to run monthly partition maintenance
CREATE OR REPLACE FUNCTION monthly_partition_maintenance()
RETURNS TEXT AS $$
DECLARE
    create_result TEXT;
    drop_result TEXT;
    final_result TEXT;
BEGIN
    -- Create future partitions
    SELECT auto_create_partitions() INTO create_result;
    
    -- Drop old partitions (keep 12 months)
    SELECT drop_old_partitions(12) INTO drop_result;
    
    -- Combine results
    final_result := E'PARTITION MAINTENANCE RESULTS:\n' || 
                   E'CREATE: ' || create_result || E'\n' ||
                   E'DROP: ' || drop_result;
    
    -- Log the maintenance
    INSERT INTO partition_maintenance_log (operation, result)
    VALUES ('monthly_maintenance', final_result);
    
    RETURN final_result;
END;
$$ LANGUAGE plpgsql;

-- =================================
-- INITIAL PARTITION SETUP
-- =================================

-- Create partitions for the next 6 months automatically
SELECT auto_create_partitions();

-- Log the initial setup
INSERT INTO partition_maintenance_log (operation, result)
VALUES ('initial_setup', 'Created initial partitions for access_logs and system_logs');

-- =================================
-- PARTITION INFORMATION VIEWS
-- =================================

-- View to monitor partition sizes and row counts
CREATE VIEW partition_info AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    (SELECT count(*) FROM information_schema.tables 
     WHERE table_schema = t.schemaname AND table_name = t.tablename) as exists,
    CASE 
        WHEN tablename LIKE 'access_logs_%' THEN 'access_logs (monthly)'
        WHEN tablename LIKE 'system_logs_%' THEN 'system_logs (hash)'
        ELSE 'other'
    END as partition_type
FROM pg_tables t
WHERE tablename LIKE 'access_logs_%' OR tablename LIKE 'system_logs_%'
ORDER BY tablename;

-- View to check partition pruning effectiveness
CREATE VIEW partition_pruning_info AS
SELECT 
    'access_logs' as table_name,
    'Monthly by timestamp' as partition_strategy,
    (SELECT count(*) FROM pg_tables WHERE tablename LIKE 'access_logs_%') as partition_count,
    pg_size_pretty(pg_total_relation_size('access_logs')) as total_size
UNION ALL
SELECT 
    'system_logs' as table_name,
    'Hash by device_id' as partition_strategy,
    (SELECT count(*) FROM pg_tables WHERE tablename LIKE 'system_logs_%') as partition_count,
    pg_size_pretty(pg_total_relation_size('system_logs')) as total_size;

-- =================================
-- COMMENTS
-- =================================

COMMENT ON FUNCTION create_monthly_partition(DATE) IS 'Creates a new monthly partition for access_logs table';
COMMENT ON FUNCTION drop_old_partitions(INTEGER) IS 'Drops partitions older than specified months for data retention';
COMMENT ON FUNCTION auto_create_partitions() IS 'Automatically creates partitions for the next 6 months';
COMMENT ON FUNCTION monthly_partition_maintenance() IS 'Runs monthly partition maintenance (create future, drop old)';
COMMENT ON VIEW partition_info IS 'Shows information about all partitions including sizes';
COMMENT ON VIEW partition_pruning_info IS 'Summary of partition strategies and effectiveness';
