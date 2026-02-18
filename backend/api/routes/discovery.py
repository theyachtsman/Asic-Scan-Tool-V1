"""
Discovery API Routes
Scan results are stored in a temporary preview store.
Users must explicitly commit results to the device store.
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.device_store import device_store
from core.models import MinerDevice, ScanConfig, ScanProgress
from discovery.network_scanner import scanner

logger = logging.getLogger(__name__)
router = APIRouter()

# Temporary scan result store: scan_id -> List[MinerDevice]
# Results are held here until user explicitly adds them
_scan_results: Dict[str, List[MinerDevice]] = {}


class StartScanRequest(BaseModel):
    ip_ranges: List[str]
    methods: List[str] = ["ping", "arp"]
    ping_timeout: float = 1.0
    api_timeout: float = 5.0
    max_concurrent: int = 100
    collect_stats: bool = True
    username: str = ""
    password: str = ""


class ScanResponse(BaseModel):
    scan_id: str
    status: str
    message: str


class CommitRequest(BaseModel):
    device_ids: Optional[List[str]] = None  # None = commit all


@router.post("/start", response_model=ScanResponse)
async def start_scan(request: StartScanRequest, background_tasks: BackgroundTasks):
    """Start a new network scan. Results are held in preview until committed."""
    scan_id = str(uuid.uuid4())[:8]

    config = ScanConfig(
        ip_ranges=request.ip_ranges,
        methods=request.methods,
        ping_timeout=request.ping_timeout,
        api_timeout=request.api_timeout,
        max_concurrent=request.max_concurrent,
        collect_stats=request.collect_stats,
        username=request.username,
        password=request.password,
    )

    async def run_scan():
        try:
            from api.routes.websocket import broadcast_scan_progress, broadcast_scan_results

            async def on_progress(progress: ScanProgress):
                await broadcast_scan_progress(progress.model_dump())

            devices = await scanner.scan(config, scan_id, progress_callback=on_progress)

            # Store in preview — do NOT auto-add to device_store
            _scan_results[scan_id] = devices

            # Broadcast scan results for preview
            await broadcast_scan_results(scan_id, [d.model_dump(mode="json") for d in devices])
            logger.info(f"Scan {scan_id} complete: {len(devices)} miners found (pending user review)")

        except Exception as e:
            logger.error(f"Scan {scan_id} failed: {e}", exc_info=True)

    background_tasks.add_task(run_scan)

    return ScanResponse(
        scan_id=scan_id,
        status="started",
        message=f"Scan started for {len(request.ip_ranges)} range(s)",
    )


@router.get("/results/{scan_id}")
async def get_scan_results(scan_id: str):
    """Get the discovered devices from a completed scan (preview, not yet committed)"""
    if scan_id not in _scan_results:
        raise HTTPException(status_code=404, detail="Scan results not found or scan still running")
    devices = _scan_results[scan_id]
    return {
        "scan_id": scan_id,
        "count": len(devices),
        "devices": [d.model_dump(mode="json") for d in devices],
    }


@router.post("/commit/{scan_id}")
async def commit_scan_results(scan_id: str, request: CommitRequest):
    """
    Commit selected (or all) scan results to the device store.
    device_ids=None commits all. Pass a list to commit specific devices.
    """
    if scan_id not in _scan_results:
        raise HTTPException(status_code=404, detail="Scan results not found")

    all_devices = _scan_results[scan_id]

    if request.device_ids is None:
        # Commit all
        to_commit = all_devices
    else:
        id_set = set(request.device_ids)
        to_commit = [d for d in all_devices if d.id in id_set]

    device_store.upsert_many(to_commit)

    # Broadcast updated miners list
    try:
        from api.routes.websocket import broadcast_miners_update
        await broadcast_miners_update(device_store.get_all())
    except Exception:
        pass

    logger.info(f"Committed {len(to_commit)} devices from scan {scan_id} to store")
    return {
        "status": "committed",
        "scan_id": scan_id,
        "committed": len(to_commit),
        "total_found": len(all_devices),
    }


@router.delete("/results/{scan_id}")
async def discard_scan_results(scan_id: str):
    """Discard scan results without adding to store"""
    _scan_results.pop(scan_id, None)
    return {"status": "discarded", "scan_id": scan_id}


@router.post("/cancel/{scan_id}")
async def cancel_scan(scan_id: str):
    """Cancel an active scan"""
    scanner.cancel_scan(scan_id)
    return {"status": "cancelled", "scan_id": scan_id}


@router.get("/progress/{scan_id}", response_model=Optional[ScanProgress])
async def get_scan_progress(scan_id: str):
    """Get current scan progress"""
    progress = scanner.get_progress(scan_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Scan not found")
    return progress


@router.get("/active")
async def get_active_scans():
    """Get list of active scan IDs"""
    return {"active_scans": scanner.get_active_scans()}


@router.get("/local-networks")
async def get_local_networks():
    """Detect local network ranges for auto-fill"""
    import socket

    networks = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

        parts = local_ip.split(".")
        if len(parts) == 4:
            base = ".".join(parts[:3])
            networks.append(f"{base}.1-254")
    except Exception:
        networks.append("192.168.1.1-254")

    return {"networks": networks, "suggested": networks[0] if networks else "192.168.1.1-254"}
