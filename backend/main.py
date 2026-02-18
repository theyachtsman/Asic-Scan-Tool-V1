"""
ASIC Scan Tool - Main Backend Entry Point
FastAPI server with WebSocket support for real-time updates
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import discovery, miners, firmware, settings, websocket
from core.config import settings as app_settings
from core.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 ASIC Scan Tool Backend Starting...")
    logger.info(f"   Version: 1.0.0")
    logger.info(f"   Host: {app_settings.HOST}:{app_settings.PORT}")
    yield
    logger.info("🛑 ASIC Scan Tool Backend Shutting Down...")


app = FastAPI(
    title="ASIC Scan Tool API",
    description="Network-based ASIC miner discovery and management platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Electron frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(discovery.router, prefix="/api/discovery", tags=["Discovery"])
app.include_router(miners.router, prefix="/api/miners", tags=["Miners"])
app.include_router(firmware.router, prefix="/api/firmware", tags=["Firmware"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=app_settings.HOST,
        port=app_settings.PORT,
        reload=False,
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=20,
    )
