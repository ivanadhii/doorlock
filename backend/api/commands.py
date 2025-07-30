"""
Command management API endpoints
Handle remote commands for ESP8266 devices
"""

import json
import uuid
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, Field

from utils.database import get_db
from utils.logger import log_api_request, log_performance
from services.auth_service import get_current_api_key, rate_limited

router = APIRouter()


# Pydantic Models
class UnlockTimerCommand(BaseModel):
    device_id: str = Field(..., pattern="^doorlock_[a-z]+_[0-9]+$")
    duration_minutes: int = Field(..., ge=10, le=120, description="Duration in minutes (10-120)")


class RFIDControlCommand(BaseModel):
    device_id: str = Field(..., pattern="^doorlock_[a-z]+_[0-9]+$") 
    action: str = Field(..., pattern="^(enable|disable)$")


class CommandStatus(BaseModel):
    command_id: str
    device_id: str
    command_type: str
    status: str
    created_at: str
    sent_at: Optional[str] = None
    executed_at: Optional[str] = None
    retry_count: int = 0


# Unlock Timer Command
@router.post("/command/unlock-timer")
@rate_limited(max_requests=20, window_seconds=3600)
@log_performance("unlock_timer_command")
async def send_unlock_timer(
    request: Request,
    device_id: str,
    duration_minutes: int,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Send unlock timer command to device"""
    
    log_api_request(
        method="POST",
        path="/api/doorlock/command/unlock-timer",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    # Validate duration
    if duration_minutes not in [10, 20, 30, 60]:
        raise HTTPException(
            status_code=400, 
            detail="Duration must be 10, 20, 30, or 60 minutes"
        )
    
    # Validate device exists
    await validate_device_exists(db, device_id)
    
    try:
        # Generate command ID
        command_id = f"cmd_{uuid.uuid4().hex[:8]}"
        
        # Create command payload
        command_payload = {
            "action": "unlock",
            "duration_minutes": duration_minutes
        }
        
        # Insert command into database
        await db.execute(text("""
            INSERT INTO remote_commands (
                command_id, device_id, command_type, command_payload,
                status, created_at, retry_count
            ) VALUES (
                :command_id, :device_id, :command_type, :command_payload,
                'queued', NOW(), 0
            )
        """), {
            "command_id": command_id,
            "device_id": device_id,
            "command_type": "unlock_timer",
            "command_payload": json.dumps(command_payload)
        })
        
        await db.commit()
        
        return {
            "message": f"Unlock timer command queued for {device_id}",
            "command_id": command_id,
            "device_id": device_id,
            "duration_minutes": duration_minutes,
            "estimated_delivery": "Next device sync (within 8 hours)",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send command: {str(e)}")


# RFID Control Command
@router.post("/command/rfid-control")
@rate_limited(max_requests=20, window_seconds=3600)
@log_performance("rfid_control_command")
async def send_rfid_control(
    request: Request,
    device_id: str,
    action: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Send RFID control command to device"""
    
    log_api_request(
        method="POST",
        path="/api/doorlock/command/rfid-control",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    # Validate action
    if action not in ["enable", "disable"]:
        raise HTTPException(
            status_code=400,
            detail="Action must be 'enable' or 'disable'"
        )
    
    # Validate device exists
    await validate_device_exists(db, device_id)
    
    try:
        # Generate command ID
        command_id = f"cmd_{uuid.uuid4().hex[:8]}"
        
        # Create command payload
        command_payload = {
            "action": action
        }
        
        # Insert command into database
        await db.execute(text("""
            INSERT INTO remote_commands (
                command_id, device_id, command_type, command_payload,
                status, created_at, retry_count
            ) VALUES (
                :command_id, :device_id, :command_type, :command_payload,
                'queued', NOW(), 0
            )
        """), {
            "command_id": command_id,
            "device_id": device_id,
            "command_type": "rfid_control",
            "command_payload": json.dumps(command_payload)
        })
        
        await db.commit()
        
        action_emoji = "🟢" if action == "enable" else "🔴"
        
        return {
            "message": f"RFID {action} command queued for {device_id}",
            "command_id": command_id,
            "device_id": device_id,
            "action": action,
            "status_emoji": action_emoji,
            "estimated_delivery": "Next device sync (within 8 hours)",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send command: {str(e)}")


# Get Command Status
@router.get("/command/status/{command_id}")
@rate_limited(max_requests=30, window_seconds=3600)
async def get_command_status(
    command_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get status of specific command"""
    
    log_api_request(
        method="GET",
        path=f"/api/doorlock/command/status/{command_id}",
        client_ip=request.client.host
    )
    
    try:
        result = await db.execute(text("""
            SELECT 
                command_id,
                device_id,
                command_type,
                command_payload,
                status,
                created_at,
                sent_at,
                executed_at,
                ack_received_at,
                retry_count,
                error_message
            FROM remote_commands
            WHERE command_id = :command_id
        """), {"command_id": command_id})
        
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Command {command_id} not found")
        
        # Parse command payload
        payload = json.loads(row.command_payload) if isinstance(row.command_payload, str) else row.command_payload
        
        return {
            "command_id": row.command_id,
            "device_id": row.device_id,
            "command_type": row.command_type,
            "payload": payload,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "executed_at": row.executed_at.isoformat() if row.executed_at else None,
            "ack_received_at": row.ack_received_at.isoformat() if row.ack_received_at else None,
            "retry_count": row.retry_count,
            "error_message": row.error_message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get command status: {str(e)}")


# Get Device Commands
@router.get("/commands/{device_id}/history")
@rate_limited(max_requests=20, window_seconds=3600)
async def get_device_commands(
    device_id: str,
    request: Request,
    limit: int = 20,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get command history for specific device"""
    
    log_api_request(
        method="GET",
        path=f"/api/doorlock/commands/{device_id}/history",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Build query with optional status filter
        query = """
            SELECT 
                command_id,
                command_type,
                command_payload,
                status,
                created_at,
                sent_at,
                executed_at,
                retry_count
            FROM remote_commands
            WHERE device_id = :device_id
        """
        
        params = {"device_id": device_id, "limit": limit}
        
        if status:
            query += " AND status = :status"
            params["status"] = status
        
        query += " ORDER BY created_at DESC LIMIT :limit"
        
        result = await db.execute(text(query), params)
        
        commands = []
        for row in result:
            # Parse command payload
            payload = json.loads(row.command_payload) if isinstance(row.command_payload, str) else row.command_payload
            
            commands.append({
                "command_id": row.command_id,
                "command_type": row.command_type,
                "payload": payload,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "executed_at": row.executed_at.isoformat() if row.executed_at else None,
                "retry_count": row.retry_count
            })
        
        return {
            "device_id": device_id,
            "commands": commands,
            "count": len(commands),
            "filter_status": status,
            "limit": limit,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get device commands: {str(e)}")


# Get Pending Commands for All Devices
@router.get("/commands/pending")
@rate_limited(max_requests=10, window_seconds=3600)
async def get_all_pending_commands(
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get all pending commands across all devices"""
    
    log_api_request(
        method="GET",
        path="/api/doorlock/commands/pending",
        client_ip=request.client.host
    )
    
    try:
        result = await db.execute(text("""
            SELECT 
                rc.command_id,
                rc.device_id,
                rc.command_type,
                rc.command_payload,
                rc.status,
                rc.created_at,
                rc.retry_count,
                d.device_name,
                d.location
            FROM remote_commands rc
            JOIN devices d ON rc.device_id = d.device_id
            WHERE rc.status IN ('queued', 'sent')
            ORDER BY rc.created_at ASC
        """))
        
        pending_commands = []
        queued_count = 0
        sent_count = 0
        
        for row in result:
            # Parse command payload
            payload = json.loads(row.command_payload) if isinstance(row.command_payload, str) else row.command_payload
            
            command_info = {
                "command_id": row.command_id,
                "device_id": row.device_id,
                "device_name": row.device_name,
                "location": row.location,
                "command_type": row.command_type,
                "payload": payload,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "retry_count": row.retry_count
            }
            
            pending_commands.append(command_info)
            
            if row.status == "queued":
                queued_count += 1
            elif row.status == "sent":
                sent_count += 1
        
        return {
            "pending_commands": pending_commands,
            "total_pending": len(pending_commands),
            "queued": queued_count,
            "sent": sent_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pending commands: {str(e)}")


# Cancel Command
@router.delete("/command/{command_id}")
@rate_limited(max_requests=10, window_seconds=3600)
async def cancel_command(
    command_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Cancel a pending command"""
    
    log_api_request(
        method="DELETE",
        path=f"/api/doorlock/command/{command_id}",
        client_ip=request.client.host
    )
    
    try:
        # Check if command exists and is cancellable
        result = await db.execute(text("""
            SELECT command_id, device_id, status
            FROM remote_commands
            WHERE command_id = :command_id
        """), {"command_id": command_id})
        
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Command {command_id} not found")
        
        if row.status not in ["queued", "sent"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel command with status '{row.status}'"
            )
        
        # Update command status to cancelled
        await db.execute(text("""
            UPDATE remote_commands
            SET status = 'cancelled', error_message = 'Cancelled by admin'
            WHERE command_id = :command_id
        """), {"command_id": command_id})
        
        await db.commit()
        
        return {
            "message": f"Command {command_id} cancelled successfully",
            "command_id": command_id,
            "device_id": row.device_id,
            "previous_status": row.status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cancel command: {str(e)}")


# Helper Functions
async def validate_device_exists(db: AsyncSession, device_id: str):
    """Validate that device exists and is active"""
    
    result = await db.execute(text("""
        SELECT device_id, is_active
        FROM devices
        WHERE device_id = :device_id
    """), {"device_id": device_id})
    
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    
    if not row.is_active:
        raise HTTPException(status_code=400, detail=f"Device {device_id} is not active")


# Command Statistics
@router.get("/commands/statistics")
@rate_limited(max_requests=10, window_seconds=3600)
async def get_command_statistics(
    request: Request,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Get command execution statistics"""
    
    log_api_request(
        method="GET",
        path="/api/doorlock/commands/statistics",
        client_ip=request.client.host
    )
    
    try:
        # Get command statistics for the last N hours
        result = await db.execute(text("""
            SELECT 
                command_type,
                status,
                COUNT(*) as count,
                AVG(EXTRACT(EPOCH FROM (executed_at - created_at))) as avg_execution_time
            FROM remote_commands
            WHERE created_at >= NOW() - interval ':hours hours'
            GROUP BY command_type, status
            ORDER BY command_type, status
        """), {"hours": hours})
        
        statistics = {}
        total_commands = 0
        
        for row in result:
            command_type = row.command_type
            status = row.status
            count = row.count
            avg_time = row.avg_execution_time
            
            if command_type not in statistics:
                statistics[command_type] = {
                    "total": 0,
                    "by_status": {},
                    "avg_execution_time": 0
                }
            
            statistics[command_type]["by_status"][status] = count
            statistics[command_type]["total"] += count
            
            if avg_time and status == "success":
                statistics[command_type]["avg_execution_time"] = round(avg_time, 2)
            
            total_commands += count
        
        # Calculate success rates
        for command_type in statistics:
            stats = statistics[command_type]
            success_count = stats["by_status"].get("success", 0)
            total_count = stats["total"]
            
            if total_count > 0:
                stats["success_rate"] = round((success_count / total_count) * 100, 1)
            else:
                stats["success_rate"] = 0
        
        return {
            "period_hours": hours,
            "total_commands": total_commands,
            "by_command_type": statistics,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get command statistics: {str(e)}")


# Retry Failed Commands
@router.post("/commands/retry-failed")
@rate_limited(max_requests=5, window_seconds=3600)
async def retry_failed_commands(
    request: Request,
    device_id: Optional[str] = None,
    max_retries: int = 3,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_current_api_key)
):
    """Retry failed commands for specific device or all devices"""
    
    log_api_request(
        method="POST",
        path="/api/doorlock/commands/retry-failed",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Build query
        query = """
            UPDATE remote_commands
            SET status = 'queued', retry_count = retry_count + 1, error_message = NULL
            WHERE status = 'failed' 
            AND retry_count < :max_retries
        """
        
        params = {"max_retries": max_retries}
        
        if device_id:
            query += " AND device_id = :device_id"
            params["device_id"] = device_id
            await validate_device_exists(db, device_id)
        
        query += " RETURNING command_id, device_id, command_type"
        
        result = await db.execute(text(query), params)
        
        retried_commands = []
        for row in result:
            retried_commands.append({
                "command_id": row.command_id,
                "device_id": row.device_id,
                "command_type": row.command_type
            })
        
        await db.commit()
        
        return {
            "message": f"Retried {len(retried_commands)} failed commands",
            "device_id": device_id,
            "retried_commands": retried_commands,
            "count": len(retried_commands),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to retry commands: {str(e)}")
