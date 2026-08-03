import { useCallback, useEffect, useRef, useState } from 'react';
import type { FinalizedResult, LivePartial, LiveServerMessage, LiveStartResponse, TokenResponse } from './types';

export type LiveStatus =
  | 'idle' // not connected, no session yet
  | 'starting' // creating the draft meeting
  | 'connecting' // opening the WebSocket + microphone
  | 'streaming' // socket open, partials arriving
  | 'finalizing' // finalize control frame sent
  | 'finalized' // finalized frame received
  | 'error';

const WS_RECONNECT_CLOSE_CODES = new Set([4401, 4403, 4404]);

function wsUrl(meetingId: string, token: string, roomId?: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const params = new URLSearchParams({ token, meeting_id: meetingId });
  if (roomId) params.set('room_id', roomId);
  return `${proto}://${window.location.host}/api/v1/meetings/live?${params.toString()}`;
}

/**
 * Live transcription session hook.
 *
 * Owns the full lifecycle: login token → draft meeting → getUserMedia
 * microphone → WebSocket binary chunks → partial updates → finalize →
 * finalized result with action items. All server communication goes through
 * the real backend contract; nothing is mocked in the UI.
 */
export function useLiveSession() {
  const [status, setStatus] = useState<LiveStatus>('idle');
  const [token, setToken] = useState<string>(() => sessionStorage.getItem('live_token') ?? '');
  const [meetingId, setMeetingId] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [partials, setPartials] = useState<LivePartial[]>([]);
  const [finalized, setFinalized] = useState<FinalizedResult | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const statusRef = useRef<LiveStatus>('idle');
  statusRef.current = status;

  const setErrorMsg = useCallback((message: string) => {
    setError(message);
    setStatus('error');
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError('');
    try {
      const resp = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const body = (await resp.json()) as TokenResponse & { detail?: string };
      if (!resp.ok) {
        setErrorMsg(typeof body.detail === 'string' ? body.detail : 'Login failed');
        return;
      }
      setToken(body.access_token);
      sessionStorage.setItem('live_token', body.access_token);
      setStatus('idle');
    } catch (err) {
      setErrorMsg(`Login request failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [setErrorMsg]);

  const logout = useCallback(() => {
    sessionStorage.removeItem('live_token');
    setToken('');
    setMeetingId('');
    setPartials([]);
    setFinalized(null);
    setError('');
    setStatus('idle');
  }, []);

  const startSession = useCallback(async () => {
    setError('');
    setPartials([]);
    setFinalized(null);
    setStatus('starting');
    try {
      const resp = await fetch('/api/v1/meetings/live/start', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = (await resp.json()) as LiveStartResponse & { detail?: string };
      if (!resp.ok) {
        setErrorMsg(typeof body.detail === 'string' ? body.detail : 'Could not start a live session');
        return;
      }
      setMeetingId(body.meeting_id);
      setStatus('idle');
    } catch (err) {
      setErrorMsg(`Start session failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [token, setErrorMsg]);

  const connect = useCallback(async () => {
    if (!token || !meetingId) {
      setErrorMsg('Log in and start a session before connecting.');
      return;
    }
    setError('');
    setStatus('connecting');
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setErrorMsg('This browser does not support microphone capture (getUserMedia).');
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      const ws = new WebSocket(wsUrl(meetingId, token));
      wsRef.current = ws;

      ws.onopen = () => {
        // Stream WebM/Opus chunks as binary frames — the backend detects the
        // WebM magic bytes and treats them as WEBM_OPUS chunks.
        recorder.ondataavailable = (event: BlobEvent) => {
          if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
            ws.send(event.data);
          }
        };
        recorder.start(1000); // 1s slices → frequent partials
        setStatus('streaming');
      };

      ws.onmessage = (event: MessageEvent) => {
        let msg: LiveServerMessage;
        try {
          msg = JSON.parse(String(event.data)) as LiveServerMessage;
        } catch {
          return; // ignore non-JSON frames
        }
        if (msg.type === 'partial') {
          setPartials((prev) => {
            const next = [...prev];
            const idx = next.findIndex((p) => p.sequence === msg.sequence);
            if (idx >= 0) next[idx] = msg;
            else next.push(msg);
            return next.sort((a, b) => a.sequence - b.sequence);
          });
        } else if (msg.type === 'finalized') {
          setFinalized(msg);
          setStatus('finalized');
          stopCapture();
        } else if (msg.type === 'error') {
          setErrorMsg(msg.detail ?? msg.code ?? 'Live session error');
        }
      };

      ws.onerror = () => {
        setErrorMsg('WebSocket connection error.');
      };

      ws.onclose = (event: CloseEvent) => {
        // Stop the recorder; keep the session (it survives disconnects server-side).
        stopCapture();
        const inFlight =
          statusRef.current === 'streaming' ||
          statusRef.current === 'connecting' ||
          statusRef.current === 'finalizing';
        if (inFlight) {
          if (WS_RECONNECT_CLOSE_CODES.has(event.code)) {
            setErrorMsg(`Connection rejected (code ${event.code}). Check your token and meeting.`);
          } else {
            // Any close while the session is in flight — including "normal"
            // code 1000, which the backend uses when it crashes mid-stream —
            // means no `finalized` frame arrived. Surfacing it prevents a
            // silent hang (badge stuck on "Live — recording", unreachable
            // Finalize button).
            setErrorMsg(`Connection closed unexpectedly (code ${event.code}).`);
          }
        }
      };
    } catch (err) {
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setErrorMsg('Microphone permission denied. Allow mic access and retry.');
      } else {
        setErrorMsg(`Could not open microphone: ${err instanceof Error ? err.message : String(err)}`);
      }
      setStatus('error');
    }
  }, [token, meetingId, setErrorMsg]);

  const finalize = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setErrorMsg('Not connected — cannot finalize.');
      return;
    }
    setStatus('finalizing');
    ws.send(JSON.stringify({ type: 'finalize' }));
  }, [setErrorMsg]);

  const disconnect = useCallback(() => {
    stopCapture();
    // Mark the session as no longer in flight BEFORE closing so the close
    // handler does not surface a spurious "closed unexpectedly" error for a
    // user-initiated disconnect.
    if (statusRef.current !== 'finalized') statusRef.current = 'idle';
    wsRef.current?.close(1000, 'client disconnect');
    wsRef.current = null;
    if (statusRef.current !== 'finalized') setStatus('idle');
  }, []);

  const stopCapture = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // already stopped / invalid state
      }
    }
    mediaRecorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      stopCapture();
      wsRef.current?.close(1000, 'view unmounted');
    };
  }, [stopCapture]);

  return {
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
  };
}
