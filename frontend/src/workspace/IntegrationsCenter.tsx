import { useEffect, useState, useCallback } from 'react';
import { workspaceRequest } from '../api/workspace';
import { getCalendarStatus, disconnectCalendar, getAuthUrl } from '../api/googleCalendar';

interface IntegrationState {
  connected: boolean;
  provider?: string;
  mode?: string;
  account_email?: string;
  account_url?: string;
  token_expires_at?: string | null;
}

interface HealthState {
  status: 'healthy' | 'expiring_soon' | 'needs_reauth' | 'disconnected';
  token_expires_at: string | null;
  last_sync: string | null;
  error_count: number;
  provider: string;
  account_email: string;
}

interface CredentialField {
  key: string;
  label: string;
  placeholder: string;
  optional?: boolean;
}

/** Per-provider credential form fields (POSTed as {credentials: {...}}). */
const CREDENTIAL_FIELDS: Record<string, CredentialField[]> = {
  jira: [
    { key: 'token', label: 'OAuth2 access token', placeholder: 'paste access token' },
    { key: 'site_url', label: 'Site URL', placeholder: 'https://acme.atlassian.net' },
    { key: 'email', label: 'Email', placeholder: 'you@acme.com', optional: true },
    { key: 'default_project', label: 'Default project key', placeholder: 'ACME', optional: true },
  ],
  linear: [
    { key: 'token', label: 'API key', placeholder: 'lin_api_xxx' },
    { key: 'workspace_url', label: 'Workspace URL', placeholder: 'https://acme.linear.app', optional: true },
    { key: 'default_project', label: 'Team ID', placeholder: 'team-uuid', optional: true },
  ],
  asana: [
    { key: 'token', label: 'Personal access token', placeholder: '1/xxxxx:yyyyy' },
    { key: 'email', label: 'Email', placeholder: 'you@acme.com', optional: true },
    { key: 'default_project', label: 'Workspace GID', placeholder: 'workspace-gid', optional: true },
  ],
  todoist: [
    { key: 'token', label: 'REST token', placeholder: 'paste REST token' },
    { key: 'email', label: 'Email', placeholder: 'you@acme.com', optional: true },
    { key: 'default_project', label: 'Project ID', placeholder: 'project-id', optional: true },
  ],
};

/** Status dot color mapping. */
const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e',
  expiring_soon: '#eab308',
  needs_reauth: '#ef4444',
  disconnected: '#ef4444',
};

/** Format ISO timestamp to human-readable relative time. */
function formatLastSync(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  if (diffMs < 60_000) return 'just now';
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}h ago`;
  return d.toLocaleDateString();
}

/** Persisted connector configuration catalog with PM credential connect flow. */
export function IntegrationsCenter() {
  const [items, setItems] = useState<Record<string, IntegrationState>>({})
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [formOpen, setFormOpen] = useState<string | null>(null);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [healthMap, setHealthMap] = useState<Record<string, HealthState>>({});

  const load = () =>
    workspaceRequest<{ items: Record<string, IntegrationState> }>('/integrations')
      .then((b) => setItems(b.items))
      .catch((e: Error) => setError(e.message));

  /** Fetch health status for all PM integrations. */
  const loadHealth = useCallback(async (integrations: Record<string, IntegrationState>) => {
    const entries = Object.entries(integrations);
    const results: Record<string, HealthState> = {};
    await Promise.allSettled(
      entries.map(async ([name, state]) => {
        if (!state.provider) return;
        try {
          const h = await workspaceRequest<HealthState>(
            `/integrations/${encodeURIComponent(name)}/health`
          );
          results[name] = h;
        } catch {
          // Health endpoint not available or 404 — skip
        }
      })
    );
    setHealthMap(results);
  }, []);

  useEffect(() => {
    void load();
    void getCalendarStatus()
      .then((b) => setCalendarConnected(b.connected))
      .catch(() => setCalendarConnected(false));
  }, []);

  /** Reload integrations + health after connect/disconnect. */
  const reloadAll = useCallback(async () => {
    const resp = await workspaceRequest<{ items: Record<string, IntegrationState> }>('/integrations');
    setItems(resp.items);
    await loadHealth(resp.items);
  }, [loadHealth]);

  useEffect(() => {
    if (Object.keys(items).length > 0) {
      void loadHealth(items);
    }
  }, [items, loadHealth]);

  const openForm = (name: string) => {
    setFormOpen(name);
    setCreds({});
    setError('');
  };

  const connect = async (name: string) => {
    setSaving(name);
    setError('');
    try {
      await workspaceRequest(`/integrations/${encodeURIComponent(name)}/connect`, {
        method: 'POST',
        body: JSON.stringify({ credentials: creds }),
      });
      setFormOpen(null);
      await reloadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      setSaving(null);
    }
  };

  const toggle = async (name: string, enabled: boolean) => {
    setError('');
    try {
      await workspaceRequest(`/integrations/${encodeURIComponent(name)}/connect`, {
        method: 'POST',
        body: JSON.stringify({ enabled }),
      });
      await reloadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  };

  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Execution connections</span>
          <h2>Integrations</h2>
        </div>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span>!</span>
          <div>
            <p>{error}</p>
          </div>
        </div>
      )}

      <div className="integration-grid">
        <article className="integration-card featured" style={{ borderColor: 'var(--accent)' }}>
          <span className="integration-logo">G</span>
          <div>
            <h3>Google Calendar</h3>
            <p>{calendarConnected ? 'Connected · Syncing events' : 'Browse and import meetings'}</p>
          </div>
          <button
            className={calendarConnected ? 'secondary' : 'primary'}
            onClick={
              calendarConnected
                ? () => {
                    void disconnectCalendar().then(() => setCalendarConnected(false));
                  }
                : async () => {
                    const { authorization_url } = await getAuthUrl();
                    window.location.href = authorization_url;
                  }
            }
          >
            {calendarConnected ? 'Disconnect' : 'Connect'}
          </button>
        </article>

        {Object.entries(items).map(([name, state]) => {
          const provider = state.provider ?? '';
          const isPm = provider in CREDENTIAL_FIELDS;
          const health = healthMap[name];
          const statusColor = health ? STATUS_COLORS[health.status] ?? '#94a3b8' : '#94a3b8';
          const lastSyncText = health ? formatLastSync(health.last_sync) : null;

          if (!isPm) {
            // Legacy connector: plain toggle
            return (
              <article className="integration-card" key={name}>
                <span className="integration-logo">{name[0]}</span>
                <div>
                  <h3>{name}</h3>
                  <p>Persistent connector configuration</p>
                </div>
                <button
                  className={state.connected ? 'secondary' : 'primary'}
                  onClick={() => void toggle(name, !state.connected)}
                >
                  {state.connected ? 'Disconnect' : 'Connect'}
                </button>
              </article>
            );
          }
          // PM provider: form-backed connect with health indicators
          return (
            <article className="integration-card" key={name}>
              <span className="integration-logo">{name[0]}</span>
              <div>
                <h3>
                  {name}
                  {state.connected && health && (
                    <span
                      title={`Status: ${health.status}`}
                      style={{
                        display: 'inline-block',
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        backgroundColor: statusColor,
                        marginLeft: 8,
                        verticalAlign: 'middle',
                      }}
                    />
                  )}
                </h3>
                <p>
                  {state.connected
                    ? `Connected · ${state.account_email ?? ''}${state.account_url ? ` · ${state.account_url}` : ''}`
                    : 'Connect with API credentials'}
                </p>
                {state.connected && lastSyncText && (
                  <p style={{ fontSize: '0.8em', color: 'var(--text-muted, #888)', margin: '2px 0 0' }}>
                    Last sync: {lastSyncText}
                  </p>
                )}
                {state.connected && state.account_url ? (
                  <a href={state.account_url} target="_blank" rel="noreferrer">
                    Open {name}
                  </a>
                ) : null}
              </div>
              {state.connected ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
                  {health?.status === 'needs_reauth' && (
                    <button
                      className="primary"
                      onClick={() => openForm(name)}
                      style={{ fontSize: '0.85em' }}
                    >
                      Re-authorize
                    </button>
                  )}
                  {health?.status === 'expiring_soon' && (
                    <button
                      className="secondary"
                      onClick={() => openForm(name)}
                      style={{ fontSize: '0.85em' }}
                    >
                      Renew token
                    </button>
                  )}
                  <button className="secondary" onClick={() => void toggle(name, false)}>
                    Disconnect
                  </button>
                </div>
              ) : formOpen === name ? (
                <button className="primary" disabled={saving === name} onClick={() => void connect(name)}>
                  {saving === name ? 'Connecting…' : 'Save connection'}
                </button>
              ) : (
                <button className="primary" onClick={() => openForm(name)}>
                  Connect
                </button>
              )}
              {formOpen === name && (
                <div className="integration-form">
                  {CREDENTIAL_FIELDS[provider]?.map((field) => (
                    <label key={field.key}>
                      {field.label}
                      {field.optional ? ' (optional)' : ''}
                      <input
                        type={field.key === 'token' ? 'password' : 'text'}
                        placeholder={field.placeholder}
                        value={creds[field.key] ?? ''}
                        onChange={(e) => setCreds({ ...creds, [field.key]: e.target.value })}
                      />
                    </label>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
