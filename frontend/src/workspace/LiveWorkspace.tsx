import { LiveTranscriptionView } from '../live/LiveTranscriptionView';
/** Real microphone and WebSocket live-transcription workspace. */
export function LiveWorkspace(){return <section className="live-workspace"><div className="live-command"><div><span className="recording-dot"></span><strong>Secure live transcription</strong><small>Live draft. Speaker labels and wording may change after final processing.</small></div></div><LiveTranscriptionView /></section>}
