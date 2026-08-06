/** Google Calendar integration API client.
 *
 * Backend routes live under /api/v1/integrations/google-calendar (NOT the
 * /api/v1/workspace prefix used by workspaceRequest), so this module uses its
 * own request helper with the same bearer-token auth pattern.
 */
interface CalendarRequestInit {
  method?: string;
  body?: unknown;
}

async function calendarRequest<T>(path: string, init?: CalendarRequestInit): Promise<T> {
  const token = sessionStorage.getItem('workspace_token') ?? '';
  const response = await fetch(`/api/v1/integrations/google-calendar${path}`, {
    method: init?.method ?? 'GET',
    headers: {
      ...(init?.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({})) as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`);
  return body;
}

export interface CalendarEvent {
  id: string;
  summary: string;
  description: string;
  start: string;
  end: string;
  attendees: Array<{ email: string; display_name: string; response_status: string }>;
  location: string;
  meet_link: string | null;
  organizer: { email: string; display_name: string };
  calendar_id: string;
  html_link: string;
  imported: boolean;
}

export interface CalendarStatus {
  connected: boolean;
  calendar_id: string;
  connected_at: string | null;
  token_expires_at: string | null;
  needs_reauth: boolean;
}

export interface ImportResult {
  meeting: {
    id: string;
    title: string;
    source: string;
    google_calendar_event_id: string;
    date: string;
    duration: string;
    participants: number;
    review_status: string;
    calendar_context: {
      attendees: string[];
      location: string;
      meet_link: string | null;
      description: string;
    };
  };
}

/** Start the OAuth flow: POST /auth, returns the Google consent URL. */
export async function initiateCalendarAuth(): Promise<{ authorization_url: string; state: string }> {
  return calendarRequest<{ authorization_url: string; state: string }>('/auth', { method: 'POST' });
}

/** Check whether the current user has connected Google Calendar. */
export async function getCalendarStatus(): Promise<CalendarStatus> {
  return calendarRequest<CalendarStatus>('/status');
}

/** List upcoming events (default: next 7 days). */
export async function fetchUpcomingEvents(days = 7): Promise<{ events: CalendarEvent[]; calendar_id: string; days: number }> {
  return calendarRequest<{ events: CalendarEvent[]; calendar_id: string; days: number }>(`/events?days=${days}`);
}

/** Import a calendar event as a meeting record. */
export async function importCalendarEvent(eventId: string, calendarId = 'primary'): Promise<ImportResult> {
  return calendarRequest<ImportResult>(`/import/${encodeURIComponent(eventId)}?calendar_id=${calendarId}`, {
    method: 'POST',
  });
}

/** Disconnect Google Calendar (soft-delete stored tokens). */
export async function disconnectCalendar(): Promise<void> {
  await calendarRequest<void>('/disconnect', { method: 'DELETE' });
}

// Backwards-compatible aliases used by the shared event picker.
export const getAuthUrl = initiateCalendarAuth;
export const listEvents = fetchUpcomingEvents;
export const importEvent = importCalendarEvent;
