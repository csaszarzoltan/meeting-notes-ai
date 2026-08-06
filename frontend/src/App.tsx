import { useEffect, useState } from 'react';
import { CommandPalette } from './workspace/CommandPalette';
import { ActionCenter } from './workspace/ActionCenter';
import { BatchCenter } from './workspace/BatchCenter';
import { ComplianceCenter } from './workspace/ComplianceCenter';
import { Dashboard } from './workspace/Dashboard';
import { InsightsCenter } from './workspace/InsightsCenter';
import { IntegrationsCenter } from './workspace/IntegrationsCenter';
import { LiveWorkspace } from './workspace/LiveWorkspace';
import { MeetingLibrary } from './workspace/MeetingLibrary';
import { MeetingSetup } from './workspace/MeetingSetup';
import { MobileNavigation } from './workspace/MobileNavigation';
import { PlaceholderView } from './workspace/PlaceholderView';
import { ReviewWorkspace } from './workspace/ReviewWorkspace';
import { SharingCenter } from './workspace/SharingCenter';
import { WorkspaceSettings } from './workspace/WorkspaceSettings';
import type { MeetingCard, MeetingResult, WorkspaceView } from './workspace/types';

const NAV: Array<[WorkspaceView, string, string]> = [
  ['home', '⌂', 'Home'], ['meetings', '◫', 'Meetings'], ['record', '●', 'Record'],
  ['actions', '✓', 'Actions'], ['batches', '▦', 'Batches'], ['team', '♙', 'Team'],
  ['sharing', '↗', 'Sharing'], ['insights', '✦', 'Insights'],
  ['compliance', '◈', 'Compliance'], ['integrations', '◇', 'Integrations'],
  ['settings', '⚙', 'Settings'],
];

/** Unified responsive application shell for the capture, trust, and execution layers. */
export function App() {

  const [view, setView] = useState<WorkspaceView>('home');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selected, setSelected] = useState<MeetingCard | null>(null);
  const [result, setResult] = useState<MeetingResult | null>(null);
  const [live, setLive] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setCommandOpen(true); } if (event.key === 'Escape') setCommandOpen(false); }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler); }, []);
  const navigate = (next: WorkspaceView) => {
    setView(next); setSelected(null); setResult(null); setLive(false); setMobileOpen(false);
  };
  const content = () => {
    if (selected || result) return <ReviewWorkspace meeting={selected ?? undefined} result={result ?? undefined} onBack={() => navigate('meetings')} onNavigate={navigate} />;
    if (live) return <LiveWorkspace />;
    if (view === 'home') return <Dashboard navigate={navigate} openMeeting={setSelected} />;
    if (view === 'meetings') return <MeetingLibrary onOpen={setSelected} />;
    if (view === 'record') return <MeetingSetup onComplete={setResult} onLive={() => setLive(true)} />;
    if (view === 'actions') return <ActionCenter />;
    if (view === 'batches') return <BatchCenter />;
    if (view === 'sharing') return <SharingCenter />;
    if (view === 'insights') return <InsightsCenter />;
    if (view === 'compliance') return <ComplianceCenter />;
    if (view === 'integrations') return <IntegrationsCenter />;
    if (view === 'settings') return <WorkspaceSettings />;
    return <PlaceholderView />;
  };
  return <div className="app-shell" data-theme={theme} data-density={density}><a className="skip-link" href="#main-content">Skip to main content</a>
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}><div className="brand"><span className="brand-mark">M</span><div><strong>MeetingNotes</strong><small>Verified intelligence</small></div></div><nav aria-label="Product navigation">{NAV.map(([id, icon, label]) => <button key={id} className={view === id && !selected ? 'active' : ''} onClick={() => navigate(id)}><span aria-hidden="true">{icon}</span>{label}{label === 'Actions' && <em>12</em>}</button>)}</nav><div className="sidebar-bottom"><div className="usage-meter"><span><strong>1,240</strong> / 1,500 min</span><progress max="1500" value="1240" /></div><div className="security-chip"><span>◈</span><div><strong>Privacy protected</strong><small>All systems healthy</small></div></div><button className="user-chip"><span className="avatar">Z</span><span><strong>Zoltan</strong><small>Acme workspace</small></span><span>⋯</span></button></div></aside>
    <div className="app-frame"><header className="topbar"><button className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle navigation">☰</button><button className="global-search" onClick={() => setCommandOpen(true)} aria-label="Open global search"><span>⌕</span><span>Search meetings, decisions, actions, or people</span><kbd>⌘ K</kbd></button><div className="top-actions"><button className="icon-button" aria-label="Toggle density" onClick={() => setDensity(density === 'comfortable' ? 'compact' : 'comfortable')}>↕</button><button className="icon-button" aria-label="Toggle theme" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? '☾' : '☀'}</button><button className="icon-button notification" aria-label="Notifications">♢<i></i></button><button className="primary compact" onClick={() => navigate('record')}>＋ New meeting</button></div></header><main id="main-content" tabIndex={-1} className={selected || result || live ? 'main-wide' : ''}>{content()}</main><MobileNavigation active={view} onNavigate={navigate} /><CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} onNavigate={navigate} onOpenMeeting={setSelected} /></div>
  </div>;
}
