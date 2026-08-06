
import { getAuthUrl, getCalendarStatus, listEvents, importEvent, CalendarEvent } from '../api/googleCalendar';
import { useEffect, useState } from 'react';
import { MeetingResult } from './types';
import { SkeletonGrid } from './AsyncState';

type CalendarEventPickerProps = {
  onComplete: (result: MeetingResult) => void;
};

export function CalendarEventPicker({ onComplete }: CalendarEventPickerProps) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [importing, setImporting] = useState<string | null>(null);
  const [imported, setImported] = useState<string | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    const fetchStatusAndEvents = async () => {
      try {
        const status = await getCalendarStatus();
        setConnected(status.connected);
        if (status.connected) {
          const { events } = await listEvents(7);
          setEvents(events);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch calendar status');
      } finally {
        setLoading(false);
      }
    };

    fetchStatusAndEvents();
  }, []);

  const handleConnect = async () => {
    try {
      const { authorization_url } = await getAuthUrl();
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start OAuth flow');
    }
  };

  const handleImport = async (eventId: string) => {
    try {
      setImporting(eventId);
      const result = await importEvent(eventId);
      setImported(eventId);
      // Normalize the import response into a full MeetingResult so the review
      // studio renders cleanly (calendar imports have no transcript/decisions yet).
      const meeting = result.meeting;
      const normalized: MeetingResult = {
        id: meeting.id,
        transcript: '',
        summary: meeting.title,
        action_items: [],
        decisions: [],
        key_points: [],
        mode: 'general',
        review_status: 'needs_review',
        phi_redacted: false,
        redaction_matches: 0,
        warnings: [],
      };
      onComplete(normalized);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import event');
    } finally {
      setImporting(null);
    }
  };

  if (connected === false) {
    return (
      <div className="calendar-connect">
        <h3>Connect your Google Calendar to import upcoming meetings</h3>
        <button onClick={handleConnect} className="primary">
          Connect Google Calendar
        </button>
      </div>
    );
  }

  if (loading) {
    return <SkeletonGrid />;
  }

  if (error) {
    return <div className="error-banner">{error}</div>;
  }

  if (events.length === 0 && !loading && connected === true) {
    return (
      <div className="empty-state">
        <h3>No upcoming meetings</h3>
        <p>Your calendar is clear for the next 7 days.</p>
      </div>
    );
  }

  return (
    <div className="calendar-events">
      <h3>Upcoming Meetings</h3>
      <div className="event-list">
        {events.map((event) => (
          <div key={event.id} className="event-card">
            <h3>{event.summary}</h3>
            <div className="event-time">
              {new Date(event.start).toLocaleDateString()}
              {' '} - {' '}
              {new Date(event.start).toLocaleTimeString()} to {new Date(event.end).toLocaleTimeString()}
            </div>
            <div className="event-details">
              <p>{event.description}</p>
              <p>Attendees: {event.attendees.length}</p>
              <p>Location: {event.location}</p>
            </div>
            {event.attendees.length > 0 && (
              <div className="attendee-stack">
                {event.attendees.slice(0, 4).map((a) => (
                  <span key={a.email} className="attendee-avatar" title={a.display_name || a.email}>
                    {(a.display_name || a.email || '?').slice(0, 2).toUpperCase()}
                  </span>
                ))}
                {event.attendees.length > 4 && (
                  <span className="attendee-avatar">+{event.attendees.length - 4}</span>
                )}
              </div>
            )}
            <button
              onClick={() => handleImport(event.id)}
              disabled={event.imported || importing === event.id}
              className="secondary"
            >
              {event.imported ? '✓ Imported' : importing === event.id ? 'Importing…' : 'Import →'}
            </button>
            {imported === event.id && <div className="import-success">✓ Imported to your workspace</div>}
          </div>
        ))}
      </div>
    </div>
  );
}