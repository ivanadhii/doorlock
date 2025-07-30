-- =================================
-- SAMPLE DATA FOR DOORLOCK SYSTEM
-- Test data for development and integration testing
-- =================================

-- Set timezone for consistent timestamps
SET timezone = 'Asia/Jakarta';

-- =================================
-- SAMPLE DEVICES
-- =================================

INSERT INTO devices (device_id, device_name, location, is_active, hardware_version, total_reboots) VALUES
-- Otista location devices
('doorlock_otista_001', 'Otista Main Door', 'otista', true, 'v2.1', 0),
('doorlock_otista_002', 'Otista Side Door', 'otista', true, 'v2.1', 1),
('doorlock_otista_003', 'Otista Emergency Exit', 'otista', true, 'v2.0', 2),

-- Kemayoran location devices  
('doorlock_kemayoran_001', 'Kemayoran Main Entrance', 'kemayoran', true, 'v2.1', 0),
('doorlock_kemayoran_002', 'Kemayoran Staff Door', 'kemayoran', true, 'v2.0', 1),
('doorlock_kemayoran_003', 'Kemayoran Parking Gate', 'kemayoran', false, 'v1.9', 5),

-- Test devices for development
('doorlock_test_001', 'Test Device Alpha', 'otista', true, 'v2.2-dev', 0),
('doorlock_test_002', 'Test Device Beta', 'kemayoran', true, 'v2.2-dev', 0);

-- =================================
-- DEVICE STATUS (Current state)
-- =================================

INSERT INTO device_status (
    device_id, door_status, rfid_enabled, battery_percentage, 
    uptime_seconds, wifi_rssi, free_heap, location, 
    spam_detected, total_access_count, session_id
) VALUES
-- Active devices with good status
('doorlock_otista_001', 'locked', true, 95, 86400, -45, 28672, 'otista', false, 1250, '20250728_0800_001'),
('doorlock_otista_002', 'locked', true, 87, 172800, -52, 27850, 'otista', false, 890, '20250728_0800_002'),
('doorlock_otista_003', 'unlocked', false, 78, 259200, -48, 26420, 'otista', false, 2100, '20250728_0800_003'),

('doorlock_kemayoran_001', 'locked', true, 92, 345600, -41, 29100, 'kemayoran', false, 1850, '20250728_0800_004'),
('doorlock_kemayoran_002', 'locked', true, 65, 432000, -58, 25600, 'kemayoran', false, 750, '20250728_0800_005'),

-- Problematic device (offline, low battery)
('doorlock_kemayoran_003', 'locked', true, 15, 518400, -78, 22100, 'kemayoran', true, 5000, '20250727_1600_001'),

-- Test devices
('doorlock_test_001', 'locked', true, 100, 3600, -35, 30000, 'otista', false, 50, '20250728_0800_999'),
('doorlock_test_002', 'unlocked', true, 88, 7200, -42, 28500, 'kemayoran', false, 25, '20250728_0800_998');

-- =================================
-- DEVICE FIRMWARE STATUS
-- =================================

INSERT INTO device_firmware (
    device_id, current_version, available_version, last_known_good_version,
    ota_status, ota_retry_count, firmware_file_path, firmware_size_bytes
) VALUES
-- Production devices - ready for update
('doorlock_otista_001', 'v2.1.0', 'v2.2.0', 'v2.1.0', 'idle', 0, 
 '/firmware/devices/doorlock_otista_001/v2.1.0.bin', 524288),
('doorlock_otista_002', 'v2.1.0', 'v2.2.0', 'v2.1.0', 'idle', 0,
 '/firmware/devices/doorlock_otista_002/v2.1.0.bin', 524288),
('doorlock_otista_003', 'v2.0.0', 'v2.2.0', 'v2.0.0', 'idle', 0,
 '/firmware/devices/doorlock_otista_003/v2.0.0.bin', 512000),

('doorlock_kemayoran_001', 'v2.1.0', 'v2.2.0', 'v2.1.0', 'idle', 0,
 '/firmware/devices/doorlock_kemayoran_001/v2.1.0.bin', 524288),
('doorlock_kemayoran_002', 'v2.0.0', 'v2.2.0', 'v2.0.0', 'failed', 2,
 '/firmware/devices/doorlock_kemayoran_002/v2.0.0.bin', 512000),

-- Problematic device
('doorlock_kemayoran_003', 'v1.9.0', 'v2.2.0', 'v1.9.0', 'idle', 0,
 '/firmware/devices/doorlock_kemayoran_003/v1.9.0.bin', 480000),

-- Test devices - latest version
('doorlock_test_001', 'v2.2.0', NULL, 'v2.2.0', 'idle', 0,
 '/firmware/devices/doorlock_test_001/v2.2.0.bin', 540000),
('doorlock_test_002', 'v2.2.0', NULL, 'v2.2.0', 'idle', 0,
 '/firmware/devices/doorlock_test_002/v2.2.0.bin', 540000);

-- =================================
-- SAMPLE ACCESS LOGS (Recent activity)
-- =================================

-- Generate access logs for the last 3 days
INSERT INTO access_logs (device_id, card_uid, access_granted, access_type, user_name, timestamp, session_id) VALUES

-- Yesterday's activity (2025-07-27)
('doorlock_otista_001', '04A1B2C3D4E5F6', true, 'rfid', 'John Doe', '2025-07-27 07:30:15+07', '20250727_0800_001'),
('doorlock_otista_001', '04B1C2D3E4F5A6', true, 'rfid', 'Jane Smith', '2025-07-27 08:15:22+07', '20250727_0800_001'),
('doorlock_otista_001', 'E004123456', false, 'rfid', NULL, '2025-07-27 09:45:18+07', '20250727_0800_001'),
('doorlock_otista_001', '04C1D2E3F4A5B6', true, 'rfid', 'Mike Johnson', '2025-07-27 17:20:35+07', '20250727_1600_001'),

('doorlock_otista_002', '04A1B2C3D4E5F6', true, 'rfid', 'John Doe', '2025-07-27 08:45:12+07', '20250727_0800_002'),
('doorlock_otista_002', '04D1E2F3A4B5C6', false, 'rfid', NULL, '2025-07-27 12:30:45+07', '20250727_0800_002'),

('doorlock_kemayoran_001', '04E1F2A3B4C5D6', true, 'rfid', 'Sarah Wilson', '2025-07-27 09:15:30+07', '20250727_0800_004'),
('doorlock_kemayoran_001', '04F1A2B3C4D5E6', true, 'rfid', 'Tom Brown', '2025-07-27 16:45:20+07', '20250727_1600_004'),

-- Today's activity (2025-07-28)
('doorlock_otista_001', '04A1B2C3D4E5F6', true, 'rfid', 'John Doe', '2025-07-28 07:45:10+07', '20250728_0800_001'),
('doorlock_otista_001', '04B1C2D3E4F5A6', true, 'rfid', 'Jane Smith', '2025-07-28 08:30:25+07', '20250728_0800_001'),
('doorlock_otista_001', '04C1D2E3F4A5B6', true, 'rfid', 'Mike Johnson', '2025-07-28 09:15:18+07', '20250728_0800_001'),

('doorlock_otista_002', '04G1H2I3J4K5L6', false, 'rfid', NULL, '2025-07-28 10:20:32+07', '20250728_0800_002'),
('doorlock_otista_002', '04A1B2C3D4E5F6', true, 'rfid', 'John Doe', '2025-07-28 14:15:45+07', '20250728_0800_002'),

('doorlock_kemayoran_001', '04E1F2A3B4C5D6', true, 'rfid', 'Sarah Wilson', '2025-07-28 08:00:15+07', '20250728_0800_004'),
('doorlock_kemayoran_001', '04F1A2B3C4D5E6', true, 'rfid', 'Tom Brown', '2025-07-28 17:30:40+07', '20250728_0800_004'),

('doorlock_kemayoran_002', '04H1I2J3K4L5M6', true, 'rfid', 'Lisa Davis', '2025-07-28 09:45:28+07', '20250728_0800_005'),

-- Spam detection example (kemayoran_003)
('doorlock_kemayoran_003', 'SPAM_CARD_001', false, 'rfid', NULL, '2025-07-28 11:00:00+07', '20250728_0800_006'),
('doorlock_kemayoran_003', 'SPAM_CARD_001', false, 'rfid', NULL, '2025-07-28 11:00:05+07', '20250728_0800_006'),
('doorlock_kemayoran_003', 'SPAM_CARD_001', false, 'rfid', NULL, '2025-07-28 11:00:10+07', '20250728_0800_006'),
('doorlock_kemayoran_003', 'SPAM_CARD_002', false, 'rfid', NULL, '2025-07-28 11:00:15+07', '20250728_0800_006'),
('doorlock_kemayoran_003', 'SPAM_CARD_002', false, 'rfid', NULL, '2025-07-28 11:00:20+07', '20250728_0800_006');

-- =================================
-- SAMPLE SYSTEM LOGS
-- =================================

INSERT INTO system_logs (device_id, log_level, message, details, timestamp) VALUES

-- Normal operational logs
('doorlock_otista_001', 'INFO', 'System boot completed', 
 '{"boot_time_ms": 3500, "free_heap": 28672, "wifi_connected": true}', 
 '2025-07-28 00:00:15+07'),

('doorlock_otista_001', 'INFO', 'Sync completed successfully', 
 '{"sync_duration_ms": 2300, "records_sent": 15, "commands_received": 0}', 
 '2025-07-28 08:00:45+07'),

('doorlock_otista_002', 'WARN', 'Low battery warning', 
 '{"battery_percentage": 65, "estimated_days_remaining": 30}', 
 '2025-07-28 08:01:20+07'),

('doorlock_kemayoran_002', 'ERROR', 'OTA update failed', 
 '{"error": "Download timeout", "retry_count": 2, "firmware_version": "v2.2.0"}', 
 '2025-07-28 02:15:30+07'),

('doorlock_kemayoran_003', 'WARN', 'Spam detection triggered', 
 '{"failed_attempts": 120, "time_window_minutes": 60, "unique_cards": 5}', 
 '2025-07-28 11:00:25+07'),

-- Test device logs
('doorlock_test_001', 'DEBUG', 'Test access log generated', 
 '{"test_mode": true, "card_uid": "TEST_CARD_001"}', 
 '2025-07-28 10:30:00+07'),

('doorlock_test_002', 'INFO', 'Development firmware loaded', 
 '{"version": "v2.2.0-dev", "build_timestamp": "2025-07-28T05:00:00Z"}', 
 '2025-07-28 06:00:00+07');

-- =================================
-- SAMPLE REMOTE COMMANDS
-- =================================

INSERT INTO remote_commands (command_id, device_id, command_type, command_payload, status, created_at, sent_at, executed_at) VALUES

-- Successfully executed commands
('cmd_success_001', 'doorlock_otista_001', 'unlock_timer', 
 '{"action": "unlock", "duration_minutes": 30}', 
 'success', '2025-07-28 09:00:00+07', '2025-07-28 09:00:15+07', '2025-07-28 09:00:18+07'),

('cmd_success_002', 'doorlock_kemayoran_001', 'rfid_control', 
 '{"action": "disable"}', 
 'success', '2025-07-28 10:00:00+07', '2025-07-28 10:00:12+07', '2025-07-28 10:00:15+07'),

-- Pending commands (in queue)
('cmd_pending_001', 'doorlock_otista_002', 'unlock_timer', 
 '{"action": "unlock", "duration_minutes": 20}', 
 'queued', '2025-07-28 14:30:00+07', NULL, NULL),

('cmd_pending_002', 'doorlock_kemayoran_002', 'rfid_control', 
 '{"action": "enable"}', 
 'queued', '2025-07-28 14:35:00+07', NULL, NULL),

-- Failed command (for testing error handling)
('cmd_failed_001', 'doorlock_kemayoran_003', 'unlock_timer', 
 '{"action": "unlock", "duration_minutes": 10}', 
 'failed', '2025-07-28 12:00:00+07', '2025-07-28 12:00:20+07', NULL),

-- Sent but not acknowledged yet
('cmd_sent_001', 'doorlock_test_001', 'rfid_control', 
 '{"action": "disable"}', 
 'sent', '2025-07-28 15:00:00+07', '2025-07-28 15:00:10+07', NULL);

-- =================================
-- SAMPLE FIRMWARE DEPLOYMENT
-- =================================

INSERT INTO firmware_deployments (
    deployment_id, firmware_version, target_devices, batch_size, batch_delay_minutes,
    deployment_status, total_devices, successful_devices, failed_devices,
    created_by, created_at
) VALUES

-- Completed deployment
('550e8400-e29b-41d4-a716-446655440001', 'v2.1.0', 
 '{"doorlock_otista_001", "doorlock_otista_002", "doorlock_kemayoran_001"}', 
 2, 2, 'completed', 3, 3, 0, 'admin', '2025-07-25 10:00:00+07'),

-- Failed deployment (high failure rate)
('550e8400-e29b-41d4-a716-446655440002', 'v2.2.0', 
 '{"doorlock_kemayoran_002", "doorlock_kemayoran_003"}', 
 2, 2, 'failed', 2, 0, 2, 'admin', '2025-07-27 14:00:00+07');

-- =================================
-- SAMPLE DEVICE REBOOTS
-- =================================

INSERT INTO device_reboots (device_id, reboot_reason, uptime_before_reboot, battery_percentage, free_heap, wifi_rssi, reboot_timestamp) VALUES

-- Normal reboots
('doorlock_otista_002', 'power', 172800, 90, 27850, -52, '2025-07-26 03:00:00+07'),
('doorlock_otista_003', 'ota', 259200, 82, 26420, -48, '2025-07-25 15:30:00+07'),
('doorlock_kemayoran_002', 'manual', 86400, 70, 25600, -58, '2025-07-27 09:00:00+07'),

-- Problematic reboots (watchdog)
('doorlock_kemayoran_003', 'watchdog', 21600, 18, 22100, -78, '2025-07-27 08:15:00+07'),
('doorlock_kemayoran_003', 'watchdog', 18000, 17, 21800, -80, '2025-07-27 13:30:00+07'),
('doorlock_kemayoran_003', 'watchdog', 14400, 16, 21500, -82, '2025-07-27 18:45:00+07'),
('doorlock_kemayoran_003', 'watchdog', 12600, 15, 21200, -78, '2025-07-28 02:20:00+07'),
('doorlock_kemayoran_003', 'watchdog', 10800, 15, 22100, -78, '2025-07-28 05:30:00+07');

-- =================================
-- SAMPLE API USAGE
-- =================================

INSERT INTO api_usage (device_id, endpoint, method, status_code, response_time_ms, timestamp) VALUES

-- Normal API usage
('doorlock_otista_001', '/api/doorlock/bulk-upload', 'POST', 200, 145, '2025-07-28 08:00:30+07'),
('doorlock_otista_001', '/api/doorlock/command-ack', 'POST', 200, 89, '2025-07-28 08:01:15+07'),
('doorlock_otista_002', '/api/doorlock/bulk-upload', 'POST', 200, 167, '2025-07-28 08:00:45+07'),
('doorlock_kemayoran_001', '/api/doorlock/bulk-upload', 'POST', 200, 134, '2025-07-28 08:01:00+07'),

-- API errors (for monitoring)
('doorlock_kemayoran_003', '/api/doorlock/bulk-upload', 'POST', 500, 2500, '2025-07-28 08:02:30+07'),
('doorlock_test_001', '/api/doorlock/commands/doorlock_test_001', 'GET', 404, 45, '2025-07-28 10:15:00+07'),

-- Dashboard API usage (no device_id)
(NULL, '/api/doorlock/status', 'GET', 200, 234, '2025-07-28 09:30:00+07'),
(NULL, '/api/doorlock/logs/doorlock_otista_001', 'GET', 200, 156, '2025-07-28 09:30:15+07'),
(NULL, '/api/doorlock/command/unlock-timer', 'POST', 200, 78, '2025-07-28 09:45:00+07');

-- =================================
-- UPDATE DEVICE LAST_SEEN TIMESTAMPS
-- =================================

-- Update last_seen for active devices
UPDATE devices SET last_seen = CURRENT_TIMESTAMP 
WHERE device_id IN ('doorlock_otista_001', 'doorlock_otista_002', 'doorlock_otista_003', 
                    'doorlock_kemayoran_001', 'doorlock_kemayoran_002',
                    'doorlock_test_001', 'doorlock_test_002');

-- Set older last_seen for problematic device
UPDATE devices SET last_seen = CURRENT_TIMESTAMP - interval '12 hours'
WHERE device_id = 'doorlock_kemayoran_003';

-- =================================
-- CREATE SAMPLE DASHBOARD VIEWS
-- =================================

-- Dashboard overview view
CREATE VIEW dashboard_overview AS
SELECT 
    d.device_id,
    d.device_name,
    d.location,
    ds.door_status,
    ds.rfid_enabled,
    ds.battery_percentage,
    ds.last_sync,
    CASE 
        WHEN ds.last_sync >= CURRENT_TIMESTAMP - interval '2 hours' THEN 'online'
        WHEN ds.last_sync >= CURRENT_TIMESTAMP - interval '12 hours' THEN 'warning'
        ELSE 'offline'
    END as connection_status,
    df.current_version as firmware_version,
    df.available_version as firmware_update_available,
    df.ota_status,
    d.total_reboots,
    ds.total_access_count
FROM devices d
LEFT JOIN device_status ds ON d.device_id = ds.device_id
LEFT JOIN device_firmware df ON d.device_id = df.device_id
WHERE d.is_active = true
ORDER BY d.location, d.device_id;

-- Fleet health summary
CREATE VIEW fleet_health_summary AS
SELECT 
    location,
    COUNT(*) as total_devices,
    SUM(CASE WHEN connection_status = 'online' THEN 1 ELSE 0 END) as online_devices,
    SUM(CASE WHEN connection_status = 'warning' THEN 1 ELSE 0 END) as warning_devices,
    SUM(CASE WHEN connection_status = 'offline' THEN 1 ELSE 0 END) as offline_devices,
    AVG(battery_percentage) as avg_battery_percentage,
    MIN(battery_percentage) as min_battery_percentage,
    SUM(CASE WHEN battery_percentage < 20 THEN 1 ELSE 0 END) as low_battery_devices,
    SUM(total_access_count) as total_access_count
FROM dashboard_overview
GROUP BY location
ORDER BY location;

-- Recent activity summary
CREATE VIEW recent_activity_summary AS
SELECT 
    al.device_id,
    d.device_name,
    d.location,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN al.access_granted THEN 1 ELSE 0 END) as successful_attempts,
    SUM(CASE WHEN NOT al.access_granted THEN 1 ELSE 0 END) as failed_attempts,
    COUNT(DISTINCT al.card_uid) as unique_cards,
    MAX(al.timestamp) as last_activity
FROM access_logs al
JOIN devices d ON al.device_id = d.device_id
WHERE al.timestamp >= CURRENT_TIMESTAMP - interval '24 hours'
GROUP BY al.device_id, d.device_name, d.location
ORDER BY last_activity DESC;

-- OTA deployment status
CREATE VIEW ota_status_summary AS
SELECT 
    df.ota_status,
    COUNT(*) as device_count,
    AVG(df.ota_progress) as avg_progress,
    COUNT(CASE WHEN df.ota_retry_count > 0 THEN 1 END) as devices_with_retries
FROM device_firmware df
JOIN devices d ON df.device_id = d.device_id
WHERE d.is_active = true
GROUP BY df.ota_status
ORDER BY 
    CASE df.ota_status 
        WHEN 'downloading' THEN 1
        WHEN 'flashing' THEN 2
        WHEN 'failed' THEN 3
        WHEN 'idle' THEN 4
        ELSE 5
    END;

-- System alerts view
CREATE VIEW system_alerts AS
SELECT 
    'low_battery' as alert_type,
    'Device ' || ds.device_id || ' has low battery (' || ds.battery_percentage || '%)' as message,
    'warning' as severity,
    ds.device_id,
    ds.last_sync as alert_time
FROM device_status ds
JOIN devices d ON ds.device_id = d.device_id
WHERE d.is_active = true AND ds.battery_percentage < 20

UNION ALL

SELECT 
    'device_offline' as alert_type,
    'Device ' || d.device_id || ' is offline (last seen: ' || 
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - COALESCE(ds.last_sync, d.last_seen)))/3600 || ' hours ago)' as message,
    'error' as severity,
    d.device_id,
    COALESCE(ds.last_sync, d.last_seen) as alert_time
FROM devices d
LEFT JOIN device_status ds ON d.device_id = ds.device_id
WHERE d.is_active = true 
    AND COALESCE(ds.last_sync, d.last_seen) < CURRENT_TIMESTAMP - interval '2 hours'

UNION ALL

SELECT 
    'ota_failed' as alert_type,
    'OTA update failed for device ' || df.device_id || ' (retry count: ' || df.ota_retry_count || ')' as message,
    'error' as severity,
    df.device_id,
    df.last_ota_attempt as alert_time
FROM device_firmware df
JOIN devices d ON df.device_id = d.device_id
WHERE d.is_active = true AND df.ota_status = 'failed'

UNION ALL

SELECT 
    'frequent_reboots' as alert_type,
    'Device ' || d.device_id || ' has frequent reboots (' || d.total_reboots || ' total)' as message,
    'warning' as severity,
    d.device_id,
    d.last_seen as alert_time
FROM devices d
WHERE d.is_active = true AND d.total_reboots >= 5

ORDER BY alert_time DESC;

-- =================================
-- PERFORMANCE TEST DATA GENERATION
-- =================================

-- Function to generate bulk test data (for load testing)
CREATE OR REPLACE FUNCTION generate_test_access_logs(
    target_device_id VARCHAR(50),
    days_back INTEGER DEFAULT 7,
    logs_per_day INTEGER DEFAULT 50
)
RETURNS TEXT AS $
DECLARE
    i INTEGER;
    j INTEGER;
    test_timestamp TIMESTAMP WITH TIME ZONE;
    card_uids TEXT[] := ARRAY['04A1B2C3D4E5F6', '04B1C2D3E4F5A6', '04C1D2E3F4A5B6', 'E004123456', '04D1E2F3A4B5C6'];
    user_names TEXT[] := ARRAY['John Doe', 'Jane Smith', 'Mike Johnson', '', 'Sarah Wilson'];
    access_granted BOOLEAN;
    card_uid TEXT;
    user_name TEXT;
    session_id TEXT;
BEGIN
    FOR i IN 0..days_back-1 LOOP
        session_id := to_char(CURRENT_DATE - i, 'YYYYMMDD') || '_0800_' || 
                     lpad((random() * 999)::INTEGER::TEXT, 3, '0');
        
        FOR j IN 1..logs_per_day LOOP
            test_timestamp := (CURRENT_DATE - i) + 
                            (random() * interval '16 hours') + 
                            interval '6 hours';
            
            card_uid := card_uids[1 + (random() * (array_length(card_uids, 1) - 1))::INTEGER];
            user_name := user_names[1 + (random() * (array_length(user_names, 1) - 1))::INTEGER];
            access_granted := CASE WHEN card_uid = 'E004123456' THEN false ELSE random() > 0.1 END;
            
            INSERT INTO access_logs (device_id, card_uid, access_granted, access_type, user_name, timestamp, session_id)
            VALUES (target_device_id, card_uid, access_granted, 'rfid', 
                   CASE WHEN user_name = '' THEN NULL ELSE user_name END, 
                   test_timestamp, session_id);
        END LOOP;
    END LOOP;
    
    RETURN format('Generated %s access logs for device %s over %s days', 
                  days_back * logs_per_day, target_device_id, days_back);
END;
$ LANGUAGE plpgsql;

-- =================================
-- FINAL DATA VALIDATION
-- =================================

-- Verify sample data counts
DO $
DECLARE
    device_count INTEGER;
    status_count INTEGER;
    access_log_count INTEGER;
    system_log_count INTEGER;
    command_count INTEGER;
    firmware_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO device_count FROM devices;
    SELECT COUNT(*) INTO status_count FROM device_status;
    SELECT COUNT(*) INTO access_log_count FROM access_logs;
    SELECT COUNT(*) INTO system_log_count FROM system_logs;
    SELECT COUNT(*) INTO command_count FROM remote_commands;
    SELECT COUNT(*) INTO firmware_count FROM device_firmware;
    
    RAISE NOTICE 'Sample data validation:';
    RAISE NOTICE '- Devices: %', device_count;
    RAISE NOTICE '- Device Status: %', status_count;
    RAISE NOTICE '- Access Logs: %', access_log_count;
    RAISE NOTICE '- System Logs: %', system_log_count;
    RAISE NOTICE '- Commands: %', command_count;
    RAISE NOTICE '- Firmware Records: %', firmware_count;
    
    IF device_count >= 8 AND status_count >= 8 AND access_log_count >= 20 THEN
        RAISE NOTICE '✅ Sample data created successfully!';
    ELSE
        RAISE WARNING '⚠️ Sample data may be incomplete';
    END IF;
END;
$;

-- Update table statistics after inserting sample data
ANALYZE devices;
ANALYZE device_status;
ANALYZE access_logs;
ANALYZE system_logs;
ANALYZE remote_commands;
ANALYZE device_firmware;
ANALYZE firmware_deployments;
ANALYZE device_reboots;
ANALYZE api_usage;

-- Log sample data creation
INSERT INTO partition_maintenance_log (operation, result)
VALUES ('sample_data_creation', 'Created comprehensive sample data for development and testing');

-- =================================
-- COMMENTS
-- =================================

COMMENT ON VIEW dashboard_overview IS 'Complete device overview for dashboard display';
COMMENT ON VIEW fleet_health_summary IS 'Aggregated health metrics by location';
COMMENT ON VIEW recent_activity_summary IS 'Recent access activity summary for monitoring';
COMMENT ON VIEW ota_status_summary IS 'OTA deployment status across all devices';
COMMENT ON VIEW system_alerts IS 'System-wide alerts and warnings for dashboard notifications';
COMMENT ON FUNCTION generate_test_access_logs(VARCHAR, INTEGER, INTEGER) IS 'Generate bulk test access logs for performance testing';
