import { useMemo, useState } from 'react';

type ActionStatus = 'Suggested' | 'Confirmed' | 'Synced' | 'Completed';
interface WorkAction { id: number; title: string; owner: string; due: string; meeting: string; timestamp: string; status: ActionStatus; destination: string; }
const INITIAL: WorkAction[] = [
  { id: 1, title: 'Deliver the source-linked review prototype', owner: 'Zoltan', due: 'Today', meeting: 'Q3 product roadmap', timestamp: '18:42', status: 'Suggested', destination: 'Microsoft Planner' },
  { id: 2, title: 'Validate privacy defaults with regulated users', owner: 'Maya', due: 'Tomorrow', meeting: 'Security review', timestamp: '32:10', status: 'Confirmed', destination: 'Jira' },
  { id: 3, title: 'Send the renewal recap to Northstar', owner: 'Unassigned', due: 'Overdue', meeting: 'Northstar client sync', timestamp: '47:03', status: 'Suggested', destination: 'Salesforce' },
  { id: 4, title: 'Publish onboarding success metrics', owner: 'Zoltan', due: 'Friday', meeting: 'Growth sync', timestamp: '11:26', status: 'Synced', destination: 'Linear' },
];
const FILTERS = ['Assigned to me', 'Unassigned', 'Due soon', 'Overdue', 'Waiting for approval', 'Synced', 'Completed'];

/** Convert extracted commitments into confirmed, synchronized work. */
export function ActionCenter() {
  const [items, setItems] = useState(INITIAL); const [filter, setFilter] = useState('Assigned to me');
  const visible = useMemo(() => items.filter((item) => filter === 'Unassigned' ? item.owner === 'Unassigned' : filter === 'Overdue' ? item.due === 'Overdue' : filter === 'Synced' ? item.status === 'Synced' : filter === 'Completed' ? item.status === 'Completed' : filter === 'Waiting for approval' ? item.status === 'Suggested' : filter === 'Assigned to me' ? item.owner === 'Zoltan' : true), [filter, items]);
  const update = (id: number, status: ActionStatus) => setItems((current) => current.map((item) => item.id === id ? { ...item, status } : item));
  return <section aria-labelledby="actions-title"><div className="page-heading"><div><span className="eyebrow">Execution layer</span><h2 id="actions-title">Action Center</h2><p>Confirm ownership, set deadlines, and move commitments into real work.</p></div><button className="primary">Connect task system</button></div>
    <div className="action-stats"><article><strong>{items.filter((item) => item.status === 'Suggested').length}</strong><span>Waiting for approval</span></article><article><strong>4</strong><span>Due soon</span></article><article><strong>1</strong><span>Overdue</span></article><article><strong>{items.filter((item) => item.status === 'Synced').length}</strong><span>Synced</span></article></div>
    <div className="filter-strip" aria-label="Action filters">{FILTERS.map((name) => <button key={name} className={filter === name ? 'active' : ''} onClick={() => setFilter(name)}>{name}</button>)}</div>
    <div className="execution-list">{visible.map((item) => <article className="execution-card" key={item.id}><label><input type="checkbox" checked={item.status === 'Completed'} onChange={() => update(item.id, item.status === 'Completed' ? 'Confirmed' : 'Completed')} /><span className="sr-only">Mark {item.title} complete</span></label><div className="execution-main"><div><span className={`status-pill task-${item.status.toLowerCase()}`}>{item.status}</span><strong>{item.title}</strong></div><p><span className="avatar tiny">{item.owner[0]}</span>{item.owner} · {item.due} · {item.meeting}</p><button className="evidence-link">◉ Source evidence · {item.timestamp}</button></div><div className="execution-destination"><small>Destination</small><strong>{item.destination}</strong>{item.status === 'Suggested' ? <button className="primary compact" onClick={() => update(item.id, 'Confirmed')}>Confirm action</button> : <button className="secondary">{item.status === 'Synced' ? 'Open task ↗' : 'Sync now'}</button>}</div></article>)}</div>
  </section>;
}
