import { useEffect,useState } from 'react';
import { workspaceRequest } from '../api/workspace';
import { getCalendarStatus, disconnectCalendar, getAuthUrl } from '../api/googleCalendar';
/** Persisted connector configuration catalog. */
export function IntegrationsCenter(){const[items,setItems]=useState<Record<string,{connected:boolean}>>({});const[calendarConnected,setCalendarConnected]=useState(false);const load=()=>workspaceRequest<{items:Record<string,{connected:boolean}>}>('/integrations').then(b=>setItems(b.items));useEffect(()=>{void load(); void getCalendarStatus().then(b=>setCalendarConnected(b.connected)).catch(()=>setCalendarConnected(false));},[]);const toggle=async(name:string,enabled:boolean)=>{await workspaceRequest(`/integrations/${encodeURIComponent(name)}/connect`,{method:'POST',body:JSON.stringify({enabled})});await load()};return <section><div className="page-heading"><div><span className="eyebrow">Execution connections</span><h2>Integrations</h2></div></div><div className="integration-grid">
    <article className="integration-card featured" style={{borderColor:'var(--accent)'}}>
      <span className="integration-logo">G</span>
      <div><h3>Google Calendar</h3><p>{calendarConnected ? 'Connected · Syncing events' : 'Browse and import meetings'}</p></div>
      <button className={calendarConnected ? 'secondary' : 'primary'} onClick={calendarConnected ? () => { void disconnectCalendar().then(() => setCalendarConnected(false)); } : async () => { const { authorization_url } = await getAuthUrl(); window.location.href = authorization_url; }}>
        {calendarConnected ? 'Disconnect' : 'Connect'}
      </button>
    </article>
    {Object.entries(items).map(([name,state])=><article className="integration-card" key={name}><span className="integration-logo">{name[0]}</span><div><h3>{name}</h3><p>Persistent connector configuration</p></div><button className={state.connected?'secondary':'primary'} onClick={()=>void toggle(name,!state.connected)}>{state.connected?'Disconnect':'Connect'}</button></article>)}
</div></section>}
