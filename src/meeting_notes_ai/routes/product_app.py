# ruff: noqa: E501
"""Accessible, dependency-free product shell for the core upload and review journey."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["product-ui"])

_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MeetingNotesAI workspace</title>
<style>
:root{color-scheme:light dark;--bg:#f5f7fb;--card:#fff;--ink:#172033;--muted:#536079;--brand:#3157d5;--danger:#b42318;--ok:#067647;--border:#c9d2e3}
@media(prefers-color-scheme:dark){:root{--bg:#111827;--card:#1f2937;--ink:#f9fafb;--muted:#cbd5e1;--brand:#8da2fb;--border:#475569}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}.skip{position:absolute;left:-9999px}.skip:focus{left:1rem;top:1rem;background:var(--card);padding:.75rem;z-index:2}.wrap{max-width:960px;margin:auto;padding:1rem}header{padding:1rem 0}.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:1.25rem;margin-bottom:1rem;box-shadow:0 3px 12px #0001}.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}label{display:block;font-weight:650;margin-bottom:.35rem}input,select,button,textarea{font:inherit}input[type=file],select{width:100%;padding:.7rem;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--ink)}button{border:0;border-radius:8px;padding:.75rem 1rem;background:var(--brand);color:white;font-weight:700;cursor:pointer}button[disabled]{opacity:.55;cursor:wait}.hint,.muted{color:var(--muted);font-size:.92rem}.check{display:flex;gap:.6rem;align-items:flex-start}.check label{font-weight:500}.status{border-left:5px solid var(--brand)}.error{border-color:var(--danger);color:var(--danger)}.success{border-color:var(--ok)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg);padding:1rem;border-radius:8px}progress{width:100%;height:1rem}.badge{display:inline-block;padding:.2rem .55rem;border-radius:999px;background:var(--bg);font-size:.85rem}
</style>
</head>
<body><a class="skip" href="#main-content">Skip to main content</a>
<div class="wrap"><header><h1>MeetingNotesAI</h1><p class="muted">Upload once, review clearly, and share only when ready.</p></header>
<main id="main-content" tabindex="-1">
<section class="card" aria-labelledby="new-title"><h2 id="new-title">New meeting</h2>
<form id="meeting-form" novalidate>
<div class="grid"><div><label for="meeting-file">Audio file</label><input id="meeting-file" name="file" type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/webm" required><p class="hint">WAV, MP3, MP4 or WebM, up to 25 MB.</p></div>
<div><label for="mode">Meeting type</label><select id="mode" name="mode"><option value="general">General meeting</option><option value="healthcare">Healthcare consultation</option><option value="legal">Legal or deposition</option></select></div>
<div><label for="language">Language code <span class="muted">(optional)</span></label><input id="language" name="language" inputmode="text" maxlength="12" placeholder="e.g. en"></div></div>
<div class="check"><input id="phi-redaction" name="phi_redaction" type="checkbox"><label for="phi-redaction">Mask detected personal health information before returning the transcript. This is enabled automatically for healthcare meetings.</label></div>
<div id="health-options" hidden><div class="check"><input id="consent" name="consent_confirmed" type="checkbox"><label for="consent">Consent has been confirmed for this recording.</label></div></div>
<p id="form-error" class="error" role="alert"></p><button id="submit" type="submit">Process meeting</button></form></section>
<section id="processing" class="card status" hidden aria-labelledby="status-title"><h2 id="status-title">Processing status</h2><p id="status" aria-live="polite">Waiting</p><progress id="progress" max="4" value="0">0 of 4</progress></section>
<section id="review" class="card" hidden aria-labelledby="review-title"><h2 id="review-title">Review before sharing</h2><p><span id="review-badge" class="badge"></span> AI-generated notes can be inaccurate. Check the transcript and sensitive information before sharing.</p><div id="summary"></div><h3>Transcript</h3><pre id="transcript"></pre><h3>Action items</h3><ul id="actions"></ul></section>
</main></div>
<script>
const form=document.querySelector('#meeting-form'),mode=document.querySelector('#mode'),phi=document.querySelector('#phi-redaction'),health=document.querySelector('#health-options');
function applyMode(){const isHealth=mode.value==='healthcare';health.hidden=!isHealth;if(isHealth)phi.checked=true;phi.disabled=isHealth;}
mode.addEventListener('change',applyMode);applyMode();
form.addEventListener('submit',async e=>{e.preventDefault();const file=document.querySelector('#meeting-file').files[0],err=document.querySelector('#form-error'),status=document.querySelector('#status'),progress=document.querySelector('#progress'),submit=document.querySelector('#submit');err.textContent='';if(!file){err.textContent='Choose an audio file to continue.';return}if(file.size===0){err.textContent='The selected file is empty. Choose another recording.';return}if(file.size>25*1024*1024){err.textContent='The file is larger than 25 MB.';return}const data=new FormData(form);data.set('phi_redaction',String(phi.checked));document.querySelector('#processing').hidden=false;document.querySelector('#review').hidden=true;submit.disabled=true;status.textContent='Uploading recording…';progress.value=1;try{status.textContent='Transcribing and creating notes…';progress.value=2;const res=await fetch('/api/v1/meetings',{method:'POST',body:data});const body=await res.json();if(!res.ok)throw new Error(typeof body.detail==='string'?body.detail:(body.detail?.message||'Processing could not be completed.'));status.textContent='Ready for review';progress.value=4;document.querySelector('#review').hidden=false;document.querySelector('#review-badge').textContent=body.review_status==='needs_review'?'Needs review':'Ready';document.querySelector('#transcript').textContent=body.transcript||'No transcript returned.';const actions=document.querySelector('#actions');actions.replaceChildren(...(body.action_items||[]).map(a=>{const li=document.createElement('li');li.textContent=(a.assignee?`${a.assignee}: `:'')+a.description;return li}));document.querySelector('#review').scrollIntoView({behavior:'smooth'});}catch(ex){status.textContent='Processing failed';progress.value=0;err.textContent=ex.message;}finally{submit.disabled=false}});
</script></body></html>'''

@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def product_app() -> HTMLResponse:
    return HTMLResponse(_HTML, headers={"Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; object-src 'none'; base-uri 'none'"})
