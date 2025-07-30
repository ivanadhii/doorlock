"""
Firmware management API endpoints
Handle OTA updates and firmware deployment
"""

import os
import hashlib
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from utils.database import get_db
from utils.logger import log_api_request, log_ota_event, log_performance
from services.auth_service import admin_required, rate_limited

router = APIRouter()

# Configuration
FIRMWARE_DIR = "/app/firmware"
MAX_FIRMWARE_SIZE = 2 * 1024 * 1024  # 2MB


# Get Firmware Status
@router.get("/status")
@rate_limited(max_requests=30, window_seconds=3600)
async def get_firmware_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get firmware status for all devices"""
    
    log_api_request(
        method="GET",
        path="/api/firmware/status",
        client_ip=request.client.host
    )
    
    try:
        result = await db.execute(text("""
            SELECT 
                df.device_id,
                d.device_name,
                d.location,
                df.current_version,
                df.available_version,
                df.last_known_good_version,
                df.ota_status,
                df.ota_retry_count,
                df.ota_progress,
                df.last_ota_attempt,
                df.last_successful_ota
            FROM device_firmware df
            JOIN devices d ON df.device_id = d.device_id
            WHERE d.is_active = true
            ORDER BY d.location, d.device_id
        """))
        
        devices = []
        for row in result:
            device_info = {
                "device_id": row.device_id,
                "device_name": row.device_name,
                "location": row.location,
                "current_version": row.current_version,
                "available_version": row.available_version,
                "last_known_good_version": row.last_known_good_version,
                "ota_status": row.ota_status,
                "ota_retry_count": row.ota_retry_count,
                "ota_progress": row.ota_progress,
                "last_ota_attempt": row.last_ota_attempt.isoformat() if row.last_ota_attempt else None,
                "last_successful_ota": row.last_successful_ota.isoformat() if row.last_successful_ota else None,
                "update_available": row.available_version and row.available_version != row.current_version,
                "status_icon": {
                    "idle": "⚪",
                    "pending": "🟡", 
                    "downloading": "🔵",
                    "flashing": "🟣",
                    "success": "🟢",
                    "failed": "🔴",
                    "rollback": "🟠"
                }.get(row.ota_status, "⚪")
            }
            devices.append(device_info)
        
        # Calculate summary
        total_devices = len(devices)
        devices_with_updates = sum(1 for d in devices if d["update_available"])
        active_ota = sum(1 for d in devices if d["ota_status"] in ["downloading", "flashing"])
        failed_ota = sum(1 for d in devices if d["ota_status"] == "failed")
        
        return {
            "devices": devices,
            "summary": {
                "total_devices": total_devices,
                "devices_with_updates": devices_with_updates,
                "active_ota_processes": active_ota,
                "failed_ota_processes": failed_ota
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get firmware status: {str(e)}")


# Upload Firmware
@router.post("/upload")
@rate_limited(max_requests=5, window_seconds=3600)
@log_performance("firmware_upload")
async def upload_firmware(
    request: Request,
    file: UploadFile = File(...),
    version: str = None,
    description: str = None,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Upload new firmware template"""
    
    log_api_request(
        method="POST",
        path="/api/firmware/upload",
        client_ip=request.client.host
    )
    
    try:
        # Validate file
        if not file.filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail="Only .bin files are allowed")
        
        # Read and validate file size
        content = await file.read()
        if len(content) > MAX_FIRMWARE_SIZE:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Maximum size: {MAX_FIRMWARE_SIZE / 1024 / 1024}MB"
            )
        
        # Generate file hash
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Generate version if not provided
        if not version:
            version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Save file
        os.makedirs(f"{FIRMWARE_DIR}/templates", exist_ok=True)
        file_path = f"{FIRMWARE_DIR}/templates/{version}.bin"
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Log upload
        log_ota_event(
            device_id="template",
            event_type="firmware_uploaded",
            firmware_version=version
        )
        
        return {
            "message": "Firmware uploaded successfully",
            "version": version,
            "filename": file.filename,
            "size_bytes": len(content),
            "size_mb": round(len(content) / 1024 / 1024, 2),
            "sha256": file_hash,
            "file_path": file_path,
            "description": description,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload firmware: {str(e)}")


# Deploy Firmware to Device
@router.post("/deploy/{device_id}")
@rate_limited(max_requests=10, window_seconds=3600)
@log_performance("firmware_deploy")
async def deploy_firmware(
    device_id: str,
    request: Request,
    version: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Deploy specific firmware version to device"""
    
    log_api_request(
        method="POST",
        path=f"/api/firmware/deploy/{device_id}",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Validate device exists
        device_result = await db.execute(text("""
            SELECT device_id, is_active FROM devices WHERE device_id = :device_id
        """), {"device_id": device_id})
        
        device_row = device_result.first()
        if not device_row:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
        
        if not device_row.is_active:
            raise HTTPException(status_code=400, detail=f"Device {device_id} is not active")
        
        # Check if firmware template exists
        template_path = f"{FIRMWARE_DIR}/templates/{version}.bin"
        if not os.path.exists(template_path):
            raise HTTPException(status_code=404, detail=f"Firmware version {version} not found")
        
        # Create device-specific firmware directory
        device_firmware_dir = f"{FIRMWARE_DIR}/devices/{device_id}"
        os.makedirs(device_firmware_dir, exist_ok=True)
        
        # Copy and customize firmware for device
        device_firmware_path = f"{device_firmware_dir}/{version}.bin"
        
        # For now, just copy the template
        # TODO: Implement binary patching for device-specific configs
        import shutil
        shutil.copy2(template_path, device_firmware_path)
        
        # Get file info
        file_size = os.path.getsize(device_firmware_path)
        
        # Calculate file hash
        with open(device_firmware_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Update device firmware record
        await db.execute(text("""
            UPDATE device_firmware
            SET 
                available_version = :version,
                firmware_file_path = :file_path,
                firmware_size_bytes = :file_size,
                firmware_checksum = :file_hash,
                ota_status = 'pending',
                ota_retry_count = 0,
                ota_progress = 0,
                updated_at = NOW()
            WHERE device_id = :device_id
        """), {
            "device_id": device_id,
            "version": version,
            "file_path": device_firmware_path,
            "file_size": file_size,
            "file_hash": file_hash
        })
        
        await db.commit()
        
        # Log deployment
        log_ota_event(
            device_id=device_id,
            event_type="firmware_deployed",
            firmware_version=version
        )
        
        return {
            "message": f"Firmware {version} deployed to {device_id}",
            "device_id": device_id,
            "firmware_version": version,
            "file_path": device_firmware_path,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "checksum": file_hash,
            "status": "pending",
            "estimated_delivery": "Next device sync (within 8 hours)",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to deploy firmware: {str(e)}")


# Batch Deploy Firmware
@router.post("/deploy/batch")
@rate_limited(max_requests=3, window_seconds=3600)
@log_performance("firmware_batch_deploy")
async def batch_deploy_firmware(
    request: Request,
    version: str,
    device_ids: Optional[List[str]] = None,
    location: Optional[str] = None,
    batch_size: int = 10,
    batch_delay_minutes: int = 2,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Deploy firmware to multiple devices in batches"""
    
    log_api_request(
        method="POST",
        path="/api/firmware/deploy/batch",
        client_ip=request.client.host
    )
    
    try:
        # Determine target devices
        if device_ids:
            # Specific device list
            target_query = """
                SELECT device_id FROM devices 
                WHERE device_id = ANY(:device_ids) AND is_active = true
            """
            target_params = {"device_ids": device_ids}
        elif location:
            # All devices in location
            target_query = """
                SELECT device_id FROM devices 
                WHERE location = :location AND is_active = true
            """
            target_params = {"location": location}
        else:
            # All active devices
            target_query = """
                SELECT device_id FROM devices WHERE is_active = true
            """
            target_params = {}
        
        result = await db.execute(text(target_query), target_params)
        target_devices = [row.device_id for row in result]
        
        if not target_devices:
            raise HTTPException(status_code=400, detail="No target devices found")
        
        # Check firmware template exists
        template_path = f"{FIRMWARE_DIR}/templates/{version}.bin"
        if not os.path.exists(template_path):
            raise HTTPException(status_code=404, detail=f"Firmware version {version} not found")
        
        # Create firmware deployment record
        deployment_id = f"deploy_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        await db.execute(text("""
            INSERT INTO firmware_deployments (
                deployment_id, firmware_version, target_devices, batch_size,
                batch_delay_minutes, deployment_status, total_devices,
                successful_devices, failed_devices, created_at
            ) VALUES (
                :deployment_id, :version, :target_devices, :batch_size,
                :batch_delay, 'pending', :total_devices, 0, 0, NOW()
            )
        """), {
            "deployment_id": deployment_id,
            "version": version,
            "target_devices": target_devices,
            "batch_size": batch_size,
            "batch_delay": batch_delay_minutes,
            "total_devices": len(target_devices)
        })
        
        await db.commit()
        
        # Log batch deployment
        log_ota_event(
            device_id="batch",
            event_type="batch_deployment_started",
            firmware_version=version
        )
        
        return {
            "message": f"Batch deployment initiated for {len(target_devices)} devices",
            "deployment_id": deployment_id,
            "firmware_version": version,
            "target_devices": target_devices,
            "total_devices": len(target_devices),
            "batch_size": batch_size,
            "batch_delay_minutes": batch_delay_minutes,
            "estimated_completion": f"{len(target_devices) // batch_size * batch_delay_minutes} minutes",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to start batch deployment: {str(e)}")


# Get Deployment Status
@router.get("/deployment/{deployment_id}")
@rate_limited(max_requests=20, window_seconds=3600)
async def get_deployment_status(
    deployment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Get status of firmware deployment"""
    
    log_api_request(
        method="GET",
        path=f"/api/firmware/deployment/{deployment_id}",
        client_ip=request.client.host
    )
    
    try:
        result = await db.execute(text("""
            SELECT * FROM firmware_deployments WHERE deployment_id = :deployment_id
        """), {"deployment_id": deployment_id})
        
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Deployment {deployment_id} not found")
        
        # Calculate progress
        progress_percentage = 0
        if row.total_devices > 0:
            completed = row.successful_devices + row.failed_devices
            progress_percentage = round((completed / row.total_devices) * 100, 1)
        
        return {
            "deployment_id": row.deployment_id,
            "firmware_version": row.firmware_version,
            "status": row.deployment_status,
            "total_devices": row.total_devices,
            "successful_devices": row.successful_devices,
            "failed_devices": row.failed_devices,
            "progress_percentage": progress_percentage,
            "batch_size": row.batch_size,
            "batch_delay_minutes": row.batch_delay_minutes,
            "created_at": row.created_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get deployment status: {str(e)}")


# Rollback Firmware
@router.post("/rollback/{device_id}")
@rate_limited(max_requests=10, window_seconds=3600)
@log_performance("firmware_rollback")
async def rollback_firmware(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(admin_required)
):
    """Rollback device to last known good firmware version"""
    
    log_api_request(
        method="POST",
        path=f"/api/firmware/rollback/{device_id}",
        client_ip=request.client.host,
        device_id=device_id
    )
    
    try:
        # Get device firmware info
        result = await db.execute(text("""
            SELECT 
                current_version,
                last_known_good_version,
                ota_status
            FROM device_firmware
            WHERE device_id = :device_id
        """), {"device_id": device_id})
        
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device firmware record not found")
        
        if not row.last_known_good_version:
            raise HTTPException(status_code=400, detail="No known good version to rollback to")
        
        rollback_version = row.last_known_good_version
        
        # Set rollback as available version
        await db.execute(text("""
            UPDATE device_firmware
            SET 
                available_version = :rollback_version,
                ota_status = 'pending',
                ota_retry_count = 0,
                ota_progress = 0,
                updated_at = NOW()
            WHERE device_id = :device_id
        """), {
            "device_id": device_id,
            "rollback_version": rollback_version
        })
        
        await db.commit()
        
        # Log rollback
        log_ota_event(
            device_id=device_id,
            event_type="firmware_rollback",
            firmware_version=rollback_version
        )
        
        return {
            "message": f"Firmware rollback initiated for {device_id}",
            "device_id": device_id,
            "current_version": row.current_version,
            "rollback_to_version": rollback_version,
            "status": "pending",
            "estimated_delivery": "Next device sync (within 8 hours)",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to rollback firmware: {str(e)}")
