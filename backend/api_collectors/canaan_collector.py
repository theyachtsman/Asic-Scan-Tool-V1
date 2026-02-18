"""
Canaan Avalon API Collector
Supports: Avalon series miners (Avalon Made, AvalonMiner)
Protocols: CGMiner TCP API (port 4028) + HTTP REST API + LuCI web interface
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


class CanaanCollector:
    """
    Collects full statistics from Canaan Avalon devices.
    Avalon miners use a custom CGMiner-based API with specific field names.
    """

    CGMINER_PORT = 4028

    async def collect(
        self,
        ip: str,
        username: str = "admin",
        password: str = "admin",
        timeout: float = 10.0,
    ) -> Optional[MinerStats]:
        """Collect full stats from a Canaan Avalon miner"""

        # Try CGMiner TCP API first
        stats = await self._collect_cgminer(ip, timeout)
        if stats:
            return stats

        # Try HTTP API (newer Avalon models)
        stats = await self._collect_http(ip, username, password, timeout)
        return stats

    async def _cgminer_command(
        self, ip: str, command: str, parameter: str = "", timeout: float = 5.0
    ) -> Optional[Dict]:
        """Send command to Avalon CGMiner API"""
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
            logger.debug(f"Canaan CGMiner command '{command}' failed for {ip}: {e}")

        return None

    async def _collect_cgminer(self, ip: str, timeout: float) -> Optional[MinerStats]:
        """Collect stats via CGMiner TCP API"""
        try:
            summary_resp, stats_resp, pools_resp, version_resp = await asyncio.gather(
                self._cgminer_command(ip, "summary", timeout=timeout),
                self._cgminer_command(ip, "stats", timeout=timeout),
                self._cgminer_command(ip, "pools", timeout=timeout),
                self._cgminer_command(ip, "version", timeout=timeout),
                return_exceptions=True,
            )

            if not summary_resp or isinstance(summary_resp, Exception):
                return None

            stats = MinerStats(last_updated=datetime.utcnow())

            # Parse SUMMARY
            summary_list = summary_resp.get("SUMMARY", [])
            summary = summary_list[0] if summary_list else {}

            # Debug log the summary response
            logger.info(f"[Canaan] {ip} SUMMARY keys: {list(summary.keys())}")
            logger.debug(f"[Canaan] {ip} SUMMARY data: {summary}")

            # Avalon uses different field names - try multiple variants
            # GHS 5s = GH/s 5 second average, MHS 5s = MH/s 5 second average
            # Avalon also uses MHS 30s, MHS 1m, MHS 5m for different time windows
            hashrate_rt = (
                summary.get("GHS 5s") or summary.get("GHS 5m") or 
                summary.get("MHS 5s") or summary.get("MHS 30s") or 
                summary.get("MHS 1m") or 0
            )
            hashrate_av = summary.get("GHS av") or summary.get("GHS avg") or summary.get("MHS av", 0)
            
            logger.info(f"[Canaan] {ip} hashrate_rt={hashrate_rt}, hashrate_av={hashrate_av}")
            
            # Convert to TH/s (from GH/s or MH/s)
            # Check if values are in MH/s range (typically > 1000000 for TH/s miners)
            if hashrate_rt > 1000000:  # MH/s value
                stats.hashrate_rt = float(hashrate_rt) / 1000000.0  # MH/s to TH/s
            else:
                stats.hashrate_rt = self._parse_hashrate(hashrate_rt)
                
            if hashrate_av > 1000000:  # MH/s value
                stats.hashrate_avg = float(hashrate_av) / 1000000.0
            else:
                stats.hashrate_avg = self._parse_hashrate(hashrate_av)
            
            stats.uptime_seconds = int(summary.get("Elapsed", 0))
            stats.uptime_str = self._format_uptime(stats.uptime_seconds)
            stats.total_hw_errors = int(summary.get("Hardware Errors", 0))

            # Parse STATS - Avalon specific fields
            if stats_resp and not isinstance(stats_resp, Exception):
                stats_list = stats_resp.get("STATS", [])
                for block in stats_list:
                    self._parse_avalon_stats(block, stats)

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

            # Parse VERSION
            if version_resp and not isinstance(version_resp, Exception):
                version_list = version_resp.get("VERSION", [{}])
                version_info = version_list[0] if version_list else {}
                stats.firmware_version = (
                    version_info.get("CompileTime", "")
                    or version_info.get("Miner", "")
                )
                stats.firmware_type = detect_firmware_from_version(stats.firmware_version)

            return stats

        except Exception as e:
            logger.debug(f"Canaan CGMiner collection failed for {ip}: {e}")
            return None

    def _parse_avalon_stats(self, block: Dict, stats: MinerStats):
        """Parse Avalon-specific STATS block"""
        # Avalon uses MM (module manager) data format
        # Example: "MM ID0" contains temp/fan/hashrate data

        temps = []
        fans = []
        hashboards = []

        for key, value in block.items():
            key_lower = key.lower()

            # Avalon temperature fields: Temp, TMax, TAvg
            if key in ["Temp", "TMax", "TAvg"] and isinstance(value, (int, float)):
                if value > 0:
                    temps.append(float(value))

            # Avalon fan fields: Fan1, Fan2, FanR, Fan
            if re.match(r"fan\d*", key_lower) or key_lower == "fan":
                if isinstance(value, (int, float)) and value > 0:
                    fans.append(int(value))

            # Power - try multiple field names
            if key in ["PS", "Power", "InputPower", "power", "PowerConsumption"] and isinstance(value, (int, float)):
                if value > 0:
                    stats.power_consumption = float(value)

            # MAC address
            if key in ["MAC", "MacAddr", "mac", "MACAddr"] and isinstance(value, str):
                stats.mac_address = value

        # Parse MM (module) data - Avalon specific
        # MM data is often in format: "MM ID0 Ver[...] DNA[...] Elapsed[...] MW[...] LW[...] MH[...] HW[...]"
        mm_data = block.get("MM ID0", "") or block.get("MM", "")
        if mm_data:
            self._parse_mm_data(mm_data, stats)

        # Parse hashboard data - Avalon uses different naming
        for i in range(1, 5):
            board_key = f"Chain{i}"
            if board_key in block:
                board = HashboardInfo(
                    index=i - 1,
                    hashrate_rt=float(block.get(f"GHS{i}", 0)) / 1000,
                )
                temp_key = f"Temp{i}"
                if temp_key in block:
                    board.temp_chip = float(block[temp_key])
                hashboards.append(board)

        # Also try parsing from MM data for hashboards
        if not hashboards and mm_data:
            hashboards = self._parse_mm_boards(mm_data)

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

        # Try to get MAC from stats if not found
        if not stats.mac_address:
            mac = block.get("MAC", block.get("mac", block.get("MACAddr", "")))
            if mac:
                stats.mac_address = mac

    def _parse_mm_data(self, mm_str: str, stats: MinerStats):
        """Parse Avalon MM (module manager) data string"""
        # Extract key-value pairs from MM data string
        # Format: Key[Value] Key[Value] ...
        pattern = re.compile(r"(\w+)\[([^\]]*)\]")
        data = dict(pattern.findall(mm_str))

        if "Temp" in data:
            try:
                temps = [float(t) for t in data["Temp"].split() if t]
                if temps:
                    stats.temps = temps
                    stats.temp_max = max(temps)
                    stats.temp_min = min(temps)
                    stats.temp_avg = sum(temps) / len(temps)
            except Exception:
                pass

        if "Fan" in data:
            try:
                fans = [int(f) for f in data["Fan"].split() if f]
                if fans:
                    stats.fan_speeds = fans
                    stats.fan_speed_avg = int(sum(fans) / len(fans))
            except Exception:
                pass

        if "GHS" in data:
            try:
                stats.hashrate_rt = float(data["GHS"]) / 1000
            except Exception:
                pass

        if "PS" in data:
            try:
                stats.power_consumption = float(data["PS"])
            except Exception:
                pass

        # Also try to get MAC from MM data
        if "MAC" in data:
            stats.mac_address = data["MAC"]

    def _parse_mm_boards(self, mm_str: str) -> List[HashboardInfo]:
        """Parse hashboard info from MM data string"""
        boards = []
        pattern = re.compile(r"(\w+)\[([^\]]*)\]")
        data = dict(pattern.findall(mm_str))
        
        # Try to parse individual board data
        for i in range(3):
            temp_key = f"Temp{i+1}"
            ghs_key = f"GHS{i+1}"
            if temp_key in data or ghs_key in data:
                board = HashboardInfo(index=i)
                if temp_key in data:
                    try:
                        board.temp_chip = float(data[temp_key])
                    except Exception:
                        pass
                if ghs_key in data:
                    try:
                        board.hashrate_rt = float(data[ghs_key]) / 1000
                    except Exception:
                        pass
                boards.append(board)
        
        return boards

    async def _collect_http(
        self, ip: str, username: str, password: str, timeout: float
    ) -> Optional[MinerStats]:
        """Collect stats via Canaan HTTP API (newer models)"""
        stats = MinerStats(last_updated=datetime.utcnow())

        # Try different API endpoints
        endpoints_to_try = [
            f"http://{ip}/api/v1/hashrate",
            f"http://{ip}/api/v1/status",
            f"http://{ip}/cgi-bin/luci/rpc/sys",
        ]

        async with httpx.AsyncClient(
            timeout=timeout,
            verify=False,
            auth=(username, password),
        ) as client:
            for endpoint in endpoints_to_try:
                try:
                    resp = await client.get(endpoint)
                    if resp.status_code == 200:
                        data = resp.json()
                        self._parse_http_response(data, stats)
                        if stats.hashrate_rt > 0 or stats.hashrate_avg > 0:
                            return stats
                except Exception:
                    pass

        return None if stats.hashrate_rt == 0 else stats

    def _parse_http_response(self, data: Dict, stats: MinerStats):
        """Parse HTTP API response"""
        # Handle various response formats
        if "hashrate" in data:
            stats.hashrate_rt = float(data["hashrate"]) / 1e12  # H/s to TH/s
        if "avg_hashrate" in data:
            stats.hashrate_avg = float(data["avg_hashrate"]) / 1e12
        if "temperature" in data:
            temp = data["temperature"]
            if isinstance(temp, list):
                stats.temps = [float(t) for t in temp]
                stats.temp_max = max(stats.temps)
                stats.temp_avg = sum(stats.temps) / len(stats.temps)
            else:
                stats.temp_avg = float(temp)
        if "fan_speed" in data:
            fans = data["fan_speed"]
            if isinstance(fans, list):
                stats.fan_speeds = [int(f) for f in fans]
            else:
                stats.fan_speeds = [int(fans)]
            stats.fan_speed_avg = int(sum(stats.fan_speeds) / len(stats.fan_speeds))
        if "power" in data:
            stats.power_consumption = float(data["power"])
        if "uptime" in data:
            stats.uptime_seconds = int(data["uptime"])
            stats.uptime_str = self._format_uptime(stats.uptime_seconds)
        if "firmware" in data:
            stats.firmware_version = str(data["firmware"])
            stats.firmware_type = detect_firmware_from_version(stats.firmware_version)

    async def reboot(self, ip: str, username: str = "admin", password: str = "admin", timeout: float = 10.0) -> bool:
        """Reboot the Avalon miner"""
        # Try CGMiner restart
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, self.CGMINER_PORT),
                timeout=timeout,
            )
            writer.write(b'{"command":"restart"}')
            await writer.drain()
            writer.close()
            return True
        except Exception:
            pass

        # Try HTTP reboot
        async with httpx.AsyncClient(
            timeout=timeout, verify=False, auth=(username, password)
        ) as client:
            for endpoint in [f"http://{ip}/api/v1/reboot", f"http://{ip}/cgi-bin/reboot.cgi"]:
                try:
                    resp = await client.post(endpoint)
                    if resp.status_code in [200, 204]:
                        return True
                except Exception:
                    pass
        return False

    async def shutdown(self, ip: str, username: str = "admin", password: str = "admin", timeout: float = 10.0) -> bool:
        """Stop mining on Avalon"""
        async with httpx.AsyncClient(
            timeout=timeout, verify=False, auth=(username, password)
        ) as client:
            try:
                resp = await client.post(f"http://{ip}/api/v1/stop")
                return resp.status_code in [200, 204]
            except Exception:
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
        """Flash firmware to Avalon miner"""
        try:
            with open(firmware_path, "rb") as f:
                firmware_data = f.read()

            if progress_callback:
                await progress_callback(10, "Uploading firmware to Avalon...")

            async with httpx.AsyncClient(
                timeout=timeout, verify=False, auth=(username, password)
            ) as client:
                files = {"firmware": ("firmware.tar.gz", firmware_data, "application/octet-stream")}
                resp = await client.post(
                    f"http://{ip}/cgi-bin/upgrade.cgi",
                    files=files,
                )
                if resp.status_code in [200, 204]:
                    if progress_callback:
                        await progress_callback(100, "Firmware uploaded")
                    return True
        except Exception as e:
            logger.error(f"Canaan firmware flash failed for {ip}: {e}")
        return False

    def _parse_hashrate(self, value) -> float:
        """Convert GH/s to TH/s"""
        try:
            return float(value) / 1000.0
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
