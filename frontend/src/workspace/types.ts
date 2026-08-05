/** Shared product-workspace models. */
export type WorkspaceView = 'home' | 'meetings' | 'record' | 'batches' | 'actions' | 'team' | 'sharing' | 'insights' | 'compliance' | 'integrations' | 'settings';
export type ReviewStatus = 'needs_review' | 'in_review' | 'approved' | 'rejected' | 'ready';
export interface MeetingResult {
  id: string;
  transcript: string;
  summary: string;
  action_items: Array<{ assignee?: string | null; description: string; deadline?: string | null }>;
  decisions: string[];
  key_points: string[];
  mode: 'general' | 'healthcare' | 'legal';
  review_status: ReviewStatus;
  phi_redacted: boolean;
  redaction_matches: number;
  warnings: string[];
}
export interface MeetingCard {
  id: string; title: string; date: string; duration: string; mode: string; status?: ReviewStatus; review_status?: ReviewStatus; participants: number; summary: string; owner?: string; sensitivity?: string;
}
export interface Evidence { timestamp: string; speaker: string; text: string; confidence: number; }
export interface MeetingDetail extends MeetingCard { action_items?: Array<{assignee?: string | null; description: string; deadline?: string | null}>; transcript: string; decisions: Array<string | {text: string; timestamp: string; confidence: number}>; key_points: string[]; evidence: Evidence[]; versions: Array<{number:number; reviewer:string; at:string; status:string}>; audio_url?: string; }

