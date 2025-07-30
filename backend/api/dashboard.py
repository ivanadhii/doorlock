"""
Dashboard API endpoints
Provides data for the web dashboard interface
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from utils.database import get_db, get_database_stats
from utils.redis_client import (
    get_cached_dashboard_data, cache_dashboard_data,
    get_cache_stats, check_redis_health
)
from utils.logger import log_api_request, log_performance
from services.auth_service import admin_required, rate_limited

router = APIRouter()


# Dashboard Overview
@router.get("/overview")
@rate_limited(max_requests=60, window_seconds=3600)
@log_performance("dashboard_overview")
async def get_dashboard_overview(
    request: Request,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get complete dashboard overview with caching"""
    
    log_api_request(
        method="GET",
        path="/api/dashboard/overview",
        client_ip=request.client.host
    )
    
    try:
        # Try cache first (unless force refresh)
        if not force_refresh:
            cached_data = await get_cached_dashboard_data("overview")
            if cached_data:
                cached_data["source"] = "cache"
                return cached_data
        
        # Get fresh data from database
        result = await db.execute(text("""
            SELECT 
                COUNT(*) as total_devices,
                SUM(CASE WHEN ds.last_sync >= NOW() - interval '8 hours' THEN 1 ELSE 0 END) as online_devices,
                SUM(CASE WHEN ds.last_sync < NOW() - interval '8 hours' AND ds.last_sync >= NOW() - interval '24 hours' THEN 1 ELSE 0 END) as warning_devices,
                SUM(CASE WHEN ds.last_sync < NOW() - interval '24 hours' OR ds.last_sync IS NULL THEN 1 ELSE 0 END) as offline_devices,
                ROUND(AVG(ds.battery_percentage), 1) as avg_battery,
                MIN(ds.battery_percentage) as min_battery,
                SUM(CASE WHEN ds.battery_percentage < 20 THEN 1 ELSE 0 END) as low_battery_devices,
                SUM(ds.total_access_count) as total_access_count
            FROM devices d
            LEFT JOIN device_status ds ON d.device_id = ds.device_id
            WHERE d.is_active = true
        """))
        
        overview_row = result.first()
        
        # Get recent activity (last 24 hours)
        activity_result = await db.execute(text("""
            SELECT 
                COUNT(*) as total_attempts,
                SUM(CASE WHEN access_granted THEN 1 ELSE 0 END) as successful_attempts,
                SUM(CASE WHEN NOT access_granted THEN 1 ELSE 0 END) as failed_attempts,
                COUNT(DISTINCT device_id) as active_devices,
                COUNT(DISTINCT card_uid) as unique_cards
            FROM access_logs
            WHERE timestamp >= NOW() - interval '24 hours'
        """))
        
        activity_row = activity_result.first()
        
        # Get system alerts
        alerts_result = await db.execute(text("""
            SELECT COUNT(*) as alert_count
            FROM (
                SELECT device_id FROM device_status 
                WHERE battery_percentage < 20
                UNION
                SELECT d.device_id FROM devices d
                LEFT JOIN device_status ds ON d.device_id = ds.device_id
                WHERE d.is_active = true 
                AND (ds.last_sync < NOW() - interval '8 hours' OR ds.last_sync IS NULL)
                UNION
                SELECT device_id FROM device_firmware
                WHERE ota_status = 'failed'
            ) alerts
        """))
        
        alert_count = alerts_result.scalar()
        
        # Get command statistics
        command_result = await db.execute(text("""
            SELECT 
                COUNT(*) as total_commands,
                SUM(CASE WHEN status IN ('queued', 'sent') THEN 1 ELSE 0 END) as pending_commands,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_commands,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_commands
            FROM remote_commands
            WHERE created_at >= NOW() - interval '24 hours'
        """))
        
        command_row = command_result.first()
        
        # Build overview data
        overview_data = {
            "fleet_status": {
                "total_devices": overview_row.total_devices or 0,
                "online_devices": overview_row.online_devices or 0,
                "warning_devices": overview_row.warning_devices or 0,
                "offline_devices": overview_row.offline_devices or 0,
                "online_percentage": round(
                    (overview_row.online_devices or 0) / max(overview_row.total_devices or 1, 1) * 100, 1
                )
            },
            "battery_status": {
                "average_battery": overview_row.avg_battery or 0,
                "minimum_battery": overview_row.min_battery or 0,
                "low_battery_devices": overview_row.low_battery_devices or 0,
                "battery_health": "good" if (overview_row.avg_battery or 0) > 50 else "warning"
            },
            "activity_summary": {
                "total_access_attempts": activity_row.total_attempts or 0,
                "successful_attempts": activity_row.successful_attempts or 0,
                "failed_attempts": activity_row.failed_attempts or 0,
                "success_rate": round(
                    (activity_row.successful_attempts or 0) / max(activity_row.total_attempts or 1, 1) * 100, 1
                ),
                "active_devices_24h": activity_row.active_devices or 0,
                "unique_cards_24h": activity_row.unique_cards or 0
            },
            "system_status": {
                "total_alerts": alert_count or 0,
                "pending_commands": command_row.pending_commands or 0,
                "command_success_rate": round(
                    (command_row.successful_commands or 0) / max(command_row.total_commands or 1, 1) * 100, 1
                ) if command_row.total_commands else 100
            },
            "last_updated": datetime.utcnow().isoformat(),
            "source": "database"
        }
        
        # Cache the data
        await cache_dashboard_data("overview", overview_data)
        
        return overview_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard overview: {str(e)}")


# Fleet Health Summary
@router.get("/fleet-health")
@rate_limited(max_requests=30, window_seconds=3600)
async def get_fleet_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get fleet health summary by location"""
    
    log_api_request(
        method="GET",
        path="/api/dashboard/fleet-health",
        client_ip=request.client.host
    )
    
    try:
        # Try cache first
        cached_data = await get_cached_dashboard_data("fleet_health")
        if cached_data:
            cached_data["source"] = "cache"
            return cached_data
        
        result = await db.execute(text("""
            SELECT 
                d.location,
                COUNT(*) as total_devices,
                SUM(CASE WHEN ds.last_sync >= NOW() - interval '8 hours' THEN 1 ELSE 0 END) as online_devices,
                SUM(CASE WHEN ds.last_sync < NOW() - interval '8 hours' AND ds.last_sync >= NOW() - interval '24 hours' THEN 1 ELSE 0 END) as warning_devices,
                SUM(CASE WHEN ds.last_sync < NOW() - interval '24 hours' OR ds.last_sync IS NULL THEN 1 ELSE 0 END) as offline_devices,
                ROUND(AVG(ds.battery_percentage), 1) as avg_battery_percentage,
                MIN(ds.battery_percentage) as min_battery_percentage,
                SUM(CASE WHEN ds.battery_percentage < 20 THEN 1 ELSE 0 END) as low_battery_devices,
                SUM(ds.total_access_count) as total_access_count
            FROM devices d
            LEFT JOIN device_status ds ON d.device_id = ds.device_id
            WHERE d.is_active = true
            GROUP BY d.location
            ORDER BY d.location
        """))
        
        locations = []
        for row in result:
            location_data = {
                "location": row.location,
                "total_devices": row.total_devices,
                "online_devices": row.online_devices,
                "warning_devices": row.warning_devices,
                "offline_devices": row.offline_devices,
                "online_percentage": round(
                    row.online_devices / max(row.total_devices, 1) * 100, 1
                ),
                "avg_battery_percentage": row.avg_battery_percentage or 0,
                "min_battery_percentage": row.min_battery_percentage or 0,
                "low_battery_devices": row.low_battery_devices,
                "total_access_count": row.total_access_count or 0,
                "health_status": "good" if row.online_devices == row.total_devices else "warning"
            }
            locations.append(location_data)
        
        fleet_health_data = {
            "locations": locations,
            "summary": {
                "total_locations": len(locations),
                "healthy_locations": sum(1 for loc in locations if loc["health_status"] == "good"),
                "warning_locations": sum(1 for loc in locations if loc["health_status"] == "warning")
            },
            "last_updated": datetime.utcnow().isoformat(),
            "source": "database"
        }
        
        # Cache the data
        await cache_dashboard_data("fleet_health", fleet_health_data)
        
        return fleet_health_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get fleet health: {str(e)}")


# Recent Activity
@router.get("/recent-activity")
@rate_limited(max_requests=30, window_seconds=3600)
async def get_recent_activity(
    request: Request,
    hours: int = 24,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get recent access activity across all devices"""
    
    log_api_request(
        method="GET",
        path="/api/dashboard/recent-activity",
        client_ip=request.client.host
    )
    
    try:
        result = await db.execute(text("""
            SELECT 
                al.device_id,
                d.device_name,
                d.location,
                al.card_uid,
                al.access_granted,
                al.access_type,
                al.user_name,
                al.timestamp
            FROM access_logs al
            JOIN devices d ON al.device_id = d.device_id
            WHERE al.timestamp >= NOW() - interval ':hours hours'
            ORDER BY al.timestamp DESC
            LIMIT :limit
        """), {"hours": hours, "limit": limit})
        
        activities = []
        for row in result:
            activities.append({
                "device_id": row.device_id,
                "device_name": row.device_name,
                "location": row.location,
                "card_uid": row.card_uid,
                "access_granted": row.access_granted,
                "access_type": row.access_type,
                "user_name": row.user_name,
                "timestamp": row.timestamp.isoformat(),
                "status_icon": "✅" if row.access_granted else "❌"
            })
        
        return {
            "activities": activities,
            "count": len(activities),
            "period_hours": hours,
            "limit": limit,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent activity: {str(e)}")


# System Alerts
@router.get("/alerts")
@rate_limited(max_requests=30, window_seconds=3600)
async def get_system_alerts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get system alerts and warnings"""
    
    log_api_request(
        method="GET",
        path="/api/dashboard/alerts",
        client_ip=request.client.host
    )
    
    try:
        # Try cache first
        cached_data = await get_cached_dashboard_data("alerts")
        if cached_data:
            cached_data["source"] = "cache"
            return cached_data
        
        # Get system alerts from database view
        result = await db.execute(text("""
            SELECT 
                alert_type,
                message,
                severity,
                device_id,
                alert_time
            FROM system_alerts
            ORDER BY 
                CASE severity 
                    WHEN 'error' THEN 1
                    WHEN 'warning' THEN 2
                    ELSE 3
                END,
                alert_time DESC
            LIMIT 20
        """))
        
        alerts = []
        error_count = 0
        warning_count = 0
        
        for row in result:
            alert = {
                "alert_type": row.alert_type,
                "message": row.message,
                "severity": row.severity,
                "device_id": row.device_id,
                "alert_time": row.alert_time.isoformat(),
                "icon": "🔴" if row.severity == "error" else "🟡"
            }
            alerts.append(alert)
            
            if row.severity == "error":
                error_count += 1
            elif row.severity == "warning":
                warning_count += 1
        
        alerts_data = {
            "alerts": alerts,
            "summary": {
                "total_alerts": len(alerts),
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": len(alerts) - error_count - warning_count
            },
            "last_updated": datetime.utcnow().isoformat(),
            "source": "database"
        }
        
        # Cache the data
        await cache_dashboard_data("alerts", alerts_data)
        
        return alerts_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system alerts: {str(e)}")


# System Statistics
@router.get("/system-stats")
@rate_limited(max_requests=10, window_seconds=3600)
async def get_system_statistics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get comprehensive system statistics"""
    
    log_api_request(
        method="GET",
        path="/api/dashboard/system-stats",
        client_ip=request.client.host
    )
    
    try:
        # Get database statistics
        db_stats = await get_database_stats()
        
        # Get Redis statistics
        redis_stats = await get_cache_stats()
        
        # Get application statistics
        app_result = await db.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM devices WHERE is_active = true) as active_devices,
                (SELECT COUNT(*) FROM access_logs WHERE timestamp >= NOW() - interval '24 hours') as access_logs_24h,
                (SELECT COUNT(*) FROM remote_commands WHERE created_at >= NOW() - interval '24 hours') as commands_24h,
                (SELECT COUNT(*) FROM api_usage WHERE timestamp >= NOW() - interval '1 hour') as api_calls_1h
        """))
        
        app_row = app_result.first()
        
        system_stats = {
            "database": db_stats,
            "cache": redis_stats,
            "application": {
                "active_devices": app_row.active_devices,
                "access_logs_24h": app_row.access_logs_24h,
                "commands_24h": app_row.commands_24h,
                "api_calls_1h": app_row.api_calls_1h
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return system_stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system statistics: {str(e)}")


# Health Check
@router.get("/health")
async def dashboard_health_check(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Dashboard-specific health check"""
    
    try:
        # Check database
        from utils.database import check_database_health
        db_health = await check_database_health()
        
        # Check Redis
        redis_health = await check_redis_health()
        
        # Overall health status
        overall_status = "healthy"
        if db_health["status"] != "healthy" or redis_health["status"] != "healthy":
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "components": {
                "database": db_health,
                "cache": redis_health
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
