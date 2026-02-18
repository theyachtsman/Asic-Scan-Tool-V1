"""
Device Store - In-memory store for discovered miners with persistence
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.models import MinerDevice, MinerStatus

logger = logging.getLogger(__name__)


class DeviceStore:
    """
    Thread-safe in-memory store for miner devices.
    Persists to JSON file for session recovery.
    """

    def __init__(self):
        self._devices: Dict[str, MinerDevice] = {}  # id -> MinerDevice
        self._store_file: Optional[Path] = None

        try:
            from core.config import settings
            self._store_file = settings.DATA_DIR / "devices.json"
            self._load()
        except Exception as e:
            logger.warning(f"Could not load device store: {e}")

    def _load(self):
        """Load devices from disk"""
        if self._store_file and self._store_file.exists():
            try:
                with open(self._store_file, "r") as f:
                    data = json.load(f)
                for item in data:
                    device = MinerDevice(**item)
                    self._devices[device.id] = device
                logger.info(f"Loaded {len(self._devices)} devices from store")
            except Exception as e:
                logger.warning(f"Failed to load device store: {e}")

    def _save(self):
        """Persist devices to disk"""
        if self._store_file:
            try:
                data = [d.model_dump(mode="json") for d in self._devices.values()]
                with open(self._store_file, "w") as f:
                    json.dump(data, f, indent=2, default=str)
            except Exception as e:
                logger.warning(f"Failed to save device store: {e}")

    def upsert(self, device: MinerDevice):
        """Add or update a device"""
        if device.id in self._devices:
            existing = self._devices[device.id]
            # Preserve first_seen
            device.first_seen = existing.first_seen or device.first_seen
            # Preserve user-set fields
            if not device.location:
                device.location = existing.location
            if not device.notes:
                device.notes = existing.notes
            if not device.tags:
                device.tags = existing.tags
        self._devices[device.id] = device
        self._save()

    def upsert_many(self, devices: List[MinerDevice]):
        """Bulk upsert"""
        for device in devices:
            self.upsert(device)

    def get(self, device_id: str) -> Optional[MinerDevice]:
        """Get device by ID"""
        return self._devices.get(device_id)

    def get_by_ip(self, ip: str) -> Optional[MinerDevice]:
        """Get device by IP address"""
        for device in self._devices.values():
            if device.ip == ip:
                return device
        return None

    def get_all(self) -> List[MinerDevice]:
        """Get all devices"""
        return list(self._devices.values())

    def get_online(self) -> List[MinerDevice]:
        """Get only online devices"""
        return [d for d in self._devices.values() if d.status == MinerStatus.ONLINE]

    def delete(self, device_id: str) -> bool:
        """Remove a device"""
        if device_id in self._devices:
            del self._devices[device_id]
            self._save()
            return True
        return False

    def clear(self):
        """Clear all devices"""
        self._devices.clear()
        self._save()

    def mark_offline(self, device_id: str):
        """Mark a device as offline"""
        if device_id in self._devices:
            self._devices[device_id].status = MinerStatus.OFFLINE
            self._devices[device_id].is_reachable = False
            self._save()

    def count(self) -> int:
        return len(self._devices)

    def count_online(self) -> int:
        return sum(1 for d in self._devices.values() if d.status == MinerStatus.ONLINE)

    def summary_stats(self) -> dict:
        """Get aggregate stats across all miners"""
        devices = self.get_all()
        online = [d for d in devices if d.status == MinerStatus.ONLINE]

        total_hashrate = sum(
            d.stats.hashrate_rt for d in online if d.stats
        )
        total_power = sum(
            d.stats.power_consumption for d in online if d.stats
        )

        brands = {}
        for d in devices:
            brand = d.brand if isinstance(d.brand, str) else d.brand.value
            brands[brand] = brands.get(brand, 0) + 1

        return {
            "total": len(devices),
            "online": len(online),
            "offline": len(devices) - len(online),
            "total_hashrate_ths": round(total_hashrate, 2),
            "total_power_watts": round(total_power, 2),
            "brands": brands,
        }


# Global device store instance
device_store = DeviceStore()
