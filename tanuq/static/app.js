/* Tanuq control-plane SPA (view layer only; UI is never an authority). */
let current = 'dashboard';
const approved = new Set(); // fingerprints approved in this UI session
const $ = s => document.querySelector(s);
function tok(){ return localStorage.getItem('tanuq_token') || ''; }
function saveToken(){ localStorage.setItem('tanuq_token', $('#token').value.trim()); location.reload(); }
async function api(path, opts){
  const r = await fetch(path, Object.assign({headers: {'X-TANUQ-Token': tok(), 'Content-Type':'application/json'}}, opts||{}));
  if (r.status === 403) { localStorage.removeItem('tanuq_token'); location.reload(); throw new Error('forbidden'); }
  return r.json();
}
function esc(s){ return (s??'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function badge(v){
  if (v==='VERIFIED'||v==='ACTIVE'||v===true||v==='VALID') return '<span class="badge ok">'+esc(v)+'</span>';
  if (v==='DENIED'||v==='INVALID'||v==='FAILED'||v==='ROLLBACK_FAILED') return '<span class="badge bad">'+esc(v)+'</span>';
  if (v==='ROLLED_BACK'||v==='APPROVAL_REQUIRED'||v==='MISSING'||v==='UNAVAILABLE') return '<span class="badge warn">'+esc(v)+'</span>';
  return '<span class="badge muted">'+esc(v??'-')+'</span>';
}
function show(t){
  current = t;
  document.querySelectorAll('#tabs button[data-t]').forEach(b=>b.classList.toggle('active', b.dataset.t===t));
  ({dashboard:vDashboard, pending:vPending, activity:vActivity, incidents:vIncidents,    evidence:vEvidence, blocked:vBlocked, status:vStatus})[t]();
}
function showSetup(){
  $('#tokenbox').style.display='none';
  $('#app').style.display='none';
  $('#setup').style.display='block';
}
async function setupGo(){
  const err = $('#setup-error');
  if (!err) return;
  err.textContent = '';
  const ws = $('#setup-ws').value.trim();
  if (!ws){ err.textContent = 'Enter your project folder path.'; return; }
  const scope = document.querySelector('input[name="setup-scope"]:checked').value;
  let allowed = [];
  if (scope === 'custom'){
    allowed = $('#setup-paths').value.split(',').map(s => s.trim()).filter(Boolean);
    if (!allowed.length){ err.textContent = 'List at least one subfolder, or keep "Whole project" selected.'; return; }
  }
  const depth = document.querySelector('input[name="setup-depth"]:checked').value;
  let b;
  try { b = await api('/api/setup', {method:'POST', body: JSON.stringify({workspace: ws, allowed_paths: allowed, verification_depth: depth})}); }
  catch(e){ return; } // 403: token reset + reload already handled by api()
  if (b && b.error){ err.textContent = b.error; return; }
  $('#setup').innerHTML = `<div class="card"><h3>You are protected ✓</h3><div class="kv">
    <div>Project</div><div>${esc(b.workspace)}</div>
    <div>Protected folders</div><div>${esc(b.allowed_paths.join(', '))}</div>
    <div>Verification</div><div>${esc(b.verification_depth)}</div>
    <div>Evidence</div><div>${badge('VALID')} anchored, tamper-evident chain</div>
    <div>Browser access</div><div class="small">unlocked with your device token — stored only in this browser; it is an access key, never a decision</div>
  </div>
  <button class="act primary" data-action="setup-done">Open Tanuq</button></div>`;
  const connectCard = $('#connect-card');
  if (connectCard) connectCard.style.display = 'block';
}
async function connectGo(){
  const err = $('#connect-error');
  if (err) err.textContent = '';
  let b;
  try { b = await api('/api/connect', {method:'POST', body: JSON.stringify({agent: 'claude_code'})}); }
  catch(e){ return; } // 403: token reset + reload already handled by api()
  if (b && b.error){ if (err) err.textContent = b.error; return; }
  const card = $('#connect-card');
  if (card) card.innerHTML = `<h3>Connected ✓</h3><div class="kv">
    <div>Agent</div><div>Claude Code</div>
    <div>Hook installed</div><div><span class="badge ok">Edit + Write governed</span></div>
  </div>
  <p class="small"><b>Next:</b> open Claude Code in this project and make a change. Low-risk edits apply automatically; risky ones wait for your approval here.</p>`;
}
function guard(data){ if(data && data.error){ $('#view').innerHTML = '<div class="card bad">'+esc(data.error)+'</div>'; return true;} return false; }

async function vDashboard(){
  const d = await api('/api/dashboard'); if (guard(d)) return;
  $('#hdrstate').outerHTML = '<span id="hdrstate" class="badge '+(d.anchor==='ACTIVE'?'ok':'bad')+'">Governed: ON · Anchor: '+esc(d.anchor)+'</span>';
  $('#view').innerHTML = `
  ${d.pending_count ? `<div class="card" style="border-color:var(--warn)"><h3>⏳ ${d.pending_count} change(s) awaiting your decision</h3><div class="small">Review them in the Pending Approvals tab.</div></div>` : ''}
  <div class="card"><h3>Workspace</h3><div class="kv">
    <div>Workspace</div><div>${esc(d.workspace)}</div>
    <div>Protected scope</div><div>${esc(d.protected_scope.join(', '))}</div>
    <div>Governed mode</div><div>${badge(true)} deterministic policy · approval for HIGH/CRITICAL · UNKNOWN denied</div>
    <div>Verification depth</div><div>${esc(d.verification_depth)}</div>
    <div>Evidence chain</div><div>${badge(d.chain_valid?'VALID':'INVALID')} (${d.events} events) · Anchor ${badge(d.anchor)}</div>
    <div>Pending approvals</div><div><b>${d.pending_count}</b></div>
    <div>Incidents</div><div>${d.incident_count? '<span class="badge '+(d.critical_incidents?'bad':'warn')+'">'+esc(d.incident_count)+' active ('+esc(d.critical_incidents)+' critical)</span> — see Incidents tab' : badge('NONE')}</div>
  </div></div>
  <div class="card"><h3>Recent verified changes</h3>${d.recent_verified.length? '<table><tr><th>Path</th><th>Risk</th><th>Fingerprint</th><th>Result</th></tr>'+
    d.recent_verified.map(i=>`<tr><td>${esc(i.path)}</td><td>${badge(i.risk||'-')}</td><td class="small">${esc(i.fingerprint.slice(0,12))}</td><td>${badge(i.terminal)}</td></tr>`).join('')+'</table>' : '<div class="empty">None yet.</div>'}</div>
  <div class="card"><h3>Recent blocked / rolled back</h3>${(d.recent_rolled_back.length||d.blocked_count)? '<div class="small">'+d.recent_rolled_back.map(i=>esc(i.path)+' — '+esc(i.terminal)).join('<br>')+'</div>' : '<div class="empty">Nothing blocked or rolled back.</div>'}${d.blocked_count? `<div class="small">${d.blocked_count} blocked action(s) in evidence — see Blocked Actions.</div>`:''}</div>
  <div class="card"><h3>Last operation result</h3><div>${d.last_terminal? badge(d.last_terminal) : '<span class="empty">No operations yet.</span>'}</div></div>`;
}

async function vPending(){
  const d = await api('/api/pending'); if (guard(d)) return;
  if (!d.pending.length){ $('#view').innerHTML = '<div class="card"><div class="empty">No pending approvals. Proposals that require your approval appear here.</div></div>'; return; }
  $('#view').innerHTML = d.pending.map(p=>`
  <div class="card"><h3>${esc(p.path)} ${(p.approval && p.approval.state === 'granted') ? '<span class="badge ok">APPROVED — execute bekleniyor</span>' : ((p.approval && p.approval.state === 'consumed') ? '<span class="badge muted">Onay kullanıldı</span>' : ((p.approval && p.approval.state === 'expired') ? '<span class="badge warn">Onay süresi doldu — yeniden onaylayın</span>' : badge(p.state)))} ${badge(p.risk)}</h3>
    <div class="kv">
      <div>What the AI wants to do</div><div>${esc(p.reason)}</div>
      <div>Action</div><div>${esc(p.action)}</div>
      <div>Risk</div><div>${badge(p.risk)} — this change needs your approval before it can be applied</div>
    </div>
    <details class="small" style="margin-top:8px"><summary>Technical details</summary>
      <div class="kv">
        <div>Fingerprint</div><div class="small">${esc(p.fingerprint)}</div>
        <div>Session</div><div>${esc(p.session||'-')}</div>
        <div>Created</div><div>${esc(p.created_at||'-')}</div>
        <div>Approval validity</div><div>Single-use · expires 3600s after you approve</div>
        <div>Approval state</div><div>${esc((p.approval && p.approval.state) || "none")}</div>
      </div>
    </details>
    </div>
    <p class="small"><b>What does this approval authorize?</b><br>${esc(p.what_this_authorizes)}</p>
    <h3 class="small">DIFF (old → new)</h3>
    <pre class="diff">--- old (len ${p.diff.old_len})\n+++ new (len ${p.diff.new_len})\n\nOLD:\n${esc(p.diff.old_preview)}\n\nNEW:\n${esc(p.diff.new_preview)}</pre>
    <div style="margin-top:8px">
      ${(p.approval && p.approval.state === 'granted') ? '<button class="act primary" disabled>Onaylandı — execute bekleniyor</button>' : '<button class="act primary" data-action="approve" data-fp="${esc(p.fingerprint)}">Approve</button>'}
      <button class="act danger" data-action="reject" data-fp="${esc(p.fingerprint)}">Reject</button>
      ${(p.risk === 'HIGH' || p.risk === 'CRITICAL') && !(p.approval && p.approval.state === 'granted') ? '' : '<button class="act primary" data-action="execute" data-fp="${esc(p.fingerprint)}">Uygula</button>'}
    </div>
  </div>`).join('');
}
async function approve(fp){
  let b;
  try { b = await api('/api/approve', {method:'POST', body: JSON.stringify({fingerprint: fp})}); }
  catch(e){ return; } // 403: token reset + reload already handled by api()
  if (b && b.error){
    $('#view').innerHTML = '<div class="card bad"><h3>Approve failed</h3><div class="small">'+esc(b.error)+'</div><button class="act primary" data-action="refresh">Geri</button></div>';
    return;
  }
  approved.add(fp);
  show('pending');
}
async function reject(fp){ await api('/api/reject', {method:'POST', body: JSON.stringify({fingerprint: fp})}); show('pending'); }
async function execute(fp){
  const b = await api('/api/execute', {method:'POST', body: JSON.stringify({fingerprint: fp})});
  if (b && b.error){ $('#view').innerHTML = '<div class="card bad">'+esc(b.error)+'</div>'; return; }
  const t = b.terminal || '';
  $('#view').innerHTML = '<div class="card"><h3>Execute result '+badge(t)+'</h3><div class="kv">'
    + '<div>Apply success</div><div>'+badge(!!b.apply_success)+'</div>'
    + '<div>Verification</div><div>'+badge(!!b.verification_passed)+'</div>'
    + '<div>Pending proposals now</div><div>'+esc(b.pending_count??'-')+'</div>'
    + (b.in_flight? '<div>Note</div><div class="small">an execution is already in flight (fail-closed 409)</div>':'')
    + '</div>'
    + (b.guidance? '<p class="small">'+esc(b.guidance)+'</p>':'')
    + '<button class="act primary" data-action="refresh">Back to pending</button></div>';
}

async function vActivity(){
  const d = await api('/api/operations'); if (guard(d)) return;
  $('#view').innerHTML = '<div class="card"><h3>Operations (projection over journals/evidence — no content)</h3>' +
   (d.operations.length? '<table><tr><th>Operation</th><th>State</th><th>Path</th><th>Session</th><th>Risk</th><th>Approval</th><th>Incidents</th><th>Evidence</th></tr>' +
    d.operations.map(o=>`<tr><td class="small">${esc(o.operation_id.slice(0,12))}</td><td>${badge(o.state)}</td><td class="small">${esc(o.path)}</td><td class="small">${esc(o.sessions.join(', ')||'-')}</td><td>${o.risk? badge(o.risk.risk):'-'}</td><td class="small">${o.approvals.length? esc(o.approvals.map(a=>(a.approval_id||'').slice(0,8)+'/'+(a.status||'granted')).join(', ')):'-'}</td><td>${o.incidents.length? '<span class="badge bad">'+esc(o.incidents.join(','))+'</span>':'-'}</td><td class="small">${esc(o.evidence_refs.first_seq)}..${esc(o.evidence_refs.last_seq)} (${esc(o.evidence_refs.events)})</td></tr>`).join('')+'</table>'
   : '<div class="empty">No operations recorded yet.</div>') + '</div>';
}

async function vIncidents(){
  const d = await api('/api/incidents'); if (guard(d)) return;
  const head = `<div class="card"><h3>Incidents — ${d.total} active (${d.critical} critical)</h3>
    <div class="small">Detect-only projection over the journals and anchor. Tanuq never auto-repairs:
    repair is an explicit, separately-authorized operator decision (fail-closed). Detected ${esc(d.detected_at)}.</div></div>`;
  if (!d.incidents.length){
    $('#view').innerHTML = head + '<div class="card"><div class="empty">No incidents. Workspace state is clean.</div></div>';
    return;
  }
  $('#view').innerHTML = head + d.incidents.map(i=>`
  <div class="card ${i.severity==='critical'?'critical':''}"><h3>${badge(i.severity.toUpperCase())} ${esc(i.type)}</h3>
    <div class="kv">
      <div>Detected</div><div>${esc(i.detected)}</div>
      <div>Related operation</div><div class="small">${esc(i.operation||'-')}</div>
      <div>Path</div><div class="small">${esc(i.path||'-')}</div>
      <div>Current state</div><div>${esc(i.current_state)}</div>
      <div>Recovery status</div><div>${esc(i.recovery_status)}</div>
      <div>Recommended action</div><div>${esc(i.recommended_action)}</div>
      ${i.detail? `<div>Detail</div><div class="small">${esc(i.detail)}</div>` : ''}
    </div></div>`).join('');
}

async function vEvidence(){
  const d = await api('/api/evidence'); if (guard(d)) return;
  const l = await api('/api/lineage?limit=10'); if (guard(l)) return;
  $('#view').innerHTML = `
  <div class="card"><h3>Chain status</h3><div class="kv">
    <div>Evidence chain</div><div>${badge(d.chain_valid?'VALID':'INVALID')}</div>
    <div>Anchor</div><div>${badge(d.anchor)}</div>
    <div>Events</div><div>${d.events}</div>
  </div><p class="small">${esc(d.note)} If you lose the anchor key (~/.tanuq/keys), anchored evidence can no longer be verified (fail-closed).</p>
  <button class="act primary" data-action="verify">Verify now</button></div>
  <div class="card"><h3>Operation lineage (proposal → risk → approval → execution → outcome)</h3>
  ${l.chains.length? l.chains.map(c=>`
    <div class="card" style="margin-bottom:8px">
      <div class="small"><b>${esc(c.fingerprint_short)}</b> · ${esc(c.path)} ${badge(c.outcome||'PENDING')}${c.sessions.length? ' · session: '+esc(c.sessions.join(', ')):''}</div>
      ${c.proposal? `<div class="small">proposal: ${esc(c.proposal.action)} — ${esc(c.proposal.reason)} (seq ${esc(c.proposal.seq)})</div>`:''}
      ${c.risk? `<div class="small">risk: ${badge(c.risk.risk)} allowed=${esc(c.risk.allowed)} approval_required=${esc(c.risk.approval_required)} · ${esc(c.risk.reason)}${c.risk.signals.length? ' · signals: '+esc(c.risk.signals.map(s=>s.join('=')).join(', ')):''}</div>`:''}
      ${c.approvals.length? c.approvals.map(a=>`<div class="small">approval: ${esc((a.approval_id||'').slice(0,8))} status=${badge((a.status||'granted').toUpperCase())} authorizer=${esc(a.authorizer||'-')}</div>`).join(''):''}
      ${c.execution? `<div class="small">execution: ${esc(c.execution.intent_id.slice(0,8))} ${esc(c.execution.lifecycle.join(' → '))}</div>`:''}
      ${c.denied_reason? `<div class="small">denial: ${esc(c.denied_reason)}</div>`:''}
      ${c.refs.length? `<div class="small">evidence seq ${esc(Math.min(...c.refs))}..${esc(Math.max(...c.refs))} (${esc(c.refs.length)} events)</div>`:''}
    </div>`).join('') : '<div class="empty">No operations recorded yet.</div>'}</div>
  <div class="card"><h3>Event chain (latest ${d.rows.length})</h3>
  <table><tr><th>Seq</th><th>Type</th><th>Path</th><th>Fingerprint</th><th>Result</th><th>Time</th><th>Hash</th></tr>
  ${d.rows.slice().reverse().map(e=>`<tr><td>${esc(e.sequence)}</td><td class="small">${esc(e.event_type)}</td><td class="small">${esc(e.path)}</td><td class="small">${esc((e.fingerprint||'').slice(0,12))}</td><td>${badge(e.result??'-')}</td><td class="small">${esc(e.timestamp||'-')}</td><td class="small">${esc((e.current_hash||'').slice(0,10))}…</td></tr>`).join('')}
  </table></div>`;
}

async function vBlocked(){
  const d = await api('/api/blocked'); if (guard(d)) return;
  $('#view').innerHTML = '<div class="card"><h3>Blocked actions (source: EventStore evidence)</h3>' +
   (d.blocked.length? '<table><tr><th>Target</th><th>Risk</th><th>Reason</th><th>Fingerprint</th></tr>' +
    d.blocked.map(b=>`<tr><td>${esc(b.path)}</td><td>${badge(b.risk||'-')}</td><td class="small">${esc(b.reason)}</td><td class="small">${esc(b.fingerprint.slice(0,12))}</td></tr>`).join('')+'</table>'
   : '<div class="empty">Nothing has been blocked.</div>') + '</div>';
}

async function vStatus(){
  const d = await api('/api/status'); if (guard(d)) return;
  $('#view').innerHTML = `<div class="card"><h3>Status</h3><div class="kv">
    <div>Workspace</div><div>${esc(d.workspace)}</div>
    <div>Protected scope</div><div>${esc(d.protected_scope.join(', '))}</div>
    <div>Governed mode</div><div>${badge(true)}</div>
    <div>Verification depth</div><div>${esc(d.verification_depth)}</div>
    <div>Evidence chain</div><div>${badge(d.chain_valid?'VALID':'INVALID')} · Anchor ${badge(d.anchor)} · ${d.events} events</div>
    <div>Pending approvals</div><div>${d.pending}</div>
    <div>OS sandbox</div><div>${badge('NOT INCLUDED')}</div>
    <div>Network enforcement</div><div>${badge('NOT INCLUDED')}</div>
    <div>Governed channel only</div><div class="small">${esc(d.limits.governed_channel_only)}</div>
  </div></div>`;
}

document.addEventListener('click', e => {
  const nav = e.target.closest('#tabs button[data-t]');
  if (nav) { show(nav.dataset.t); return; }
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;
  if (action === 'approve') approve(el.dataset.fp);
  else if (action === 'reject') reject(el.dataset.fp);
  else if (action === 'execute') execute(el.dataset.fp);
  else if (action === 'verify') show('evidence');
  else if (action === 'refresh') show(current);
  else if (action === 'setup-go') setupGo();
  else if (action === 'setup-done') location.reload();
  else if (action === 'connect-go') connectGo();
});
document.addEventListener('change', e => {
  if (e.target && e.target.name === 'setup-scope'){
    const inp = $('#setup-paths');
    if (inp) inp.disabled = e.target.value !== 'custom';
  }
});
document.getElementById('unlock').addEventListener('click', saveToken);

(async function init(){
  if (!tok()) return;
  try {
    const h = await api('/api/health');
    if (h.ok){
      if (h.initialized === false){ showSetup(); return; }
      $('#tokenbox').style.display='none'; $('#app').style.display='block'; show('dashboard'); return;
    }
  } catch(e){}
  localStorage.removeItem('tanuq_token');
})();
