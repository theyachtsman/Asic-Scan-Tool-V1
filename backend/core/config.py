"""
Application Configuration
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8765

    # Security
    SECRET_KEY: str = "asic-scan-tool-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Discovery defaults
    DEFAULT_SCAN_TIMEOUT: float = 2.0
    DEFAULT_PING_TIMEOUT: float = 1.0
    DEFAULT_API_TIMEOUT: float = 5.0
    MAX_CONCURRENT_SCANS: int = 100
    MAX_CONCURRENT_API_CALLS: int = 50

    # Miner credentials defaults
    DEFAULT_BITMAIN_USER: str = "root"
    DEFAULT_BITMAIN_PASS: str = "root"
    DEFAULT_CANAAN_USER: str = "admin"
    DEFAULT_CANAAN_PASS: str = "admin"
    DEFAULT_BITDEER_USER: str = "admin"
    DEFAULT_BITDEER_PASS: str = "admin"

    # Paths
    DATA_DIR: Path = Path(os.getenv("APPDATA", Path.home())) / "AsicScanTool"
    FIRMWARE_DIR: Path = DATA_DIR / "firmware"
    LOGS_DIR: Path = DATA_DIR / "logs"
    DB_PATH: Path = DATA_DIR / "asicscan.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
