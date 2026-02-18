"""
MicroBT Whatsminer API Collector
Supports: Whatsminer M20, M30, M50, M60 series
Protocols: BTMiner TCP API (port 4028) + HTTP API
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx

from core.models import (
    FirmwareType,
    HashboardInfo,
    MinerStats,
    PoolInfo,
)
from discovery.miner_identifier import detect_firmware_from_version

logger = logging.getLogger(__name__)


class MicroBTCollector:
    """
    Collects full statistics from MicroBT Whatsminer devices.
    Whatsminers use BTMiner (CGMiner-compatible) TCP API on port 4028.
    """

    BTMINER_PORT = 4028

    async def collect(
        self,
        ip: str,
        username: str = "admin",
        password: str = "admin",
        timeout: float = 10.0,
    ) -> Optional[MinerStats]:
        """Collect full stats from a Whatsminer"""
        stats = await self._collect_btminer(ip, timeout)
        if stats:
            return stats
        stats = await self._collect_http(ip, username, password, timeout)
        return stats

    async def _btminer_command(self, ip: str, command: str, timeout: float = 5.0) -> Optional[Dict]:
        """Send a command to BTMiner TCP API"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, self.BTMINER_PORT),
                timeout=timeout,
            )
            payload = {"cmd": command}
            writer.write(json.dumps(payload).encode())
            await writer.drain()

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
            logger.debug(f"BTMiner command '{command}' failed for {ip}: {e}")
        return None

    async def _collect_btminer(self, ip: str, timeout: float) -> Optional[MinerStats]:
        """Collect stats via BTMiner TCP API (CGMiner-compatible)"""
        try:
            summary_task = self._btminer_command(ip, "summary", timeout=timeout)
            edevs_task = self._btminer_command(ip, "edevs", timeout=timeout)
            pools_task = self._btminer_command(ip, "pools", timeout=timeout)
            devdetails_task = self._btminer_command(ip, "devdetails", timeout=timeout)

            summary_resp, edevs_resp, pools_resp, devdetails_resp = await asyncio.gather(
                summary_task, edevs_task, pools_task, devdetails_task,
                return_exceptions=True,
            )

            if not summary_resp or isinstance(summary_resp, Exception):
                return None

            stats = MinerStats(last_updated=datetime.utcnow())

            # Parse SUMMARY
            summary_list = summary_resp.get("SUMMARY", [])
            summary = summary_list[0] if summary_list else {}

            stats.hashrate_rt = self._parse_hashrate(summary.get("GHS 5s", summary.get("MHS 5s", 0)))
            stats.hashrate_avg = self._parse_hashrate(summary.get("GHS av", summary.get("MHS av", 0)))
            stats.uptime_seconds = int(summary.get("Elapsed", 0))
            stats.uptime_str = self._format_uptime(stats.uptime_seconds)
            stats.total_hw_errors = int(summary.get("Hardware Errors", 0))

            # Whatsminer reports power in SUMMARY
            power_val = (
                summary.get("Power", 0)
                or summary.get("power", 0)
                or summary.get("Watts", 0)
                or summary.get("watts", 0)
                or summary.get("Power Use", 0)
            )
            if power_val:
                stats.power_consumption = float(power_val)

            # Parse EDEVS (hashboards)
            if edevs_resp and not isinstance(edevs_resp, Exception):
                devs = edevs_resp.get("DEVS", [])
                hashboards = []
                temps = []
                fans = []

                for dev in devs:
                    board = HashboardInfo(
                        index=int(dev.get("ASC", dev.get("GPU", 0))),
                        hashrate_rt=self._parse_hashrate(dev.get("GHS 5s", dev.get("MHS 5s", 0))),
                        hashrate_avg=self._parse_hashrate(dev.get("GHS av", dev.get("MHS av", 0))),
                        temp_chip=float(dev.get("Chip Temp Avg", dev.get("Temperature", 0))),
                        temp_pcb=float(dev.get("PCB Temp Avg", dev.get("Temp", 0))),
                        chips_active=int(dev.get("Effective Chips", dev.get("Chips", 0))),
                        chips_total=int(dev.get("Chip Count", dev.get("Chips", 0))),
                        hw_errors=int(dev.get("Hardware Errors", 0)),
                    )
                    hashboards.append(board)

                    t = board.temp_chip or board.temp_pcb
                    if t > 0:
                        temps.append(t)

                    # Fan speeds from devs
                    for fk in ["Fan Speed In", "Fan Speed Out", "Fan1", "Fan2"]:
                        fv = dev.get(fk, 0)
                        if fv and int(fv) > 0:
                            fans.append(int(fv))

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

            # Parse POOLS
            if pools_resp and not isinstance(pools_resp, Exception):
                for pool_data in pools_resp.get("POOLS", []):
                    pool = PoolInfo(
                        url=pool_data.get("URL", ""),
                        user=pool_data.get("User", ""),
                        status=pool_data.get("Status", ""),
                        priority=int(pool_data.get("Priority", 0)),
                        accepted=int(pool_data.get("Accepted", 0)),
                        rejected=int(pool_data.get("Rejected", 0)),
                        stale=int(pool_data.get("Stale", 0)),
                    )
                    stats.pools.append(pool)
                    if pool_data.get("Stratum Active") or pool_data.get("Status") == "Alive":
                        stats.active_pool = pool.url
                        stats.worker_name = pool.user

            # Parse DEVDETAILS for firmware info
            if devdetails_resp and not isinstance(devdetails_resp, Exception):
                details_list = devdetails_resp.get("DEVDETAILS", [])
                if details_list:
                    detail = details_list[0]
                    stats.firmware_version = detail.get("Driver", "")
                    stats.firmware_type = detect_firmware_from_version(stats.firmware_version)

            # Calculate efficiency
            if stats.hashrate_avg > 0 and stats.power_consumption > 0:
                stats.efficiency = stats.power_consumption / stats.hashrate_avg

            return stats

        except Exception as e:
            logger.debug(f"BTMiner collection failed for {ip}: {e}")
            return None

    async def _collect_http(self, ip: str, username: str, password: str, timeout: float) -> Optional[MinerStats]:
        """Collect stats via Whatsminer HTTP API (fallback)"""
        stats = MinerStats(last_updated=datetime.utcnow())
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.get(
                    f"http://{ip}/api/v1/summary",
                    auth=(username, password),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    stats.hashrate_rt = float(data.get("hashrate", 0)) / 1e12
                    stats.power_consumption = float(data.get("power", 0))
                    stats.uptime_seconds = int(data.get("uptime", 0))
                    stats.uptime_str = self._format_uptime(stats.uptime_seconds)
                    return stats
        except Exception as e:
            logger.debug(f"Whatsminer HTTP collection failed for {ip}: {e}")
        return None

    async def reboot(self, ip: str, username: str = "admin", password: str = "admin", timeout: float = 10.0) -> bool:
        """Reboot the Whatsminer"""
        try:
            result = await self._btminer_command(ip, "restart", timeout=timeout)
            if result:
                return True
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.post(
                    f"http://{ip}/api/v1/reboot",
                    auth=(username, password),
                )
                return resp.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Whatsminer reboot failed for {ip}: {e}")
        return False

    async def shutdown(self, ip: str, username: str = "admin", password: str = "admin", timeout: float = 10.0) -> bool:
        """Shutdown the Whatsminer"""
        try:
            result = await self._btminer_command(ip, "quit", timeout=timeout)
            if result:
                return True
        except Exception as e:
            logger.error(f"Whatsminer shutdown failed for {ip}: {e}")
        return False

    def _parse_hashrate(self, value) -> float:
        """Convert GH/s or MH/s to TH/s"""
        try:
            v = float(value)
            # If value looks like MH/s (very large), convert
            if v > 1_000_000:
                return v / 1_000_000  # MH/s -> TH/s
            return v / 1000.0  # GH/s -> TH/s
        except (ValueError, TypeError):
            return 0.0

    def _format_uptime(self, seconds: int) -> str:
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
