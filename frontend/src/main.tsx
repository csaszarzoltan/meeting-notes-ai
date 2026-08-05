import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { AuthGate } from './AuthGate';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('Missing #root mount point');

createRoot(container).render(
  <StrictMode>
    <AuthGate><App /></AuthGate>
  </StrictMode>,
);
