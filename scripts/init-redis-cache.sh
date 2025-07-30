#!/bin/bash

# =================================
# REDIS CACHE INITIALIZATION SCRIPT
# Initialize Redis with doorlock system cache data
# =================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Check if Redis is running
check_redis() {
    log "Checking Redis connection..."
    
    if docker-compose exec redis-cache redis-cli ping > /dev/null 2>&1; then
        log "Redis is running and accessible ✅"
    else
        error "Redis is not running or not accessible"
        exit 1
    fi
}

# Initialize device status cache from database
init_device_status_cache() {
    log "Initializing device status cache from database..."
    
    # Get device data from PostgreSQL and cache in Redis
    docker-compose exec postgres-db psql -U doorlock -d doorlock_system -t -c "
        SELECT 
            'HMSET doorlock:device_status:' || ds.device_id || ' ' ||
            'device_id ' || ds.device_id || ' ' ||
            'door_status ' || ds.door_status || ' ' ||
            'rfid_enabled ' || ds.rfid_enabled || ' ' ||
            'battery_percentage ' || COALESCE(ds.battery_percentage::text, '0') || ' ' ||
            'last_sync ' || EXTRACT(EPOCH FROM ds.last_sync)::text || ' ' ||
            'location ' || ds.location || ' ' ||
            'total_access_count ' || ds.total_access_count::text || ' ' ||
            '&& EXPIRE doorlock:device_status:' || ds.device_id || ' 3600'
        FROM device_status ds 
        JOIN devices d ON ds.device_id = d.device_id 
        WHERE d.is_active = true;
    " | while read -r redis_cmd; do
        if [[ -n "$redis_cmd" && "$redis_cmd" != *"rows)"* ]]; then
            # Execute Redis command
            docker-compose exec redis-cache redis-cli --raw -c "$redis_cmd" > /dev/null
        fi
    done
    
    # Count cached devices
    cached_count=$(docker-compose exec redis-cache redis-cli --raw EVAL "return #redis.call('keys', 'doorlock:device_status:*')" 0)
    log "Cached status for $cached_count devices ✅"
}

# Initialize dashboard cache
init_dashboard_cache() {
    log "Initializing dashboard cache..."
    
    # Cache fleet health summary
    docker-compose exec postgres-db psql -U doorlock -d doorlock_system -t -c "
        SELECT json_build_object(
            'total_devices', COUNT(*),
            'online_devices', SUM(CASE WHEN connection_status = 'online' THEN 1 ELSE 0 END),
            'warning_devices', SUM(CASE WHEN connection_status = 'warning' THEN 1 ELSE 0 END),
            'offline_devices', SUM(CASE WHEN connection_status = 'offline' THEN 1 ELSE 0 END),
            'avg_battery_percentage', ROUND(AVG(battery_percentage), 1),
            'low_battery_devices', SUM(CASE WHEN battery_percentage < 20 THEN 1 ELSE 0 END),
            'last_updated', EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
        )
        FROM dashboard_overview;
    " | while read -r json_data; do
        if [[ -n "$json_data" && "$json_data" != *"rows)"* ]]; then
            docker-compose exec redis-cache redis-cli SET "doorlock:dashboard:fleet_health" "$json_data" EX 300 > /dev/null
        fi
    done
    
    # Cache recent activity summary
    docker-compose exec postgres-db psql -U doorlock -d doorlock_system -t -c "
        SELECT json_agg(json_build_object(
            'device_id', device_id,
            'device_name', device_name,
            'location', location,
            'total_attempts', total_attempts,
            'successful_attempts', successful_attempts,
            'failed_attempts', failed_attempts,
            'last_activity', EXTRACT(EPOCH FROM last_activity)
        ))
        FROM recent_activity_summary;
    " | while read -r json_data; do
        if [[ -n "$json_data" && "$json_data" != "null" && "$json_data" != *"rows)"* ]]; then
            docker-compose exec redis-cache redis-cli SET "doorlock:dashboard:recent_activity" "$json_data" EX 300 > /dev/null
        fi
    done
    
    log "Dashboard cache initialized ✅"
}

# Initialize OTA progress cache
init_ota_cache() {
    log "Initializing OTA progress cache..."
    
    # Cache OTA status for devices with active OTA
    docker-compose exec postgres-db psql -U doorlock -d doorlock_system -t -c "
        SELECT 
            'HMSET doorlock:ota:progress:' || df.device_id || ' ' ||
            'device_id ' || df.device_id || ' ' ||
            'ota_status ' || df.ota_status || ' ' ||
            'current_version ' || df.current_version || ' ' ||
            'available_version ' || COALESCE(df.available_version, 'null') || ' ' ||
            'ota_progress ' || df.ota_progress::text || ' ' ||
            'retry_count ' || df.ota_retry_count::text || ' ' ||
            'last_attempt ' || COALESCE(EXTRACT(EPOCH FROM df.last_ota_attempt)::text, '0') || ' ' ||
            '&& EXPIRE doorlock:ota:progress:' || df.device_id || ' 1800'
        FROM device_firmware df 
        JOIN devices d ON df.device_id = d.device_id 
        WHERE d.is_active = true AND df.ota_status != 'idle';
    " | while read -r redis_cmd; do
        if [[ -n "$redis_cmd" && "$redis_cmd" != *"rows)"* ]]; then
            docker-compose exec redis-cache redis-cli --raw -c "$redis_cmd" > /dev/null
        fi
    done
    
    # Count cached OTA progress
    ota_count=$(docker-compose exec redis-cache redis-cli --raw EVAL "return #redis.call('keys', 'doorlock:ota:progress:*')" 0)
    log "Cached OTA progress for $ota_count devices ✅"
}

# Initialize system alerts cache
init_alerts_cache() {
    log "Initializing system alerts cache..."
    
    # Cache system alerts
    docker-compose exec postgres-db psql -U doorlock -d doorlock_system -t -c "
        SELECT json_agg(json_build_object(
            'alert_type', alert_type,
            'message', message,
            'severity', severity,
            'device_id', device_id,
            'alert_time', EXTRACT(EPOCH FROM alert_time)
        ))
        FROM system_alerts
        ORDER BY alert_time DESC;
    " | while read -r json_data; do
        if [[ -n "$json_data" && "$json_data" != "null" && "$json_data" != *"rows)"* ]]; then
            docker-compose exec redis-cache redis-cli SET "doorlock:alerts:system" "$json_data" EX 300 > /dev/null
        fi
    done
    
    log "System alerts cache initialized ✅"
}

# Set up cache warming schedule
setup_cache_warming() {
    log "Setting up cache warming keys..."
    
    # Set cache warming indicators
    current_time=$(date +%s)
    
    docker-compose exec redis-cache redis-cli SET "doorlock:cache:last_warmed" "$current_time" > /dev/null
    docker-compose exec redis-cache redis-cli SET "doorlock:cache:warming_enabled" "true" > /dev/null
    
    log "Cache warming setup completed ✅"
}

# Show cache statistics
show_cache_stats() {
    log "Cache Statistics:"
    
    echo -e "${BLUE}=== REDIS CACHE STATISTICS ===${NC}"
    
    # Memory usage
    memory_info=$(docker-compose exec redis-cache redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human")
    echo -e "${BLUE}Memory Usage:${NC}"
    echo "$memory_info" | sed 's/^/  /'
    
    # Key counts by pattern
    echo -e "\n${BLUE}Cached Keys:${NC}"
    
    patterns=(
        "doorlock:device_status:*"
        "doorlock:dashboard:*"
        "doorlock:ota:progress:*"  
        "doorlock:alerts:*"
        "doorlock:api_rate:*"
    )
    
    for pattern in "${patterns[@]}"; do
        count=$(docker-compose exec redis-cache redis-cli --raw EVAL "return #redis.call('keys', '$pattern')" 0)
        echo "  $pattern: $count keys"
    done
    
    # Total keys
    total_keys=$(docker-compose exec redis-cache redis-cli DBSIZE)
    echo -e "\n  ${GREEN}Total keys in database: $total_keys${NC}"
    
    echo -e "${BLUE}=========================${NC}"
}

# Test cache performance
test_cache_performance() {
    log "Testing cache performance..."
    
    # Test device status retrieval
    start_time=$(date +%s%N)
    device_count=$(docker-compose exec redis-cache redis-cli --raw EVAL "
        local keys = redis.call('keys', 'doorlock:device_status:*')
        local count = 0
        for i = 1, #keys do
            local data = redis.call('hgetall', keys[i])
            if #data > 0 then
                count = count + 1
            end
        end
        return count
    " 0)
    end_time=$(date +%s%N)
    
    duration_ms=$(( (end_time - start_time) / 1000000 ))
    
    log "Retrieved $device_count device statuses in ${duration_ms}ms ✅"
    
    if [[ $duration_ms -lt 100 ]]; then
        log "Cache performance: EXCELLENT (< 100ms)"
    elif [[ $duration_ms -lt 500 ]]; then
        log "Cache performance: GOOD (< 500ms)"
    else
        warn "Cache performance: SLOW (> 500ms) - consider optimization"
    fi
}

# Main initialization function
main() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "  REDIS CACHE INITIALIZATION"
    echo "========================================"
    echo -e "${NC}"
    
    check_redis
    init_device_status_cache
    init_dashboard_cache
    init_ota_cache
    init_alerts_cache
    setup_cache_warming
    
    echo ""
    show_cache_stats
    test_cache_performance
    
    echo ""
    log "🎉 Redis cache initialization completed successfully!"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Test cache with: ${GREEN}python3 scripts/test-redis.py${NC}"
    echo "2. Monitor cache: ${GREEN}docker-compose exec redis-cache redis-cli MONITOR${NC}"
    echo "3. Check cache keys: ${GREEN}docker-compose exec redis-cache redis-cli KEYS 'doorlock:*'${NC}"
}

# Run main function
main "$@"
