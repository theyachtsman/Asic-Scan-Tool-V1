"""
Miner Identifier - Detects brand, model, and firmware from a reachable host
Supports: Bitmain (Antminer), Canaan (Avalon), Bitdeer (Sealminer), MicroBT (Whatsminer)
"""

import asyncio
import logging
import re
import socket
from datetime import datetime
from typing import Optional

import httpx

from core.models import (
    DiscoveryMethod,
    FirmwareType,
    MinerBrand,
    MinerDevice,
    MinerStatus,
)

logger = logging.getLogger(__name__)

# ─── MAC OUI prefixes for known ASIC manufacturers ───────────────────────────
# Format: first 3 bytes (6 hex chars) uppercase, no separators

BITMAIN_OUIS = {
    "001A4B", "14B457", "D43D7E", "C4F312", "A0B045",
    "B42E99", "38D547", "000A35", "E0D55E", "3CA308",
    "C4F3FC", "D4E0B0", "A09F10", "B4860F",
}

CANAAN_OUIS = {
    "001DC0", "A4CF12", "B827EB", "DCA632", "E45F01",
    "00E04C", "A44CC8", "D83ADD", "3497F6",
}

MICROBT_OUIS = {
    "AC1F6B", "002590", "B07B25", "00E04C", "C8B5AD",
    "D4C9EF", "3497F6", "A44CC8", "1C1B0D",
}

BITDEER_OUIS = {
    "002590", "AC1F6B", "B07B25",
}


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to XX:XX:XX:XX:XX:XX uppercase"""
    if not mac:
        return ""
    mac = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(mac) == 12:
        return ":".join(mac[i:i+2] for i in range(0, 12, 2)).upper()
    return mac.upper()


def get_oui(mac: str) -> str:
    """Get OUI prefix (first 3 bytes) from MAC address as 6 uppercase hex chars"""
    clean = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(clean) >= 6:
        return clean[:6].upper()
    return ""


def brand_from_mac(mac: str) -> MinerBrand:
    """Guess brand from MAC OUI"""
    oui = get_oui(mac)
    if not oui:
        return MinerBrand.UNKNOWN
    if oui in BITMAIN_OUIS:
        return MinerBrand.BITMAIN
    if oui in MICROBT_OUIS:
        return MinerBrand.MICROBT
    if oui in CANAAN_OUIS:
        return MinerBrand.CANAAN
    if oui in BITDEER_OUIS:
        return MinerBrand.BITDEER
    return MinerBrand.UNKNOWN


def brand_from_hostname(hostname: str) -> MinerBrand:
    """Guess brand from hostname"""
    h = hostname.lower()
    if any(x in h for x in ["antminer", "bitmain", "s19", "s21", "t19", "t21", "s9", "l7", "e9"]):
        return MinerBrand.BITMAIN
    if any(x in h for x in ["avalon", "canaan", "avalonminer", "ava"]):
        return MinerBrand.CANAAN
    if any(x in h for x in ["whatsminer", "microbt", "m20", "m30", "m50", "m60", "m56"]):
        return MinerBrand.MICROBT
    if any(x in h for x in ["sealminer", "bitdeer", "seal"]):
        return MinerBrand.BITDEER
    return MinerBrand.UNKNOWN


def detect_firmware_from_version(version_str: str) -> FirmwareType:
    """Detect firmware type from version string"""
    v = version_str.lower()
    if "braiins" in v or "bos" in v:
        return FirmwareType.BRAIINS
    if "vnish" in v:
        return FirmwareType.VNISH
    if "lux" in v or "luxos" in v:
        return FirmwareType.LUXOS
    if "epic" in v:
        return FirmwareType.EPIC
    return FirmwareType.STOCK


class MinerIdentifier:
    """
    Identifies ASIC miners by probing their HTTP API endpoints.
    Supports Bitmain, Canaan (Avalon), MicroBT (Whatsminer), Bitdeer (Sealminer).
    """

    CGMINER_PORT = 4028

    async def identify(
        self,
        ip: str,
        mac: str = "",
        timeout: float = 5.0,
        username: str = "",
        password: str = "",
        collect_stats: bool = True,
    ) -> Optional[MinerDevice]:
        """
        Attempt to identify a miner at the given IP.
        Returns MinerDevice if identified, None otherwise.
        """
        device = MinerDevice(
            ip=ip,
            mac=normalize_mac(mac),
            status=MinerStatus.ONLINE,
            is_reachable=True,
            discovery_method=DiscoveryMethod.PING,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
        )

        device.id = self._generate_id(ip, mac)

        # Try to get hostname
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, socket.gethostbyaddr, ip),
                timeout=2.0,
            )
            device.hostname = result[0]
        except Exception:
            device.hostname = ""

        # Initial brand guess from MAC/hostname
        if mac:
            device.brand = brand_from_mac(mac)
        if device.brand == MinerBrand.UNKNOWN and device.hostname:
            device.brand = brand_from_hostname(device.hostname)

        identified = False

        # 1. Try CGMiner TCP API port 4028 (Bitmain, Canaan, Whatsminer all use this)
        if not identified:
            result = await self._probe_cgminer(ip, timeout)
            if result:
                brand_hint = result.get("brand", "")
                model = result.get("model", "")
                model_upper = model.upper()
                # Priority: explicit brand from CGMiner detection
                if brand_hint == "microbt" or any(x in model_upper for x in ["M20", "M30", "M50", "M60", "M56", "M66", "WHATSMINER"]):
                    device.brand = MinerBrand.MICROBT
                elif brand_hint == "canaan" or any(x in model_upper for x in ["AVALON", "CANAAN", "AVALONMINER"]):
                    device.brand = MinerBrand.CANAAN
                else:
                    device.brand = MinerBrand.BITMAIN
                device.model = model
                device.firmware_version = result.get("firmware", "")
                device.firmware_type = detect_firmware_from_version(device.firmware_version)
                identified = True

        # 2. Try Canaan/Avalon HTTP API FIRST (before Bitmain, since Avalons don't use CGMiner)
        if not identified:
            result = await self._probe_canaan_http(ip, timeout, username or "admin", password or "admin")
            if result:
                device.brand = MinerBrand.CANAAN
                device.model = result.get("model", "")
                device.firmware_version = result.get("firmware", "")
                device.firmware_type = detect_firmware_from_version(device.firmware_version)
                identified = True

        # 3. Try Bitmain HTTP API
        if not identified:
            result = await self._probe_bitmain_http(ip, timeout, username or "root", password or "root")
            if result:
                device.brand = MinerBrand.BITMAIN
                device.model = result.get("model", "")
                device.firmware_version = result.get("firmware", "")
                device.firmware_type = detect_firmware_from_version(device.firmware_version)
                identified = True

        # 4. Try MicroBT Whatsminer HTTP API
        if not identified:
            result = await self._probe_whatsminer_http(ip, timeout, username or "admin", password or "admin")
            if result:
                device.brand = MinerBrand.MICROBT
                device.model = result.get("model", "")
                device.firmware_version = result.get("firmware", "")
                device.firmware_type = detect_firmware_from_version(device.firmware_version)
                identified = True

        # 5. Try Bitdeer HTTP API
        if not identified:
            result = await self._probe_bitdeer_http(ip, timeout, username or "admin", password or "admin")
            if result:
                device.brand = MinerBrand.BITDEER
                device.model = result.get("model", "")
                device.firmware_version = result.get("firmware", "")
                device.firmware_type = detect_firmware_from_version(device.firmware_version)
                identified = True

        # 6. Generic HTTP probe - check web UI title/content
        if not identified:
            result = await self._probe_generic_http(ip, timeout)
            if result:
                device.brand = result.get("brand", MinerBrand.UNKNOWN)
                device.model = result.get("model", "")
                identified = result.get("is_miner", False)

        # If still not identified but we got a CGMiner response, it's still a miner
        # Just mark as Unknown brand
        if not identified:
            # Check if we got any CGMiner response - if so, it's a miner
            device.brand = MinerBrand.UNKNOWN
            device.model = "Unknown Miner"
            identified = True

        # Set credentials based on brand
        if device.brand == MinerBrand.BITMAIN:
            device.username = username or "root"
            device.password = password or "root"
        elif device.brand == MinerBrand.MICROBT:
            device.username = username or "admin"
            device.password = password or "admin"
        else:
            device.username = username or "admin"
            device.password = password or "admin"

        # Collect full stats if requested and brand is known
        if collect_stats and device.brand != MinerBrand.UNKNOWN:
            await self._collect_stats(device, timeout)

        return device

    def _generate_id(self, ip: str, mac: str) -> str:
        """Generate unique device ID"""
        if mac and mac != "":
            clean_mac = re.sub(r"[^0-9a-fA-F]", "", mac)
            if len(clean_mac) == 12:
                return f"mac-{clean_mac.lower()}"
        return f"ip-{ip.replace('.', '-')}"

    async def _cgminer_send(self, ip: str, command: bytes, timeout: float) -> Optional[dict]:
        """Send a command to CGMiner port 4028 and return parsed JSON"""
        import json
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 4028), timeout=timeout
            )
            writer.write(command)
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
            if not data:
                return None
            text = data.decode("utf-8", errors="ignore").rstrip("\x00").strip()
            return json.loads(text)
        except Exception:
            return None

    async def _probe_cgminer(self, ip: str, timeout: float) -> Optional[dict]:
        """Probe CGMiner TCP API on port 4028 (used by Bitmain, Canaan, Whatsminer)"""
        response = await self._cgminer_send(ip, b'{"command":"version"}', timeout)
        if not response:
            return None

        if "VERSION" in response:
            version_info = response["VERSION"][0] if response["VERSION"] else {}
            miner_type = version_info.get("Type", "")
            firmware = version_info.get("CompileTime", "")
            cgminer_ver = version_info.get("CGMiner", "")
            miner_ver = version_info.get("Miner", "")
            description = version_info.get("Description", "")

            miner_type_lower = miner_type.lower()
            cgminer_lower = cgminer_ver.lower()
            miner_ver_lower = miner_ver.lower()
            description_lower = description.lower()

            logger.info(
                f"[{ip}] CGMiner version: Type={miner_type!r} CGMiner={cgminer_ver!r} "
                f"Miner={miner_ver!r} Description={description!r}"
            )

            # Detect Whatsminer: they report "BTMiner" as CGMiner version
            if "btminer" in cgminer_lower:
                brand = "microbt"
                model = miner_type or "Whatsminer"

            # Detect Avalon/Canaan by any field containing "avalon" or "canaan"
            elif any(
                "avalon" in s or "canaan" in s or "avalonminer" in s
                for s in [miner_type_lower, miner_ver_lower, description_lower, cgminer_lower]
            ):
                brand = "canaan"
                model = miner_type or miner_ver or "Avalon"

            # Detect Avalon by empty Type + specific patterns in stats
            elif not miner_type or miner_type_lower == "":
                # Try stats command to get more info
                stats_resp = await self._cgminer_send(ip, b'{"command":"stats"}', timeout)
                if stats_resp and "STATS" in stats_resp:
                    stats_str = str(stats_resp).lower()
                    # Avalon-specific patterns in stats
                    if any(x in stats_str for x in ["mm id", "avalon", "canaan", "avminer"]):
                        brand = "canaan"
                        # Try to extract model from stats
                        model = "Avalon"  # Default
                        for s in stats_resp["STATS"]:
                            for key in ["Type", "Model", "Miner"]:
                                val = s.get(key, "")
                                if val and ("avalon" in val.lower() or val.lower().startswith("a")):
                                    model = val
                                    break
                        return {
                            "model": model,
                            "firmware": firmware,
                            "cgminer_version": cgminer_ver,
                            "brand": brand,
                        }
                # Default to Bitmain if no Avalon patterns found
                brand = "bitmain"
                model = miner_type or "Antminer"

            else:
                # Non-empty Type that doesn't match Avalon/Whatsminer patterns
                brand = "bitmain"
                model = miner_type or "Antminer"

            return {
                "model": model,
                "firmware": firmware,
                "cgminer_version": cgminer_ver,
                "brand": brand,
            }
        return None

    async def _probe_bitmain_http(self, ip: str, timeout: float, user: str, passwd: str) -> Optional[dict]:
        """Probe Bitmain Antminer HTTP API"""
        endpoints = [
            f"http://{ip}/cgi-bin/get_system_info.cgi",
            f"http://{ip}/api/v1/info",
            f"http://{ip}/cgi-bin/minerConfiguration.cgi",
        ]
        auth = httpx.DigestAuth(user, passwd)

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in endpoints:
                try:
                    resp = await client.get(endpoint, auth=auth)
                    if resp.status_code == 401:
                        # Only claim Bitmain on 401 if the page content or headers
                        # confirm it's actually an Antminer (not Avalon/other)
                        # Check the root page for brand hints before claiming Bitmain
                        try:
                            root = await client.get(f"http://{ip}/", follow_redirects=True, timeout=timeout)
                            root_lower = root.text.lower()
                            if any(x in root_lower for x in ["avalon", "canaan", "avalonminer"]):
                                return None  # It's a Canaan device, not Bitmain
                            if any(x in root_lower for x in ["whatsminer", "microbt", "btminer"]):
                                return None  # It's a MicroBT device
                            if any(x in root_lower for x in ["sealminer", "bitdeer"]):
                                return None  # It's a Bitdeer device
                            # Check WWW-Authenticate header for realm hints
                            auth_header = resp.headers.get("WWW-Authenticate", "").lower()
                            if any(x in auth_header for x in ["avalon", "canaan"]):
                                return None
                        except Exception:
                            pass
                        return {"model": "Antminer (auth required)", "firmware": ""}
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except Exception:
                            continue
                        model = (
                            data.get("minertype", "")
                            or data.get("miner_type", "")
                            or data.get("type", "")
                            or "Antminer"
                        )
                        firmware = (
                            data.get("firmware_version", "")
                            or data.get("fw_ver", "")
                            or ""
                        )
                        return {"model": model, "firmware": firmware}
                except Exception:
                    pass

        return None

    async def _probe_canaan_http(self, ip: str, timeout: float, user: str, passwd: str) -> Optional[dict]:
        """Probe Canaan Avalon HTTP API"""
        endpoints = [
            f"http://{ip}/api/v1/info",
            f"http://{ip}/cgi-bin/luci/",
            f"http://{ip}/",
        ]

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in endpoints:
                try:
                    resp = await client.get(endpoint, follow_redirects=True, timeout=timeout)
                    content = resp.text.lower()

                    if any(x in content for x in ["avalon", "canaan", "avalonminer"]):
                        model_match = re.search(r"(avalon\w*\s*\d+[a-z]*)", content, re.IGNORECASE)
                        model = model_match.group(1).strip() if model_match else "Avalon"
                        # Try to get firmware version
                        fw_match = re.search(r"firmware[:\s]+([0-9a-zA-Z._-]+)", content, re.IGNORECASE)
                        fw = fw_match.group(1) if fw_match else ""
                        return {"model": model.upper(), "firmware": fw}

                    if resp.headers.get("content-type", "").startswith("application/json"):
                        try:
                            data = resp.json()
                            data_str = str(data).lower()
                            if "avalon" in data_str or "canaan" in data_str:
                                return {
                                    "model": data.get("model", data.get("type", "Avalon")),
                                    "firmware": data.get("version", data.get("fw_version", "")),
                                }
                        except Exception:
                            pass
                except Exception:
                    pass

        return None

    async def _probe_whatsminer_http(self, ip: str, timeout: float, user: str, passwd: str) -> Optional[dict]:
        """Probe MicroBT Whatsminer HTTP API"""
        endpoints = [
            f"http://{ip}/",
            f"http://{ip}/api/v1/info",
            f"http://{ip}/cgi-bin/luci/",
        ]

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in endpoints:
                try:
                    resp = await client.get(endpoint, follow_redirects=True, timeout=timeout)
                    content = resp.text

                    # Check page title for Whatsminer pattern: "WhatsMiner M20S M20S.HB14..."
                    title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
                    title = title_match.group(1) if title_match else ""

                    content_lower = content.lower()

                    # Match title like "WhatsMiner M20S ..." or "WhatsMiner M30S..."
                    whatsminer_title = re.search(
                        r"whatsminer\s+(m\d+[a-z]*(?:\s+\S+)?)",
                        title, re.IGNORECASE
                    )
                    if whatsminer_title:
                        model = whatsminer_title.group(1).strip().split()[0].upper()
                        return {"model": model, "firmware": ""}

                    if any(x in content_lower for x in ["whatsminer", "microbt", "btminer", "m20s", "m30s", "m50s", "m60s"]):
                        # Try to extract model from content
                        model_match = re.search(
                            r"(m\d+[a-z]*(?:\s*(?:pro|plus|s|v))?)",
                            content, re.IGNORECASE
                        )
                        model = model_match.group(1).strip().upper() if model_match else "Whatsminer"
                        if not re.match(r"^M\d+", model):
                            model = "Whatsminer"
                        fw_match = re.search(r"firmware[:\s]+([0-9a-zA-Z._-]+)", content, re.IGNORECASE)
                        fw = fw_match.group(1) if fw_match else ""
                        return {"model": model, "firmware": fw}

                    if resp.headers.get("content-type", "").startswith("application/json"):
                        try:
                            data = resp.json()
                            data_str = str(data).lower()
                            if any(x in data_str for x in ["whatsminer", "microbt", "btminer"]):
                                return {
                                    "model": data.get("model", data.get("type", "Whatsminer")),
                                    "firmware": data.get("version", ""),
                                }
                        except Exception:
                            pass
                except Exception:
                    pass

        return None

    async def _probe_bitdeer_http(self, ip: str, timeout: float, user: str, passwd: str) -> Optional[dict]:
        """Probe Bitdeer Sealminer HTTP API"""
        endpoints = [
            f"http://{ip}/api/v1/info",
            f"http://{ip}/api/system/info",
            f"http://{ip}/",
        ]

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            for endpoint in endpoints:
                try:
                    resp = await client.get(endpoint, follow_redirects=True, timeout=timeout)
                    content = resp.text.lower()

                    if any(x in content for x in ["sealminer", "bitdeer", "seal"]):
                        model_match = re.search(r"seal\w*\d*", content, re.IGNORECASE)
                        model = model_match.group(0) if model_match else "Sealminer"
                        return {"model": model.upper(), "firmware": ""}

                    if resp.headers.get("content-type", "").startswith("application/json"):
                        try:
                            data = resp.json()
                            data_str = str(data).lower()
                            if "seal" in data_str or "bitdeer" in data_str:
                                return {
                                    "model": data.get("model", "Sealminer"),
                                    "firmware": data.get("version", ""),
                                }
                        except Exception:
                            pass
                except Exception:
                    pass

        return None

    async def _probe_generic_http(self, ip: str, timeout: float) -> Optional[dict]:
        """Generic HTTP probe to detect miner web UI"""
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.get(f"http://{ip}/", follow_redirects=True)
                content = resp.text.lower()

                result = {"is_miner": False, "brand": MinerBrand.UNKNOWN, "model": ""}

                if any(x in content for x in ["antminer", "bitmain"]):
                    result["is_miner"] = True
                    result["brand"] = MinerBrand.BITMAIN
                    m = re.search(r"antminer\s*(\w+)", content, re.IGNORECASE)
                    result["model"] = m.group(0) if m else "Antminer"

                elif any(x in content for x in ["avalon", "canaan", "avalonminer"]):
                    result["is_miner"] = True
                    result["brand"] = MinerBrand.CANAAN
                    m = re.search(r"(avalon\w*\s*\d+[a-z]*)", content, re.IGNORECASE)
                    result["model"] = m.group(1).strip().upper() if m else "Avalon"

                elif any(x in content for x in ["whatsminer", "microbt", "btminer"]):
                    result["is_miner"] = True
                    result["brand"] = MinerBrand.MICROBT
                    m = re.search(r"(m\d+[a-z]*\s*(?:pro|plus)?)", content, re.IGNORECASE)
                    result["model"] = m.group(1).strip().upper() if m else "Whatsminer"

                elif any(x in content for x in ["sealminer", "bitdeer"]):
                    result["is_miner"] = True
                    result["brand"] = MinerBrand.BITDEER
                    result["model"] = "Sealminer"

                elif any(x in content for x in ["miner", "hashrate", "cgminer", "bmminer", "btminer"]):
                    result["is_miner"] = True

                return result if result["is_miner"] else None
        except Exception:
            return None

    async def _collect_stats(self, device: MinerDevice, timeout: float):
        """Collect full stats from identified miner"""
        try:
            from api_collectors.bitmain_collector import BitmainCollector
            from api_collectors.canaan_collector import CanaanCollector
            from api_collectors.bitdeer_collector import BitdeerCollector
            from api_collectors.microbt_collector import MicroBTCollector

            if device.brand == MinerBrand.BITMAIN:
                collector = BitmainCollector()
            elif device.brand == MinerBrand.CANAAN:
                collector = CanaanCollector()
            elif device.brand == MinerBrand.MICROBT:
                collector = MicroBTCollector()
            elif device.brand == MinerBrand.BITDEER:
                collector = BitdeerCollector()
            else:
                return

            stats = await collector.collect(
                ip=device.ip,
                username=device.username,
                password=device.password,
                timeout=timeout,
            )
            if stats:
                device.stats = stats
                if stats.firmware_version:
                    device.firmware_version = stats.firmware_version
                if stats.firmware_type != FirmwareType.UNKNOWN:
                    device.firmware_type = stats.firmware_type
                if stats.mac_address and not device.mac:
                    device.mac = stats.mac_address
                    device.id = self._generate_id(device.ip, device.mac)

        except Exception as e:
            logger.debug(f"Stats collection failed for {device.ip}: {e}")
