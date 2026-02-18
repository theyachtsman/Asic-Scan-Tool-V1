"""
Firmware Management API Routes
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.config import settings
from core.device_store import device_store
from core.models import FirmwarePackage, FlashJob, MinerBrand, MinerStatus

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory flash job tracker
_flash_jobs: Dict[str, FlashJob] = {}
_firmware_registry: Dict[str, FirmwarePackage] = {}


def _load_firmware_registry():
    """Load firmware registry from disk"""
    registry_file = settings.FIRMWARE_DIR / "registry.json"
    if registry_file.exists():
        try:
            with open(registry_file) as f:
                data = json.load(f)
            for item in data:
                pkg = FirmwarePackage(**item)
                _firmware_registry[pkg.id] = pkg
        except Exception as e:
            logger.warning(f"Failed to load firmware registry: {e}")


def _save_firmware_registry():
    """Save firmware registry to disk"""
    registry_file = settings.FIRMWARE_DIR / "registry.json"
    try:
        data = [pkg.model_dump(mode="json") for pkg in _firmware_registry.values()]
        with open(registry_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to save firmware registry: {e}")


_load_firmware_registry()


@router.get("/", response_model=List[FirmwarePackage])
async def list_firmware():
    """List all uploaded firmware packages"""
    return list(_firmware_registry.values())


@router.post("/upload")
async def upload_firmware(
    file: UploadFile = File(...),
    brand: str = Form(...),
    model: str = Form(""),
    version: str = Form(""),
    firmware_type: str = Form("Stock"),
    notes: str = Form(""),
):
    """Upload a firmware file"""
    firmware_id = str(uuid.uuid4())[:8]
    filename = file.filename or f"firmware_{firmware_id}.bin"

    # Save file
    save_path = settings.FIRMWARE_DIR / f"{firmware_id}_{filename}"
    content = await file.read()

    with open(save_path, "wb") as f:
        f.write(content)

    # Calculate checksums
    md5 = hashlib.md5(content).hexdigest()
    sha256 = hashlib.sha256(content).hexdigest()

    # Create package record
    package = FirmwarePackage(
        id=firmware_id,
        filename=filename,
        brand=brand,
        model=model,
        version=version,
        firmware_type=firmware_type,
        file_size=len(content),
        checksum_md5=md5,
        checksum_sha256=sha256,
        upload_date=datetime.utcnow(),
        notes=notes,
    )

    _firmware_registry[firmware_id] = package
    _save_firmware_registry()

    logger.info(f"Firmware uploaded: {filename} ({len(content)} bytes) ID={firmware_id}")

    return {
        "status": "uploaded",
        "firmware_id": firmware_id,
        "filename": filename,
        "size": len(content),
        "md5": md5,
        "sha256": sha256,
    }


@router.delete("/{firmware_id}")
async def delete_firmware(firmware_id: str):
    """Delete a firmware package"""
    if firmware_id not in _firmware_registry:
        raise HTTPException(status_code=404, detail="Firmware not found")

    pkg = _firmware_registry[firmware_id]

    # Delete file
    for f in settings.FIRMWARE_DIR.glob(f"{firmware_id}_*"):
        try:
            f.unlink()
        except Exception:
            pass

    del _firmware_registry[firmware_id]
    _save_firmware_registry()

    return {"status": "deleted", "firmware_id": firmware_id}


class FlashRequest(BaseModel):
    firmware_id: str
    target_ips: List[str]
    username: str = ""
    password: str = ""


@router.post("/flash")
async def flash_firmware(request: FlashRequest, background_tasks: BackgroundTasks):
    """Start a firmware flash job"""
    if request.firmware_id not in _firmware_registry:
        raise HTTPException(status_code=404, detail="Firmware not found")

    pkg = _firmware_registry[request.firmware_id]
    firmware_file = None

    # Find the firmware file
    for f in settings.FIRMWARE_DIR.glob(f"{request.firmware_id}_*"):
        firmware_file = str(f)
        break

    if not firmware_file:
        raise HTTPException(status_code=404, detail="Firmware file not found on disk")

    job_id = str(uuid.uuid4())[:8]
    job = FlashJob(
        job_id=job_id,
        firmware_id=request.firmware_id,
        target_ips=request.target_ips,
        status="running",
        started_at=datetime.utcnow(),
        progress={ip: "pending" for ip in request.target_ips},
    )
    _flash_jobs[job_id] = job

    async def run_flash_job():
        from api.routes.websocket import broadcast_flash_progress

        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent flashes

        async def flash_one(ip: str):
            async with semaphore:
                device = device_store.get_by_ip(ip)
                username = request.username or (device.username if device else "root")
                password = request.password or (device.password if device else "root")
                brand = device.brand if device else MinerBrand.BITMAIN

                job.progress[ip] = "flashing"
                await broadcast_flash_progress(job_id, job.progress)

                try:
                    success = False

                    async def progress_cb(pct, msg):
                        job.progress[ip] = f"flashing ({pct}%)"
                        await broadcast_flash_progress(job_id, job.progress)

                    if brand == MinerBrand.BITMAIN or brand == "Bitmain":
                        from api_collectors.bitmain_collector import BitmainCollector
                        collector = BitmainCollector()
                        success = await collector.flash_firmware(
                            ip, firmware_file, username, password,
                            progress_callback=progress_cb
                        )
                    elif brand == MinerBrand.CANAAN or brand == "Canaan":
                        from api_collectors.canaan_collector import CanaanCollector
                        collector = CanaanCollector()
                        success = await collector.flash_firmware(
                            ip, firmware_file, username, password,
                            progress_callback=progress_cb
                        )
                    elif brand == MinerBrand.BITDEER or brand == "Bitdeer":
                        from api_collectors.bitdeer_collector import BitdeerCollector
                        collector = BitdeerCollector()
                        success = await collector.flash_firmware(
                            ip, firmware_file, username, password,
                            progress_callback=progress_cb
                        )

                    job.progress[ip] = "complete" if success else "failed"
                    if not success:
                        job.errors[ip] = "Flash failed"

                    if device:
                        device.status = MinerStatus.FLASHING if success else MinerStatus.ERROR
                        device_store.upsert(device)

                except Exception as e:
                    job.progress[ip] = "error"
                    job.errors[ip] = str(e)
                    logger.error(f"Flash failed for {ip}: {e}")

                await broadcast_flash_progress(job_id, job.progress)

        tasks = [flash_one(ip) for ip in request.target_ips]
        await asyncio.gather(*tasks, return_exceptions=True)

        job.status = "complete"
        job.completed_at = datetime.utcnow()
        await broadcast_flash_progress(job_id, job.progress)
        logger.info(f"Flash job {job_id} complete")

    background_tasks.add_task(run_flash_job)

    return {
        "status": "started",
        "job_id": job_id,
        "targets": len(request.target_ips),
        "firmware": pkg.filename,
    }


@router.get("/jobs/{job_id}")
async def get_flash_job(job_id: str):
    """Get flash job status"""
    job = _flash_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Flash job not found")
    return job


@router.get("/jobs/")
async def list_flash_jobs():
    """List all flash jobs"""
    return list(_flash_jobs.values())
