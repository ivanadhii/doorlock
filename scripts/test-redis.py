#!/usr/bin/env python3
"""
Redis Cache Testing Script for Doorlock System
Tests caching strategies and performance
"""

import redis
import json
import time
import sys
from datetime import datetime, timedelta

def connect_redis():
    """Connect to Redis server"""
    try:
        r = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True,
            socket_timeout=5
        )
        r.ping()
        print("✅ Connected to Redis successfully")
        return r
    except redis.ConnectionError:
        print("❌ Failed to connect to Redis")
        sys.exit(1)

def test_basic_operations(r):
    """Test basic Redis operations"""
    print("\n=== Testing Basic Operations ===")
    
    # String operations
    r.set("test:basic", "Hello Doorlock System", ex=60)
    value = r.get("test:basic")
    print(f"✅ String operation: {value}")
    
    # Hash operations (for device status)
    device_data = {
        "device_id": "doorlock_test_001",
        "door_status": "locked",
        "battery_percentage": "95",
        "last_sync": datetime.now().isoformat()
    }
    r.hmset("doorlock:device_status:doorlock_test_001", device_data)
    r.expire("doorlock:device_status:doorlock_test_001", 3600)  # 1 hour TTL
    
    cached_device = r.hgetall("doorlock:device_status:doorlock_test_001")
    print(f"✅ Hash operation: {cached_device}")
    
    # JSON operations (for complex data)
    dashboard_data = {
        "total_devices": 8,
        "online_devices": 7,
        "offline_devices": 1,
        "avg_battery": 85.5,
        "last_updated": datetime.now().isoformat()
    }
    r.set("doorlock:dashboard:overview", json.dumps(dashboard_data), ex=300)  # 5 min TTL
    cached_dashboard = json.loads(r.get("doorlock:dashboard:overview"))
    print(f"✅ JSON operation: {cached_dashboard}")

def test_caching_strategies(r):
    """Test different caching strategies for doorlock system"""
    print("\n=== Testing Caching Strategies ===")
    
    # 1. Device Status Caching (1 hour TTL)
    print("1. Device Status Caching")
    devices = ["doorlock_otista_001", "doorlock_otista_002", "doorlock_kemayoran_001"]
    
    for device_id in devices:
        status_data = {
            "device_id": device_id,
            "door_status": "locked",
            "rfid_enabled": "true",
            "battery_percentage": str(85 + hash(device_id) % 15),
            "last_sync": datetime.now().isoformat(),
            "location": "otista" if "otista" in device_id else "kemayoran"
        }
        
        cache_key = f"doorlock:device_status:{device_id}"
        r.hmset(cache_key, status_data)
        r.expire(cache_key, 3600)  # 1 hour
        print(f"   ✅ Cached {device_id}")
    
    # 2. Dashboard Data Caching (5 minutes TTL)
    print("2. Dashboard Data Caching")
    dashboard_keys = [
        "doorlock:dashboard:overview",
        "doorlock:dashboard:fleet_health",
        "doorlock:dashboard:recent_activity"
    ]
    
    for key in dashboard_keys:
        data = {
            "cached_at": datetime.now().isoformat(),
            "data": f"Sample data for {key.split(':')[-1]}"
        }
        r.set(key, json.dumps(data), ex=300)  # 5 minutes
        print(f"   ✅ Cached {key}")
    
    # 3. OTA Progress Tracking (30 minutes TTL)
    print("3. OTA Progress Tracking")
    ota_devices = ["doorlock_otista_001", "doorlock_kemayoran_002"]
    
    for device_id in ota_devices:
        progress_data = {
            "device_id": device_id,
            "ota_status": "downloading",
            "progress_percent": str(45 + hash(device_id) % 50),
            "started_at": datetime.now().isoformat(),
            "firmware_version": "v2.2.0"
        }
        
        cache_key = f"doorlock:ota:progress:{device_id}"
        r.hmset(cache_key, progress_data)
        r.expire(cache_key, 1800)  # 30 minutes
        print(f"   ✅ Cached OTA progress for {device_id}")
    
    # 4. API Rate Limiting (1 hour sliding window)
    print("4. API Rate Limiting")
    for device_id in devices:
        rate_key = f"doorlock:api_rate:{device_id}"
        r.incr(rate_key)
        r.expire(rate_key, 3600)  # 1 hour
        current_rate = r.get(rate_key)
        print(f"   ✅ Rate limit for {device_id}: {current_rate} requests/hour")

def test_performance(r):
    """Test Redis performance with doorlock-like workload"""
    print("\n=== Testing Performance ===")
    
    # Test 1: Bulk device status updates (simulate 100 devices syncing)
    print("1. Bulk Device Status Updates (100 devices)")
    start_time = time.time()
    
    pipe = r.pipeline()
    for i in range(100):
        device_id = f"doorlock_test_{i:03d}"
        status_data = {
            "device_id": device_id,
            "door_status": "locked",
            "battery_percentage": str(80 + i % 20),
            "last_sync": datetime.now().isoformat()
        }
        
        cache_key = f"doorlock:device_status:{device_id}"
        pipe.hmset(cache_key, status_data)
        pipe.expire(cache_key, 3600)
    
    pipe.execute()
    bulk_time = time.time() - start_time
    print(f"   ✅ Bulk update completed in {bulk_time:.3f} seconds")
    
    # Test 2: Dashboard data retrieval (simulate dashboard loading)
    print("2. Dashboard Data Retrieval")
    start_time = time.time()
    
    # Simulate dashboard loading all device statuses
    pipe = r.pipeline()
    for i in range(100):
        device_id = f"doorlock_test_{i:03d}"
        cache_key = f"doorlock:device_status:{device_id}"
        pipe.hgetall(cache_key)
    
    results = pipe.execute()
    retrieval_time = time.time() - start_time
    print(f"   ✅ Retrieved {len(results)} device statuses in {retrieval_time:.3f} seconds")
    
    # Test 3: Cache hit ratio simulation
    print("3. Cache Hit Ratio Test")
    hits = 0
    misses = 0
    
    for i in range(50):
        device_id = f"doorlock_test_{i:03d}"
        cache_key = f"doorlock:device_status:{device_id}"
        
        if r.exists(cache_key):
            hits += 1
        else:
            misses += 1
    
    hit_ratio = (hits / (hits + misses)) * 100
    print(f"   ✅ Cache hit ratio: {hit_ratio:.1f}% ({hits} hits, {misses} misses)")

def test_expiration_and_cleanup(r):
    """Test TTL and automatic cleanup"""
    print("\n=== Testing Expiration & Cleanup ===")
    
    # Set keys with different expiration times
    test_keys = [
        ("doorlock:test:short", "Short TTL data", 5),      # 5 seconds
        ("doorlock:test:medium", "Medium TTL data", 30),   # 30 seconds
        ("doorlock:test:long", "Long TTL data", 300)       # 5 minutes
    ]
    
    for key, value, ttl in test_keys:
        r.set(key, value, ex=ttl)
        remaining_ttl = r.ttl(key)
        print(f"   ✅ Set {key} with TTL {ttl}s (remaining: {remaining_ttl}s)")
    
    # Test key existence after short delay
    print("\n   Waiting 6 seconds to test expiration...")
    time.sleep(6)
    
    for key, _, _ in test_keys:
        exists = r.exists(key)
        ttl = r.ttl(key)
        status = "EXISTS" if exists else "EXPIRED"
        print(f"   {status}: {key} (TTL: {ttl}s)")

def test_memory_usage(r):
    """Test memory usage and limits"""
    print("\n=== Testing Memory Usage ===")
    
    # Get current memory usage
    info = r.info('memory')
    used_memory = info['used_memory_human']
    max_memory = info.get('maxmemory_human', 'unlimited')
    
    print(f"   Used memory: {used_memory}")
    print(f"   Max memory: {max_memory}")
    print(f"   Memory policy: {info.get('maxmemory_policy', 'noeviction')}")
    
    # Count keys by pattern
    patterns = [
        "doorlock:device_status:*",
        "doorlock:dashboard:*",
        "doorlock:ota:*",
        "doorlock:api_rate:*"
    ]
    
    for pattern in patterns:
        keys = r.keys(pattern)
        print(f"   Keys matching '{pattern}': {len(keys)}")

def cleanup_test_data(r):
    """Clean up test data"""
    print("\n=== Cleaning Up Test Data ===")
    
    patterns = [
        "doorlock:test:*",
        "doorlock:device_status:doorlock_test_*",
        "test:*"
    ]
    
    total_deleted = 0
    for pattern in patterns:
        keys = r.keys(pattern)
        if keys:
            deleted = r.delete(*keys)
            total_deleted += deleted
            print(f"   ✅ Deleted {deleted} keys matching '{pattern}'")
    
    print(f"   Total keys deleted: {total_deleted}")

def main():
    """Main test function"""
    print("=== DOORLOCK REDIS CACHE TESTING ===")
    
    # Connect to Redis
    r = connect_redis()
    
    try:
        # Run all tests
        test_basic_operations(r)
        test_caching_strategies(r)
        test_performance(r)
        test_expiration_and_cleanup(r)
        test_memory_usage(r)
        
        print("\n✅ All Redis tests completed successfully!")
        
        # Optional: Clean up test data
        response = input("\nClean up test data? (y/N): ")
        if response.lower() == 'y':
            cleanup_test_data(r)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    
    finally:
        r.close()

if __name__ == "__main__":
    main()
