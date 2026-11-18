import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/studio.css';

// MANDATORY per modern-web-guidance: Feature-detect native Popover before loading polyfill
if (!Object.hasOwn(HTMLElement.prototype, 'popover')) {
  void import('@oddbird/popover-polyfill');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
