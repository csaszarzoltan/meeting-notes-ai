const API='/api/v1/governance';
function token(){return localStorage.getItem('meetingnotes_token')??localStorage.getItem('token')??''}
export async function governanceRequest<T>(path:string,init:RequestInit={}):Promise<T>{const response=await fetch(`${API}${path}`,{...init,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token()}`,...init.headers}});if(!response.ok){const body=await response.json().catch(()=>({detail:'Request failed'}));throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))}return response.json() as Promise<T>}
export const getLineage=(meetingId:string)=>governanceRequest(`/meetings/${meetingId}/lineage`);
export const getPolicy=(teamId:string)=>governanceRequest(`/policies/current?team_id=${encodeURIComponent(teamId)}`);
