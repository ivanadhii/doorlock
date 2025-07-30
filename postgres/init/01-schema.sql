-- =================================
-- DOORLOCK IoT SYSTEM - DATABASE SCHEMA
-- PostgreSQL 15 with Partitioning Strategy
-- =================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Set timezone
SET timezone = 'Asia/Jakarta';

-- =================================
-- CORE TABLES
-- =================================

-- Device management table
CREATE TABLE devices (
    device_id VARCHAR(50) PRIMARY KEY,
    device_name VARCHAR(100),
    location VARCHAR(50) NOT NULL,
    api_key_hash VARCHAR(255), -- For future individual device auth
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Metadata
    hardware_version VARCHAR(20),
    last_seen TIMESTAMP WITH TIME ZONE,
    total_reboots INTEGER DEFAULT 0,
    
    -- Constraints
    CONSTRAINT chk_device_id_format CHECK (device_id ~ '^doorlock_[a-z]+_[0-9]+$'),
    CONSTRAINT chk_location_valid CHECK (location IN ('otista', 'kemayoran'))
);

-- Current device status (latest sync data)
CREATE TABLE device_status (
    device_id VARCHAR(50) PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
    
    -- Door & RFID status
    door_status VARCHAR(20) NOT NULL DEFAULT 'locked',
    rfid_enabled BOOLEAN DEFAULT true,
    
    -- System metrics
    battery_percentage INTEGER CHECK (battery_percentage >= 0 AND battery_percentage <= 100),
    uptime_seconds BIGINT DEFAULT 0,
    wifi_rssi INTEGER,
    free_heap INTEGER,
    
    -- Sync information
    last_sync TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    session_id VARCHAR(50),
    location VARCHAR(50),
    
    -- Security & monitoring
    spam_detected BOOLEAN DEFAULT false,
    total_access_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_door_status CHECK (door_status IN ('locked', 'unlocked', 'locking', 'unlocking')),
    CONSTRAINT chk_wifi_rssi CHECK (wifi_rssi BETWEEN -100 AND 0)
);

-- Access logs with monthly partitioning
CREATE TABLE access_logs (
    id BIGSERIAL,
    device_id VARCHAR(50) NOT NULL,
    
    -- Access information
    card_uid VARCHAR(50),
    access_granted BOOLEAN,
    access_type VARCHAR(20) DEFAULT 'rfid',
    user_name VARCHAR(100),
    
    -- Timing
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    session_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexing hint for partitioning
    PRIMARY KEY (id, timestamp),
    
    -- Foreign key (note: partitioned tables have limitations)
    CONSTRAINT fk_access_logs_device FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT chk_access_type CHECK (access_type IN ('rfid', 'manual', 'emergency'))
) PARTITION BY RANGE (timestamp);

-- System logs with hash partitioning by device_id  
CREATE TABLE system_logs (
    id BIGSERIAL,
    device_id VARCHAR(50) NOT NULL,
    
    -- Log information
    log_level VARCHAR(10) NOT NULL DEFAULT 'INFO',
    message TEXT,
    details JSONB,
    
    -- Timing
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Partitioning key in primary key
    PRIMARY KEY (id, device_id),
    
    -- Constraints
    CONSTRAINT chk_log_level CHECK (log_level IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'))
) PARTITION BY HASH (device_id);

-- =================================
-- COMMAND MANAGEMENT TABLES
-- =================================

-- Remote commands for devices
CREATE TABLE remote_commands (
    command_id VARCHAR(50) PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    
    -- Command details
    command_type VARCHAR(50) NOT NULL,
    command_payload JSONB NOT NULL,
    
    -- Status tracking
    status VARCHAR(20) DEFAULT 'queued',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE,
    executed_at TIMESTAMP WITH TIME ZONE,
    ack_received_at TIMESTAMP WITH TIME ZONE,
    
    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Constraints
    CONSTRAINT chk_command_status CHECK (status IN ('queued', 'sent', 'success', 'failed', 'timeout')),
    CONSTRAINT chk_command_type CHECK (command_type IN ('rfid_control', 'unlock_timer')),
    CONSTRAINT chk_retry_count CHECK (retry_count >= 0 AND retry_count <= 5)
);

-- =================================
-- FIRMWARE MANAGEMENT TABLES
-- =================================

-- Device firmware tracking
CREATE TABLE device_firmware (
    device_id VARCHAR(50) PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
    
    -- Version information
    current_version VARCHAR(20) NOT NULL DEFAULT 'v1.0.0',
    available_version VARCHAR(20),
    last_known_good_version VARCHAR(20),
    
    -- OTA status
    ota_status VARCHAR(20) DEFAULT 'idle',
    ota_retry_count INTEGER DEFAULT 0,
    ota_progress INTEGER DEFAULT 0, -- 0-100%
    
    -- File information
    firmware_file_path VARCHAR(255),
    firmware_size_bytes INTEGER,
    firmware_checksum VARCHAR(64),
    
    -- Timing
    last_ota_attempt TIMESTAMP WITH TIME ZONE,
    last_successful_ota TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_ota_status CHECK (ota_status IN ('idle', 'pending', 'downloading', 'flashing', 'success', 'failed', 'rollback')),
    CONSTRAINT chk_ota_retry_count CHECK (ota_retry_count >= 0 AND ota_retry_count <= 5),
    CONSTRAINT chk_ota_progress CHECK (ota_progress >= 0 AND ota_progress <= 100),
    CONSTRAINT chk_version_format CHECK (current_version ~ '^v[0-9]+\.[0-9]+\.[0-9]+$')
);

-- Firmware deployment tracking (for rolling updates)
CREATE TABLE firmware_deployments (
    deployment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Deployment information
    firmware_version VARCHAR(20) NOT NULL,
    target_devices TEXT[], -- Array of device_ids
    
    -- Batch configuration
    batch_size INTEGER DEFAULT 10,
    batch_delay_minutes INTEGER DEFAULT 2,
    
    -- Status tracking
    deployment_status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Progress tracking
    total_devices INTEGER,
    successful_devices INTEGER DEFAULT 0,
    failed_devices INTEGER DEFAULT 0,
    
    -- Error handling
    failure_threshold_percent DECIMAL(5,2) DEFAULT 20.0,
    auto_rollback BOOLEAN DEFAULT true,
    
    -- Metadata
    created_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_deployment_status CHECK (deployment_status IN ('pending', 'running', 'completed', 'failed', 'stopped')),
    CONSTRAINT chk_batch_size CHECK (batch_size > 0 AND batch_size <= 50),
    CONSTRAINT chk_failure_threshold CHECK (failure_threshold_percent >= 0 AND failure_threshold_percent <= 100)
);

-- =================================
-- AUDIT & MONITORING TABLES
-- =================================

-- Device reboot tracking
CREATE TABLE device_reboots (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    
    -- Reboot information
    reboot_reason VARCHAR(50),
    uptime_before_reboot BIGINT,
    
    -- System state before reboot
    battery_percentage INTEGER,
    free_heap INTEGER,
    wifi_rssi INTEGER,
    
    -- Timing
    reboot_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_reboot_reason CHECK (reboot_reason IN ('watchdog', 'power', 'manual', 'ota', 'unknown'))
);

-- API usage tracking (for monitoring & rate limiting)
CREATE TABLE api_usage (
    id BIGSERIAL PRIMARY KEY,
    
    -- Request information
    device_id VARCHAR(50),
    endpoint VARCHAR(100) NOT NULL,
    method VARCHAR(10) NOT NULL,
    
    -- Response information
    status_code INTEGER,
    response_time_ms INTEGER,
    
    -- Timing
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_http_method CHECK (method IN ('GET', 'POST', 'PUT', 'DELETE')),
    CONSTRAINT chk_status_code CHECK (status_code >= 100 AND status_code < 600)
);

-- =================================
-- TRIGGER FUNCTIONS
-- =================================

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Device reboot counter trigger function
CREATE OR REPLACE FUNCTION increment_reboot_counter()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.uptime_seconds < OLD.uptime_seconds THEN
        UPDATE devices 
        SET total_reboots = total_reboots + 1,
            last_seen = CURRENT_TIMESTAMP
        WHERE device_id = NEW.device_id;
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- =================================
-- TRIGGERS
-- =================================

-- Update timestamp triggers
CREATE TRIGGER update_devices_updated_at BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_device_status_updated_at BEFORE UPDATE ON device_status
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_device_firmware_updated_at BEFORE UPDATE ON device_firmware
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Reboot counter trigger
CREATE TRIGGER track_device_reboots AFTER UPDATE ON device_status
    FOR EACH ROW EXECUTE FUNCTION increment_reboot_counter();

-- =================================
-- COMMENTS
-- =================================

COMMENT ON TABLE devices IS 'Core device registry with metadata';
COMMENT ON TABLE device_status IS 'Latest sync data from each device';
COMMENT ON TABLE access_logs IS 'Historical access attempts (partitioned by month)';
COMMENT ON TABLE system_logs IS 'System logs and events (partitioned by device)';
COMMENT ON TABLE remote_commands IS 'Commands sent to devices';
COMMENT ON TABLE device_firmware IS 'Firmware version tracking per device';
COMMENT ON TABLE firmware_deployments IS 'Rolling firmware deployment management';
COMMENT ON TABLE device_reboots IS 'Device reboot tracking for stability monitoring';
COMMENT ON TABLE api_usage IS 'API usage monitoring and analytics';

-- Create initial admin user for web interface (if needed)
-- This can be extended later for user management
