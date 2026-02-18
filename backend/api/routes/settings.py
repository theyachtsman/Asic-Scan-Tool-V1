"""
Settings API Routes
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter

from core.config import settings as app_settings
from core.models import AppSettings

logger = logging.getLogger(__name__)
router = APIRouter()

# Settings file path
_settings_file = app_settings.DATA_DIR / "app_settings.json"
_current_settings = AppSettings()


def _load_settings():
    global _current_settings
    if _settings_file.exists():
        try:
            with open(_settings_file) as f:
                data = json.load(f)
            _current_settings = AppSettings(**data)
        except Exception as e:
            logger.warning(f"Failed to load settings: {e}")


def _save_settings():
    try:
        with open(_settings_file, "w") as f:
            json.dump(_current_settings.model_dump(), f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save settings: {e}")


_load_settings()


@router.get("/", response_model=AppSettings)
async def get_settings():
    """Get current application settings"""
    return _current_settings


@router.put("/", response_model=AppSettings)
async def update_settings(new_settings: AppSettings):
    """Update application settings"""
    global _current_settings
    _current_settings = new_settings
    _save_settings()
    return _current_settings


@router.post("/reset")
async def reset_settings():
    """Reset settings to defaults"""
    global _current_settings
    _current_settings = AppSettings()
    _save_settings()
    return {"status": "reset", "settings": _current_settings}


@router.get("/export")
async def export_data():
    """Export all data as JSON"""
    from core.device_store import device_store
    devices = [d.model_dump(mode="json") for d in device_store.get_all()]
    return {
        "version": "1.0.0",
        "settings": _current_settings.model_dump(),
        "devices": devices,
        "total_devices": len(devices),
    }
