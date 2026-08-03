/**
 * WebSocket + REST contract types for the live transcription view.
 *
 * Mirrors the server contract in meeting_notes_ai/live_session.py and the
 * WS handler in meeting_notes_ai/routes/live_transcription.py.
 */

/** One incremental transcript fragment pushed over the WebSocket. */
export interface LivePartial {
  type: 'partial';
  sequence: number;
  text: string;
  timestamp: string | null;
}

/** Action item extracted after finalization. */
export interface ActionItem {
  assignee?: string | null;
  description: string;
  status?: string | null;
  due_date?: string | null;
}

/** Full transcript result returned by the finalized frame. */
export interface FinalizedResult {
  type: 'finalized';
  session_id: string | null;
  meeting_id: string;
  transcript: string;
  summary: string;
  action_items: ActionItem[];
  decisions: string[];
  key_points: string[];
  chunk_count: number;
  partial_count: number;
  duration_seconds: number;
}

/** Server-side error frame (e.g. rate_limited). */
export interface LiveErrorFrame {
  type: 'error';
  code?: string;
  detail?: string;
}

export type LiveServerMessage = LivePartial | FinalizedResult | LiveErrorFrame;

/** POST /api/v1/auth/login response. */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at?: string | null;
}

/** POST /api/v1/meetings/live/start response. */
export interface LiveStartResponse {
  meeting_id: string;
  status: string;
}
