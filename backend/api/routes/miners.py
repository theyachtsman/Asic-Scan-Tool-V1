"""
Miners API Routes - CRUD and control operations
NOTE: Static/bulk routes MUST be defined before /{device_id} parameterized routes
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.device_store import device_store
from core.models import MinerDevice, MinerStatus

logger = logging.getLogger(__name__)
router = APIRouter()


class BulkActionRequest(BaseModel):
    device_ids: List[str]
    action: str  # reboot, shutdown


class BulkDeleteRequest(BaseModel):
    device_ids: List[str]


class UpdateDeviceRequest(BaseModel):
    location: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    username: Optional[str] = None
    password: Optional[str] = None


# ─── Static / collection routes (MUST come before /{device_id}) ──────────────

@router.get("/", response_model=List[MinerDevice])
async def get_all_miners():
    """Get all discovered miners"""
    return device_store.get_all()


@router.delete("/")
async def clear_all_miners():
    """Clear all miners from store"""
    device_store.clear()
    return {"status": "cleared"}


@router.get("/summary")
async def get_summary():
    """Get aggregate stats"""
    return device_store.summary_stats()


@router.post("/bulk/action")
async def bulk_action(request: BulkActionRequest):
    """Perform bulk action on multiple miners"""
    results = {}

    async def process_device(device_id: str):
        device = device_store.get(device_id)
        if not device:
            results[device_id] = {"status": "error", "message": "Not found"}
            return

        try:
            if request.action == "reboot":
                success = await _reboot_device(device)
                if success:
                    device.status = MinerStatus.REBOOTING
                    device_store.upsert(device)
                results[device_id] = {"status": "rebooting" if success else "failed", "ip": device.ip}

            elif request.action == "shutdown":
                success = await _shutdown_device(device)
                results[device_id] = {"status": "shutdown" if success else "failed", "ip": device.ip}

            else:
                results[device_id] = {"status": "error", "message": f"Unknown action: {request.action}"}

        except Exception as e:
            results[device_id] = {"status": "error", "message": str(e)}

    tasks = [process_device(did) for did in request.device_ids]
    await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "action": request.action,
        "total": len(request.device_ids),
        "results": results,
    }


@router.post("/bulk/delete")
async def bulk_delete_miners(request: BulkDeleteRequest):
    """Remove multiple miners from the store"""
    deleted = []
    not_found = []
    for device_id in request.device_ids:
        if device_store.delete(device_id):
            deleted.append(device_id)
        else:
            not_found.append(device_id)
    logger.info(f"Bulk delete: {len(deleted)} deleted, {len(not_found)} not found")
    return {
        "status": "ok",
        "deleted": len(deleted),
        "not_found": len(not_found),
        "deleted_ids": deleted,
    }


# ─── Per-device routes (parameterized, MUST come after static routes) ─────────

@router.get("/{device_id}", response_model=MinerDevice)
async def get_miner(device_id: str):
    """Get a specific miner by ID"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")
    return device


@router.patch("/{device_id}")
async def update_miner(device_id: str, request: UpdateDeviceRequest):
    """Update miner metadata"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")

    if request.location is not None:
        device.location = request.location
    if request.notes is not None:
        device.notes = request.notes
    if request.tags is not None:
        device.tags = request.tags
    if request.username is not None:
        device.username = request.username
    if request.password is not None:
        device.password = request.password

    device_store.upsert(device)
    return {"status": "updated", "device_id": device_id}


@router.delete("/{device_id}")
async def delete_miner(device_id: str):
    """Remove a miner from the store"""
    if not device_store.delete(device_id):
        raise HTTPException(status_code=404, detail="Miner not found")
    return {"status": "deleted", "device_id": device_id}


@router.post("/{device_id}/refresh")
async def refresh_miner(device_id: str):
    """Refresh stats for a single miner"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")

    try:
        from discovery.miner_identifier import MinerIdentifier
        identifier = MinerIdentifier()
        updated = await identifier.identify(
            ip=device.ip,
            mac=device.mac,
            timeout=10.0,
            username=device.username,
            password=device.password,
            collect_stats=True,
        )
        if updated:
            updated.id = device.id
            device_store.upsert(updated)
            return {"status": "refreshed", "device": updated}
    except Exception as e:
        logger.error(f"Refresh failed for {device.ip}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "failed"}


@router.post("/{device_id}/reboot")
async def reboot_miner(device_id: str):
    """Reboot a single miner"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")

    success = await _reboot_device(device)
    if success:
        device.status = MinerStatus.REBOOTING
        device_store.upsert(device)
        return {"status": "rebooting", "ip": device.ip}
    else:
        raise HTTPException(status_code=500, detail="Reboot command failed")


@router.post("/{device_id}/shutdown")
async def shutdown_miner(device_id: str):
    """Shutdown a single miner"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")

    success = await _shutdown_device(device)
    if success:
        return {"status": "shutdown", "ip": device.ip}
    else:
        raise HTTPException(status_code=500, detail="Shutdown command failed")


@router.get("/{device_id}/logs")
async def get_miner_logs(device_id: str, lines: int = 20):
    """Fetch last N lines of logs from a miner via SSH or HTTP"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")

    log_lines = []

    # Try Bitmain/Antminer log endpoint
    try:
        import httpx
        from core.models import MinerBrand
        auth = None
        if device.username and device.password:
            auth = (device.username, device.password)

        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            # Try common log endpoints
            endpoints = [
                f"http://{device.ip}/cgi-bin/get_kernel_log.cgi",
                f"http://{device.ip}/cgi-bin/log.cgi",
                f"http://{device.ip}/api/v1/logs",
                f"http://{device.ip}/cgi-bin/luci/admin/status/syslog",
            ]
            for endpoint in endpoints:
                try:
                    kwargs = {"auth": httpx.DigestAuth(*auth)} if auth else {}
                    resp = await client.get(endpoint, **kwargs)
                    if resp.status_code == 200 and resp.text.strip():
                        raw = resp.text.strip()
                        all_lines = [l for l in raw.splitlines() if l.strip()]
                        log_lines = all_lines[-lines:]
                        break
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Log fetch failed for {device.ip}: {e}")

    # Try CGMiner API for summary/stats as "logs"
    if not log_lines:
        try:
            import asyncio, json
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(device.ip, 4028), timeout=5.0
            )
            # Use 'summary' command which is universally supported
            writer.write(b'{"command":"summary"}')
            await writer.drain()
            data = b""
            try:
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=2.0)
                    if not chunk: break
                    data += chunk
                    if b"\x00" in chunk: break
            except asyncio.TimeoutError:
                pass
            writer.close()
            if data:
                text = data.decode("utf-8", errors="ignore").rstrip("\x00").strip()
                parsed = json.loads(text)
                # Format summary as log-like output
                if "SUMMARY" in parsed and parsed["SUMMARY"]:
                    s = parsed["SUMMARY"][0]
                    log_lines = [
                        f"[Summary] Elapsed: {s.get('Elapsed', 0)}s",
                        f"[Summary] Hashrate: {s.get('GHS 5s', 0):.2f} GH/s (5s), {s.get('GHS av', 0):.2f} GH/s (avg)",
                        f"[Summary] HW Errors: {s.get('Hardware Errors', 0)}",
                        f"[Summary] Uptime: {s.get('Elapsed', 0) // 3600}h {(s.get('Elapsed', 0) % 3600) // 60}m",
                    ]
                else:
                    log_lines = [f"CGMiner response: {text[:500]}"]
        except Exception as e:
            log_lines = [f"CGMiner connection failed: {str(e)}"]

    if not log_lines:
        log_lines = [f"[{device.ip}] No logs available via HTTP API.",
                     "Logs may require SSH access or a supported firmware version."]

    return {
        "device_id": device_id,
        "ip": device.ip,
        "lines": log_lines,
        "count": len(log_lines),
    }


@router.get("/{device_id}/raw-api")
async def get_raw_api_data(device_id: str):
    """Get raw API data from miner"""
    device = device_store.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Miner not found")

    if device.stats and device.stats.raw_data:
        return device.stats.raw_data

    return {"message": "No raw data available. Try refreshing the miner."}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _reboot_device(device: MinerDevice) -> bool:
    """Helper to reboot a device based on brand"""
    from core.models import MinerBrand
    try:
        if device.brand == MinerBrand.BITMAIN or device.brand == "Bitmain":
            from api_collectors.bitmain_collector import BitmainCollector
            collector = BitmainCollector()
            return await collector.reboot(device.ip, device.username, device.password)
        elif device.brand == MinerBrand.CANAAN or device.brand == "Canaan":
            from api_collectors.canaan_collector import CanaanCollector
            collector = CanaanCollector()
            return await collector.reboot(device.ip, device.username, device.password)
        elif device.brand == MinerBrand.BITDEER or device.brand == "Bitdeer":
            from api_collectors.bitdeer_collector import BitdeerCollector
            collector = BitdeerCollector()
            return await collector.reboot(device.ip, device.username, device.password)
    except Exception as e:
        logger.error(f"Reboot failed for {device.ip}: {e}")
    return False


async def _shutdown_device(device: MinerDevice) -> bool:
    """Helper to shutdown a device based on brand"""
    from core.models import MinerBrand
    try:
        if device.brand == MinerBrand.BITMAIN or device.brand == "Bitmain":
            from api_collectors.bitmain_collector import BitmainCollector
            collector = BitmainCollector()
            return await collector.shutdown(device.ip, device.username, device.password)
        elif device.brand == MinerBrand.CANAAN or device.brand == "Canaan":
            from api_collectors.canaan_collector import CanaanCollector
            collector = CanaanCollector()
            return await collector.shutdown(device.ip, device.username, device.password)
        elif device.brand == MinerBrand.BITDEER or device.brand == "Bitdeer":
            from api_collectors.bitdeer_collector import BitdeerCollector
            collector = BitdeerCollector()
            return await collector.shutdown(device.ip, device.username, device.password)
    except Exception as e:
        logger.error(f"Shutdown failed for {device.ip}: {e}")
    return False
