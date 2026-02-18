"""
Bitmain Antminer API Collector
Supports: Stock firmware, Braiins OS, VNish, LuxOS
Protocols: CGMiner TCP API (port 4028) + HTTP REST API
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


class BitmainCollector:
    """
    Collects full statistics from Bitmain Antminer devices.
    Tries CGMiner TCP API first, then HTTP API.
    """

    CGMINER_PORT = 4028

    async def collect(
        self,
        ip: str,
        username: str = "root",
        password: str = "root",
        timeout: float = 10.0,
    ) -> Optional[MinerStats]:
        """Collect full stats from a Bitmain miner"""

        # Try CGMiner TCP API first (most reliable)
        stats = await self._collect_cgminer(ip, timeout)
        if stats:
            return stats

        # Fall back to HTTP API
        stats = await self._collect_http(ip, username, password, timeout)
        return stats

    async def _cgminer_command(
        self, ip: str, command: str, parameter: str = "", timeout: float = 5.0
    ) -> Optional[Dict]:
        """Send a command to CGMiner TCP API"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, self.CGMINER_PORT),
                timeout=timeout,
            )

            payload = {"command": command}
            if parameter:
                payload["parameter"] = parameter

            writer.write(json.dumps(payload).encode())
            await writer.drain()

            # Read response (may come in chunks)
            data = b""
            try:
                while True:
                    chunk = await asyncio.wait_for(reader.read(8192), timeout=2.0)
                    if not chunk:
                        break
                    data += chunk
                    if b"\x00" in chunk:
                        break
            except asyncio.TimeoutError:
                pass

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            if data:
                text = data.decode("utf-8", errors="ignore").rstrip("\x00").strip()
                return json.loads(text)

        except Exception as e:
            logger.debug(f"CGMiner command '{command}' failed for {ip}: {e}")

        return None

    async def _collect_cgminer(self, ip: str, timeout: float) -> Optional[MinerStats]:
        """Collect stats via CGMiner TCP API"""
        try:
            # Fetch all needed data concurrently
            summary_task = self._cgminer_command(ip, "summary", timeout=timeout)
            stats_task = self._cgminer_command(ip, "stats", timeout=timeout)
            pools_task = self._cgminer_command(ip, "pools", timeout=timeout)
            version_task = self._cgminer_command(ip, "version", timeout=timeout)

            summary_resp, stats_resp, pools_resp, version_resp = await asyncio.gather(
                summary_task, stats_task, pools_task, version_task,
                return_exceptions=True,
            )

            if not summary_resp or isinstance(summary_resp, Exception):
                return None

            stats = MinerStats(last_updated=datetime.utcnow())

            # Parse SUMMARY
            summary = summary_resp.get("SUMMARY", [{}])[0] if summary_resp.get("SUMMARY") else {}
            stats.hashrate_rt = self._parse_hashrate(summary.get("GHS 5s", 0))
            stats.hashrate_avg = self._parse_hashrate(summary.get("GHS av", 0))
            stats.uptime_seconds = int(summary.get("Elapsed", 0))
            stats.uptime_str = self._format_uptime(stats.uptime_seconds)
            stats.total_hw_errors = int(summary.get("Hardware Errors", 0))
            accepted = int(summary.get("Accepted", 0))
            rejected = int(summary.get("Rejected", 0))
            total = accepted + rejected
            stats.hw_error_rate = (stats.total_hw_errors / max(total, 1)) * 100

            # Parse STATS (hashboards, temps, fans)
            if stats_resp and not isinstance(stats_resp, Exception):
                stats_list = stats_resp.get("STATS", [])
                for stat_block in stats_list:
                    if stat_block.get("Type") in ["Antminer", ""] or "chain_acs" in str(stat_block):
                        self._parse_stats_block(stat_block, stats)

            # Parse POOLS
            if pools_resp and not isinstance(pools_resp, Exception):
                pools_list = pools_resp.get("POOLS", [])
                for pool_data in pools_list:
                    pool = PoolInfo(
                        url=pool_data.get("URL", ""),
                        user=pool_data.get("User", ""),
                        status=pool_data.get("Status", ""),
                        priority=int(pool_data.get("Priority", 0)),
                        accepted=int(pool_data.get("Accepted", 0)),
                        rejected=int(pool_data.get("Rejected", 0)),
                        stale=int(pool_data.get("Stale", 0)),
                        diff=str(pool_data.get("Diff", "")),
                    )
                    stats.pools.append(pool)
                    if pool_data.get("Stratum Active") or pool_data.get("Status") == "Alive":
                        stats.active_pool = pool.url
                        stats.worker_name = pool.user

            # Parse VERSION
            if version_resp and not isinstance(version_resp, Exception):
                version_list = version_resp.get("VERSION", [{}])
                version_info = version_list[0] if version_list else {}
                stats.firmware_version = version_info.get("CompileTime", "")
                stats.firmware_type = detect_firmware_from_version(stats.firmware_version)

            # Calculate efficiency
            if stats.hashrate_avg > 0 and stats.power_consumption > 0:
                stats.efficiency = stats.power_consumption / stats.hashrate_avg

            return stats

        except Exception as e:
            logger.debug(f"CGMiner collection failed for {ip}: {e}")
            return None

    def _parse_stats_block(self, block: Dict, stats: MinerStats):
        """Parse a STATS block for hashboard/temp/fan data"""
        temps = []
        fans = []
        hashboards = []

        # Extract all temp/fan/chain data
        for key, value in block.items():
            key_lower = key.lower()

            # Temperature fields
            if "temp" in key_lower and isinstance(value, (int, float)) and value > 0:
                temps.append(float(value))

            # Fan speed fields
            if "fan" in key_lower and isinstance(value, (int, float)) and value > 0:
                fans.append(int(value))

            # Power consumption - Antminer uses various field names
            if key_lower in [
                "power", "power_consumption", "watt", "watts",
                "power_rt", "power_real", "power_avg",
                "mac_power_consumption", "power_use",
            ]:
                if isinstance(value, (int, float)) and float(value) > 0:
                    stats.power_consumption = float(value)

        # Parse chain data (hashboards)
        chain_count = 0
        for i in range(1, 10):
            chain_key = f"chain_acn{i}"
            if chain_key in block:
                chain_count = max(chain_count, i)

        for i in range(1, chain_count + 1):
            chips_active = int(block.get(f"chain_acn{i}", 0))
            if chips_active == 0:
                continue

            board = HashboardInfo(
                index=i - 1,
                chips_active=chips_active,
                chips_total=chips_active,
            )

            # Temperature for this chain
            temp_key = f"temp{i}"
            temp2_key = f"temp2_{i}"
            if temp_key in block:
                board.temp_pcb = float(block[temp_key])
            if temp2_key in block:
                board.temp_chip = float(block[temp2_key])

            # Hashrate for this chain
            chain_rate = block.get(f"chain_rate{i}", 0)
            if chain_rate:
                board.hashrate_rt = float(chain_rate) / 1000  # Convert GH to TH

            hashboards.append(board)

        if hashboards:
            stats.hashboards = hashboards

        if temps:
            stats.temps = temps
            stats.temp_max = max(temps)
            stats.temp_min = min(temps)
            stats.temp_avg = sum(temps) / len(temps)

        if fans:
            stats.fan_speeds = fans
            stats.fan_speed_avg = int(sum(fans) / len(fans))

    async def _collect_http(
        self, ip: str, username: str, password: str, timeout: float
    ) -> Optional[MinerStats]:
        """Collect stats via Bitmain HTTP API"""
        auth = httpx.DigestAuth(username, password)
        stats = MinerStats(last_updated=datetime.utcnow())

        endpoints = {
            "summary": f"http://{ip}/cgi-bin/summary.cgi",
            "stats": f"http://{ip}/cgi-bin/stats.cgi",
            "pools": f"http://{ip}/cgi-bin/pools.cgi",
            "sysinfo": f"http://{ip}/cgi-bin/get_system_info.cgi",
        }

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            results = {}
            for key, url in endpoints.items():
                try:
                    resp = await client.get(url, auth=auth)
                    if resp.status_code == 200:
                        results[key] = resp.json()
                except Exception:
                    pass

        if not results:
            return None

        # Parse system info
        sysinfo = results.get("sysinfo", {})
        if sysinfo:
            stats.firmware_version = sysinfo.get("firmware_version", "")
            stats.firmware_type = detect_firmware_from_version(stats.firmware_version)
            stats.mac_address = sysinfo.get("macaddr", "")
            stats.hostname = sysinfo.get("hostname", "")

        # Parse summary
        summary_data = results.get("summary", {})
        if summary_data:
            summary = summary_data.get("SUMMARY", [{}])[0] if summary_data.get("SUMMARY") else summary_data
            stats.hashrate_rt = self._parse_hashrate(summary.get("GHS 5s", 0))
            stats.hashrate_avg = self._parse_hashrate(summary.get("GHS av", 0))
            stats.uptime_seconds = int(summary.get("Elapsed", 0))
            stats.uptime_str = self._format_uptime(stats.uptime_seconds)

        # Parse pools
        pools_data = results.get("pools", {})
        if pools_data:
            for pool_data in pools_data.get("POOLS", []):
                pool = PoolInfo(
                    url=pool_data.get("URL", ""),
                    user=pool_data.get("User", ""),
                    status=pool_data.get("Status", ""),
                    accepted=int(pool_data.get("Accepted", 0)),
                    rejected=int(pool_data.get("Rejected", 0)),
                )
                stats.pools.append(pool)
                if pool_data.get("Stratum Active"):
                    stats.active_pool = pool.url
                    stats.worker_name = pool.user

        stats.raw_data = results
        return stats

    async def reboot(self, ip: str, username: str = "root", password: str = "root", timeout: float = 10.0) -> bool:
        """Reboot the miner"""
        # Try CGMiner restart command
        result = await self._cgminer_command(ip, "restart", timeout=timeout)
        if result:
            return True

        # Try HTTP reboot
        auth = httpx.DigestAuth(username, password)
        endpoints = [
            f"http://{ip}/cgi-bin/reboot.cgi",
            f"http://{ip}/api/v1/reboot",
        ]
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in endpoints:
                try:
                    resp = await client.post(endpoint, auth=auth)
                    if resp.status_code in [200, 204]:
                        return True
                except Exception:
                    pass
        return False

    async def shutdown(self, ip: str, username: str = "root", password: str = "root", timeout: float = 10.0) -> bool:
        """Shutdown/stop mining"""
        result = await self._cgminer_command(ip, "quit", timeout=timeout)
        if result:
            return True

        auth = httpx.DigestAuth(username, password)
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            try:
                resp = await client.post(
                    f"http://{ip}/cgi-bin/shutdown.cgi", auth=auth
                )
                return resp.status_code in [200, 204]
            except Exception:
                return False

    async def flash_firmware(
        self,
        ip: str,
        firmware_path: str,
        username: str = "root",
        password: str = "root",
        timeout: float = 300.0,
        progress_callback=None,
    ) -> bool:
        """Flash firmware to the miner"""
        auth = httpx.DigestAuth(username, password)

        try:
            with open(firmware_path, "rb") as f:
                firmware_data = f.read()

            if progress_callback:
                await progress_callback(10, "Uploading firmware...")

            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                files = {"firmware": ("firmware.bin", firmware_data, "application/octet-stream")}
                resp = await client.post(
                    f"http://{ip}/cgi-bin/upgrade.cgi",
                    auth=auth,
                    files=files,
                )

                if resp.status_code in [200, 204]:
                    if progress_callback:
                        await progress_callback(100, "Firmware uploaded successfully")
                    return True

        except Exception as e:
            logger.error(f"Firmware flash failed for {ip}: {e}")

        return False

    def _parse_hashrate(self, value) -> float:
        """Convert GH/s to TH/s"""
        try:
            ghs = float(value)
            return ghs / 1000.0  # GH/s -> TH/s
        except (ValueError, TypeError):
            return 0.0

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime seconds to human readable"""
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
