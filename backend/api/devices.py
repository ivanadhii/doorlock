"""
Simple Device API endpoints for ESP8266 doorlock devices
Clean implementation without args/kwargs
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import json

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, Field

from utils.database import get_db
from utils.redis_client import cache_device_status, get_cached_device_status
from utils.logger import logger
from services.auth_service import get_current_api_key

router = APIRouter()


# Pydantic Models
class SyncSession(BaseModel):
    session_id: str
    period: Dict[str, str]


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
    access_type: str = "rfid"
    user_name: Optional[str] = None
    timestamp: str


class BulkUploadData(BaseModel):
    device_id: str = Field(..., pattern="^doorlock_[a-z]+_[0-9]+$")
    location: str = Field(..., pattern="^(otista|kemayoran)$")
    sync_session: SyncSession
    current_status: CurrentStatus
    access_logs: List[AccessLog] = Field(default_factory=list)
    spam_detected: bool = False
    total_access_count: int = Field(..., ge=0)
    timestamp: str


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


# Simple rate limiting function
async def simple_rate_limit_check(request: Request):
    """Simple rate limiting check"""
    try:
        from utils.redis_client import check_api_rate_limit
        client_ip = request.client.host
        rate_result = await check_api_rate_limit(client_ip, 100, 3600)
        
        if not rate_result["allowed"]:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except Exception:
        # Continue without rate limiting if Redis fails
        pass


# Test endpoints
@router.get("/test")
async def test_endpoint():
    """Test endpoint - no auth required"""
    return {"status": "working", "message": "Router is functional"}


@router.get("/test-auth")
async def test_auth_endpoint(
    request: Request, 
    api_key: str = Depends(get_current_api_key)
):
    """Test endpoint with authentication"""
    return {"status": "authenticated", "api_key_valid": True}


# Main ESP8266 Endpoints
@router.post("/bulk-upload")
async def bulk_upload(
    upload_request: BulkUploadRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Handle bulk data upload from ESP8266 doorlock device"""
    
    await simple_rate_limit_check(request)
    
    doorlock_data = upload_request.doorlock
    device_id = doorlock_data.device_id
    session_id = doorlock_data.sync_session.session_id
    
    logger.info(f"📤 Bulk upload from {device_id}, Session: {session_id}")
    
    try:
        # 1. Ensure device exists
        await ensure_device_exists(db, doorlock_data)
        
        # 2. Update device status
        await update_device_status(db, doorlock_data)
        
        # 3. Process access logs
        processed_logs = await process_access_logs(db, doorlock_data)
        
        # 4. Cache device status in background
        background_tasks.add_task(cache_device_status_background, doorlock_data)
        
        # 5. Get pending commands
        pending_commands = await get_pending_commands(db, device_id)
        
        logger.info(f"✅ Sync success: {device_id}, {len(processed_logs)} logs, {len(pending_commands)} commands")
        
        # 6. Prepare response
        response = CommandResponse(
            device_id=device_id,
            session_ack=session_id,
            commands=pending_commands,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return {"doorlock": response.dict()}
        
    except Exception as e:
        logger.error(f"❌ Bulk upload failed for {device_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk upload failed: {str(e)}")


@router.post("/command-ack")
async def command_acknowledgment(
    ack_request: CommandAckRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Handle command execution acknowledgments from ESP8266"""
    
    await simple_rate_limit_check(request)
    
    ack_data = ack_request.doorlock
    device_id = ack_data.device_id
    
    logger.info(f"📨 Command ACK from {device_id}")
    
    try:
        updated_commands = await update_command_statuses(db, ack_data)
        
        logger.info(f"✅ Command ACK success: {device_id}, {len(updated_commands)} commands")
        
        return {
            "message": "Command acknowledgments received",
            "device_id": device_id,
            "processed_commands": len(updated_commands),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Command ACK failed for {device_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Command ack failed: {str(e)}")


@router.get("/status")
async def get_all_device_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get status of all devices"""
    
    await simple_rate_limit_check(request)
    
    logger.info("📊 All devices status requested")
    
    try:
        result = await db.execute(text("""
            SELECT 
                d.device_id,
                d.device_name,
                d.location,
                d.is_active,
                ds.door_status,
                ds.rfid_enabled,
                ds.battery_percentage,
                ds.last_sync,
                CASE 
                    WHEN ds.last_sync >= NOW() - interval '8 hours' THEN 'online'
                    WHEN ds.last_sync >= NOW() - interval '24 hours' THEN 'warning'
                    ELSE 'offline'
                END as connection_status
            FROM devices d
            LEFT JOIN device_status ds ON d.device_id = ds.device_id
            WHERE d.is_active = true
            ORDER BY d.location, d.device_id
        """))
        
        devices = []
        for row in result:
            devices.append({
                "device_id": row.device_id,
                "device_name": row.device_name,
                "location": row.location,
                "door_status": row.door_status,
                "rfid_enabled": row.rfid_enabled,
                "battery_percentage": row.battery_percentage,
                "last_sync": row.last_sync.isoformat() if row.last_sync else None,
                "connection_status": row.connection_status
            })
        
        return {
            "total_devices": len(devices),
            "devices": devices,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Get all devices status failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get device status: {str(e)}")


# Helper Functions
async def ensure_device_exists(db: AsyncSession, doorlock_data: BulkUploadData):
    """Ensure device exists in database"""
    
    result = await db.execute(text("""
        SELECT device_id FROM devices WHERE device_id = :device_id
    """), {"device_id": doorlock_data.device_id})
    
    if not result.first():
        await db.execute(text("""
            INSERT INTO devices (device_id, device_name, location, is_active, created_at)
            VALUES (:device_id, :device_name, :location, true, NOW())
            ON CONFLICT (device_id) DO NOTHING
        """), {
            "device_id": doorlock_data.device_id,
            "device_name": f"{doorlock_data.location.title()} Doorlock",
            "location": doorlock_data.location
        })
        
        await db.commit()
        logger.info(f"✅ Created new device: {doorlock_data.device_id}")


async def update_device_status(db: AsyncSession, doorlock_data: BulkUploadData):
    """Update device status in database"""
    
    status = doorlock_data.current_status
    
    await db.execute(text("""
        UPDATE devices 
        SET last_seen = NOW()
        WHERE device_id = :device_id
    """), {"device_id": doorlock_data.device_id})
    
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
    
    for log_entry in doorlock_data.access_logs:
        try:
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
            logger.error(f"Error processing access log: {e}")
    
    await db.commit()
    return processed_logs


async def get_pending_commands(db: AsyncSession, device_id: str) -> List[Command]:
    """Get pending commands for device"""
    
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
        try:
            if isinstance(row.command_payload, str):
                payload = json.loads(row.command_payload)
            else:
                payload = row.command_payload
            
            command = Command(
                command_id=row.command_id,
                type=row.command_type,
                action=payload.get("action", ""),
                duration_minutes=payload.get("duration_minutes")
            )
            
            commands.append(command)
            command_ids.append(row.command_id)
        except Exception as e:
            logger.error(f"Error parsing command {row.command_id}: {e}")
    
    # Mark commands as sent
    if command_ids:
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
            executed_at = datetime.fromisoformat(response.executed_at.replace('Z', '+00:00'))
            
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
            "total_access_count": str(doorlock_data.total_access_count)
        }
        
        await cache_device_status(doorlock_data.device_id, status_data)
        
    except Exception as e:
        logger.error(f"Error caching device status: {e}")