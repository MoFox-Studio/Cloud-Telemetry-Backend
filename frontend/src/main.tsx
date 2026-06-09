import React from 'react';
import ReactDOM from 'react-dom/client';
import PublicDashboard from './PublicDashboard';
import AdminPanel from './AdminPanel';
import './index.css';
import Dither from './components/Dither';

// Dynamically extract configuration from the loader script tag
const scriptElement = document.querySelector('script[src*="telemetry.js"]');
const prefix = scriptElement?.getAttribute('data-prefix') || '/_cloud_telemetry';
const pageType = document.body.getAttribute('data-page') || scriptElement?.getAttribute('data-page') || 'public';

const rootElement = document.getElementById('app');
if (rootElement) {
  rootElement.removeAttribute('data-loading');
  const root = ReactDOM.createRoot(rootElement);
  
  root.render(
    <React.StrictMode>
      <Dither
        waveColor={[0.11, 0.15, 0.3]}
        waveSpeed={0.038}
        waveFrequency={2}
        waveAmplitude={0.36}
        brightness={0.85}
        driftStrength={0.22}
      />
      {pageType === 'admin' ? (
        <AdminPanel apiPrefix={prefix} />
      ) : (
        <PublicDashboard apiPrefix={prefix} />
      )}
    </React.StrictMode>
  );
}
