import { LiveTranscriptionView } from './live/LiveTranscriptionView';

export function App() {
  return (
    <div className="wrap">
      <header>
        <h1>MeetingNotesAI</h1>
        <p className="muted">Live transcription and action items — stream from your microphone.</p>
        <nav aria-label="Dashboard sections">
          <a href="/app">Upload &amp; review</a>
          <a href="/app/live" aria-current="page" className="active">
            Live transcription
          </a>
        </nav>
      </header>
      <main id="main-content" tabIndex={-1}>
        <LiveTranscriptionView />
      </main>
    </div>
  );
}
