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
  const [filter, setFilter] = useState('Assigned to me');
  const [error, setError] = useState('');
  const [syncingId, setSyncingId] = useState<string | null>(null);

  const load = () =>
    workspaceRequest<{ items: WorkAction[] }>('/actions')
      .then((b) => setItems(b.items))
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    void load();
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
        body: JSON.stringify({ destination: i.destination }),
      });
      setItems((prev) => prev.map((a) => (a.id === i.id ? updated : a)));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sync failed';
      setError(msg);
    } finally {
      setSyncingId(null);
    }
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
              onClick={() => {
                /* retry last sync — find first syncing or just dismiss */
                setError('');
              }}
            >
              Try again
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
              <small>{i.destination}</small>
              {i.status === 'suggested' ? (
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
                  onClick={() => void sync(i)}
                >
                  {syncingId === i.id
                    ? 'Syncing…'
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
