#!/usr/bin/env python3
"""
Ultra Clean FastAPI Backend - ZERO ARGS/KWARGS
Simple, direct implementation for ESP8266 doorlock system
"""

import os
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
from pydantic import BaseModel, Field
import uvicorn
from loguru import logger

# =================================
# DATABASE SETUP
# =================================

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://doorlock:doorlock_secure_2025@postgres-db:5432/doorlock_system"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# =================================
# SIMPLE AUTH
# =================================

API_KEY = os.getenv("API_KEY", "kentutbau123")

def check_api_key(request: Request) -> bool:
    """Simple API key check"""
    api_key = request.headers.get("X-API-Key")
    if api_key == API_KEY:
        return True
    
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == API_KEY:
            return True
    
    return False

def require_auth(request: Request):
    """Require authentication"""
    if not check_api_key(request):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# =================================
# PYDANTIC MODELS
# =================================

class SyncSession(BaseModel):
    session_id: str
    period: Dict[str, str]

class CurrentStatus(BaseModel):
    door_status: str
    rfid_enabled: bool
    battery_percentage: int
    uptime_seconds: int
    wifi_rssi: int
    free_heap: int

class AccessLog(BaseModel):
    card_uid: str
    access_granted: bool
    access_type: str = "rfid"
    user_name: Optional[str] = None
    timestamp: str

class BulkUploadData(BaseModel):
    device_id: str
    location: str
    sync_session: SyncSession
    current_status: CurrentStatus
    access_logs: List[AccessLog] = []
    spam_detected: bool = False
    total_access_count: int
    timestamp: str

class BulkUploadRequest(BaseModel):
    doorlock: BulkUploadData

class Command(BaseModel):
    command_id: str
    type: str
    action: str
    duration_minutes: Optional[int] = None

class CommandResponse(BaseModel):
    device_id: str
    session_ack: str
    commands: List[Command]
    timestamp: str

class CommandAck(BaseModel):
    command_id: str
    status: str
    executed_at: str

class CommandAckData(BaseModel):
    device_id: str
    command_responses: List[CommandAck]
    timestamp: str

class CommandAckRequest(BaseModel):
    doorlock: CommandAckData

# =================================
# FASTAPI APP
# =================================

app = FastAPI(
    title="Clean Doorlock API",
    description="Ultra clean ESP8266 doorlock API - no args/kwargs",
    version="2.0.0",
    docs_url="/docs"
)

# Simple CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================
# PUBLIC ENDPOINTS
# =================================

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "service": "Clean Doorlock API",
        "version": "2.0.0",
        "status": "running",
        "auth": "X-API-Key: kentutbau123",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "esp8266_sync": "POST /api/doorlock/bulk-upload",
            "esp8266_ack": "POST /api/doorlock/command-ack",
            "device_status": "GET /api/doorlock/status"
        }
    }

@app.get("/health")
def health():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

# =================================
# ESP8266 ENDPOINTS - CLEAN FUNCTIONS
# =================================

@app.post("/api/doorlock/bulk-upload")
async def bulk_upload(
    request: BulkUploadRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """ESP8266 bulk upload - main sync endpoint"""
    
    # Auth check
    require_auth(req)
    
    doorlock_data = request.doorlock
    device_id = doorlock_data.device_id
    
    logger.info(f"📤 Sync: {device_id}")
    
    try:
        # 1. Create device if not exists
        await db.execute(text("""
            INSERT INTO devices (device_id, device_name, location, is_active, created_at)
            VALUES (:device_id, :device_name, :location, true, NOW())
            ON CONFLICT (device_id) DO UPDATE SET last_seen = NOW()
        """), {
            "device_id": device_id,
            "device_name": f"{doorlock_data.location.title()} Door",
            "location": doorlock_data.location
        })
        
        # 2. Update status
        status = doorlock_data.current_status
        await db.execute(text("""
            INSERT INTO device_status (
                device_id, door_status, rfid_enabled, battery_percentage,
                uptime_seconds, wifi_rssi, free_heap, last_sync,
                location, spam_detected, total_access_count, updated_at
            ) VALUES (
                :device_id, :door_status, :rfid_enabled, :battery_percentage,
                :uptime_seconds, :wifi_rssi, :free_heap, NOW(),
                :location, :spam_detected, :total_access_count, NOW()
            )
            ON CONFLICT (device_id) DO UPDATE SET
                door_status = EXCLUDED.door_status,
                rfid_enabled = EXCLUDED.rfid_enabled,
                battery_percentage = EXCLUDED.battery_percentage,
                uptime_seconds = EXCLUDED.uptime_seconds,
                wifi_rssi = EXCLUDED.wifi_rssi,
                free_heap = EXCLUDED.free_heap,
                last_sync = NOW(),
                spam_detected = EXCLUDED.spam_detected,
                total_access_count = EXCLUDED.total_access_count,
                updated_at = NOW()
        """), {
            "device_id": device_id,
            "door_status": status.door_status,
            "rfid_enabled": status.rfid_enabled,
            "battery_percentage": status.battery_percentage,
            "uptime_seconds": status.uptime_seconds,
            "wifi_rssi": status.wifi_rssi,
            "free_heap": status.free_heap,
            "location": doorlock_data.location,
            "spam_detected": doorlock_data.spam_detected,
            "total_access_count": doorlock_data.total_access_count
        })
        
        # 3. Process access logs
        log_count = 0
        for log_entry in doorlock_data.access_logs:
            try:
                timestamp = datetime.fromisoformat(log_entry.timestamp.replace('Z', '+00:00'))
                await db.execute(text("""
                    INSERT INTO access_logs (
                        device_id, card_uid, access_granted, access_type,
                        user_name, timestamp, created_at
                    ) VALUES (
                        :device_id, :card_uid, :access_granted, :access_type,
                        :user_name, :timestamp, NOW()
                    )
                """), {
                    "device_id": device_id,
                    "card_uid": log_entry.card_uid,
                    "access_granted": log_entry.access_granted,
                    "access_type": log_entry.access_type,
                    "user_name": log_entry.user_name,
                    "timestamp": timestamp
                })
                log_count += 1
            except Exception as e:
                logger.error(f"Access log error: {e}")
        
        # 4. Get pending commands
        result = await db.execute(text("""
            SELECT command_id, command_type, command_payload
            FROM remote_commands
            WHERE device_id = :device_id AND status IN ('queued', 'sent')
            ORDER BY created_at ASC
        """), {"device_id": device_id})
        
        commands = []
        command_ids = []
        
        for row in result:
            try:
                payload = json.loads(row.command_payload) if isinstance(row.command_payload, str) else row.command_payload
                command = Command(
                    command_id=row.command_id,
                    type=row.command_type,
                    action=payload.get("action", ""),
                    duration_minutes=payload.get("duration_minutes")
                )
                commands.append(command)
                command_ids.append(row.command_id)
            except Exception as e:
                logger.error(f"Command parse error: {e}")
        
        # 5. Mark commands as sent
        if command_ids:
            await db.execute(text("""
                UPDATE remote_commands
                SET status = 'sent', sent_at = NOW()
                WHERE command_id = ANY(:command_ids)
            """), {"command_ids": command_ids})
        
        await db.commit()
        
        logger.info(f"✅ Sync complete: {device_id} - {log_count} logs, {len(commands)} commands")
        
        # 6. Return response
        response = CommandResponse(
            device_id=device_id,
            session_ack=doorlock_data.sync_session.session_id,
            commands=commands,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return {"doorlock": response.dict()}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Sync failed: {device_id} - {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/doorlock/command-ack")
async def command_ack(
    request: CommandAckRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """ESP8266 command acknowledgment"""
    
    # Auth check
    require_auth(req)
    
    ack_data = request.doorlock
    device_id = ack_data.device_id
    
    logger.info(f"📨 Command ACK: {device_id}")
    
    try:
        count = 0
        for response in ack_data.command_responses:
            try:
                executed_at = datetime.fromisoformat(response.executed_at.replace('Z', '+00:00'))
                await db.execute(text("""
                    UPDATE remote_commands
                    SET status = :status, executed_at = :executed_at, ack_received_at = NOW()
                    WHERE command_id = :command_id
                """), {
                    "command_id": response.command_id,
                    "status": response.status,
                    "executed_at": executed_at
                })
                count += 1
            except Exception as e:
                logger.error(f"Command update error: {e}")
        
        await db.commit()
        
        logger.info(f"✅ Commands ACK: {device_id} - {count} updated")
        
        return {
            "message": "Commands acknowledged",
            "device_id": device_id,
            "updated": count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Command ACK failed: {device_id} - {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/doorlock/status")
async def all_devices_status(
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get all devices status"""
    
    # Auth check
    require_auth(req)
    
    try:
        result = await db.execute(text("""
            SELECT 
                d.device_id,
                d.device_name,
                d.location,
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
        logger.error(f"❌ Status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/doorlock/status/{device_id}")
async def device_status(
    device_id: str,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get specific device status"""
    
    # Auth check
    require_auth(req)
    
    try:
        result = await db.execute(text("""
            SELECT 
                d.device_id,
                d.device_name,
                d.location,
                ds.door_status,
                ds.rfid_enabled,
                ds.battery_percentage,
                ds.last_sync,
                ds.total_access_count
            FROM devices d
            LEFT JOIN device_status ds ON d.device_id = ds.device_id
            WHERE d.device_id = :device_id
        """), {"device_id": device_id})
        
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
        
        return {
            "device_id": row.device_id,
            "device_name": row.device_name,
            "location": row.location,
            "door_status": row.door_status,
            "rfid_enabled": row.rfid_enabled,
            "battery_percentage": row.battery_percentage,
            "last_sync": row.last_sync.isoformat() if row.last_sync else None,
            "total_access_count": row.total_access_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Device status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/doorlock/commands/{device_id}")
async def get_device_commands(
    device_id: str,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get pending commands for device"""
    
    # Auth check
    require_auth(req)
    
    try:
        result = await db.execute(text("""
            SELECT command_id, command_type, command_payload
            FROM remote_commands
            WHERE device_id = :device_id AND status IN ('queued', 'sent')
            ORDER BY created_at ASC
        """), {"device_id": device_id})
        
        commands = []
        for row in result:
            try:
                payload = json.loads(row.command_payload) if isinstance(row.command_payload, str) else row.command_payload
                command = Command(
                    command_id=row.command_id,
                    type=row.command_type,
                    action=payload.get("action", ""),
                    duration_minutes=payload.get("duration_minutes")
                )
                commands.append(command)
            except Exception as e:
                logger.error(f"Command parse error: {e}")
        
        return {
            "device_id": device_id,
            "commands": [cmd.dict() for cmd in commands],
            "count": len(commands),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Get commands failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =================================
# ADMIN COMMAND ENDPOINTS
# =================================

@app.post("/api/doorlock/command/unlock-timer")
async def unlock_timer_command(
    device_id: str,
    duration_minutes: int,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """Send unlock timer command"""
    
    # Auth check
    require_auth(req)
    
    if duration_minutes not in [10, 20, 30, 60]:
        raise HTTPException(status_code=400, detail="Duration must be 10, 20, 30, or 60 minutes")
    
    try:
        command_id = f"cmd_{uuid.uuid4().hex[:8]}"
        
        await db.execute(text("""
            INSERT INTO remote_commands (
                command_id, device_id, command_type, command_payload, status, created_at
            ) VALUES (
                :command_id, :device_id, 'unlock_timer', :payload, 'queued', NOW()
            )
        """), {
            "command_id": command_id,
            "device_id": device_id,
            "payload": json.dumps({"action": "unlock", "duration_minutes": duration_minutes})
        })
        
        await db.commit()
        
        logger.info(f"🔓 Unlock command: {device_id} - {duration_minutes}min")
        
        return {
            "message": f"Unlock timer queued for {device_id}",
            "command_id": command_id,
            "duration_minutes": duration_minutes
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/doorlock/command/rfid-control")
async def rfid_control_command(
    device_id: str,
    action: str,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """Send RFID control command"""
    
    # Auth check
    require_auth(req)
    
    if action not in ["enable", "disable"]:
        raise HTTPException(status_code=400, detail="Action must be 'enable' or 'disable'")
    
    try:
        command_id = f"cmd_{uuid.uuid4().hex[:8]}"
        
        await db.execute(text("""
            INSERT INTO remote_commands (
                command_id, device_id, command_type, command_payload, status, created_at
            ) VALUES (
                :command_id, :device_id, 'rfid_control', :payload, 'queued', NOW()
            )
        """), {
            "command_id": command_id,
            "device_id": device_id,
            "payload": json.dumps({"action": action})
        })
        
        await db.commit()
        
        logger.info(f"📡 RFID command: {device_id} - {action}")
        
        return {
            "message": f"RFID {action} queued for {device_id}",
            "command_id": command_id,
            "action": action
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# =================================
# ERROR HANDLERS
# =================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# =================================
# STARTUP
# =================================

@app.on_event("startup")
async def startup():
    logger.info("🚀 Ultra Clean Doorlock API Started")

@app.on_event("shutdown") 
async def shutdown():
    logger.info("🛑 API Shutting Down")

# =================================
# MAIN
# =================================

def main():
    logger.add("logs/app.log", rotation="1 MB")
    logger.info("Starting Ultra Clean Doorlock API")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )

if __name__ == "__main__":
    main()