# ⚡ ASIC Scan Tool

A production-ready, cross-platform ASIC miner discovery and management platform.

> Comparable to Advanced IP Scanner + Minerstat + Awesome Miner — but fully self-hosted, vendor-agnostic, and open.

---

## 🎯 Features

- **Automatic Network Discovery** — ICMP ping sweep, ARP table scan, DHCP lease discovery
- **Multi-Brand Support** — Bitmain (Antminer), Canaan (Avalon), Bitdeer (Sealminer)
- **Multi-Firmware Support** — Stock, Braiins OS, VNish, LuxOS, ePIC
- **Live Dashboard** — Real-time hashrate, temperature, power, fan speed
- **Miners Table** — Sortable, filterable, bulk-selectable with expandable detail rows
- **Remote Management** — Reboot, shutdown, bulk actions
- **Firmware Manager** — Upload, store, and batch-deploy firmware
- **WebSocket Updates** — Real-time push from backend to UI
- **Cross-Platform** — Windows (.exe installer) and Linux (AppImage)

---

## 🏗️ Architecture

```
AsicScanTool/
├── backend/                    # Python FastAPI backend
│   ├── main.py                 # Entry point
│   ├── core/
│   │   ├── config.py           # App settings
│   │   ├── models.py           # Pydantic data models
│   │   ├── device_store.py     # In-memory device registry
│   │   └── logger.py           # Logging setup
│   ├── discovery/
│   │   ├── network_scanner.py  # Ping/ARP/DHCP scanner
│   │   └── miner_identifier.py # Brand/model detection
│   ├── api_collectors/
│   │   ├── bitmain_collector.py
│   │   ├── canaan_collector.py
│   │   └── bitdeer_collector.py
│   └── api/routes/
│       ├── discovery.py        # /api/discovery/*
│       ├── miners.py           # /api/miners/*
│       ├── firmware.py         # /api/firmware/*
│       ├── settings.py         # /api/settings/*
│       └── websocket.py        # /ws/ WebSocket
│
├── frontend/                   # Electron + React + TypeScript
│   ├── electron/
│   │   ├── main.ts             # Electron main process
│   │   └── preload.ts          # Context bridge
│   └── src/
│       ├── api/client.ts       # Axios API client
│       ├── store/minerStore.ts # Zustand global state
│       ├── hooks/useWebSocket.ts
│       ├── types/miner.ts      # TypeScript types
│       └── components/
│           ├── Dashboard.tsx
│           ├── MinersTable.tsx
│           ├── ScanPanel.tsx
│           ├── FirmwareManager.tsx
│           ├── SettingsPanel.tsx
│           ├── Sidebar.tsx
│           ├── AlertBanner.tsx
│           └── StatusBar.tsx
│
├── start-dev.bat               # Windows dev launcher
└── start-dev.sh                # Linux dev launcher
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+

### Development Mode

**Windows:**
```bat
start-dev.bat
```

**Linux/macOS:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

This starts:
1. Python backend on `http://127.0.0.1:8765`
2. Vite dev server on `http://localhost:5173`

Open `http://localhost:5173` in your browser, or run the Electron app.

### Manual Start

**Backend:**
```bash
cd backend
pip install -r requirements.txt
python main.py
```

**Frontend (browser):**
```bash
cd frontend
npm install
npm run dev
```

**Frontend (Electron):**
```bash
cd frontend
npm run dev:electron
```

---

## 📦 Building for Production

### Windows Installer (.exe)
```bash
cd frontend
npm run build:win
```
Output: `dist/ASIC Scan Tool Setup 1.0.0.exe`

### Linux AppImage
```bash
cd frontend
npm run build:linux
```
Output: `dist/ASIC Scan Tool-1.0.0.AppImage`

---

## 🔌 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/discovery/start` | POST | Start network scan |
| `/api/discovery/progress/{id}` | GET | Get scan progress |
| `/api/discovery/local-networks` | GET | Detect local subnets |
| `/api/miners/` | GET | List all miners |
| `/api/miners/summary` | GET | Summary stats |
| `/api/miners/{id}/reboot` | POST | Reboot miner |
| `/api/miners/{id}/shutdown` | POST | Shutdown miner |
| `/api/miners/bulk/action` | POST | Bulk reboot/shutdown |
| `/api/firmware/upload` | POST | Upload firmware |
| `/api/firmware/flash` | POST | Flash firmware to miners |
| `/api/settings/` | GET/PUT | App settings |
| `/ws/` | WebSocket | Real-time updates |

---

## 🔧 Configuration

Settings are stored in `backend/data/settings.json` and can be configured via the Settings panel in the UI.

Key settings:
- `default_ip_range` — Default scan range (e.g. `192.168.1.1-254`)
- `scan_timeout` — Ping timeout in seconds
- `api_timeout` — Miner API timeout
- `max_concurrent_scans` — Parallel scan threads
- `bitmain_user/pass` — Default Bitmain credentials
- `canaan_user/pass` — Default Canaan credentials
- `bitdeer_user/pass` — Default Bitdeer credentials

---

## 🧩 Adding New Miner Brands

1. Create `backend/api_collectors/newbrand_collector.py`
2. Implement the `collect_stats(ip, username, password, timeout)` async function
3. Register in `backend/discovery/miner_identifier.py`
4. Add brand detection signatures to `MINER_SIGNATURES`

---

## 📄 License

MIT License — Free for personal and commercial use.
