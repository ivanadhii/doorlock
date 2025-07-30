-- =================================
-- PERFORMANCE INDEXES FOR DOORLOCK SYSTEM
-- Optimized for 100+ devices, frequent reads, batch inserts
-- =================================

-- =================================
-- DEVICES TABLE INDEXES
-- =================================

-- Primary key index (automatically created)
-- device_id already has PRIMARY KEY index

-- Location-based queries (for fleet management by location)
CREATE INDEX idx_devices_location ON devices(location) WHERE is_active = true;

-- Active devices lookup (frequent dashboard queries)
CREATE INDEX idx_devices_active ON devices(is_active, last_seen DESC) WHERE is_active = true;

-- Reboot monitoring (stability tracking)
CREATE INDEX idx_devices_reboots ON devices(total_reboots DESC, last_seen DESC) WHERE total_reboots > 0;

-- =================================
-- DEVICE STATUS TABLE INDEXES  
-- =================================

-- Primary key index (automatically created)
-- device_id already has PRIMARY KEY index

-- Dashboard queries - battery monitoring
CREATE INDEX idx_device_status_battery ON device_status(battery_percentage ASC, last_sync DESC) 
    WHERE battery_percentage IS NOT NULL;

-- Low battery alerts (< 20%)
CREATE INDEX idx_device_status_low_battery ON device_status(device_id, battery_percentage, last_sync) 
    WHERE battery_percentage < 20;

-- Online/offline status (sync age monitoring)
CREATE INDEX idx_device_status_sync ON device_status(last_sync DESC, device_id);

-- Door status monitoring
CREATE INDEX idx_device_status_door ON device_status(door_status, last_sync DESC);

-- RFID status tracking
CREATE INDEX idx_device_status_rfid ON device_status(rfid_enabled, device_id) WHERE rfid_enabled = false;

-- Spam detection monitoring
CREATE INDEX idx_device_status_spam ON device_status(spam_detected, total_access_count DESC) 
    WHERE spam_detected = true;

-- Location-based status queries
CREATE INDEX idx_device_status_location ON device_status(location, last_sync DESC);

-- Session tracking (for duplicate detection)
CREATE INDEX idx_device_status_session ON device_status(session_id, last_sync DESC) 
    WHERE session_id IS NOT NULL;

-- =================================
-- ACCESS LOGS TABLE INDEXES (Applied to all partitions)
-- =================================

-- Device-based access history (most common query)
CREATE INDEX idx_access_logs_device_time ON access_logs(device_id, timestamp DESC);

-- Card UID lookup (user activity tracking)
CREATE INDEX idx_access_logs_card ON access_logs(card_uid, timestamp DESC) WHERE card_uid IS NOT NULL;

-- Access granted/denied analysis
CREATE INDEX idx_access_logs_granted ON access_logs(access_granted, timestamp DESC, device_id);

-- User name lookup (if available)
CREATE INDEX idx_access_logs_user ON access_logs(user_name, timestamp DESC) 
    WHERE user_name IS NOT NULL AND user_name != '';

-- Session-based queries (bulk upload correlation)
CREATE INDEX idx_access_logs_session ON access_logs(session_id, device_id) WHERE session_id IS NOT NULL;

-- Access type analysis (RFID vs manual)
CREATE INDEX idx_access_logs_type ON access_logs(access_type, timestamp DESC);

-- Recent access logs (dashboard queries - last 24 hours)
CREATE INDEX idx_access_logs_recent ON access_logs(timestamp DESC, device_id) 
    WHERE timestamp >= CURRENT_TIMESTAMP - interval '24 hours';

-- Composite index for common dashboard query pattern
CREATE INDEX idx_access_logs_dashboard ON access_logs(device_id, access_granted, timestamp DESC);

-- =================================
-- SYSTEM LOGS TABLE INDEXES (Applied to all partitions)
-- =================================

-- Device-based log queries (troubleshooting)
CREATE INDEX idx_system_logs_device_time ON system_logs(device_id, timestamp DESC);

-- Log level filtering (error monitoring)
CREATE INDEX idx_system_logs_level ON system_logs(log_level, timestamp DESC, device_id);

-- Error log monitoring
CREATE INDEX idx_system_logs_errors ON system_logs(device_id, timestamp DESC) 
    WHERE log_level IN ('ERROR', 'FATAL');

-- Recent logs for dashboard (last 24 hours)
CREATE INDEX idx_system_logs_recent ON system_logs(timestamp DESC, device_id, log_level) 
    WHERE timestamp >= CURRENT_TIMESTAMP - interval '24 hours';

-- JSONB details search (for advanced troubleshooting)
CREATE INDEX idx_system_logs_details ON system_logs USING GIN(details) WHERE details IS NOT NULL;

-- =================================
-- REMOTE COMMANDS TABLE INDEXES
-- =================================

-- Device command queue (most frequent query)
CREATE INDEX idx_remote_commands_device_status ON remote_commands(device_id, status, created_at ASC);

-- Pending commands lookup
CREATE INDEX idx_remote_commands_pending ON remote_commands(device_id, created_at ASC) 
    WHERE status IN ('queued', 'sent');

-- Command status tracking
CREATE INDEX idx_remote_commands_status ON remote_commands(status, created_at DESC);

-- Command type analysis
CREATE INDEX idx_remote_commands_type ON remote_commands(command_type, status, created_at DESC);

-- Retry monitoring
CREATE INDEX idx_remote_commands_retry ON remote_commands(retry_count DESC, status, device_id) 
    WHERE retry_count > 0;

-- Execution time analysis
CREATE INDEX idx_remote_commands_execution ON remote_commands(sent_at, executed_at) 
    WHERE sent_at IS NOT NULL AND executed_at IS NOT NULL;

-- Failed commands monitoring
CREATE INDEX idx_remote_commands_failed ON remote_commands(device_id, created_at DESC) 
    WHERE status = 'failed';

-- =================================
-- DEVICE FIRMWARE TABLE INDEXES
-- =================================

-- OTA status monitoring (dashboard queries)
CREATE INDEX idx_device_firmware_ota_status ON device_firmware(ota_status, device_id);

-- Available updates check
CREATE INDEX idx_device_firmware_updates ON device_firmware(device_id, current_version, available_version) 
    WHERE available_version IS NOT NULL AND available_version != current_version;

-- Retry monitoring
CREATE INDEX idx_device_firmware_retry ON device_firmware(ota_retry_count DESC, ota_status) 
    WHERE ota_retry_count > 0;

-- OTA progress monitoring
CREATE INDEX idx_device_firmware_progress ON device_firmware(ota_progress, ota_status) 
    WHERE ota_status IN ('downloading', 'flashing');

-- Last OTA attempt tracking
CREATE INDEX idx_device_firmware_last_attempt ON device_firmware(last_ota_attempt DESC, ota_status);

-- Version tracking
CREATE INDEX idx_device_firmware_version ON device_firmware(current_version, last_successful_ota DESC);

-- =================================
-- FIRMWARE DEPLOYMENTS TABLE INDEXES
-- =================================

-- Deployment status monitoring
CREATE INDEX idx_firmware_deployments_status ON firmware_deployments(deployment_status, created_at DESC);

-- Active deployments
CREATE INDEX idx_firmware_deployments_active ON firmware_deployments(deployment_status, started_at DESC) 
    WHERE deployment_status IN ('pending', 'running');

-- Version-based deployment history
CREATE INDEX idx_firmware_deployments_version ON firmware_deployments(firmware_version, deployment_status, created_at DESC);

-- Progress monitoring
CREATE INDEX idx_firmware_deployments_progress ON firmware_deployments(
    deployment_status, 
    (successful_devices::float / NULLIF(total_devices, 0)) DESC
) WHERE total_devices > 0;

-- =================================
-- DEVICE REBOOTS TABLE INDEXES
-- =================================

-- Device reboot history
CREATE INDEX idx_device_reboots_device_time ON device_reboots(device_id, reboot_timestamp DESC);

-- Reboot reason analysis
CREATE INDEX idx_device_reboots_reason ON device_reboots(reboot_reason, reboot_timestamp DESC);

-- Recent reboots monitoring (last 24 hours)
CREATE INDEX idx_device_reboots_recent ON device_reboots(reboot_timestamp DESC, device_id, reboot_reason) 
    WHERE reboot_timestamp >= CURRENT_TIMESTAMP - interval '24 hours';

-- Watchdog reboot monitoring
CREATE INDEX idx_device_reboots_watchdog ON device_reboots(device_id, reboot_timestamp DESC) 
    WHERE reboot_reason = 'watchdog';

-- Uptime analysis
CREATE INDEX idx_device_reboots_uptime ON device_reboots(uptime_before_reboot DESC, device_id);

-- =================================
-- API USAGE TABLE INDEXES
-- =================================

-- Device API usage monitoring
CREATE INDEX idx_api_usage_device_time ON api_usage(device_id, timestamp DESC) WHERE device_id IS NOT NULL;

-- Endpoint performance monitoring
CREATE INDEX idx_api_usage_endpoint ON api_usage(endpoint, response_time_ms DESC, timestamp DESC);

-- Error rate monitoring
CREATE INDEX idx_api_usage_errors ON api_usage(status_code, endpoint, timestamp DESC) 
    WHERE status_code >= 400;

-- Response time analysis
CREATE INDEX idx_api_usage_performance ON api_usage(endpoint, response_time_ms ASC, timestamp DESC);

-- Recent API usage (last hour for rate limiting)
CREATE INDEX idx_api_usage_recent ON api_usage(device_id, timestamp DESC) 
    WHERE timestamp >= CURRENT_TIMESTAMP - interval '1 hour';

-- =================================
-- COMPOSITE INDEXES FOR COMPLEX QUERIES
-- =================================

-- Dashboard overview query (device status + last access)
CREATE INDEX idx_dashboard_overview ON device_status(
    is_active, 
    last_sync DESC, 
    battery_percentage ASC, 
    door_status
) WHERE is_active = true;

-- Fleet health monitoring (battery + connectivity)
CREATE INDEX idx_fleet_health ON device_status(
    battery_percentage ASC, 
    last_sync DESC, 
    wifi_rssi DESC
) WHERE battery_percentage IS NOT NULL;

-- Security monitoring (access patterns)
CREATE INDEX idx_security_monitoring ON access_logs(
    device_id, 
    access_granted, 
    timestamp DESC, 
    card_uid
) WHERE timestamp >= CURRENT_TIMESTAMP - interval '7 days';

-- OTA deployment monitoring
CREATE INDEX idx_ota_monitoring ON device_firmware(
    ota_status, 
    last_ota_attempt DESC, 
    ota_retry_count ASC
) WHERE ota_status != 'idle';

-- =================================
-- PARTIAL INDEXES FOR EFFICIENCY
-- =================================

-- Only index active devices for most queries
CREATE INDEX idx_active_devices_only ON devices(device_id, location, last_seen DESC) 
    WHERE is_active = true;

-- Only index non-successful commands (errors need attention)
CREATE INDEX idx_failed_commands_only ON remote_commands(device_id, created_at DESC, retry_count) 
    WHERE status IN ('failed', 'timeout');

-- Only index devices with available firmware updates
CREATE INDEX idx_firmware_updates_available ON device_firmware(device_id, available_version) 
    WHERE available_version IS NOT NULL 
    AND available_version != current_version 
    AND ota_status = 'idle';

-- Only index recent access logs for dashboard performance
CREATE INDEX idx_recent_access_only ON access_logs(device_id, timestamp DESC, access_granted) 
    WHERE timestamp >= CURRENT_TIMESTAMP - interval '30 days';

-- =================================
-- STATISTICS AND MAINTENANCE
-- =================================

-- Update table statistics for better query planning
ANALYZE devices;
ANALYZE device_status;
ANALYZE access_logs;
ANALYZE system_logs;
ANALYZE remote_commands;
ANALYZE device_firmware;
ANALYZE firmware_deployments;
ANALYZE device_reboots;
ANALYZE api_usage;

-- =================================
-- INDEX MONITORING VIEWS
-- =================================

-- View to monitor index usage and effectiveness
CREATE VIEW index_usage_stats AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as times_used,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes 
ORDER BY idx_scan DESC;

-- View to identify unused indexes
CREATE VIEW unused_indexes AS
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes 
WHERE idx_scan = 0
AND indexname NOT LIKE '%_pkey'  -- Exclude primary keys
ORDER BY pg_relation_size(indexrelid) DESC;

-- View to monitor slow queries that might need indexes
CREATE VIEW slow_queries AS
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    max_time,
    rows
FROM pg_stat_statements 
WHERE mean_time > 100  -- Queries slower than 100ms
ORDER BY mean_time DESC
LIMIT 20;

-- =================================
-- COMMENTS
-- =================================

COMMENT ON VIEW index_usage_stats IS 'Monitor index usage and effectiveness';
COMMENT ON VIEW unused_indexes IS 'Identify potentially unused indexes for cleanup';
COMMENT ON VIEW slow_queries IS 'Monitor slow queries that might need optimization';

-- Log index creation completion
INSERT INTO partition_maintenance_log (operation, result)
VALUES ('index_creation', 'Created all performance indexes for doorlock system tables');
