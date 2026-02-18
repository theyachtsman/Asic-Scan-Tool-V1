/**
 * Electron Main Process
 * Manages the app window and spawns the Python backend
 */

import { app, BrowserWindow, shell, ipcMain, dialog } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const BACKEND_PORT = 8765;
const VITE_DEV_URL = 'http://localhost:5173';

function getBackendPath(): string {
  if (isDev) {
    return path.join(__dirname, '../../backend');
  }
  // In production, backend is bundled alongside the app
  return path.join(process.resourcesPath, 'backend');
}

function getPythonPath(): string {
  if (process.platform === 'win32') {
    // Check for bundled Python first
    const bundledPython = path.join(process.resourcesPath, 'python', 'python.exe');
    if (fs.existsSync(bundledPython)) return bundledPython;
    return 'python';
  }
  const bundledPython = path.join(process.resourcesPath, 'python', 'bin', 'python3');
  if (fs.existsSync(bundledPython)) return bundledPython;
  return 'python3';
}

async function startBackend(): Promise<void> {
  const backendDir = getBackendPath();
  const pythonPath = getPythonPath();
  const mainScript = path.join(backendDir, 'main.py');

  if (!fs.existsSync(mainScript)) {
    console.error(`Backend not found at: ${mainScript}`);
    return;
  }

  console.log(`Starting backend: ${pythonPath} ${mainScript}`);

  backendProcess = spawn(pythonPath, [mainScript], {
    cwd: backendDir,
    env: { ...process.env, PYTHONPATH: backendDir },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout?.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr?.on('data', (data) => {
    console.error(`[Backend ERR] ${data.toString().trim()}`);
  });

  backendProcess.on('exit', (code) => {
    console.log(`Backend exited with code ${code}`);
    backendProcess = null;
  });

  // Wait for backend to be ready
  await waitForBackend();
}

async function waitForBackend(maxAttempts = 30): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await fetch(`http://127.0.0.1:${BACKEND_PORT}/api/health`);
      if (response.ok) {
        console.log('Backend is ready!');
        return;
      }
    } catch {
      // Not ready yet
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  console.warn('Backend did not start in time');
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'ASIC Scan Tool',
    backgroundColor: '#0f172a',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: false, // Allow local API calls
    },
    icon: path.join(__dirname, '../public/icon.png'),
    show: false,
    titleBarStyle: 'default',
  });

  // Load the app
  if (isDev) {
    mainWindow.loadURL(VITE_DEV_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC Handlers
ipcMain.handle('open-external', async (_, url: string) => {
  await shell.openExternal(url);
});

ipcMain.handle('get-backend-url', () => {
  return `http://127.0.0.1:${BACKEND_PORT}`;
});

ipcMain.handle('select-firmware-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    title: 'Select Firmware File',
    filters: [
      { name: 'Firmware Files', extensions: ['bin', 'tar.gz', 'img', 'swu'] },
      { name: 'All Files', extensions: ['*'] },
    ],
    properties: ['openFile'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('show-message-box', async (_, options) => {
  return dialog.showMessageBox(mainWindow!, options);
});

// App lifecycle
app.whenReady().then(async () => {
  if (!isDev) {
    await startBackend();
  }
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendProcess) {
    console.log('Stopping backend...');
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
});

app.on('will-quit', () => {
  if (backendProcess) {
    backendProcess.kill('SIGKILL');
  }
});
