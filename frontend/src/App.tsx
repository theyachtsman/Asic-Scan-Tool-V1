/**
 * Main App Component
 */

import { useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useMinerStore } from './store/minerStore';
import { settingsApi } from './api/client';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import MinersTable from './components/MinersTable';
import ScanPanel from './components/ScanPanel';
import FirmwareManager from './components/FirmwareManager';
import SettingsPanel from './components/SettingsPanel';
import AlertBanner from './components/AlertBanner';
import StatusBar from './components/StatusBar';
import HashboardsPage from './components/HashboardsPage';

export default function App() {
  useWebSocket();

  const { activeTab, setSettings, addAlert } = useMinerStore();

  // Load settings on startup
  useEffect(() => {
    settingsApi.get()
      .then(res => setSettings(res.data))
      .catch(() => addAlert('warning', 'Could not connect to backend. Make sure the backend is running.'));
  }, [setSettings, addAlert]);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'miners': return <MinersTable />;
      case 'scan': return <ScanPanel />;
      case 'hashboards': return <HashboardsPage />;
      case 'firmware': return <FirmwareManager />;
      case 'settings': return <SettingsPanel />;
      default: return <Dashboard />;
    }
  };

  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content">
        <AlertBanner />
        <div className="content-area">
          {renderContent()}
        </div>
        <StatusBar />
      </div>
    </div>
  );
}
