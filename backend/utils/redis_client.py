"""
Redis client utilities and caching functions
Async Redis connection management
"""

import os
import json
import asyncio
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta

import redis.asyncio as redis
from loguru import logger


# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-cache:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# Cache TTL settings (in seconds)
CACHE_TTL = {
    "device_status": 3600,      # 1 hour
    "dashboard": 300,           # 5 minutes
    "ota_progress": 1800,       # 30 minutes
    "api_rate": 3600,           # 1 hour
    "alerts": 300,              # 5 minutes
}

# Key prefixes
KEY_PREFIX = {
    "device_status": "doorlock:device_status:",
    "dashboard": "doorlock:dashboard:",
    "ota_progress": "doorlock:ota:progress:",
    "api_rate": "doorlock:api_rate:",
    "alerts": "doorlock:alerts:",
    "cache": "doorlock:cache:",
}

# Global Redis client
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    
    try:
        # Create Redis client
        redis_client = redis.from_url(
            REDIS_URL,
            password=REDIS_PASSWORD,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            retry_on_timeout=True,
            socket_keepalive=True,
            socket_keepalive_options={},
        )
        
        # Test connection
        await redis_client.ping()
        
        # Set cache warming flag
        await redis_client.set(f"{KEY_PREFIX['cache']}backend_started", 
                             datetime.now().isoformat(), ex=3600)
        
        logger.info("✅ Redis connection established")
        
    except Exception as e:
        logger.error(f"❌ Redis initialization failed: {e}")
        raise


async def close_redis():
    """Close Redis connection"""
    global redis_client
    
    try:
        if redis_client:
            await redis_client.close()
        logger.info("✅ Redis connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing Redis: {e}")


async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    global redis_client
    
    if redis_client is None:
        await init_redis()
    
    return redis_client


# Device Status Caching
async def cache_device_status(device_id: str, status_data: Dict[str, Any]) -> bool:
    """Cache device status with 1 hour TTL"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['device_status']}{device_id}"
        
        # Convert to hash for efficient field access
        await client.hset(key, mapping=status_data)
        await client.expire(key, CACHE_TTL["device_status"])
        
        logger.debug(f"Cached device status: {device_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error caching device status {device_id}: {e}")
        return False


async def get_cached_device_status(device_id: str) -> Optional[Dict[str, Any]]:
    """Get cached device status"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['device_status']}{device_id}"
        
        data = await client.hgetall(key)
        
        if data:
            logger.debug(f"Cache hit: device status {device_id}")
            return data
        else:
            logger.debug(f"Cache miss: device status {device_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting cached device status {device_id}: {e}")
        return None


async def cache_all_device_statuses(devices_data: List[Dict[str, Any]]) -> int:
    """Cache multiple device statuses in batch"""
    try:
        client = await get_redis()
        pipe = client.pipeline()
        
        cached_count = 0
        for device_data in devices_data:
            device_id = device_data.get("device_id")
            if device_id:
                key = f"{KEY_PREFIX['device_status']}{device_id}"
                pipe.hset(key, mapping=device_data)
                pipe.expire(key, CACHE_TTL["device_status"])
                cached_count += 1
        
        await pipe.execute()
        logger.info(f"Batch cached {cached_count} device statuses")
        return cached_count
        
    except Exception as e:
        logger.error(f"Error batch caching device statuses: {e}")
        return 0


# Dashboard Data Caching
async def cache_dashboard_data(data_type: str, data: Any) -> bool:
    """Cache dashboard data with 5 minute TTL"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['dashboard']}{data_type}"
        
        # Serialize data to JSON
        json_data = json.dumps(data, default=str, ensure_ascii=False)
        await client.set(key, json_data, ex=CACHE_TTL["dashboard"])
        
        logger.debug(f"Cached dashboard data: {data_type}")
        return True
        
    except Exception as e:
        logger.error(f"Error caching dashboard data {data_type}: {e}")
        return False


async def get_cached_dashboard_data(data_type: str) -> Optional[Any]:
    """Get cached dashboard data"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['dashboard']}{data_type}"
        
        data = await client.get(key)
        
        if data:
            logger.debug(f"Cache hit: dashboard {data_type}")
            return json.loads(data)
        else:
            logger.debug(f"Cache miss: dashboard {data_type}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting cached dashboard data {data_type}: {e}")
        return None


# OTA Progress Caching
async def cache_ota_progress(device_id: str, progress_data: Dict[str, Any]) -> bool:
    """Cache OTA progress with 30 minute TTL"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['ota_progress']}{device_id}"
        
        await client.hset(key, mapping=progress_data)
        await client.expire(key, CACHE_TTL["ota_progress"])
        
        logger.debug(f"Cached OTA progress: {device_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error caching OTA progress {device_id}: {e}")
        return False


async def get_cached_ota_progress(device_id: str) -> Optional[Dict[str, Any]]:
    """Get cached OTA progress"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['ota_progress']}{device_id}"
        
        data = await client.hgetall(key)
        
        if data:
            logger.debug(f"Cache hit: OTA progress {device_id}")
            return data
        else:
            logger.debug(f"Cache miss: OTA progress {device_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting cached OTA progress {device_id}: {e}")
        return None


# API Rate Limiting
async def check_api_rate_limit(identifier: str, limit: int = 60, window: int = 3600) -> Dict[str, Any]:
    """Check API rate limit using sliding window"""
    try:
        client = await get_redis()
        key = f"{KEY_PREFIX['api_rate']}{identifier}"
        
        current_time = datetime.now().timestamp()
        
        # Remove old entries (outside window)
        await client.zremrangebyscore(key, 0, current_time - window)
        
        # Count current requests
        current_count = await client.zcard(key)
        
        if current_count >= limit:
            # Rate limit exceeded
            ttl = await client.ttl(key)
            return {
                "allowed": False,
                "count": current_count,
                "limit": limit,
                "reset_in": ttl
            }
        
        # Add current request
        await client.zadd(key, {str(current_time): current_time})
        await client.expire(key, window)
        
        return {
            "allowed": True,
            "count": current_count + 1,
            "limit": limit,
            "remaining": limit - current_count - 1
        }
        
    except Exception as e:
        logger.error(f"Error checking rate limit {identifier}: {e}")
        # Allow request if Redis fails
        return {"allowed": True, "count": 0, "limit": limit, "remaining": limit}


# Cache Statistics
async def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics for monitoring"""
    try:
        client = await get_redis()
        
        # Get Redis info
        info = await client.info()
        
        # Count keys by pattern
        patterns = {
            "device_status": f"{KEY_PREFIX['device_status']}*",
            "dashboard": f"{KEY_PREFIX['dashboard']}*",
            "ota_progress": f"{KEY_PREFIX['ota_progress']}*",
            "api_rate": f"{KEY_PREFIX['api_rate']}*",
            "alerts": f"{KEY_PREFIX['alerts']}*",
        }
        
        key_counts = {}
        for pattern_name, pattern in patterns.items():
            keys = await client.keys(pattern)
            key_counts[pattern_name] = len(keys)
        
        return {
            "redis_info": {
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
            },
            "key_counts": key_counts,
            "total_keys": sum(key_counts.values()),
            "hit_ratio": (
                info.get("keyspace_hits", 0) / 
                max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1)
            ) * 100
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {"error": str(e)}


# Cache Warming
async def warm_cache_from_database():
    """Warm cache with fresh data from database"""
    try:
        from utils.database import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            # Warm device status cache
            result = await session.execute(text("""
                SELECT 
                    ds.device_id,
                    ds.door_status,
                    ds.rfid_enabled,
                    ds.battery_percentage,
                    EXTRACT(EPOCH FROM ds.last_sync) as last_sync_timestamp,
                    ds.location,
                    ds.total_access_count
                FROM device_status ds 
                JOIN devices d ON ds.device_id = d.device_id 
                WHERE d.is_active = true
            """))
            
            devices_cached = 0
            for row in result:
                device_data = {
                    "device_id": row.device_id,
                    "door_status": row.door_status,
                    "rfid_enabled": str(row.rfid_enabled),
                    "battery_percentage": str(row.battery_percentage or 0),
                    "last_sync": str(row.last_sync_timestamp or 0),
                    "location": row.location,
                    "total_access_count": str(row.total_access_count or 0)
                }
                
                if await cache_device_status(row.device_id, device_data):
                    devices_cached += 1
            
            logger.info(f"Cache warmed: {devices_cached} device statuses")
            return devices_cached
            
    except Exception as e:
        logger.error(f"Error warming cache: {e}")
        return 0


# Health check function
async def check_redis_health():
    """Check Redis health for health endpoint"""
    try:
        client = await get_redis()
        await client.ping()
        
        # Get basic stats
        info = await client.info()
        
        return {
            "status": "healthy",
            "redis": "connected",
            "used_memory": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients")
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy", 
            "redis": "disconnected", 
            "error": str(e)
        }
