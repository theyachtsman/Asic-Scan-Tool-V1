"""
Network Scanner - Core discovery engine
Implements ping sweep, ARP scanning, and DHCP lease discovery
"""

import asyncio
import ipaddress
import logging
import platform
import re
import socket
import subprocess
import time
import uuid
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

import httpx

try:
    import ifaddr
    HAS_IFADDR = True
except ImportError:
    HAS_IFADDR = False

from core.models import DiscoveryMethod, MinerDevice, MinerStatus, ScanConfig, ScanProgress

logger = logging.getLogger(__name__)


def expand_ip_range(ip_range: str) -> List[str]:
    """
    Expand IP range string into list of IPs.
    Supports:
      - CIDR: 192.168.1.0/24
      - Range: 192.168.1.1-254
      - Range: 192.168.1.1-192.168.1.254
      - Single: 192.168.1.100
    """
    ip_range = ip_range.strip()
    ips = []

    try:
        # CIDR notation
        if "/" in ip_range:
            network = ipaddress.ip_network(ip_range, strict=False)
            ips = [str(ip) for ip in network.hosts()]

        # Range with dash
        elif "-" in ip_range:
            parts = ip_range.split("-")
            if len(parts) == 2:
                start_str = parts[0].strip()
                end_str = parts[1].strip()

                # Check if end is just the last octet
                if "." not in end_str:
                    base = ".".join(start_str.split(".")[:-1])
                    start_last = int(start_str.split(".")[-1])
                    end_last = int(end_str)
                    for i in range(start_last, end_last + 1):
                        ips.append(f"{base}.{i}")
                else:
                    # Full IP range
                    start_ip = ipaddress.ip_address(start_str)
                    end_ip = ipaddress.ip_address(end_str)
                    current = start_ip
                    while current <= end_ip:
                        ips.append(str(current))
                        current += 1

        # Single IP
        else:
            ipaddress.ip_address(ip_range)  # Validate
            ips = [ip_range]

    except ValueError as e:
        logger.error(f"Invalid IP range '{ip_range}': {e}")

    return ips


async def ping_host(ip: str, timeout: float = 1.0) -> bool:
    """Async ping a single host"""
    system = platform.system().lower()

    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
        return proc.returncode == 0
    except (asyncio.TimeoutError, Exception):
        return False


async def tcp_probe(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open"""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def get_hostname(ip: str) -> str:
    """Reverse DNS lookup"""
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip),
            timeout=2.0,
        )
        return result[0]
    except Exception:
        return ""


def get_arp_table() -> Dict[str, str]:
    """
    Read the system ARP table.
    Returns dict of {ip: mac}
    """
    arp_map = {}
    system = platform.system().lower()

    try:
        if system == "windows":
            result = subprocess.run(
                ["arp", "-a"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Parse Windows ARP output
            # Format: 192.168.1.1          aa-bb-cc-dd-ee-ff     dynamic
            pattern = re.compile(
                r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([\w-]{17})\s+\w+"
            )
            for match in pattern.finditer(result.stdout):
                ip = match.group(1)
                mac = match.group(2).replace("-", ":").upper()
                arp_map[ip] = mac
        else:
            # Linux/Mac
            result = subprocess.run(
                ["arp", "-n"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            pattern = re.compile(
                r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+\w+\s+([\w:]{17})"
            )
            for match in pattern.finditer(result.stdout):
                ip = match.group(1)
                mac = match.group(2).upper()
                arp_map[ip] = mac

    except Exception as e:
        logger.warning(f"ARP table read failed: {e}")

    return arp_map


def get_dhcp_leases() -> Dict[str, str]:
    """
    Try to read DHCP leases from common locations.
    Returns dict of {ip: mac}
    """
    leases = {}
    system = platform.system().lower()

    lease_files = []
    if system == "linux":
        lease_files = [
            "/var/lib/dhcp/dhcpd.leases",
            "/var/lib/dhcpd/dhcpd.leases",
            "/tmp/dhcp.leases",
        ]
    elif system == "darwin":
        lease_files = ["/var/db/dhcpd_leases"]

    for lease_file in lease_files:
        try:
            with open(lease_file, "r") as f:
                content = f.read()
            # Parse ISC DHCP lease format
            ip_pattern = re.compile(r"lease\s+(\d+\.\d+\.\d+\.\d+)")
            mac_pattern = re.compile(r"hardware ethernet\s+([\w:]+)")
            current_ip = None
            for line in content.splitlines():
                ip_match = ip_pattern.search(line)
                if ip_match:
                    current_ip = ip_match.group(1)
                mac_match = mac_pattern.search(line)
                if mac_match and current_ip:
                    leases[current_ip] = mac_match.group(1).upper()
        except Exception:
            pass

    return leases


class NetworkScanner:
    """
    Main network scanner that orchestrates discovery
    """

    # Common ASIC miner ports to probe
    MINER_PORTS = [80, 443, 4028, 8080, 8443]

    def __init__(self):
        self._active_scans: Dict[str, ScanProgress] = {}
        self._cancel_flags: Dict[str, bool] = {}

    async def scan(
        self,
        config: ScanConfig,
        scan_id: str,
        progress_callback=None,
    ) -> List[MinerDevice]:
        """
        Run a full network scan based on config.
        Returns list of discovered miner devices.
        """
        start_time = time.time()
        found_devices: List[MinerDevice] = []

        # Initialize progress
        progress = ScanProgress(
            scan_id=scan_id,
            status="running",
        )
        self._active_scans[scan_id] = progress
        self._cancel_flags[scan_id] = False

        try:
            # Expand all IP ranges
            all_ips: List[str] = []
            for ip_range in config.ip_ranges:
                expanded = expand_ip_range(ip_range)
                all_ips.extend(expanded)

            # Deduplicate
            all_ips = list(dict.fromkeys(all_ips))
            progress.total_hosts = len(all_ips)

            logger.info(f"[{scan_id}] Starting scan of {len(all_ips)} hosts")

            # Get ARP table upfront if ARP method enabled
            arp_table = {}
            if DiscoveryMethod.ARP in config.methods or "arp" in config.methods:
                logger.info(f"[{scan_id}] Reading ARP table...")
                arp_table = get_arp_table()
                logger.info(f"[{scan_id}] ARP table has {len(arp_table)} entries")

            # Get DHCP leases if enabled
            dhcp_leases = {}
            if DiscoveryMethod.DHCP in config.methods or "dhcp" in config.methods:
                dhcp_leases = get_dhcp_leases()
                logger.info(f"[{scan_id}] DHCP leases: {len(dhcp_leases)} entries")

            # Merge ARP + DHCP for MAC lookup
            mac_lookup = {**dhcp_leases, **arp_table}

            # Ping sweep with concurrency control
            semaphore = asyncio.Semaphore(config.max_concurrent)
            reachable_ips: List[str] = []

            async def probe_ip(ip: str):
                if self._cancel_flags.get(scan_id):
                    return

                async with semaphore:
                    if self._cancel_flags.get(scan_id):
                        return

                    # Try ping first
                    is_up = await ping_host(ip, config.ping_timeout)

                    # If ping fails, try TCP probe on miner ports
                    if not is_up:
                        for port in [80, 4028]:
                            if await tcp_probe(ip, port, 0.5):
                                is_up = True
                                break

                    progress.scanned_hosts += 1
                    progress.current_ip = ip
                    elapsed = time.time() - start_time
                    progress.elapsed_seconds = elapsed
                    if progress.scanned_hosts > 0:
                        rate = progress.scanned_hosts / elapsed if elapsed > 0 else 1
                        remaining = progress.total_hosts - progress.scanned_hosts
                        progress.estimated_remaining = remaining / rate if rate > 0 else 0
                    progress.percent = (progress.scanned_hosts / progress.total_hosts * 100) if progress.total_hosts > 0 else 0

                    if is_up:
                        reachable_ips.append(ip)
                        progress.found_miners += 1  # Temp count, refined later

                    if progress_callback:
                        await progress_callback(progress)

            # Run all probes
            tasks = [probe_ip(ip) for ip in all_ips]
            await asyncio.gather(*tasks, return_exceptions=True)

            if self._cancel_flags.get(scan_id):
                progress.status = "cancelled"
                return found_devices

            logger.info(f"[{scan_id}] Found {len(reachable_ips)} reachable hosts")

            # Now identify miners from reachable hosts
            from discovery.miner_identifier import MinerIdentifier
            identifier = MinerIdentifier()

            identify_sem = asyncio.Semaphore(min(config.max_concurrent, 50))
            identified_count = 0
            total_to_identify = len(reachable_ips)

            async def identify_host(ip: str):
                nonlocal identified_count
                if self._cancel_flags.get(scan_id):
                    return None
                async with identify_sem:
                    if self._cancel_flags.get(scan_id):
                        return None
                    mac = mac_lookup.get(ip, "")
                    try:
                        device = await identifier.identify(
                            ip=ip,
                            mac=mac,
                            timeout=config.api_timeout,
                            username=config.username,
                            password=config.password,
                            collect_stats=config.collect_stats,
                        )
                        identified_count += 1
                        # Update progress during identification phase
                        progress.current_ip = ip
                        # Keep percent at 50-100 range for identification phase
                        if total_to_identify > 0:
                            progress.percent = 50.0 + (identified_count / total_to_identify * 50)
                        else:
                            progress.percent = 100.0
                        progress.found_miners = len(found_devices)
                        if progress_callback:
                            await progress_callback(progress)
                        return device
                    except Exception as e:
                        logger.warning(f"[{scan_id}] Error identifying {ip}: {e}")
                        identified_count += 1
                        return None

            id_tasks = [identify_host(ip) for ip in reachable_ips]
            results = await asyncio.gather(*id_tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"[{scan_id}] Identification task exception: {result}")
                elif isinstance(result, MinerDevice):
                    found_devices.append(result)
                    # Update found count in real-time
                    progress.found_miners = len(found_devices)
                    if progress_callback:
                        await progress_callback(progress)

            progress.found_miners = len(found_devices)
            progress.status = "complete"
            progress.percent = 100.0
            progress.elapsed_seconds = time.time() - start_time

            logger.info(
                f"[{scan_id}] Scan complete: {len(found_devices)} miners found "
                f"in {progress.elapsed_seconds:.1f}s"
            )

        except Exception as e:
            logger.error(f"[{scan_id}] Scan error: {e}", exc_info=True)
            progress.status = "error"
            progress.errors.append(str(e))
        finally:
            self._active_scans[scan_id] = progress
            self._cancel_flags.pop(scan_id, None)

        if progress_callback:
            await progress_callback(progress)

        return found_devices

    def cancel_scan(self, scan_id: str):
        """Cancel an active scan"""
        if scan_id in self._cancel_flags:
            self._cancel_flags[scan_id] = True
            logger.info(f"[{scan_id}] Scan cancellation requested")

    def get_progress(self, scan_id: str) -> Optional[ScanProgress]:
        """Get current scan progress"""
        return self._active_scans.get(scan_id)

    def get_active_scans(self) -> List[str]:
        """Get list of active scan IDs"""
        return list(self._active_scans.keys())


# Global scanner instance
scanner = NetworkScanner()
