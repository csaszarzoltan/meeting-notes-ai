import { useEffect, useMemo, useRef, useState } from 'react';
import { workspaceRequest } from '../api/workspace';
import type { MeetingCard, WorkspaceView } from './types';

interface Props { open:boolean; onClose:()=>void; onNavigate:(view:WorkspaceView)=>void; onOpenMeeting?:(meeting:MeetingCard)=>void }
const COMMANDS=[
  {label:'Start recording',hint:'Open secure live capture',view:'record' as WorkspaceView,icon:'●'},
  {label:'Upload recording',hint:'Create notes from audio or video',view:'record' as WorkspaceView,icon:'↑'},
  {label:'Open review queue',hint:'Continue meetings that need verification',view:'meetings' as WorkspaceView,icon:'✓'},
  {label:'Overdue actions',hint:'Resolve commitments that need attention',view:'actions' as WorkspaceView,icon:'!'},
  {label:'Open privacy settings',hint:'Retention, approval, and processing region',view:'settings' as WorkspaceView,icon:'◈'},
];
/** Keyboard-first global meeting search and command surface. */
export function CommandPalette({open,onClose,onNavigate,onOpenMeeting}:Props){
  const[query,setQuery]=useState(''); const[meetings,setMeetings]=useState<MeetingCard[]>([]); const[selected,setSelected]=useState(0); const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{if(!open)return;setQuery('');setMeetings([]);setSelected(0);setTimeout(()=>input.current?.focus(),0)},[open]);
  useEffect(()=>{if(!open||query.trim().length<2){setMeetings([]);return}const timer=window.setTimeout(()=>{void workspaceRequest<{items:MeetingCard[]}>(`/meetings?q=${encodeURIComponent(query)}`).then(body=>setMeetings(body.items)).catch(()=>setMeetings([]))},180);return()=>window.clearTimeout(timer)},[open,query]);
  const commands=useMemo(()=>COMMANDS.filter(item=>`${item.label} ${item.hint}`.toLowerCase().includes(query.toLowerCase())),[query]);
  const rows=[...meetings.map(meeting=>({kind:'meeting' as const,meeting,label:meeting.title,hint:meeting.summary,icon:'◫'})),...commands.map(command=>({kind:'command' as const,...command}))];
  const activate=(index:number)=>{const row=rows[index];if(!row)return;if(row.kind==='meeting'){onOpenMeeting?.(row.meeting);onNavigate('meetings')}else onNavigate(row.view);onClose()};
  const onKeyDown=(event:React.KeyboardEvent)=>{if(event.key==='ArrowDown'){event.preventDefault();setSelected(value=>Math.min(rows.length-1,value+1))}else if(event.key==='ArrowUp'){event.preventDefault();setSelected(value=>Math.max(0,value-1))}else if(event.key==='Enter'){event.preventDefault();activate(selected)}else if(event.key==='Escape')onClose()};
  if(!open)return null;
  return <div className="command-backdrop" role="presentation" onMouseDown={onClose}><section className="command-palette" role="dialog" aria-modal="true" aria-label="Search and commands" onMouseDown={event=>event.stopPropagation()} onKeyDown={onKeyDown}><header><span>⌕</span><input ref={input} value={query} onChange={event=>{setQuery(event.target.value);setSelected(0)}} placeholder="Search meetings, transcripts, decisions, or actions…" aria-label="Search meetings and commands"/><kbd>Esc</kbd></header><div className="command-results">{rows.length?rows.map((row,index)=><button className={index===selected?'selected':''} key={`${row.kind}-${row.label}`} onMouseEnter={()=>setSelected(index)} onClick={()=>activate(index)}><span className="command-icon">{row.icon}</span><span><strong>{row.label}</strong><small>{row.hint}</small></span><em>{row.kind==='meeting'?'Meeting':'Command'}</em></button>):<div className="command-empty"><strong>{query.length<2?'Search meetings':'No matching result'}</strong><small>Type at least two characters to search private workspace content.</small></div>}</div><footer><span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>↵</kbd> Open</span><span><kbd>Esc</kbd> Close</span></footer></section></div>;
}
