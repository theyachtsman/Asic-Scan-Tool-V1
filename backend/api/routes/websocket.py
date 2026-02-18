"""
WebSocket Routes - Real-time updates to frontend
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients
_clients: Set[WebSocket] = set()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        disconnected = []
        msg_str = json.dumps(message, default=str)

        for connection in self.active_connections:
            try:
                await connection.send_text(msg_str)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to a specific client"""
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception:
            self.disconnect(websocket)


manager = ConnectionManager()


@router.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint"""
    await manager.connect(websocket)

    # Send initial state
    try:
        from core.device_store import device_store
        devices = [d.model_dump(mode="json") for d in device_store.get_all()]
        await manager.send_personal(websocket, {
            "type": "initial_state",
            "data": {
                "miners": devices,
                "summary": device_store.summary_stats(),
            }
        })
    except Exception as e:
        logger.error(f"Failed to send initial state: {e}")

    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                await handle_client_message(websocket, msg)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def handle_client_message(websocket: WebSocket, msg: dict):
    """Handle incoming WebSocket messages from client"""
    msg_type = msg.get("type", "")

    if msg_type == "ping":
        await manager.send_personal(websocket, {"type": "pong"})

    elif msg_type == "get_miners":
        from core.device_store import device_store
        devices = [d.model_dump(mode="json") for d in device_store.get_all()]
        await manager.send_personal(websocket, {
            "type": "miners_update",
            "data": devices,
        })

    elif msg_type == "get_summary":
        from core.device_store import device_store
        await manager.send_personal(websocket, {
            "type": "summary_update",
            "data": device_store.summary_stats(),
        })


async def broadcast_scan_progress(progress: dict):
    """Broadcast scan progress to all clients"""
    await manager.broadcast({
        "type": "scan_progress",
        "data": progress,
    })


async def broadcast_miners_update(devices):
    """Broadcast updated miners list to all clients"""
    from core.device_store import device_store
    device_list = [d.model_dump(mode="json") for d in devices]
    await manager.broadcast({
        "type": "miners_update",
        "data": device_list,
        "summary": device_store.summary_stats(),
    })


async def broadcast_flash_progress(job_id: str, progress: dict):
    """Broadcast firmware flash progress"""
    await manager.broadcast({
        "type": "flash_progress",
        "job_id": job_id,
        "data": progress,
    })


async def broadcast_scan_results(scan_id: str, devices: list):
    """Broadcast scan results (preview) to all clients"""
    await manager.broadcast({
        "type": "scan_results",
        "scan_id": scan_id,
        "data": devices,
        "count": len(devices),
    })


async def broadcast_alert(alert_type: str, message: str, device_ip: str = ""):
    """Broadcast an alert to all clients"""
    await manager.broadcast({
        "type": "alert",
        "alert_type": alert_type,
        "message": message,
        "device_ip": device_ip,
    })
