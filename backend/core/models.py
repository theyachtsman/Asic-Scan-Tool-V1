"""
Core Data Models - Pydantic schemas for all miner data
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MinerBrand(str, Enum):
    BITMAIN = "Bitmain"
    CANAAN = "Canaan"
    BITDEER = "Bitdeer"
    MICROBT = "MicroBT"
    UNKNOWN = "Unknown"


class FirmwareType(str, Enum):
    STOCK = "Stock"
    BRAIINS = "Braiins OS"
    VNISH = "VNish"
    LUXOS = "LuxOS"
    EPIC = "ePIC"
    UNKNOWN = "Unknown"


class MinerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    SCANNING = "scanning"
    REBOOTING = "rebooting"
    FLASHING = "flashing"


class DiscoveryMethod(str, Enum):
    PING = "ping"
    ARP = "arp"
    DHCP = "dhcp"
    MDNS = "mdns"
    MANUAL = "manual"


class PoolInfo(BaseModel):
    url: str = ""
    user: str = ""
    status: str = ""
    priority: int = 0
    accepted: int = 0
    rejected: int = 0
    stale: int = 0
    diff: str = ""


class HashboardInfo(BaseModel):
    index: int = 0
    hashrate_rt: float = 0.0       # GH/s real-time
    hashrate_avg: float = 0.0      # GH/s average
    temp_chip: float = 0.0         # °C
    temp_pcb: float = 0.0          # °C
    fan_speed: int = 0             # RPM
    chips_total: int = 0
    chips_active: int = 0
    voltage: float = 0.0
    frequency: float = 0.0
    hw_errors: int = 0
    status: str = "ok"


class MinerStats(BaseModel):
    """Full miner statistics"""
    # Hashrate
    hashrate_rt: float = 0.0       # TH/s real-time
    hashrate_avg: float = 0.0      # TH/s average
    hashrate_ideal: float = 0.0    # TH/s rated

    # Power
    power_consumption: float = 0.0  # Watts
    power_limit: float = 0.0        # Watts
    efficiency: float = 0.0         # J/TH

    # Temperatures
    temp_max: float = 0.0
    temp_min: float = 0.0
    temp_avg: float = 0.0
    temps: List[float] = []

    # Fans
    fan_speeds: List[int] = []
    fan_speed_avg: int = 0

    # Uptime
    uptime_seconds: int = 0
    uptime_str: str = ""

    # Errors
    hw_error_rate: float = 0.0
    total_hw_errors: int = 0

    # Boards
    hashboards: List[HashboardInfo] = []

    # Pools
    pools: List[PoolInfo] = []
    active_pool: str = ""
    worker_name: str = ""

    # Network
    mac_address: str = ""
    hostname: str = ""

    # Firmware
    firmware_version: str = ""
    firmware_type: FirmwareType = FirmwareType.UNKNOWN

    # Raw API data
    raw_data: Dict[str, Any] = {}

    # Timestamp
    last_updated: Optional[datetime] = None


class MinerDevice(BaseModel):
    """Represents a discovered ASIC miner"""
    id: str = ""                    # Unique ID (MAC or IP-based)
    ip: str = ""
    mac: str = ""
    hostname: str = ""

    # Identity
    brand: MinerBrand = MinerBrand.UNKNOWN
    model: str = ""
    firmware_type: FirmwareType = FirmwareType.UNKNOWN
    firmware_version: str = ""

    # Status
    status: MinerStatus = MinerStatus.OFFLINE
    is_reachable: bool = False

    # Discovery
    discovery_method: DiscoveryMethod = DiscoveryMethod.PING
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    # Credentials
    username: str = ""
    password: str = ""

    # Stats (populated after API query)
    stats: Optional[MinerStats] = None

    # Tags / grouping
    tags: List[str] = []
    location: str = ""
    notes: str = ""

    class Config:
        use_enum_values = True


class ScanConfig(BaseModel):
    """Configuration for a network scan"""
    ip_ranges: List[str] = Field(default_factory=list, description="CIDR ranges or IP ranges like 192.168.1.1-254")
    methods: List[DiscoveryMethod] = [DiscoveryMethod.PING, DiscoveryMethod.ARP]
    ping_timeout: float = 1.0
    api_timeout: float = 5.0
    max_concurrent: int = 100
    collect_stats: bool = True
    username: str = ""
    password: str = ""


class ScanProgress(BaseModel):
    """Real-time scan progress"""
    scan_id: str = ""
    status: str = "idle"           # idle, running, complete, cancelled
    total_hosts: int = 0
    scanned_hosts: int = 0
    found_miners: int = 0
    current_ip: str = ""
    percent: float = 0.0
    elapsed_seconds: float = 0.0
    estimated_remaining: float = 0.0
    errors: List[str] = []


class FirmwarePackage(BaseModel):
    """Firmware package for deployment"""
    id: str = ""
    filename: str = ""
    brand: MinerBrand = MinerBrand.UNKNOWN
    model: str = ""
    version: str = ""
    firmware_type: FirmwareType = FirmwareType.STOCK
    file_size: int = 0
    checksum_md5: str = ""
    checksum_sha256: str = ""
    upload_date: Optional[datetime] = None
    notes: str = ""


class FlashJob(BaseModel):
    """Firmware flash job"""
    job_id: str = ""
    firmware_id: str = ""
    target_ips: List[str] = []
    status: str = "pending"        # pending, running, complete, failed
    progress: Dict[str, str] = {}  # ip -> status
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: Dict[str, str] = {}


class AppSettings(BaseModel):
    """User-configurable application settings"""
    # Network
    default_ip_range: str = "192.168.1.1-254"
    scan_timeout: float = 2.0
    api_timeout: float = 5.0
    max_concurrent_scans: int = 100
    auto_refresh_interval: int = 30  # seconds, 0 = disabled

    # Credentials
    bitmain_user: str = "root"
    bitmain_pass: str = "root"
    canaan_user: str = "admin"
    canaan_pass: str = "admin"
    bitdeer_user: str = "admin"
    bitdeer_pass: str = "admin"

    # UI
    theme: str = "dark"
    table_density: str = "comfortable"
    show_offline_miners: bool = True

    # Alerts
    alert_temp_threshold: float = 85.0
    alert_hashrate_drop_pct: float = 20.0
    alert_offline_notify: bool = True
