import { useEffect, useMemo, useState } from 'react';
import { workspaceRequest } from '../api/workspace';

interface WorkAction {
  id: string;
  title: string;
  owner: string;
  due: string;
  meeting: string;
  timestamp: string;
  status: string;
  destination: string;
  external_id?: string | null;
  external_url?: string | null;
  sync_state?: string;
}

interface PreviewData {
  title: string;
  description: string;
  assignee: string;
  priority: string;
  due: string;
  project: string;
  destination: string;
}

const FILTERS = [
  'Assigned to me',
  'Unassigned',
  'Due soon',
  'Overdue',
  'Waiting for approval',
  'Queued',
  'Completed',
];

/** Persisted action confirmation and connector synchronization. */
export function ActionCenter() {
  const [items, setItems] = useState<WorkAction[]>([]);
  const [integrations, setIntegrations] = useState<Record<string, { connected: boolean }>>({});
  const [filter, setFilter] = useState('Assigned to me');
  const [error, setError] = useState('');
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [previewActionId, setPreviewActionId] = useState<string | null>(null);
  const [editingFields, setEditingFields] = useState<Partial<PreviewData>>({});

  const load = () =>
    workspaceRequest<{ items: WorkAction[] }>('/actions')
      .then((b) => setItems(b.items))
      .catch((e: Error) => setError(e.message));

  const loadIntegrations = () =>
    workspaceRequest<{ items: Record<string, { connected: boolean }> }>('/integrations')
      .then((b) => setIntegrations(b.items))
      .catch(() => setIntegrations({}));

  useEffect(() => {
    void load();
    void loadIntegrations();
  }, []);

  const visible = useMemo(
    () =>
      items.filter(
        (i) =>
          filter === 'Unassigned'
            ? i.owner === 'Unassigned'
            : filter === 'Overdue'
              ? i.due === 'Overdue'
              : filter === 'Queued'
                ? i.status === 'queued'
                : filter === 'Completed'
                  ? i.status === 'completed'
                  : filter === 'Waiting for approval'
                    ? i.status === 'suggested'
                    : filter === 'Assigned to me'
                      ? i.owner === 'Zoltan'
                      : true,
      ),
    [items, filter],
  );

  const confirm = async (i: WorkAction) => {
    await workspaceRequest(`/actions/${i.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'confirmed', owner: i.owner, due: i.due }),
    });
    await load();
  };

  const sync = async (i: WorkAction) => {
    setSyncingId(i.id);
    setError('');
    try {
      const updated = await workspaceRequest<WorkAction>(`/actions/${i.id}/queue`, {
        method: 'POST',
        body: JSON.stringify({ destination: i.destination, confirmed: true }),
      });
      setItems((prev) => prev.map((a) => (a.id === i.id ? updated : a)));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sync failed';
      setError(msg);
    } finally {
      setSyncingId(null);
    }
  };

  const requestPreview = async (i: WorkAction) => {
    setSyncingId(i.id);
    setError('');
    try {
      // Attempt queue without confirmed to get preview via 409
      const resp = await workspaceRequest<{ detail: { preview: PreviewData; message: string } }>(
        `/actions/${i.id}/queue`,
        {
          method: 'POST',
          body: JSON.stringify({ destination: i.destination }),
        },
      );
      // If somehow succeeds without preview, just sync
      setItems((prev) => prev.map((a) => (a.id === i.id ? resp as unknown as WorkAction : a)));
    } catch (e: unknown) {
      // Check if it's a 409 with preview data
      const err = e as { message?: string; status?: number; data?: { preview?: PreviewData } };
      if (err.data?.preview) {
        setPreviewData(err.data.preview);
        setPreviewActionId(i.id);
        setEditingFields(err.data.preview);
      } else {
        setError(err.message || 'Failed to get preview');
      }
    } finally {
      setSyncingId(null);
    }
  };

  const confirmPush = async () => {
    if (!previewActionId || !previewData) return;
    setSyncingId(previewActionId);
    setError('');
    try {
      const updated = await workspaceRequest<WorkAction>(`/actions/${previewActionId}/queue`, {
        method: 'POST',
        body: JSON.stringify({
          destination: editingFields.destination || previewData.destination,
          confirmed: true,
        }),
      });
      setItems((prev) => prev.map((a) => (a.id === previewActionId ? updated : a)));
      setPreviewData(null);
      setPreviewActionId(null);
      setEditingFields({});
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sync failed';
      setError(msg);
    } finally {
      setSyncingId(null);
    }
  };

  const cancelPreview = () => {
    setPreviewData(null);
    setPreviewActionId(null);
    setEditingFields({});
  };

  const setDestination = (i: WorkAction, destination: string) => {
    setItems((prev) => prev.map((a) => (a.id === i.id ? { ...a, destination } : a)));
  };

  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Execution layer</span>
          <h2>Action Center</h2>
          <p>Confirm ownership and synchronize accountable work.</p>
        </div>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span>!</span>
          <div>
            <p>{error}</p>
            <button
              className="text-button"
              style={{ padding: 0 }}
              onClick={() => setError('')}
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Preview / Confirmation Card */}
      {previewData && (
        <div className="preview-card" style={{ border: '2px solid #3b82f6', borderRadius: 8, padding: 16, marginBottom: 16, background: '#f0f7ff' }}>
          <h3 style={{ margin: '0 0 12px' }}>Preview: Sync to {previewData.destination}</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <label>
              Title
              <input
                value={editingFields.title ?? previewData.title}
                onChange={(e) => setEditingFields((p) => ({ ...p, title: e.target.value }))}
                style={{ width: '100%', marginTop: 2 }}
              />
            </label>
            <label>
              Assignee
              <input
                value={editingFields.assignee ?? previewData.assignee}
                onChange={(e) => setEditingFields((p) => ({ ...p, assignee: e.target.value }))}
                style={{ width: '100%', marginTop: 2 }}
              />
            </label>
            <label>
              Priority
              <select
                value={editingFields.priority ?? previewData.priority}
                onChange={(e) => setEditingFields((p) => ({ ...p, priority: e.target.value }))}
                style={{ width: '100%', marginTop: 2 }}
              >
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
              </select>
            </label>
            <label>
              Project
              <input
                value={editingFields.project ?? previewData.project}
                onChange={(e) => setEditingFields((p) => ({ ...p, project: e.target.value }))}
                style={{ width: '100%', marginTop: 2 }}
              />
            </label>
            <label style={{ gridColumn: '1 / -1' }}>
              Description
              <textarea
                value={editingFields.description ?? previewData.description}
                onChange={(e) => setEditingFields((p) => ({ ...p, description: e.target.value }))}
                rows={3}
                style={{ width: '100%', marginTop: 2 }}
              />
            </label>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button
              className="primary"
              disabled={syncingId === previewActionId}
              onClick={() => void confirmPush()}
            >
              {syncingId === previewActionId ? 'Syncing…' : 'Confirm & Push'}
            </button>
            <button className="secondary" onClick={cancelPreview}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="filter-strip">
        {FILTERS.map((f) => (
          <button
            className={f === filter ? 'active' : ''}
            onClick={() => setFilter(f)}
            key={f}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="execution-list">
        {visible.map((i) => (
          <article className="execution-card" key={i.id}>
            <div className="execution-main">
              <span
                className={`status-pill ${i.sync_state === 'task-synced' ? 'task-synced' : `task-${i.status}`}`}
              >
                {i.sync_state === 'task-synced' ? 'task-synced' : i.status}
              </span>
              <strong>{i.title}</strong>
              <p>
                {i.owner} · {i.due} · {i.meeting}
              </p>
              <button className="evidence-link">Source evidence · {i.timestamp}</button>
            </div>
            <div className="execution-destination">
              {i.status === 'confirmed' ? (
                <>
                  <select
                    aria-label="Sync destination"
                    value={i.destination === 'Not selected' ? '' : i.destination}
                    onChange={(e) => setDestination(i, e.target.value)}
                  >
                    <option value="" disabled>
                      Select destination…
                    </option>
                    {Object.entries(integrations)
                      .filter(([, s]) => s.connected)
                      .map(([name]) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                  </select>
                  <button
                    className="primary compact"
                    disabled={syncingId === i.id || i.destination === 'Not selected'}
                    onClick={() => void requestPreview(i)}
                  >
                    {syncingId === i.id ? 'Loading preview…' : 'Sync'}
                  </button>
                </>
              ) : i.status === 'suggested' ? (
                <button className="primary" onClick={() => void confirm(i)}>
                  Confirm action
                </button>
              ) : i.status === 'queued' && i.external_url ? (
                <a
                  href={i.external_url}
                  target="_blank"
                  rel="noreferrer"
                  className="primary compact"
                  style={{ textDecoration: 'none', display: 'inline-block', textAlign: 'center' }}
                >
                  View in {i.destination}
                </a>
              ) : i.status === 'queued' ? (
                <span>{i.external_id}</span>
              ) : (
                <button
                  className="secondary"
                  disabled={syncingId === i.id}
                  onClick={() => void requestPreview(i)}
                >
                  {syncingId === i.id
                    ? 'Loading preview…'
                    : `Sync to ${i.destination || 'provider'}`}
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
