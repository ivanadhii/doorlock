-- =================================
-- DEVICE ROOM RESIDENTS TABLE
-- Room-based resident management with laundry/parkir packages
-- =================================

-- =================================
-- RESIDENTS TABLE
-- =================================

CREATE TABLE device_room_residents (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    card_uid VARCHAR(50) NOT NULL,
    resident_name VARCHAR(100) NOT NULL,
    has_laundry_package BOOLEAN DEFAULT false,
    has_parkir_package BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT unique_device_card UNIQUE(device_id, card_uid),
    CONSTRAINT chk_resident_name_not_empty CHECK (LENGTH(TRIM(resident_name)) > 0)
);

-- =================================
-- INDEXES FOR PERFORMANCE
-- =================================

-- Query residents by device (most common query)
CREATE INDEX idx_device_room_residents_device ON device_room_residents(device_id) WHERE is_active = true;

-- Query by card UID (for cross-device lookup)
CREATE INDEX idx_device_room_residents_card ON device_room_residents(card_uid) WHERE is_active = true;

-- Query active residents only
CREATE INDEX idx_device_room_residents_active ON device_room_residents(is_active, device_id);

-- Query residents with packages (for reporting)
CREATE INDEX idx_device_room_residents_laundry ON device_room_residents(has_laundry_package) WHERE has_laundry_package = true;
CREATE INDEX idx_device_room_residents_parkir ON device_room_residents(has_parkir_package) WHERE has_parkir_package = true;

-- =================================
-- TRIGGER FOR AUTO UPDATE TIMESTAMP
-- =================================

CREATE TRIGGER update_device_room_residents_updated_at 
    BEFORE UPDATE ON device_room_residents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =================================
-- USEFUL VIEWS FOR DASHBOARD
-- =================================

-- View: Room residents with device info
CREATE VIEW room_residents_view AS
SELECT 
    drr.id,
    drr.device_id,
    d.device_name,
    d.location,
    drr.card_uid,
    drr.resident_name,
    drr.has_laundry_package,
    drr.has_parkir_package,
    drr.is_active,
    drr.created_at,
    drr.updated_at
FROM device_room_residents drr
JOIN devices d ON drr.device_id = d.device_id
WHERE drr.is_active = true
ORDER BY d.location, d.device_id, drr.resident_name;

-- View: Resident package summary
CREATE VIEW resident_package_summary AS
SELECT 
    d.location,
    COUNT(*) as total_residents,
    SUM(CASE WHEN drr.has_laundry_package THEN 1 ELSE 0 END) as residents_with_laundry,
    SUM(CASE WHEN drr.has_parkir_package THEN 1 ELSE 0 END) as residents_with_parkir,
    SUM(CASE WHEN drr.has_laundry_package AND drr.has_parkir_package THEN 1 ELSE 0 END) as residents_with_both_packages
FROM device_room_residents drr
JOIN devices d ON drr.device_id = d.device_id
WHERE drr.is_active = true AND d.is_active = true
GROUP BY d.location
ORDER BY d.location;

-- View: Card access across devices (for multi-room access tracking)
CREATE VIEW card_multi_access AS
SELECT 
    drr.card_uid,
    drr.resident_name,
    COUNT(DISTINCT drr.device_id) as accessible_rooms,
    ARRAY_AGG(DISTINCT d.location ORDER BY d.location) as locations,
    ARRAY_AGG(DISTINCT d.device_name ORDER BY d.device_name) as room_names
FROM device_room_residents drr
JOIN devices d ON drr.device_id = d.device_id
WHERE drr.is_active = true AND d.is_active = true
GROUP BY drr.card_uid, drr.resident_name
HAVING COUNT(DISTINCT drr.device_id) > 1
ORDER BY drr.resident_name;

-- =================================
-- ENHANCED ACCESS LOGS VIEW WITH RESIDENT INFO
-- =================================

-- Update existing dashboard view to include resident info
CREATE OR REPLACE VIEW enhanced_access_logs AS
SELECT 
    al.id,
    al.device_id,
    d.device_name,
    d.location,
    al.card_uid,
    al.access_granted,
    al.access_type,
    al.timestamp,
    al.session_id,
    -- Resident info (NULL if card not registered)
    drr.resident_name,
    drr.has_laundry_package,
    drr.has_parkir_package,
    -- Indicators
    CASE 
        WHEN drr.resident_name IS NOT NULL THEN 'registered'
        ELSE 'unknown'
    END as card_status,
    CASE 
        WHEN al.access_granted THEN '✅'
        ELSE '❌'
    END as access_icon
FROM access_logs al
JOIN devices d ON al.device_id = d.device_id
LEFT JOIN device_room_residents drr ON (
    al.device_id = drr.device_id AND 
    al.card_uid = drr.card_uid AND 
    drr.is_active = true
)
ORDER BY al.timestamp DESC;

-- =================================
-- FUNCTIONS FOR RESIDENT MANAGEMENT
-- =================================

-- Function to register new resident
CREATE OR REPLACE FUNCTION register_resident(
    p_device_id VARCHAR(50),
    p_card_uid VARCHAR(50),
    p_resident_name VARCHAR(100),
    p_has_laundry BOOLEAN DEFAULT false,
    p_has_parkir BOOLEAN DEFAULT false
)
RETURNS TEXT AS $$
DECLARE
    result_msg TEXT;
BEGIN
    -- Check if device exists
    IF NOT EXISTS (SELECT 1 FROM devices WHERE device_id = p_device_id AND is_active = true) THEN
        RETURN 'ERROR: Device not found or inactive';
    END IF;
    
    -- Insert or update resident
    INSERT INTO device_room_residents (
        device_id, card_uid, resident_name, 
        has_laundry_package, has_parkir_package
    ) VALUES (
        p_device_id, p_card_uid, p_resident_name,
        p_has_laundry, p_has_parkir
    )
    ON CONFLICT (device_id, card_uid) 
    DO UPDATE SET
        resident_name = EXCLUDED.resident_name,
        has_laundry_package = EXCLUDED.has_laundry_package,
        has_parkir_package = EXCLUDED.has_parkir_package,
        is_active = true,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN format('SUCCESS: Resident %s registered for device %s', p_resident_name, p_device_id);
END;
$$ LANGUAGE plpgsql;

-- Function to toggle package status
CREATE OR REPLACE FUNCTION toggle_resident_package(
    p_device_id VARCHAR(50),
    p_card_uid VARCHAR(50),
    p_package_type VARCHAR(10), -- 'laundry' or 'parkir'
    p_status BOOLEAN
)
RETURNS TEXT AS $$
DECLARE
    affected_rows INTEGER;
    resident_name TEXT;
BEGIN
    -- Validate package type
    IF p_package_type NOT IN ('laundry', 'parkir') THEN
        RETURN 'ERROR: Package type must be laundry or parkir';
    END IF;
    
    -- Update package status
    IF p_package_type = 'laundry' THEN
        UPDATE device_room_residents 
        SET has_laundry_package = p_status, updated_at = CURRENT_TIMESTAMP
        WHERE device_id = p_device_id AND card_uid = p_card_uid AND is_active = true;
    ELSE
        UPDATE device_room_residents 
        SET has_parkir_package = p_status, updated_at = CURRENT_TIMESTAMP
        WHERE device_id = p_device_id AND card_uid = p_card_uid AND is_active = true;
    END IF;
    
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    
    IF affected_rows = 0 THEN
        RETURN 'ERROR: Resident not found';
    END IF;
    
    -- Get resident name for confirmation
    SELECT resident_name INTO resident_name 
    FROM device_room_residents 
    WHERE device_id = p_device_id AND card_uid = p_card_uid;
    
    RETURN format('SUCCESS: %s package %s for %s', 
                  INITCAP(p_package_type), 
                  CASE WHEN p_status THEN 'enabled' ELSE 'disabled' END,
                  resident_name);
END;
$$ LANGUAGE plpgsql;

-- =================================
-- NO SAMPLE DATA
-- Residents will be added through admin interface or API calls
-- =================================

-- Table is ready for production use

-- =================================
-- DATA VALIDATION
-- =================================

DO $$
DECLARE
    table_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'device_room_residents'
    ) INTO table_exists;
    
    RAISE NOTICE 'Resident table validation:';
    RAISE NOTICE '- Table created: %', table_exists;
    RAISE NOTICE '- Ready for production data';
    
    IF table_exists THEN
        RAISE NOTICE '✅ Resident table ready for use!';
    ELSE
        RAISE WARNING '⚠️ Table creation may have failed';
    END IF;
END;
$$;

-- Update table statistics
ANALYZE device_room_residents;

-- Log resident table creation
INSERT INTO partition_maintenance_log (operation, result)
VALUES ('resident_table_creation', 'Created device_room_residents table with views and functions');

-- =================================
-- COMMENTS
-- =================================

COMMENT ON TABLE device_room_residents IS 'Room-based resident management with package tracking';
COMMENT ON COLUMN device_room_residents.device_id IS 'References the room/doorlock device';
COMMENT ON COLUMN device_room_residents.card_uid IS 'RFID card unique identifier';
COMMENT ON COLUMN device_room_residents.resident_name IS 'Name of the room resident';
COMMENT ON COLUMN device_room_residents.has_laundry_package IS 'Whether resident has laundry service package';
COMMENT ON COLUMN device_room_residents.has_parkir_package IS 'Whether resident has parking package';

COMMENT ON VIEW room_residents_view IS 'Complete resident information with device details';
COMMENT ON VIEW resident_package_summary IS 'Package statistics by location';
COMMENT ON VIEW card_multi_access IS 'Cards with access to multiple rooms';
COMMENT ON VIEW enhanced_access_logs IS 'Access logs enriched with resident information';

COMMENT ON FUNCTION register_resident(VARCHAR, VARCHAR, VARCHAR, BOOLEAN, BOOLEAN) IS 'Register new resident to device/room';
COMMENT ON FUNCTION toggle_resident_package(VARCHAR, VARCHAR, VARCHAR, BOOLEAN) IS 'Toggle laundry/parkir package for resident';