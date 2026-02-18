"""
Bitdeer Sealminer API Collector
Supports: Sealminer A1, A2 series
Protocols: HTTP REST API (JSON)
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from core.models import (
    FirmwareType,
    HashboardInfo,
    MinerStats,
    PoolInfo,
)
from discovery.miner_identifier import detect_firmware_from_version

logger = logging.getLogger(__name__)


class BitdeerCollector:
    """
    Collects full statistics from Bitdeer Sealminer devices.
    Sealminer uses a modern REST JSON API.
    """

    async def collect(
        self,
        ip: str,
        username: str = "admin",
        password: str = "admin",
        timeout: float = 10.0,
    ) -> Optional[MinerStats]:
        """Collect full stats from a Bitdeer Sealminer"""

        # Get auth token first
        token = await self._authenticate(ip, username, password, timeout)

        # Collect all data
        stats = await self._collect_all(ip, token, timeout)
        return stats

    async def _authenticate(
        self, ip: str, username: str, password: str, timeout: float
    ) -> Optional[str]:
        """Authenticate and get session token"""
        auth_endpoints = [
            f"http://{ip}/api/v1/auth/login",
            f"http://{ip}/api/auth",
            f"http://{ip}/api/v1/login",
        ]

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in auth_endpoints:
                try:
                    resp = await client.post(
                        endpoint,
                        json={"username": username, "password": password},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        token = (
                            data.get("token")
                            or data.get("access_token")
                            or data.get("data", {}).get("token")
                        )
                        if token:
                            return token
                except Exception:
                    pass

        return None

    async def _collect_all(
        self, ip: str, token: Optional[str], timeout: float
    ) -> Optional[MinerStats]:
        """Collect all stats from Sealminer"""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        stats = MinerStats(last_updated=datetime.utcnow())

        # API endpoints to query
        api_map = {
            "summary": f"http://{ip}/api/v1/summary",
            "hashrate": f"http://{ip}/api/v1/hashrate",
            "pools": f"http://{ip}/api/v1/pools",
            "system": f"http://{ip}/api/v1/system",
            "fans": f"http://{ip}/api/v1/fans",
            "temps": f"http://{ip}/api/v1/temperatures",
            "power": f"http://{ip}/api/v1/power",
            "boards": f"http://{ip}/api/v1/hashboards",
        }

        results = {}
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for key, url in api_map.items():
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        results[key] = resp.json()
                    elif resp.status_code == 401 and not token:
                        # Try without auth
                        resp2 = await client.get(url)
                        if resp2.status_code == 200:
                            results[key] = resp2.json()
                except Exception:
                    pass

        if not results:
            # Try legacy endpoint format
            return await self._collect_legacy(ip, token, timeout)

        # Parse summary
        summary = results.get("summary", {})
        if summary:
            data = summary.get("data", summary)
            stats.hashrate_rt = self._parse_hashrate_ths(data.get("hashrate_rt", data.get("hashrate", 0)))
            stats.hashrate_avg = self._parse_hashrate_ths(data.get("hashrate_avg", data.get("avg_hashrate", 0)))
            stats.uptime_seconds = int(data.get("uptime", 0))
            stats.uptime_str = self._format_uptime(stats.uptime_seconds)

        # Parse hashrate
        hashrate_data = results.get("hashrate", {})
        if hashrate_data and stats.hashrate_rt == 0:
            data = hashrate_data.get("data", hashrate_data)
            stats.hashrate_rt = self._parse_hashrate_ths(data.get("rt", data.get("realtime", 0)))
            stats.hashrate_avg = self._parse_hashrate_ths(data.get("avg", data.get("average", 0)))
            stats.hashrate_ideal = self._parse_hashrate_ths(data.get("ideal", data.get("rated", 0)))

        # Parse pools
        pools_data = results.get("pools", {})
        if pools_data:
            pool_list = pools_data.get("data", pools_data.get("pools", []))
            if isinstance(pool_list, list):
                for pool_item in pool_list:
                    pool = PoolInfo(
                        url=pool_item.get("url", pool_item.get("pool_url", "")),
                        user=pool_item.get("user", pool_item.get("worker", "")),
                        status=pool_item.get("status", ""),
                        accepted=int(pool_item.get("accepted", 0)),
                        rejected=int(pool_item.get("rejected", 0)),
                        diff=str(pool_item.get("diff", "")),
                    )
                    stats.pools.append(pool)
                    if pool_item.get("active") or pool_item.get("status") == "active":
                        stats.active_pool = pool.url
                        stats.worker_name = pool.user

        # Parse system info
        system_data = results.get("system", {})
        if system_data:
            data = system_data.get("data", system_data)
            stats.firmware_version = str(data.get("firmware_version", data.get("fw_version", "")))
            stats.firmware_type = detect_firmware_from_version(stats.firmware_version)
            stats.mac_address = data.get("mac", data.get("mac_address", ""))
            stats.hostname = data.get("hostname", "")

        # Parse fans
        fans_data = results.get("fans", {})
        if fans_data:
            data = fans_data.get("data", fans_data)
            fan_list = data.get("fans", data.get("fan_speeds", []))
            if isinstance(fan_list, list):
                stats.fan_speeds = [int(f.get("speed", f) if isinstance(f, dict) else f) for f in fan_list]
                if stats.fan_speeds:
                    stats.fan_speed_avg = int(sum(stats.fan_speeds) / len(stats.fan_speeds))

        # Parse temperatures
        temps_data = results.get("temps", {})
        if temps_data:
            data = temps_data.get("data", temps_data)
            temp_list = data.get("temperatures", data.get("temps", []))
            if isinstance(temp_list, list):
                stats.temps = [float(t.get("value", t) if isinstance(t, dict) else t) for t in temp_list]
                if stats.temps:
                    stats.temp_max = max(stats.temps)
                    stats.temp_min = min(stats.temps)
                    stats.temp_avg = sum(stats.temps) / len(stats.temps)

        # Parse power
        power_data = results.get("power", {})
        if power_data:
            data = power_data.get("data", power_data)
            stats.power_consumption = float(data.get("consumption", data.get("power", data.get("watt", 0))))
            stats.power_limit = float(data.get("limit", data.get("max_power", 0)))

        # Parse hashboards
        boards_data = results.get("boards", {})
        if boards_data:
            board_list = boards_data.get("data", boards_data.get("hashboards", []))
            if isinstance(board_list, list):
                hashboards = []
                for i, board_item in enumerate(board_list):
                    board = HashboardInfo(
                        index=i,
                        hashrate_rt=self._parse_hashrate_ths(board_item.get("hashrate", 0)),
                        temp_chip=float(board_item.get("temp_chip", board_item.get("chip_temp", 0))),
                        temp_pcb=float(board_item.get("temp_pcb", board_item.get("board_temp", 0))),
                        chips_total=int(board_item.get("chips_total", board_item.get("total_chips", 0))),
                        chips_active=int(board_item.get("chips_active", board_item.get("active_chips", 0))),
                        hw_errors=int(board_item.get("hw_errors", 0)),
                        status=board_item.get("status", "ok"),
                    )
                    hashboards.append(board)
                stats.hashboards = hashboards

        # Calculate efficiency
        if stats.hashrate_avg > 0 and stats.power_consumption > 0:
            stats.efficiency = stats.power_consumption / stats.hashrate_avg

        stats.raw_data = results
        return stats

    async def _collect_legacy(
        self, ip: str, token: Optional[str], timeout: float
    ) -> Optional[MinerStats]:
        """Try legacy/alternative API endpoints"""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        stats = MinerStats(last_updated=datetime.utcnow())

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            # Try combined status endpoint
            for endpoint in [
                f"http://{ip}/api/v1/status",
                f"http://{ip}/api/status",
                f"http://{ip}/status",
            ]:
                try:
                    resp = await client.get(endpoint, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        self._parse_status_response(data, stats)
                        if stats.hashrate_rt > 0:
                            return stats
                except Exception:
                    pass

        return None

    def _parse_status_response(self, data: Dict, stats: MinerStats):
        """Parse a combined status response"""
        # Flatten nested data
        if "data" in data:
            data = data["data"]

        stats.hashrate_rt = self._parse_hashrate_ths(
            data.get("hashrate", data.get("hash_rate", data.get("rt_hashrate", 0)))
        )
        stats.hashrate_avg = self._parse_hashrate_ths(
            data.get("avg_hashrate", data.get("average_hashrate", 0))
        )

        temp = data.get("temperature", data.get("temp", 0))
        if isinstance(temp, (int, float)):
            stats.temp_avg = float(temp)
            stats.temps = [float(temp)]
        elif isinstance(temp, list):
            stats.temps = [float(t) for t in temp]
            stats.temp_max = max(stats.temps)
            stats.temp_avg = sum(stats.temps) / len(stats.temps)

        fan = data.get("fan_speed", data.get("fan", 0))
        if isinstance(fan, (int, float)):
            stats.fan_speeds = [int(fan)]
            stats.fan_speed_avg = int(fan)
        elif isinstance(fan, list):
            stats.fan_speeds = [int(f) for f in fan]
            stats.fan_speed_avg = int(sum(stats.fan_speeds) / len(stats.fan_speeds))

        stats.power_consumption = float(data.get("power", data.get("watt", 0)))
        stats.uptime_seconds = int(data.get("uptime", 0))
        stats.uptime_str = self._format_uptime(stats.uptime_seconds)
        stats.firmware_version = str(data.get("firmware", data.get("fw_version", "")))
        stats.firmware_type = detect_firmware_from_version(stats.firmware_version)

    async def reboot(self, ip: str, username: str = "admin", password: str = "admin", timeout: float = 10.0) -> bool:
        """Reboot the Sealminer"""
        token = await self._authenticate(ip, username, password, timeout)
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in [
                f"http://{ip}/api/v1/system/reboot",
                f"http://{ip}/api/v1/reboot",
                f"http://{ip}/api/reboot",
            ]:
                try:
                    resp = await client.post(endpoint, headers=headers)
                    if resp.status_code in [200, 204]:
                        return True
                except Exception:
                    pass
        return False

    async def shutdown(self, ip: str, username: str = "admin", password: str = "admin", timeout: float = 10.0) -> bool:
        """Shutdown/stop mining on Sealminer"""
        token = await self._authenticate(ip, username, password, timeout)
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in [
                f"http://{ip}/api/v1/mining/stop",
                f"http://{ip}/api/v1/shutdown",
            ]:
                try:
                    resp = await client.post(endpoint, headers=headers)
                    if resp.status_code in [200, 204]:
                        return True
                except Exception:
                    pass
        return False

    async def flash_firmware(
        self,
        ip: str,
        firmware_path: str,
        username: str = "admin",
        password: str = "admin",
        timeout: float = 300.0,
        progress_callback=None,
    ) -> bool:
        """Flash firmware to Sealminer"""
        token = await self._authenticate(ip, username, password, timeout)
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        try:
            with open(firmware_path, "rb") as f:
                firmware_data = f.read()

            if progress_callback:
                await progress_callback(10, "Uploading firmware to Sealminer...")

            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                files = {"file": ("firmware.bin", firmware_data, "application/octet-stream")}
                resp = await client.post(
                    f"http://{ip}/api/v1/firmware/upgrade",
                    headers=headers,
                    files=files,
                )
                if resp.status_code in [200, 202]:
                    if progress_callback:
                        await progress_callback(100, "Firmware uploaded to Sealminer")
                    return True
        except Exception as e:
            logger.error(f"Bitdeer firmware flash failed for {ip}: {e}")
        return False

    def _parse_hashrate_ths(self, value) -> float:
        """Parse hashrate value to TH/s"""
        try:
            v = float(value)
            # If value is very large, it's in H/s
            if v > 1e9:
                return v / 1e12
            # If value is in GH/s range
            elif v > 1000:
                return v / 1000
            # Already in TH/s
            return v
        except (ValueError, TypeError):
            return 0.0

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime"""
        if seconds <= 0:
            return "0s"
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        return " ".join(parts) or "< 1m"
