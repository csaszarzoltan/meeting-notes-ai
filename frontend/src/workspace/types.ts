/** Shared product-workspace models. */
export type WorkspaceView = 'home' | 'meetings' | 'record' | 'batches' | 'actions' | 'team' | 'sharing' | 'compliance' | 'integrations' | 'settings';
export type ReviewStatus = 'needs_review' | 'approved' | 'ready';
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
  id: string; title: string; date: string; duration: string; mode: string; status: ReviewStatus; participants: number; summary: string;
}
