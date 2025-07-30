"""
Device API endpoints for ESP8266 doorlock devices
Handles bulk uploads, command acknowledgments, and device status
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, insert, update
from pydantic import BaseModel, Field

from utils.database import get_db
from utils.redis_client import (
    cache_device_status, get_cached_device_status,
    cache_ota_progress, check_api_rate_limit
)
from utils.logger import log_api_request, log_device_sync, log_performance
from services.auth_service import get_current_api_key, rate_limited

router = APIRouter()


# Pydantic Models
class SyncSession(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    period: Dict[str, str] = Field(..., description="Time period for this sync")


class CurrentStatus(BaseModel):
    door_status: str = Field(..., pattern="^(locked|unlocked|locking|unlocking)$")
    rfid_enabled: bool
    battery_percentage: int = Field(..., ge=0, le=100)
    uptime_seconds: int = Field(..., ge=0)
    wifi_rssi: int = Field(..., ge=-100, le=0)
    free_heap: int = Field(..., ge=0)


class AccessLog(BaseModel):
    card_uid: str
    access_granted: bool
    access_type: str = Field(default="rfid")
    user_name: Optional[str] = None
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class BulkUploadData(BaseModel):
    device_id: str = Field(..., pattern="^doorlock_[a-z]+_[0-9]+$")
    location: str = Field(..., pattern="^(otista|kemayoran)$")
    sync_session: SyncSession
    current_status: CurrentStatus
    access_logs: List[AccessLog] = Field(default_factory=list)
    spam_detected: bool = Field(default=False)
    total_access_count: int = Field(..., ge=0)
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class BulkUploadRequest(BaseModel):
    doorlock: BulkUploadData


class Command(BaseModel):
    command_id: str
    type: str = Field(..., pattern="^(rfid_control|unlock_timer)$")
    action: str
    duration_minutes: Optional[int] = None


class CommandResponse(BaseModel):
    device_id: str
    session_ack: str
    commands: List[Command]
    timestamp: str


class CommandAck(BaseModel):
    command_id: str
    status: str = Field(..., pattern="^(success|failed|timeout)$")
    executed_at: str


class CommandAckData(BaseModel):
    device_id: str
    command_responses: List[CommandAck]
    timestamp: str


class CommandAckRequest(BaseModel):
    doorlock: CommandAckData


# Bulk Upload Endpoint
@router.post("/bulk-upload")
@rate_limited(max_requests=100, window_seconds=3600)  # 100 requests per hour per device
@log_performance("bulk_upload")
async def bulk_upload(
    request: Request,
    upload_request: BulkUploadRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """
    Handle bulk data upload from ESP8266 doorlock device
    This is the main sync endpoint called every 8 hours
    """
    
    doorlock_data = upload_request.doorlock
    device_id = doorlock_data.device_id
    session_id = doorlock_data.sync_session.session_id
    
    # Log API request
    log_api_request(
        method="POST",
        path="/api/doorlock/bulk-upload", 
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # 1. Ensure device exists in database
        await ensure_device_exists(db, doorlock_data)
        
        # 2. Update device status
        await update_device_status(db, doorlock_data)
        
        # 3. Process access logs
        processed_logs = await process_access_logs(db, doorlock_data)
        
        # 4. Cache device status
        background_tasks.add_task(cache_device_status_background, doorlock_data)
        
        # 5. Get pending commands
        pending_commands = await get_pending_commands(db, device_id)
        
        # 6. Log sync event
        log_device_sync(
            device_id=device_id,
            sync_type="bulk_upload",
            status="success",
            records_count=len(processed_logs),
            commands_count=len(pending_commands)
        )
        
        # 7. Prepare response
        response = CommandResponse(
            device_id=device_id,
            session_ack=session_id,
            commands=pending_commands,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return {"doorlock": response.dict()}
        
    except Exception as e:
        log_device_sync(
            device_id=device_id,
            sync_type="bulk_upload", 
            status="error"
        )
        raise HTTPException(status_code=500, detail=f"Bulk upload failed: {str(e)}")


# Command Acknowledgment Endpoint
@router.post("/command-ack")
@rate_limited(max_requests=50, window_seconds=3600)
@log_performance("command_ack")
async def command_acknowledgment(
    request: Request,
    ack_request: CommandAckRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """
    Handle command execution acknowledgments from ESP8266
    """
    
    ack_data = ack_request.doorlock
    device_id = ack_data.device_id
    
    log_api_request(
        method="POST",
        path="/api/doorlock/command-ack",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Update command statuses
        updated_commands = await update_command_statuses(db, ack_data)
        
        log_device_sync(
            device_id=device_id,
            sync_type="command_ack",
            status="success", 
            commands_count=len(updated_commands)
        )
        
        return {
            "message": "Command acknowledgments received",
            "device_id": device_id,
            "processed_commands": len(updated_commands),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        log_device_sync(
            device_id=device_id,
            sync_type="command_ack",
            status="error"
        )
        raise HTTPException(status_code=500, detail=f"Command ack failed: {str(e)}")


# Get Commands Endpoint (Alternative)
@router.get("/commands/{device_id}")
@rate_limited(max_requests=20, window_seconds=3600)
async def get_commands(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """
    Get pending commands for specific device (alternative endpoint)
    """
    
    log_api_request(
        method="GET",
        path=f"/api/doorlock/commands/{device_id}",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Get pending commands without clearing queue
        pending_commands = await get_pending_commands(db, device_id, clear_queue=False)
        
        return {
            "device_id": device_id,
            "commands": [cmd.dict() for cmd in pending_commands],
            "count": len(pending_commands),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get commands: {str(e)}")


# Device Status Endpoint
@router.get("/status/{device_id}")
@rate_limited(max_requests=60, window_seconds=3600)
async def get_device_status(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """
    Get detailed status of specific device
    """
    
    log_api_request(
        method="GET", 
        path=f"/api/doorlock/status/{device_id}",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Try cache first
        cached_status = await get_cached_device_status(device_id)
        if cached_status:
            return {
                "device_id": device_id,
                "status": cached_status,
                "source": "cache",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Get from database if not cached
        result = await db.execute(text("""
            SELECT 
                ds.*,
                d.device_name,
                d.is_active,
                d.total_reboots,
                df.current_version as firmware_version,
                df.ota_status
            FROM device_status ds
            JOIN devices d ON ds.device_id = d.device_id
            LEFT JOIN device_firmware df ON ds.device_id = df.device_id
            WHERE ds.device_id = :device_id
        """), {"device_id": device_id})
        
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
        
        # Calculate sync age
        if row.last_sync:
            sync_age_minutes = (datetime.utcnow() - row.last_sync).total_seconds() / 60
        else:
            sync_age_minutes = 999999
        
        status = {
            "device_id": row.device_id,
            "device_name": row.device_name,
            "location": row.location,
            "door_status": row.door_status,
            "rfid_enabled": row.rfid_enabled,
            "battery_percentage": row.battery_percentage,
            "last_sync": row.last_sync.isoformat() if row.last_sync else None,
            "sync_age_minutes": round(sync_age_minutes, 1),
            "is_online": sync_age_minutes < 480,  # 8 hours
            "total_reboots": row.total_reboots,
            "firmware_version": row.firmware_version,
            "ota_status": row.ota_status
        }
        
        return {
            "device_id": device_id,
            "status": status,
            "source": "database",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get device status: {str(e)}")


# Helper Functions
async def ensure_device_exists(db: AsyncSession, doorlock_data: BulkUploadData):
    """Ensure device exists in database, create if not exists"""
    
    # Check if device exists
    result = await db.execute(text("""
        SELECT device_id FROM devices WHERE device_id = :device_id
    """), {"device_id": doorlock_data.device_id})
    
    if not result.first():
        # Create device
        await db.execute(text("""
            INSERT INTO devices (device_id, device_name, location, is_active, created_at)
            VALUES (:device_id, :device_name, :location, true, NOW())
            ON CONFLICT (device_id) DO NOTHING
        """), {
            "device_id": doorlock_data.device_id,
            "device_name": f"{doorlock_data.location.title()} Doorlock",
            "location": doorlock_data.location
        })
        
        # Create device firmware entry
        await db.execute(text("""
            INSERT INTO device_firmware (device_id, current_version, ota_status)
            VALUES (:device_id, 'v1.0.0', 'idle')
            ON CONFLICT (device_id) DO NOTHING
        """), {"device_id": doorlock_data.device_id})
        
        await db.commit()


async def update_device_status(db: AsyncSession, doorlock_data: BulkUploadData):
    """Update device status in database"""
    
    status = doorlock_data.current_status
    
    # Update device last_seen
    await db.execute(text("""
        UPDATE devices 
        SET last_seen = NOW()
        WHERE device_id = :device_id
    """), {"device_id": doorlock_data.device_id})
    
    # Upsert device status
    await db.execute(text("""
        INSERT INTO device_status (
            device_id, door_status, rfid_enabled, battery_percentage,
            uptime_seconds, wifi_rssi, free_heap, last_sync, session_id,
            location, spam_detected, total_access_count, updated_at
        ) VALUES (
            :device_id, :door_status, :rfid_enabled, :battery_percentage,
            :uptime_seconds, :wifi_rssi, :free_heap, NOW(), :session_id,
            :location, :spam_detected, :total_access_count, NOW()
        )
        ON CONFLICT (device_id) DO UPDATE SET
            door_status = EXCLUDED.door_status,
            rfid_enabled = EXCLUDED.rfid_enabled,
            battery_percentage = EXCLUDED.battery_percentage,
            uptime_seconds = EXCLUDED.uptime_seconds,
            wifi_rssi = EXCLUDED.wifi_rssi,
            free_heap = EXCLUDED.free_heap,
            last_sync = EXCLUDED.last_sync,
            session_id = EXCLUDED.session_id,
            location = EXCLUDED.location,
            spam_detected = EXCLUDED.spam_detected,
            total_access_count = EXCLUDED.total_access_count,
            updated_at = NOW()
    """), {
        "device_id": doorlock_data.device_id,
        "door_status": status.door_status,
        "rfid_enabled": status.rfid_enabled,
        "battery_percentage": status.battery_percentage,
        "uptime_seconds": status.uptime_seconds,
        "wifi_rssi": status.wifi_rssi,
        "free_heap": status.free_heap,
        "session_id": doorlock_data.sync_session.session_id,
        "location": doorlock_data.location,
        "spam_detected": doorlock_data.spam_detected,
        "total_access_count": doorlock_data.total_access_count
    })
    
    await db.commit()


async def process_access_logs(db: AsyncSession, doorlock_data: BulkUploadData) -> List[dict]:
    """Process and insert access logs"""
    
    processed_logs = []
    
    if not doorlock_data.access_logs:
        return processed_logs
    
    # Batch insert access logs
    for log_entry in doorlock_data.access_logs:
        try:
            # Parse timestamp
            timestamp = datetime.fromisoformat(log_entry.timestamp.replace('Z', '+00:00'))
            
            await db.execute(text("""
                INSERT INTO access_logs (
                    device_id, card_uid, access_granted, access_type,
                    user_name, timestamp, session_id, created_at
                ) VALUES (
                    :device_id, :card_uid, :access_granted, :access_type,
                    :user_name, :timestamp, :session_id, NOW()
                )
            """), {
                "device_id": doorlock_data.device_id,
                "card_uid": log_entry.card_uid,
                "access_granted": log_entry.access_granted,
                "access_type": log_entry.access_type,
                "user_name": log_entry.user_name,
                "timestamp": timestamp,
                "session_id": doorlock_data.sync_session.session_id
            })
            
            processed_logs.append({
                "card_uid": log_entry.card_uid,
                "access_granted": log_entry.access_granted,
                "timestamp": timestamp.isoformat()
            })
            
        except Exception as e:
            # Log error but continue processing other logs
            from utils.logger import logger
            logger.error(f"Error processing access log for {doorlock_data.device_id}: {e}")
    
    await db.commit()
    return processed_logs


async def get_pending_commands(db: AsyncSession, device_id: str, clear_queue: bool = True) -> List[Command]:
    """Get pending commands for device"""
    
    # Get pending commands
    result = await db.execute(text("""
        SELECT command_id, command_type, command_payload
        FROM remote_commands
        WHERE device_id = :device_id 
        AND status IN ('queued', 'sent')
        ORDER BY created_at ASC
    """), {"device_id": device_id})
    
    commands = []
    command_ids = []
    
    for row in result:
        # Parse command payload
        import json
        payload = json.loads(row.command_payload) if isinstance(row.command_payload, str) else row.command_payload
        
        command = Command(
            command_id=row.command_id,
            type=row.command_type,
            action=payload.get("action", ""),
            duration_minutes=payload.get("duration_minutes")
        )
        
        commands.append(command)
        command_ids.append(row.command_id)
    
    # Mark commands as sent if clearing queue
    if clear_queue and command_ids:
        await db.execute(text("""
            UPDATE remote_commands
            SET status = 'sent', sent_at = NOW()
            WHERE command_id = ANY(:command_ids)
        """), {"command_ids": command_ids})
        
        await db.commit()
    
    return commands


async def update_command_statuses(db: AsyncSession, ack_data: CommandAckData) -> List[dict]:
    """Update command execution statuses"""
    
    updated_commands = []
    
    for response in ack_data.command_responses:
        try:
            # Parse timestamp
            executed_at = datetime.fromisoformat(response.executed_at.replace('Z', '+00:00'))
            
            # Update command status
            await db.execute(text("""
                UPDATE remote_commands
                SET 
                    status = :status,
                    executed_at = :executed_at,
                    ack_received_at = NOW()
                WHERE command_id = :command_id
            """), {
                "command_id": response.command_id,
                "status": response.status,
                "executed_at": executed_at
            })
            
            updated_commands.append({
                "command_id": response.command_id,
                "status": response.status,
                "executed_at": executed_at.isoformat()
            })
            
        except Exception as e:
            from utils.logger import logger
            logger.error(f"Error updating command {response.command_id}: {e}")
    
    await db.commit()
    return updated_commands


async def cache_device_status_background(doorlock_data: BulkUploadData):
    """Background task to cache device status"""
    
    try:
        status_data = {
            "device_id": doorlock_data.device_id,
            "door_status": doorlock_data.current_status.door_status,
            "rfid_enabled": str(doorlock_data.current_status.rfid_enabled),
            "battery_percentage": str(doorlock_data.current_status.battery_percentage),
            "last_sync": str(datetime.utcnow().timestamp()),
            "location": doorlock_data.location,
            "total_access_count": str(doorlock_data.total_access_count),
            "spam_detected": str(doorlock_data.spam_detected)
        }
        
        await cache_device_status(doorlock_data.device_id, status_data)
        
    except Exception as e:
        from utils.logger import logger
        logger.error(f"Error caching device status for {doorlock_data.device_id}: {e}")


# All Devices Status Endpoint
@router.get("/status")
@rate_limited(max_requests=30, window_seconds=3600)
async def get_all_device_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get status of all devices"""
    
    log_api_request(
        method="GET",
        path="/api/doorlock/status",
        client_ip=request.client.host
    )
    
    try:
        result = await db.execute(text("""
            SELECT 
                d.device_id,
                d.device_name,
                d.location,
                d.is_active,
                d.total_reboots,
                ds.door_status,
                ds.rfid_enabled,
                ds.battery_percentage,
                ds.last_sync,
                df.current_version as firmware_version,
                df.ota_status,
                CASE 
                    WHEN ds.last_sync >= NOW() - interval '8 hours' THEN 'online'
                    WHEN ds.last_sync >= NOW() - interval '24 hours' THEN 'warning'
                    ELSE 'offline'
                END as connection_status
            FROM devices d
            LEFT JOIN device_status ds ON d.device_id = ds.device_id
            LEFT JOIN device_firmware df ON d.device_id = df.device_id
            WHERE d.is_active = true
            ORDER BY d.location, d.device_id
        """))
        
        devices = []
        online_count = 0
        warning_count = 0
        offline_count = 0
        
        for row in result:
            device_info = {
                "device_id": row.device_id,
                "device_name": row.device_name,
                "location": row.location,
                "door_status": row.door_status,
                "rfid_enabled": row.rfid_enabled,
                "battery_percentage": row.battery_percentage,
                "last_sync": row.last_sync.isoformat() if row.last_sync else None,
                "connection_status": row.connection_status,
                "firmware_version": row.firmware_version,
                "ota_status": row.ota_status,
                "total_reboots": row.total_reboots
            }
            
            devices.append(device_info)
            
            # Count status
            if row.connection_status == "online":
                online_count += 1
            elif row.connection_status == "warning":
                warning_count += 1
            else:
                offline_count += 1
        
        return {
            "total_devices": len(devices),
            "online_devices": online_count,
            "warning_devices": warning_count,
            "offline_devices": offline_count,
            "devices": devices,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get device status: {str(e)}")


# Device Access Logs Endpoint
@router.get("/logs/{device_id}")
@rate_limited(max_requests=20, window_seconds=3600)
async def get_access_logs(
    device_id: str,
    request: Request,
    limit: int = 50,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get access logs for specific device"""
    
    log_api_request(
        method="GET",
        path=f"/api/doorlock/logs/{device_id}",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        result = await db.execute(text("""
            SELECT 
                card_uid,
                access_granted,
                access_type,
                user_name,
                timestamp,
                session_id
            FROM access_logs
            WHERE device_id = :device_id
            AND timestamp >= NOW() - interval ':hours hours'
            ORDER BY timestamp DESC
            LIMIT :limit
        """), {
            "device_id": device_id,
            "hours": hours,
            "limit": limit
        })
        
        logs = []
        for row in result:
            logs.append({
                "card_uid": row.card_uid,
                "access_granted": row.access_granted,
                "access_type": row.access_type,
                "user_name": row.user_name,
                "timestamp": row.timestamp.isoformat(),
                "session_id": row.session_id
            })
        
        return {
            "device_id": device_id,
            "logs": logs,
            "count": len(logs),
            "hours": hours,
            "limit": limit,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get access logs: {str(e)}")
