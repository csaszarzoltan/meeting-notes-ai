import { useEffect, useRef, useState } from 'react';
import { useLiveSession } from './useLiveSession';
import type { LiveStatus } from './useLiveSession';

const STATUS_LABEL: Record<LiveStatus, string> = {
  idle: 'Not connected',
  starting: 'Starting session…',
  connecting: 'Connecting microphone…',
  streaming: 'Live — recording',
  finalizing: 'Finalizing…',
  finalized: 'Finalized',
  error: 'Error',
};

export function LiveTranscriptionView() {
  const {
    status,
    token,
    meetingId,
    error,
    partials,
    finalized,
    login,
    logout,
    startSession,
    connect,
    finalize,
    disconnect,
  } = useLiveSession();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const transcriptRef = useRef<HTMLDivElement>(null);

  // Keep the streaming panel pinned to the newest partial.
  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [partials, finalized]);

  const latestText =
    finalized?.transcript ??
    partials
      .map((p) => p.text)
      .filter(Boolean)
      .join(' ')
      .trim();

  return (
    <section className="card" aria-labelledby="live-title">
      <div className="live-head">
        <div>
          <h2 id="live-title">Live transcription</h2>
          <p className="hint">
            Stream audio from your microphone and get a live transcript with action items —
            no upload required.
          </p>
        </div>
        <span className={`badge badge-${status === 'streaming' ? 'live' : status === 'finalized' ? 'ok' : 'muted'}`} aria-live="polite">
          {STATUS_LABEL[status]}
        </span>
      </div>

      {!token ? (
        <form
          className="auth-form"
          onSubmit={(e) => {
            e.preventDefault();
            void login(email, password);
          }}
        >
          <div className="grid">
            <div>
              <label htmlFor="live-email">Email</label>
              <input
                id="live-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="live-password">Password</label>
              <input
                id="live-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>
          <button type="submit" disabled={status === 'connecting'}>
            Log in
          </button>
          <p className="hint">
            Uses <code>POST /api/v1/auth/login</code>. New users can sign up via{' '}
            <code>POST /api/v1/auth/signup</code>.
          </p>
        </form>
      ) : (
        <div className="session-bar">
          <span className="badge">Logged in</span>
          {meetingId && (
            <span className="muted" title="Draft meeting this session attaches to">
              Meeting {meetingId.slice(0, 8)}…
            </span>
          )}
          <button type="button" className="ghost" onClick={logout}>
            Log out
          </button>
        </div>
      )}

      {token && (
        <div className="controls" role="group" aria-label="Live session controls">
          <button
            type="button"
            onClick={() => void startSession()}
            disabled={status === 'starting' || status === 'streaming' || status === 'finalizing'}
          >
            New live session
          </button>
          <button
            type="button"
            onClick={() => void connect()}
            disabled={!meetingId || status === 'connecting' || status === 'streaming' || status === 'finalizing'}
          >
            {status === 'streaming' ? 'Recording…' : 'Connect microphone'}
          </button>
          <button
            type="button"
            onClick={finalize}
            disabled={status !== 'streaming' && status !== 'finalizing'}
          >
            Finalize &amp; extract actions
          </button>
          <button type="button" className="ghost" onClick={disconnect} disabled={status !== 'streaming'}>
            Stop
          </button>
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div
        ref={transcriptRef}
        className="transcript"
        aria-live="polite"
        aria-label="Streaming transcript"
        data-testid="transcript-panel"
      >
        {latestText ? (
          <p>{latestText}</p>
        ) : (
          <p className="muted">
            {status === 'streaming'
              ? 'Listening… partial transcript will appear here.'
              : 'Transcript will stream here as you speak.'}
          </p>
        )}
      </div>

      {partials.length > 0 && status !== 'finalized' && (
        <p className="hint">
          {partials.length} partial update{partials.length === 1 ? '' : 's'} · last sequence{' '}
          {partials[partials.length - 1].sequence}
        </p>
      )}

      {finalized && (
        <div className="finalized" aria-label="Finalized meeting notes">
          {finalized.summary && (
            <>
              <h3>Summary</h3>
              <p>{finalized.summary}</p>
            </>
          )}
          <h3>Action items</h3>
          {finalized.action_items.length > 0 ? (
            <ul className="actions">
              {finalized.action_items.map((item, i) => (
                <li key={`${item.description}-${i}`}>
                  {item.assignee ? <strong>{item.assignee}: </strong> : null}
                  {item.description}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No action items extracted.</p>
          )}
          {finalized.decisions.length > 0 && (
            <>
              <h3>Decisions</h3>
              <ul className="actions">
                {finalized.decisions.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </>
          )}
          <p className="hint">
            Session {finalized.session_id ?? 'n/a'} · {finalized.chunk_count} chunks ·{' '}
            {finalized.partial_count} partials · {finalized.duration_seconds.toFixed(1)}s
          </p>
        </div>
      )}
    </section>
  );
}
