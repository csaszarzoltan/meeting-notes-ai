import { useMemo, useState } from 'react';
import type { MeetingCard } from './types';

const SEED: MeetingCard[] = [
  { id: 'q3', title: 'Q3 product roadmap', date: 'Today, 10:30', duration: '42 min', mode: 'General', status: 'needs_review', participants: 6, summary: 'Prioritized activation, mobile review, and enterprise controls.' },
  { id: 'clinic', title: 'Patient follow-up', date: 'Yesterday, 15:00', duration: '28 min', mode: 'Healthcare', status: 'approved', participants: 2, summary: 'SOAP note approved with PHI redaction verified.' },
  { id: 'client', title: 'Northstar client sync', date: 'Mon, 09:00', duration: '51 min', mode: 'General', status: 'ready', participants: 8, summary: 'Renewal risks, ownership, and next milestones captured.' },
];

/** Searchable, filterable meeting library with an actionable empty state. */
export function MeetingLibrary({ onOpen }: { onOpen: (meeting: MeetingCard) => void }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const visible = useMemo(() => SEED.filter((item) =>
    item.title.toLowerCase().includes(query.toLowerCase()) && (status === 'all' || item.status === status)), [query, status]);
  return <section aria-labelledby="meetings-title">
    <div className="page-heading"><div><span className="eyebrow">Knowledge hub</span><h2 id="meetings-title">Meetings</h2><p>Find every decision, action, and source moment.</p></div><button className="primary">＋ New meeting</button></div>
    <div className="toolbar" role="search">
      <label className="search-field"><span className="sr-only">Search meetings</span><span aria-hidden="true">⌕</span><input aria-label="Search meetings" placeholder="Search meetings, people, or topics" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <label><span className="sr-only">Filter by status</span><select aria-label="Filter meetings by status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All statuses</option><option value="needs_review">Needs review</option><option value="approved">Approved</option><option value="ready">Ready</option></select></label>
      <button className="secondary">Filters <span className="shortcut">F</span></button>
    </div>
    {visible.length ? <div className="meeting-list">{visible.map((meeting) => <button className="meeting-row" key={meeting.id} onClick={() => onOpen(meeting)}>
      <span className={`mode-icon mode-${meeting.mode.toLowerCase()}`}>{meeting.mode === 'Healthcare' ? '✚' : '◉'}</span>
      <span className="meeting-main"><strong>{meeting.title}</strong><small>{meeting.summary}</small><span className="meta">{meeting.date} · {meeting.duration} · {meeting.participants} people</span></span>
      <span className={`status-pill status-${meeting.status}`}>{meeting.status === 'needs_review' ? 'Needs review' : meeting.status === 'approved' ? 'Approved' : 'Ready'}</span><span aria-hidden="true">›</span>
    </button>)}</div> : <div className="empty-state"><span className="empty-icon">⌕</span><h3>No meetings match</h3><p>Clear your filters or record a new conversation.</p><button className="secondary" onClick={() => { setQuery(''); setStatus('all'); }}>Clear filters</button></div>}
  </section>;
}
