"use strict";
const STARTS=[7,9,11,13,15,17,19], EVE=new Set([17,19]);
let DAYS=["Mon","Tue","Wed","Thu","Fri","Sat"], PERIODS=STARTS.map(t=>pad(t)+":00-"+pad(t+2)+":00");
let SEM="II", D=null, CUR="overview";
function pad(n){return('0'+n).slice(-2);}
function timeOf(t){return pad(t)+":00-"+pad(t+2)+":00";}
const esc=s=>(''+(s==null?'':s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const $=id=>document.getElementById(id);
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200);}

async function api(path,opts){const r=await fetch('/api'+path,opts);if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
async function loadData(){
  try{D=await api('/'+SEM+'/data');$('status').textContent='● connected';$('status').style.color='#8fe0a5';}
  catch(e){$('status').textContent='● offline';$('status').style.color='#f5b7b1';throw e;}
  if(D.meta&&D.meta.days){DAYS=D.meta.days;}
}
function S(){return D.sessions;}
function VENS(){return D.venues;}
function venMap(){const m={};VENS().forEach(v=>m[v.venue]=v);return m;}
function der(){return D.derived;}

async function setSem(sem){SEM=sem;$('semI').className=sem==='I'?'on':'';$('semII').className=sem==='II'?'on':'';await loadData();renderNav();R[CUR]();}
function renderNav(){const m=der().metrics;
  const items=[['overview','Overview'],['timetable','Timetable'],['sessions','Sessions'],['instr','Instructor TT'],
   ['progtt','Programme TT'],
   ['venue','Venue Dashboard'],['workload','Workload'],['capacity','Venue Capacity'],['catalogue','Catalogue'],
   ['streams','Streams'],['flags','Red-flags'],['reports','Reports'],['rules','Rules'],['data','Data']];
  $('nav').innerHTML=items.map(it=>`<button class="${it[0]===CUR?'active':''}" onclick="go('${it[0]}')">${it[1]}${it[0]==='flags'&&m.hard?`<span class="badge">${m.hard}</span>`:''}</button>`).join('');
}
function go(k){CUR=k;document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));$('t-'+k).classList.add('active');renderNav();R[k]();}

const R={};
R.overview=function(){const m=der().metrics;const est=m.estimated?' <span class="tag">occupancy estimated</span>':'';
  const cards=[['Class sessions',m.sessions,''],['Venues',m.venues,''],['Seat capacity / period',m.seatcap.toLocaleString(),''],
   ['Overall utilisation',m.util+'%',''],['Peak-period utilisation',m.peak+'%',''],['Instructors',m.instructors,''],
   ['Modules',m.modules,''],['Vacant venue-periods',m.vacant,''],['Hard rule-breaks',m.hard,m.hard?'warn':'ok'],
   ['Items to review',m.review,''],['Instructors over a cap',m.overloads,m.overloads?'warn':'ok'],['At/over soft limit',m.softs,'']];
  const busy=[...der().vutil].sort((a,b)=>b.periods_used-a.periods_used).slice(0,10);
  const loads=der().workload.slice(0,10);
  let h=`<h2>Overview — Semester ${SEM}${est}</h2><div class="cards">`;
  cards.forEach(c=>h+=`<div class="card ${c[2]}"><div class="n">${c[1]}</div><div class="l">${c[0]}</div></div>`);
  h+='</div><div class="note">'+esc(D.model_note||'')+'</div>';
  h+='<div class="two"><div><h3>Busiest venues</h3><div class="wrap"><table><tr><th>Venue [cap]</th><th>Used</th><th>Util</th></tr>';
  busy.forEach(b=>h+=`<tr><td>${esc(b.venue)} [${b.capacity}]</td><td>${b.periods_used}</td><td>${b.utilisation}%</td></tr>`);
  h+='</table></div></div><div><h3>Highest instructor loads</h3><div class="wrap"><table><tr><th>Instructor</th><th>Mods</th><th>Total h</th><th>Flag</th></tr>';
  loads.forEach(w=>h+=`<tr><td>${esc(w.instructor)}</td><td>${w.modules}</td><td>${w.total_h}</td><td>${w.flags.length?'<span class="pill amber">'+esc(w.flags.join(', '))+'</span>':''}</td></tr>`);
  h+='</table></div></div></div>';$('t-overview').innerHTML=h;
};
R.timetable=function(){
  let h=`<h2>Timetable — Semester ${SEM}</h2><div class="controls">Day: <select id="daysel">`+DAYS.map(d=>`<option>${d}</option>`).join('')+
   `</select><select id="premsel"><option value="">All premises</option><option>Main</option><option>Saba</option></select>`+
   `<span class="small">green = session · shaded = vacant · grey = no session (Saba ends 17:00)</span></div><div id="dg" class="wrap"></div>`;
  $('t-timetable').innerHTML=h;
  const draw=()=>$('dg').innerHTML=dayGrid($('daysel').value,$('premsel').value);
  $('daysel').onchange=draw;$('premsel').onchange=draw;draw();
};
function dayGrid(day,prem){const all=S();let vs=[...VENS()].sort((a,b)=>(a.premises==='Main'?0:1)-(b.premises==='Main'?0:1)||b.capacity-a.capacity);
  if(prem)vs=vs.filter(v=>v.premises===prem);
  let h='<table class="grid"><tr><th>VENUE [cap]</th>'+PERIODS.map(p=>`<th>${p}</th>`).join('')+'</tr>';
  vs.forEach(v=>{h+=`<tr><td style="text-align:left"><b>${esc(v.venue)}</b> [${v.capacity}] <span class="small">${v.premises}${v.is_lab?' · lab':''}</span></td>`;
    STARTS.forEach(t=>{const allowed=v.premises==='Main'||!EVE.has(t);
      if(!allowed){h+='<td class="na">—</td>';return;}
      const s=all.find(x=>x.day===day&&x.venue===v.venue&&x.t===t);
      h+= s?`<td class="occ">${esc(s.prog)}\n${esc(s.mod)}\n${esc(s.instr)} (${s.occ})</td>`:'<td class="vac"></td>';});
    h+='</tr>';});
  const inP=s=>!prem||venMap()[s.venue].premises===prem;
  h+='<tr class="foot"><td>VENUES USED</td>'+STARTS.map(t=>`<td>${all.filter(s=>s.day===day&&s.t===t&&inP(s)).length}</td>`).join('')+'</tr>';
  h+='<tr class="foot"><td>SEATS FILLED</td>'+STARTS.map(t=>`<td>${all.filter(s=>s.day===day&&s.t===t&&inP(s)).reduce((a,s)=>a+s.occ,0)}</td>`).join('')+'</tr>';
  return h+'</table>';
}
R.sessions=function(){
  let h=`<h2>Sessions — Semester ${SEM}</h2>`;
  h+=`<div class="note warn">Full editing (add / edit / delete) writes to the shared database — everyone sees the change. Edits are checked against the rules and you'll be warned before saving anything that breaks one; you may override.</div>`;
  h+=`<div class="controls"><input type="text" id="ssearch" placeholder="Search cohort, module, instructor, venue…" style="min-width:240px">`+
   `<button class="btn" onclick="openEdit(null)">+ Add session</button>`+
   `<a class="btn sec" href="/api/${SEM}/export.xlsx">Export Excel</a><a class="btn sec" href="/api/${SEM}/export.csv">Export CSV</a>`+
   `<button class="btn danger" onclick="resetSem()">Reset to published</button><span class="small" id="scount"></span></div><div id="stable" class="wrap"></div>`;
  $('t-sessions').innerHTML=h;$('ssearch').oninput=drawSessions;drawSessions();
};
function drawSessions(){const q=($('ssearch').value||'').toLowerCase();const V=venMap();
  const rows=S().filter(s=>!q||[s.prog,s.mod,s.instr,s.venue,s.day,s.nta].join(' ').toLowerCase().includes(q));
  let h='<table><tr><th>Day</th><th>Period</th><th>Venue</th><th>Cohort</th><th>NTA</th><th>Str</th><th>Module</th><th>Instructor</th><th>Occ</th><th></th></tr>';
  rows.slice(0,600).forEach(s=>{const v=V[s.venue];const over=v&&s.occ>v.capacity+10;
    h+=`<tr><td>${s.day}</td><td>${timeOf(s.t)}</td><td>${esc(s.venue)} <span class="small">[${v?v.capacity:'?'}]</span></td>`+
    `<td>${esc(s.prog)}</td><td>${esc(s.nta)}</td><td>${esc(s.stream)}</td><td>${esc(s.mod)}</td><td>${esc(s.instr)}</td>`+
    `<td class="${over?'flag-red':''}">${s.occ}</td><td style="white-space:nowrap"><button class="btn small" onclick="openEdit(${s.id})">Edit</button> <button class="btn small danger" onclick="delSession(${s.id})">✕</button></td></tr>`;});
  h+='</table>';$('stable').innerHTML=h;
  $('scount').textContent=rows.length+' of '+S().length+(rows.length>600?' (showing 600)':'');
}
async function delSession(id){if(!confirm('Delete this session?'))return;await api(`/${SEM}/session/${id}`,{method:'DELETE'});await loadData();drawSessions();renderNav();toast('Session deleted');}

let CONFIRMED=false;
function openEdit(id){CONFIRMED=false;const s=id==null?{day:'Mon',t:7,venue:VENS()[0].venue,prog:'',nta:'',stream:'A',mod:'',code:'',instr:'',occ:0,est:0}:JSON.parse(JSON.stringify(S().find(x=>x.id===id)));
  const names=Object.keys(D.instructors).sort();
  const vopts=VENS().map(v=>`<option ${v.venue===s.venue?'selected':''}>${esc(v.venue)}</option>`).join('');
  $('modal').innerHTML=`<h3>${id==null?'Add session':'Edit session'}</h3>
   <div class="frow"><label>Day<select id="e_day">${DAYS.map(d=>`<option ${d===s.day?'selected':''}>${d}</option>`).join('')}</select></label>
    <label>Period<select id="e_t">${STARTS.map(t=>`<option value="${t}" ${t===s.t?'selected':''}>${timeOf(t)}</option>`).join('')}</select></label>
    <label>Venue<select id="e_venue">${vopts}</select></label></div>
   <div class="frow"><label>Cohort / programme<input type="text" id="e_prog" value="${esc(s.prog)}"></label>
    <label>NTA<input type="text" id="e_nta" value="${esc(s.nta)}"></label>
    <label>Stream<input type="text" id="e_stream" value="${esc(s.stream)}"></label></div>
   <div class="frow"><label>Module<input type="text" id="e_mod" value="${esc(s.mod)}"></label>
    <label>Code<input type="text" id="e_code" value="${esc(s.code)}"></label></div>
   <div class="frow"><label>Instructor<input type="text" id="e_instr" list="instlist" value="${esc(s.instr)}"><datalist id="instlist">${names.map(n=>`<option>${esc(n)}</option>`).join('')}</datalist></label>
    <label>Occupancy<input type="number" id="e_occ" value="${s.occ}"></label></div>
   <div id="e_viol"><div class="small">Checking…</div></div>
   <div id="e_sugg"></div>
   <div style="text-align:right;margin-top:10px"><button class="btn sec" onclick="closeModal()">Cancel</button> <button class="btn" id="e_save">Save</button></div>`;
  $('overlay').classList.add('show');
  const gather=()=>{const t=+$('e_t').value;return{id:(id==null?undefined:id),day:$('e_day').value,t,venue:$('e_venue').value,
    prog:$('e_prog').value,nta:$('e_nta').value,stream:$('e_stream').value,mod:$('e_mod').value,code:$('e_code').value,
    instr:$('e_instr').value,occ:+$('e_occ').value||0,est:s.est};};
  let timer=null, SUGG=[];
  const applyPatch=(p)=>{const set=(id,v)=>{const el=$(id);if(el)el.value=v;};
    if('day' in p)set('e_day',p.day); if('t' in p)set('e_t',p.t); if('venue' in p)set('e_venue',p.venue);
    if('instr' in p)set('e_instr',p.instr); if('occ' in p)set('e_occ',p.occ); if('stream' in p)set('e_stream',p.stream);
    if('prog' in p)set('e_prog',p.prog); if('nta' in p)set('e_nta',p.nta); if('mod' in p)set('e_mod',p.mod); if('code' in p)set('e_code',p.code);
    CONFIRMED=false; check();};
  const applySplit=async(s)=>{
    if(id==null){alert('Please save this session first, then split it.');return;}
    if(!confirm('Split this class into parallel streams? It will resize this session and create the extra stream sessions in free rooms.'))return;
    await api(`/${SEM}/apply_fix`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,base:gather(),update:s.update,create:s.create})});
    closeModal();await loadData();drawSessions();renderNav();if(CUR!=='sessions')R[CUR]();toast('Class split into '+(s.create.length+1)+' streams');};
  const renderSuggestions=async(cand)=>{let r={};try{r=await api(`/${SEM}/suggest`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cand)});}catch(e){}
    SUGG=r.suggestions||[]; const box=$('e_sugg');
    if(!SUGG.length){box.innerHTML='';return;}
    box.innerHTML='<div style="margin:8px 0 2px"><b class="small">✨ Suggested fixes — click one to apply:</b></div>'+
      SUGG.map((s,i)=>`<button class="btn sec small" style="margin:0 5px 5px 0;white-space:normal;text-align:left" data-i="${i}">${esc(s.label)}</button>`).join('');
    box.querySelectorAll('button[data-i]').forEach(b=>{b.onclick=()=>{const s=SUGG[+b.dataset.i]; if(s.type==='patch')applyPatch(s.patch); else applySplit(s);};});};
  const check=async()=>{const cand=gather();let vio=[];try{vio=(await api(`/${SEM}/validate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cand)})).violations;}catch(e){}
    const box=$('e_viol');
    if(vio.length){box.innerHTML=`<div class="viol"><b>${vio.length} rule warning(s):</b><ul>`+vio.map(x=>`<li class="${x.hard?'hard':''}">[${x.rule}] ${esc(x.msg)}</li>`).join('')+`</ul></div>`;
      $('e_save').textContent=CONFIRMED?'Save anyway':'Save anyway ⚠'; renderSuggestions(cand);}
    else{box.innerHTML='<div class="viol" style="background:var(--greenbg);border-color:#8fce9f"><b>No rule conflicts.</b></div>';$('e_save').textContent='Save';CONFIRMED=true;$('e_sugg').innerHTML='';}
    return vio;};
  ['e_day','e_t','e_venue','e_prog','e_nta','e_stream','e_mod','e_code','e_instr','e_occ'].forEach(f=>{const el=$(f);
    el.oninput=()=>{CONFIRMED=false;clearTimeout(timer);timer=setTimeout(check,300);};el.onchange=el.oninput;});
  check();
  $('e_save').onclick=async()=>{const vio=await check();
    if(vio.length&&!CONFIRMED){CONFIRMED=true;$('e_save').textContent='Save anyway';return;}
    const cand=gather();
    if(id==null)await api(`/${SEM}/session`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cand)});
    else await api(`/${SEM}/session/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(cand)});
    closeModal();await loadData();drawSessions();renderNav();if(CUR!=='sessions')R[CUR]();
    toast(vio.length?'Saved with '+vio.length+' override(s) — see Red-flags':'Saved');};
}
function closeModal(){$('overlay').classList.remove('show');}
document.addEventListener('click',e=>{if(e.target&&e.target.id==='overlay')closeModal();});

R.instr=function(){const names=[...new Set(S().map(s=>s.instr).filter(Boolean))].sort();
  let h=`<h2>Instructor Timetable — Semester ${SEM}</h2><div class="controls">Instructor: <select id="isel">`+names.map(n=>`<option>${esc(n)}</option>`).join('')+`</select></div><div id="ig" class="wrap"></div>`;
  $('t-instr').innerHTML=h;
  const draw=()=>{const n=$('isel').value;const all=S();
    let g='<table class="grid"><tr><th>Day</th>'+PERIODS.map(p=>`<th>${p}</th>`).join('')+'</tr>';
    DAYS.forEach(d=>{g+=`<tr><td style="text-align:left"><b>${d}</b></td>`+STARTS.map(t=>{const s=all.find(x=>x.instr===n&&x.day===d&&x.t===t);
      return s?`<td class="occ">${esc(s.mod)}\n${esc(s.prog)}\n@${esc(s.venue)}</td>`:'<td class="vac"></td>';}).join('')+'</tr>';});
    const w=der().workload.find(x=>x.instructor===n)||{modules:0,daytime_h:0,evening_h:0,total_h:0,flags:[]};const inf=D.instructors[n]||{};
    g+='</table><div class="small" style="margin-top:6px">'+(inf.dept?('Dept: '+esc(inf.dept)+(inf.qual?' · '+esc(inf.qual):'')+' · '):'')+
      'Modules: '+w.modules+' · Daytime '+w.daytime_h+'h · Evening '+w.evening_h+'h · Total '+w.total_h+'h '+
      (w.flags.length?'<span class="pill amber">'+esc(w.flags.join(', '))+'</span>':'<span class="pill ok">within limits</span>')+'</div>';
    $('ig').innerHTML=g;};
  $('isel').onchange=draw;draw();
};
function baseProgs(p){p=(p||'').replace(/\(STRM[^)]*\)/gi,'');
  return [...new Set(p.split(/[+,]/).map(s=>s.replace(/\s+/g,' ').trim().replace(/^,+|,+$/g,'')).filter(Boolean))];}
R.progtt=function(){const all=S();
  const set=new Set(); all.forEach(s=>baseProgs(s.prog).forEach(p=>set.add(p)));
  const progs=[...set].sort();
  if(!window.__ptProg||!progs.includes(window.__ptProg))window.__ptProg=progs[0]||'';
  const ntas=[...new Set(all.filter(s=>baseProgs(s.prog).includes(window.__ptProg)).map(s=>s.nta))].sort((a,b)=>ntaLevel(a)-ntaLevel(b));
  if(!window.__ptNta||!ntas.includes(window.__ptNta))window.__ptNta=ntas[0]||'';
  const strms=['All streams',...[...new Set(all.filter(s=>baseProgs(s.prog).includes(window.__ptProg)&&s.nta===window.__ptNta).map(s=>s.stream).filter(x=>x))].sort()];
  if(!window.__ptStream||!strms.includes(window.__ptStream))window.__ptStream='All streams';
  let h=`<h2>Programme Timetable — Semester ${SEM}</h2>`;
  h+=`<div class="controls noprint"><b>Programme:</b> <select id="ptsel">`+progs.map(p=>`<option ${p===window.__ptProg?'selected':''}>${esc(p)}</option>`).join('')+`</select>`+
     `<b>NTA level:</b> <select id="ptnta">`+ntas.map(n=>`<option ${n===window.__ptNta?'selected':''}>${esc(n)}</option>`).join('')+`</select>`+
     `<b>Stream:</b> <select id="ptstrm">`+strms.map(s=>`<option ${s===window.__ptStream?'selected':''}>${esc(s)}</option>`).join('')+`</select>`+
     `<button class="btn sec" onclick="window.print()">🖨 Print / Save PDF</button>`+
     `<button class="btn sec" onclick="progExportXls()">Excel</button>`+
     `<button class="btn sec" onclick="progExportCSV()">CSV</button></div>`;
  h+='<div id="ptgrid" class="wrap"></div>';
  $('t-progtt').innerHTML=h;
  const draw=()=>{const rows=ptRows();
    let g=`<h3>${esc(window.__ptProg)} · ${esc(window.__ptNta)}${window.__ptStream!=='All streams'?' · Stream '+esc(window.__ptStream):''} — Semester ${SEM} <span class="small">(${rows.length} sessions)</span></h3>`;
    g+='<table class="grid"><tr><th>Day</th>'+PERIODS.map(p=>`<th>${p}</th>`).join('')+'</tr>';
    DAYS.forEach(d=>{g+=`<tr><td style="text-align:left"><b>${d}</b></td>`+STARTS.map(t=>{
      const cell=rows.filter(s=>s.day===d&&s.t===t);
      return cell.length?`<td class="occ">${cell.map(s=>esc(s.mod)+'\n'+esc(s.prog)+'\n@'+esc(s.venue)+' · '+esc(s.instr)).join('\n———\n')}</td>`:'<td class="vac"></td>';
    }).join('')+'</tr>';});
    $('ptgrid').innerHTML=g+'</table>';};
  $('ptsel').onchange=()=>{window.__ptProg=$('ptsel').value;window.__ptNta='';window.__ptStream='';R.progtt();};
  $('ptnta').onchange=()=>{window.__ptNta=$('ptnta').value;window.__ptStream='';R.progtt();};
  $('ptstrm').onchange=()=>{window.__ptStream=$('ptstrm').value;draw();};
  draw();
};
function ptRows(){const prog=window.__ptProg,nta=window.__ptNta,strm=window.__ptStream;
  return S().filter(s=>baseProgs(s.prog).includes(prog)&&s.nta===nta&&(!strm||strm==='All streams'||s.stream===strm));}
const PHEAD=['Day','Period','Venue','Cohort/Stream','NTA','Module','Code','Instructor','Occupancy'];
function progRows(){return ptRows().slice().sort((a,b)=>DAYS.indexOf(a.day)-DAYS.indexOf(b.day)||a.t-b.t)
    .map(s=>[s.day,timeOf(s.t),s.venue,s.prog,s.nta,s.mod,s.code,s.instr,s.occ]);}
function ptFname(){return `CBE_Sem${SEM}_${window.__ptProg}_${(window.__ptNta||'').replace(/\s+/g,'')}${window.__ptStream&&window.__ptStream!=='All streams'?'_'+window.__ptStream:''}_timetable`;}
function progExportCSV(){dl([csvR(PHEAD)].concat(progRows().map(csvR)).join('\n'),ptFname()+'.csv','text/csv');}
function progExportXls(){let t='<table border=1><tr>'+PHEAD.map(h=>'<th>'+h+'</th>').join('')+'</tr>';
  progRows().forEach(r=>t+='<tr>'+r.map(c=>'<td>'+(''+c).replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</td>').join('')+'</tr>');
  dl('<html xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta charset="utf-8"></head><body>'+t+'</table></body></html>',ptFname()+'.xls','application/vnd.ms-excel');}
R.venue=function(){const vd=[...der().vutil].sort((a,b)=>(a.premises==='Main'?0:1)-(b.premises==='Main'?0:1)||b.periods_used-a.periods_used);
  let h=`<h2>Venue Dashboard — Semester ${SEM}</h2><div class="wrap"><table><tr><th>Venue</th><th>Cap</th><th>Type</th><th>Premises</th><th>Periods used</th><th>Available</th><th>Seat-periods</th><th>Utilisation</th></tr>`;
  vd.forEach(o=>h+=`<tr><td>${esc(o.venue)}</td><td>${o.capacity}</td><td>${o.type}</td><td>${o.premises}</td><td>${o.periods_used}</td><td>${o.periods_avail}</td><td>${o.seat_periods_used.toLocaleString()}</td><td>${o.utilisation}%</td></tr>`);
  $('t-venue').innerHTML=h+'</table></div>';
};
R.workload=function(){
  let h=`<h2>Workload — Semester ${SEM}</h2><div class="note">Caps: 7 modules · 32 daytime h · 20 evening h (soft 6 / 28 / 16). Rows at/over a limit are highlighted. Load is read directly from the timetable.</div><div class="wrap">`;
  h+='<table><tr><th>Instructor</th><th>Department</th><th>Modules</th><th>Daytime h</th><th>Evening h</th><th>Total h</th><th>Flag</th></tr>';
  der().workload.forEach(w=>{const over=w.flags.some(f=>f===f.toUpperCase()&&f!==f.toLowerCase());
    h+=`<tr><td>${esc(w.instructor)}</td><td>${esc(w.dept||'—')}</td><td>${w.modules}</td><td>${w.daytime_h}</td><td>${w.evening_h}</td><td>${w.total_h}</td><td class="${w.flags.length?(over?'flag-red':'flag-amber'):''}">${esc(w.flags.join(', '))}</td></tr>`;});
  $('t-workload').innerHTML=h+'</table></div>';
};
R.capacity=function(){let vs=[...VENS()].sort((a,b)=>(a.premises==='Main'?0:1)-(b.premises==='Main'?0:1)||b.capacity-a.capacity);
  let h=`<h2>Venue Capacity — Semester ${SEM}</h2><div class="wrap"><table><tr><th>Venue</th><th>Capacity</th><th>Type</th><th>Premises</th></tr>`;
  vs.forEach(v=>h+=`<tr><td>${esc(v.venue)}</td><td>${v.capacity}</td><td>${v.type}</td><td>${v.premises}</td></tr>`);
  h+=`<tr class="foot"><td>TOTAL SEAT CAPACITY / SESSION</td><td>${VENS().reduce((a,v)=>a+v.capacity,0)}</td><td></td><td></td></tr>`;
  $('t-capacity').innerHTML=h+'</table></div>';
};
R.flags=function(){const m=der().metrics;const hard=der().flags.filter(f=>f.severity==='hard'),rev=der().flags.filter(f=>f.severity==='review');
  let h=`<h2>Red-flags — Semester ${SEM}</h2>`;
  h+=`<div class="cards"><div class="card ${m.hard?'warn':'ok'}"><div class="n">${m.hard}</div><div class="l">Hard rule-breaks</div></div>`+
   `<div class="card"><div class="n">${m.review}</div><div class="l">To review</div></div>`+
   `<div class="card ${m.overloads?'warn':'ok'}"><div class="n">${m.overloads}</div><div class="l">Instructors over a cap</div></div>`+
   `<div class="card"><div class="n">${m.softs}</div><div class="l">At/over soft limit</div></div></div>`;
  h+='<div class="note">'+esc(D.model_note||'')+'</div>';
  const part=der().flags.filter(f=>f.type==='PART_TIMER_NEEDED'||f.type==='NO_CAPABLE_STAFF');
  if(part.length)h+=`<div class="note warn" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span><b>${part.length}</b> module(s) could not be staffed — qualified lecturers are at capacity, on study leave, or none can teach them.</span>`+
    `<button class="btn" onclick="lecturerModal(null,'Part-time')">+ Add part-time lecturer</button>`+
    `<span class="small">After adding the lecturer (and their teaching capability), go to Rules → Generate again.</span></div>`;
  const r1=der().flags.filter(f=>f.type.startsWith('R1')).length;
  if(r1)h+=`<div class="note warn" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span><b>${r1}</b> module/stream blocks don't yet have their two weekly sessions.</span>`+
    `<button class="btn" onclick="autocompleteR1()">⚙ Auto-complete missing 2nd sessions</button>`+
    `<span class="small">Adds a second session (same lecturer, different day) in the earliest free daytime slot; anything that won't fit is listed here.</span></div>`;
  const tbl=(rows,cls)=>{if(!rows.length)return '<p class="small">None.</p>';let t='<div class="wrap"><table><tr><th>Rule</th><th>Detail</th></tr>';
    rows.forEach(f=>t+=`<tr><td class="${cls}"><b>${f.type}</b></td><td>${esc(f.detail)}</td></tr>`);return t+'</table></div>';};
  h+='<h3>Hard rule-breaks (clashes, capacity, placement, overload)</h3>'+tbl(hard,'flag-red');
  h+='<h3>To review (foundation-model advisories &amp; allocation checks)</h3>'+tbl(rev,'flag-amber');
  $('t-flags').innerHTML=h;
};
// ---------- Data management ----------
const REFC={
  instructors:{cols:['name','dept','qual','position','status','module_limit','avail_days','avail_periods'],sem:false,labels:['Name','Department','Qualification','Position','Status','Module limit','Available days','Available periods'],num:[]},
  teaching:{cols:['instructor','code','module'],sem:false,labels:['Instructor','Module code','Module'],num:[]},
  venues:{cols:['venue','capacity','premises','type'],sem:true,labels:['Venue','Capacity','Premises','Type'],num:['capacity']},
  curriculum:{cols:['programme','nta','code','module','credit','cls'],sem:true,labels:['Programme','NTA','Code','Module','Credit','Class'],num:[]},
  enrolment:{cols:['programme','department','nta','year','female','male','total'],sem:false,labels:['Programme','Department','NTA','Year','Female','Male','Total'],num:['total']},
};
let DATASUB='instructors', DATAROWS=[];
const SUBS=[['instructors','Instructors & qualifications'],['teaching','Teaching capability'],['venues','Venues'],
  ['curriculum','Curriculum'],['enrolment','Enrolment']];
R.data=function(){
  let h=`<h2>Data entry — Semester ${SEM}</h2>`;
  h+='<div class="note">Add or upload the information the timetable is built from. Edit rows one by one, or use <b>Download template</b> then <b>Upload CSV</b> to load many at once. Venues &amp; Curriculum are per-semester; the others are shared across both.</div>';
  h+='<div class="controls">'+SUBS.map(s=>`<button class="btn ${s[0]===DATASUB?'':'sec'}" onclick="dataSub('${s[0]}')">${s[1]}</button>`).join('')+'</div>';
  h+='<div id="datapanel"><div class="small">Loading…</div></div>';
  $('t-data').innerHTML=h; renderDataPanel();
};
function dataSub(k){DATASUB=k;R.data();}
R.catalogue=async function(){const r=await api(`/${SEM}/catalogue`); window.__cat=r.rows;
  const cross=r.rows.filter(x=>x.cross).length;
  let h=`<h2>Module Catalogue — Semester ${SEM} <span class="small">(${r.rows.length} modules · ${cross} cross-cutting)</span></h2>`;
  h+='<div class="note">Each module shows the <b>programmes</b> and <b>NTA levels</b> in which it is taught; modules shared by more than one programme are tagged <b>cross-cutting</b>. Click <b>Edit</b> to correct a name or code everywhere it appears.</div>';
  h+='<div class="controls"><input type="text" id="dsearch" placeholder="Search module, code or programme…" style="min-width:280px"></div><div class="wrap"><table id="dtbl"><tr><th>Code</th><th>Module</th><th>Credit</th><th>Programmes</th><th>NTA levels</th><th></th></tr>';
  h+=r.rows.map((x,i)=>`<tr><td>${esc(x.code)}</td><td>${esc(x.module)}${x.cross?' <span class="pill amber">cross-cutting</span>':''}</td><td>${esc(x.credit)}</td><td>${esc(x.programmes)}</td><td>${esc(x.ntas)}</td><td><button class="btn small" data-i="${i}">Edit</button></td></tr>`).join('');
  $('t-catalogue').innerHTML=h+'</table></div>'; wireSearch();
  document.querySelectorAll('#t-catalogue button[data-i]').forEach(b=>{b.onclick=()=>{const x=window.__cat[+b.dataset.i];moduleModal(x.code,x.module);};});};
const NTAOPTS=['NTA4','NTA5','NTA6','NTA7 Y1','NTA7 Y2','NTA8','NTA9'];
async function moduleModal(code,module){
  let progs=[];try{progs=[...new Set((await api('/ref/enrolment')).rows.map(x=>x.programme))].sort();}catch(e){}
  window.__asgCtx={code,module};
  const draw=async()=>{const c=window.__asgCtx;
    let asg=[];try{asg=(await api(`/${SEM}/module_assign?code=${encodeURIComponent(c.code||'')}&module=${encodeURIComponent(c.module||'')}`)).rows;}catch(e){}
    $('m_asg').innerHTML='<table style="width:100%"><tr><th>Programme</th><th>NTA level</th><th></th></tr>'+
      (asg.length?asg.map(a=>`<tr><td>${esc(a.programme)}</td><td>${esc(a.nta)}</td><td><button class="btn small danger" onclick="delAssign(${a._id})">Remove</button></td></tr>`).join(''):'<tr><td colspan="3" class="small">Not yet assigned to any programme.</td></tr>')+'</table>';};
  window.__reAsg=draw;
  $('modal').innerHTML='<h3>Module — details &amp; assignments</h3>'+
    '<div style="display:flex;flex-direction:column;gap:8px">'+
      `<label style="font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">Module name<input type="text" id="m_name" value="${esc(module)}"></label>`+
      `<label style="font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">Module code<input type="text" id="m_code" value="${esc(code)}"></label>`+
    '</div>'+
    '<div style="text-align:right;margin-top:6px"><button class="btn" id="m_save">Save name/code everywhere</button></div>'+
    '<h4 style="margin:12px 0 4px;color:var(--navy)">Programmes &amp; NTA levels this module is taught in</h4>'+
    '<div id="m_asg" class="wrap" style="max-height:170px;overflow:auto"></div>'+
    '<div class="controls" style="margin-top:6px"><input type="text" id="m_prog" list="m_proglist" placeholder="Programme…" style="min-width:150px"><datalist id="m_proglist">'+progs.map(p=>`<option>${esc(p)}</option>`).join('')+'</datalist>'+
      '<select id="m_nta">'+NTAOPTS.map(n=>`<option>${n}</option>`).join('')+'</select>'+
      '<button class="btn" onclick="addAssign()">+ Add</button></div>'+
    '<div style="text-align:right;margin-top:10px"><button class="btn sec" onclick="closeModal();R.catalogue()">Close</button></div>';
  $('overlay').classList.add('show'); draw();
  $('m_save').onclick=async()=>{const nm=$('m_name').value.trim(),nc=$('m_code').value.trim();
    const res=await api('/rename/module',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old_module:window.__asgCtx.module,old_code:window.__asgCtx.code,new_module:nm,new_code:nc})});
    window.__asgCtx={code:nc,module:nm}; await loadData(); draw();
    toast('Updated '+((res.sessions||0)+(res.curriculum||0)+(res.teaching||0))+' record(s)');};
}
async function addAssign(){const c=window.__asgCtx;const prog=$('m_prog').value.trim();const nta=$('m_nta').value;
  if(!prog){alert('Enter or pick a programme.');return;}
  await api(`/${SEM}/module_assign`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:c.code,module:c.module,programme:prog,nta})});
  $('m_prog').value=''; if(window.__reAsg)await window.__reAsg(); toast('Added '+prog+' · '+nta);}
async function delAssign(id){await api(`/${SEM}/module_assign/${id}`,{method:'DELETE'}); if(window.__reAsg)await window.__reAsg(); toast('Removed');}
R.streams=async function(){const r=await api(`/${SEM}/streams`);
  let h=`<h2>Streams — Semester ${SEM} <span class="small">(largest room ${r.maxcap} seats; suggested = enrolment ÷ largest room)</span></h2>`;
  h+='<div class="controls"><input type="text" id="dsearch" placeholder="Search programme…" style="min-width:260px"></div><div class="wrap"><table id="dtbl"><tr><th>Programme</th><th>NTA</th><th>Enrolment</th><th>Streams present</th><th># present</th><th>Suggested</th><th>Sessions</th></tr>';
  h+=r.rows.map(x=>`<tr><td>${esc(x.programme)}</td><td>${esc(x.nta)}</td><td>${x.enrolment||''}</td><td>${esc(x.streams_present)}</td><td>${x.n_present}</td><td>${x.suggested}</td><td>${x.sessions}</td></tr>`).join('');
  $('t-streams').innerHTML=h+'</table></div>'; wireSearch();};
R.reports=async function(){const r=await api(`/${SEM}/reports`);
  const card=(n,l,cls='')=>`<div class="card ${cls}"><div class="n">${n}</div><div class="l">${l}</div></div>`;
  let h=`<div class="controls" style="justify-content:space-between"><h2 style="border:0;margin:0">Facts &amp; Figures — Semester ${SEM}</h2><button class="btn sec noprint" onclick="window.print()">🖨 Print / Save as PDF</button></div>`;
  h+='<div class="note noprint">Totals below are generated from the data you maintain in the <b>Data</b> tab. Enrolment figures are blank until you enter or upload them (in <b>Data → Enrolment</b>). Use the CSV buttons or Print to produce reports.</div>';
  h+='<h3>Enrolment</h3><div class="cards">'+card(r.enrolment.total.toLocaleString(),'Total students')+card(r.enrolment.female.toLocaleString(),'Female')+card(r.enrolment.male.toLocaleString(),'Male')+card(r.enrolment.programmes,'Programmes')+'</div>';
  h+=reportTable('Enrolment by department',['Department','Programmes','Female','Male','Total'],r.enrolment.by_department.map(x=>[x.department,x.programmes,x.female,x.male,x.total]),'enrolment_by_department');
  h+=reportTable('Enrolment by programme',['Programme','Department','Total'],r.enrolment.by_programme.map(x=>[x.programme,x.department,x.total]),'enrolment_by_programme');
  h+=reportTable('Enrolment by NTA level',['NTA level','Total'],r.enrolment.by_nta.map(x=>[x.nta,x.total]),'enrolment_by_nta');
  h+='<h3>Academic staff</h3><div class="cards">'+card(r.staff.total,'Instructors')+card(r.staff.phd,'PhD holders')+card(r.staff.by_department.length,'Departments')+'</div>';
  h+=reportTable('Staff by department',['Department','Instructors','PhD holders'],r.staff.by_department.map(x=>[x.department,x.count,x.phd]),'staff_by_department');
  h+='<h3>Venues</h3><div class="cards">'+card(r.venues.count,'Venues')+card(r.venues.capacity.toLocaleString(),'Total seat capacity / period')+card(r.venues.labs,'Laboratories')+'</div>';
  h+=reportTable('Venues by premises',['Premises','Venues','Seat capacity'],r.venues.by_premises.map(x=>[x.premises,x.count,x.capacity]),'venues_by_premises');
  h+='<h3>Curriculum &amp; timetable</h3><div class="cards">'+card(r.modules.catalogue,'Distinct modules')+card(r.timetable.sessions,'Sessions')+card(r.timetable.utilisation+'%','Utilisation')+card(r.timetable.instructors,'Instructors used')+card(r.timetable.hard,'Hard rule-breaks',r.timetable.hard?'warn':'ok')+card(r.timetable.overloads,'Over a load cap',r.timetable.overloads?'warn':'ok')+'</div>';
  $('t-reports').innerHTML=h;};
function reportTable(title,heads,rows,csvname){
  let t=`<h4 style="margin:12px 0 4px;color:var(--navy)">${esc(title)} <button class="btn small sec noprint" onclick="exportReport('${csvname}')">CSV</button></h4><div class="wrap"><table id="rep_${csvname}"><tr>`+heads.map(hh=>`<th>${esc(hh)}</th>`).join('')+'</tr>';
  t+=(rows.length?rows.map(rr=>'<tr>'+rr.map(c=>`<td>${esc(c)}</td>`).join('')+'</tr>').join(''):`<tr><td colspan="${heads.length}" class="small">No data yet.</td></tr>`);
  return t+'</table></div>';}
function exportReport(name){const tbl=$('rep_'+name);if(!tbl)return;const csv=[];
  tbl.querySelectorAll('tr').forEach(tr=>{csv.push([...tr.children].map(td=>'"'+td.textContent.replace(/"/g,'""')+'"').join(','));});
  dl(csv.join('\n'),'CBE_'+name+'_Sem'+SEM+'.csv','text/csv');}
let TINSTRROWS=[];
async function renderTeaching(){
  const p=$('datapanel');
  const [ins,mods,teach]=await Promise.all([api('/ref/instructors'),api('/modules'),api('/ref/teaching')]);
  TINSTRROWS=ins.rows;
  const depts=['All departments',...Array.from(new Set(ins.rows.map(r=>r.dept).filter(Boolean))).sort()];
  if(!window.__tDept)window.__tDept='All departments';
  const pool=ins.rows.filter(r=>window.__tDept==='All departments'||r.dept===window.__tDept);
  const names=pool.map(r=>r.name).sort();
  if(!window.__tInstr||!names.includes(window.__tInstr))window.__tInstr=names[0]||'';
  const modByName={}; mods.rows.forEach(m=>{if(m.module)modByName[m.module]=m.code;}); window.__modByName=modByName;
  const cur=ins.rows.find(r=>r.name===window.__tInstr)||{};
  const rows=teach.rows.filter(r=>r.instructor===window.__tInstr);
  let h='<div class="note">Choose a department and lecturer, then add <b>every</b> module they are able to teach — there is no limit here. How many they are actually <b>given</b> is decided later during generation (workload), where each lecturer’s cap and any module limit apply. Use <b>+ New lecturer</b> to add someone (including a part-timer) with their qualification.</div>';
  h+='<div class="controls"><b>Department:</b> <select id="tdept">'+depts.map(d=>`<option ${d===window.__tDept?'selected':''}>${esc(d)}</option>`).join('')+'</select>'+
     '<b>Lecturer:</b> <select id="tinstr">'+(names.length?names.map(n=>`<option ${n===window.__tInstr?'selected':''}>${esc(n)}</option>`).join(''):'<option>(none in this department)</option>')+'</select>'+
     '<button class="btn" onclick="lecturerModal(null)">+ New lecturer</button>'+
     '<a class="btn sec" href="/api/ref/teaching/template.csv">Download template</a>'+
     '<label class="btn sec" style="cursor:pointer">Upload CSV<input type="file" accept=".csv" style="display:none" onchange="uploadCSV(\'teaching\',this)"></label></div>';
  if(window.__tInstr) h+=`<div class="small" style="margin:2px 0 8px"><b>${esc(cur.dept||'—')}</b> · ${esc(cur.qual||'qualification not set')}${cur.position?' · '+esc(cur.position):''} <button class="btn small sec" onclick="lecturerModal(${cur._id})">Edit lecturer details</button></div>`;
  h+='<div class="controls" style="background:#eef3fb;padding:10px 12px;border-radius:8px"><b>Add a module '+esc(window.__tInstr||'')+' can teach:</b> '+
     '<input type="text" id="tmod" list="tmodlist" placeholder="Type or pick a module…" style="min-width:300px">'+
     '<datalist id="tmodlist">'+mods.rows.map(m=>`<option value="${esc(m.module)}">${esc(m.code)}</option>`).join('')+'</datalist>'+
     '<button class="btn" onclick="teachAdd()">+ Add module</button></div>';
  h+=`<h3>${esc(window.__tInstr||'(no lecturer selected)')} — ${rows.length} module(s)</h3><div class="wrap"><table><tr><th>Module code</th><th>Module</th><th></th></tr>`;
  h+=rows.map(r=>`<tr><td>${esc(r.code)}</td><td>${esc(r.module)}</td><td><button class="btn small danger" onclick="teachDel(${r._id})">Remove</button></td></tr>`).join('')||'<tr><td colspan="3" class="small">No modules yet — add some above.</td></tr>';
  p.innerHTML=h+'</table></div>';
  $('tdept').onchange=()=>{window.__tDept=$('tdept').value;window.__tInstr='';renderTeaching();};
  $('tinstr').onchange=()=>{window.__tInstr=$('tinstr').value;renderTeaching();};
}
async function teachAdd(){const el=$('tmod');const mod=el.value.trim();if(!mod){el.focus();return;}
  if(!window.__tInstr){alert('Add or pick a lecturer first.');return;}
  const code=(window.__modByName&&window.__modByName[mod])||'';
  await api('/ref/teaching',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({instructor:window.__tInstr,code,module:mod,sem:SEM})});
  toast('Added module for '+window.__tInstr);renderTeaching();}
async function teachDel(id){await api('/ref/teaching/'+id,{method:'DELETE'});toast('Removed');renderTeaching();}
const LDAYS=['Mon','Tue','Wed','Thu','Fri','Sat'], LPERIODS=[7,9,11,13,15,17,19];
async function lecturerModal(rid,preset){
  const all=(await api('/ref/instructors')).rows;
  const row=rid==null?{}:(all.find(x=>x._id===rid)||{});
  const depts=Array.from(new Set(all.map(x=>x.dept).filter(Boolean))).sort();
  const status=row.status||preset||'On duty'; const STAT=['On duty','Study leave','Part-time','Volunteer'];
  const chDays=new Set((row.avail_days||'').split(',').map(s=>s.trim()).filter(Boolean));
  const chPer=new Set((row.avail_periods||'').split(',').map(s=>{const m=(s.match(/\d+/)||[])[0];return m?+m:null;}).filter(x=>x!=null));
  const fld=(lbl,inner)=>`<label style="font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">${lbl}${inner}</label>`;
  $('modal').innerHTML=`<h3>${rid==null?'New lecturer':'Edit lecturer'}</h3>`+
    '<div style="display:flex;flex-direction:column;gap:8px;max-height:70vh;overflow:auto">'+
      fld('Full name & title',`<input type="text" id="l_name" value="${esc(row.name||'')}">`)+
      fld('Department',`<input type="text" id="l_dept" list="deptlist" value="${esc(row.dept||(window.__tDept&&window.__tDept!=='All departments'?window.__tDept:''))}"><datalist id="deptlist">${depts.map(d=>`<option>${esc(d)}</option>`).join('')}</datalist>`)+
      fld('Academic qualification',`<input type="text" id="l_qual" value="${esc(row.qual||'')}">`)+
      fld('Position',`<input type="text" id="l_position" value="${esc(row.position||'')}">`)+
      fld('Duty status',`<select id="l_status">${STAT.map(s=>`<option ${s===status?'selected':''}>${s}</option>`).join('')}</select>`)+
      fld('Module limit (blank = normal cap; set a smaller number for part-timers / volunteers)',`<input type="number" id="l_limit" value="${esc(row.module_limit||'')}" placeholder="e.g. 2">`)+
      '<div style="font-size:11px;color:#4a5568">Available / preferred days <span class="small">(leave all unticked = any day)</span><br>'+
        LDAYS.map(d=>`<label style="display:inline-flex;align-items:center;gap:4px;margin:3px 10px 0 0;font-size:12px"><input type="checkbox" class="l_day" value="${d}" ${chDays.has(d)?'checked':''}> ${d}</label>`).join('')+'</div>'+
      '<div style="font-size:11px;color:#4a5568">Available / preferred periods <span class="small">(leave all unticked = any time)</span><br>'+
        LPERIODS.map(t=>`<label style="display:inline-flex;align-items:center;gap:4px;margin:3px 10px 0 0;font-size:12px"><input type="checkbox" class="l_per" value="${t}" ${chPer.has(t)?'checked':''}> ${('0'+t).slice(-2)}:00</label>`).join('')+'</div>'+
    '</div>'+
    `<div style="text-align:right;margin-top:10px"><button class="btn sec" onclick="closeModal()">Cancel</button> <button class="btn" id="l_save">Save</button></div>`;
  $('overlay').classList.add('show');
  const origName=row.name;
  $('l_save').onclick=async()=>{const body={name:$('l_name').value.trim(),dept:$('l_dept').value.trim(),qual:$('l_qual').value.trim(),
      position:$('l_position').value.trim(),status:$('l_status').value,module_limit:$('l_limit').value.trim(),
      avail_days:[...document.querySelectorAll('.l_day:checked')].map(c=>c.value).join(','),
      avail_periods:[...document.querySelectorAll('.l_per:checked')].map(c=>c.value).join(',')};
    if(!body.name){alert('Please enter the lecturer name.');return;}
    if(rid==null)await api('/ref/instructors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    else await api('/ref/instructors/'+rid,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(origName&&body.name!==origName){
      await api('/rename/instructor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:origName,new:body.name})});
      toast('Renamed everywhere: '+origName+' → '+body.name);}
    else toast('Lecturer saved');
    window.__tInstr=body.name; if(body.dept)window.__tDept=body.dept;
    closeModal();await loadData();renderNav();if(CUR==='data')renderDataPanel(); if(DATASUB==='teaching')renderTeaching();};
}
function ntaLevel(n){const m=(n||'').match(/(\d)/);return m?+m[1]:9;}
async function renderEnrolment(){
  const p=$('datapanel');
  const r=await api('/ref/enrolment'); DATAROWS=r.rows;
  const byProg={}; r.rows.forEach(x=>{(byProg[x.programme]||(byProg[x.programme]=[])).push(x);});
  let h='<div class="note">Enrolment is grouped <b>per programme, then per NTA level</b>. Fill in the student numbers (Female, Male, Total) for each level. Use <b>Download template</b> / <b>Upload CSV</b> to load many at once.</div>';
  h+=`<div class="controls"><button class="btn" onclick="progModal()">+ Add programme</button>`+
     `<button class="btn sec" onclick="entityEdit(null)">+ Add single row</button>`+
     `<a class="btn sec" href="/api/ref/enrolment/template.csv">Download template</a>`+
     `<label class="btn sec" style="cursor:pointer">Upload CSV<input type="file" accept=".csv" style="display:none" onchange="uploadCSV('enrolment',this)"></label>`+
     `<input type="text" id="esearch" placeholder="Search programme…" style="min-width:220px"><span class="small">${Object.keys(byProg).length} programmes</span></div>`;
  h+='<div class="wrap"><table id="etbl">';
  Object.keys(byProg).sort().forEach(prog=>{
    const rows=byProg[prog].sort((a,b)=>ntaLevel(a.nta)-ntaLevel(b.nta)||String(a.year).localeCompare(String(b.year)));
    const dept=rows[0].department||'—';
    const tot=rows.reduce((s,x)=>s+(parseInt(x.total)||0),0);
    h+=`<tr data-prog="${esc(prog)}" style="background:var(--lblue)"><td colspan="6"><b>${esc(prog)}</b> <span class="small">— ${esc(dept)} · ${rows.length} NTA level(s)${tot?' · total '+tot:''}</span></td></tr>`;
    h+=`<tr data-prog="${esc(prog)}"><th style="background:#6b83b5">NTA level</th><th style="background:#6b83b5">Year</th><th style="background:#6b83b5">Female</th><th style="background:#6b83b5">Male</th><th style="background:#6b83b5">Total</th><th style="background:#6b83b5"></th></tr>`;
    rows.forEach(x=>{h+=`<tr data-prog="${esc(prog)}"><td>${esc(x.nta)}</td><td>${esc(x.year)}</td><td>${esc(x.female)}</td><td>${esc(x.male)}</td><td>${esc(x.total)}</td>`+
      `<td style="white-space:nowrap"><button class="btn small" onclick="entityEdit(${x._id})">Edit</button> <button class="btn small danger" onclick="entityDel(${x._id})">✕</button></td></tr>`;});
  });
  h+='</table></div>';
  p.innerHTML=h;
  const s=$('esearch'); if(s)s.oninput=()=>{const qq=s.value.toLowerCase();
    document.querySelectorAll('#etbl tr[data-prog]').forEach(tr=>{tr.style.display=(!qq||tr.dataset.prog.toLowerCase().includes(qq))?'':'none';});};
}
function progModal(){
  const depts=[...new Set((DATAROWS||[]).map(x=>x.department).filter(Boolean))].sort();
  const levels=["NTA4","NTA5","NTA6","NTA7 Y1","NTA7 Y2","NTA8","NTA9"];
  const pre=new Set(["NTA4","NTA5","NTA6","NTA7 Y1","NTA8"]);
  $('modal').innerHTML='<h3>Add a programme</h3>'+
    '<div style="display:flex;flex-direction:column;gap:8px">'+
      '<label style="font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">Programme name<input type="text" id="pg_name" placeholder="e.g. Business Administration"></label>'+
      `<label style="font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">Department<input type="text" id="pg_dept" list="pgdepts" placeholder="e.g. Business Administration"><datalist id="pgdepts">${depts.map(d=>`<option>${esc(d)}</option>`).join('')}</datalist></label>`+
      '<div><div class="small" style="margin-bottom:4px">NTA levels this programme offers (tick all that apply):</div>'+
        levels.map(l=>`<label style="display:inline-flex;align-items:center;gap:5px;margin:2px 12px 4px 0;font-size:12px"><input type="checkbox" class="pg_lvl" value="${l}" ${pre.has(l)?'checked':''}> ${l.replace('Y1',' Yr1').replace('Y2',' Yr2')}</label>`).join('')+
      '</div>'+
    '</div>'+
    '<div style="text-align:right;margin-top:10px"><button class="btn sec" onclick="closeModal()">Cancel</button> <button class="btn" id="pg_save">Add programme</button></div>';
  $('overlay').classList.add('show');
  $('pg_save').onclick=async()=>{const name=$('pg_name').value.trim();if(!name){alert('Please enter a programme name.');return;}
    const dept=$('pg_dept').value.trim();
    const chosen=[...document.querySelectorAll('.pg_lvl:checked')].map(c=>c.value);
    if(!chosen.length){alert('Please tick at least one NTA level.');return;}
    let r;try{r=await api('/enrolment/add_programme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({programme:name,department:dept,levels:chosen})});}catch(e){alert('Could not add: '+e.message);return;}
    closeModal();renderEnrolment();toast('Added '+name+' with '+r.added+' NTA level(s)');};
}
async function renderDataPanel(){
  const p=$('datapanel');
  if(DATASUB==='teaching')return renderTeaching();
  if(DATASUB==='enrolment')return renderEnrolment();
  const cfg=REFC[DATASUB]; const q=cfg.sem?`?sem=${SEM}`:'';
  const r=await api(`/ref/${DATASUB}${q}`); DATAROWS=r.rows;
  let deptSel='';
  if(DATASUB==='instructors'){const depts=['All departments',...Array.from(new Set(r.rows.map(x=>x.dept).filter(Boolean))).sort()];
    deptSel=`<b>Dept:</b> <select id="ddept">`+depts.map(d=>`<option>${esc(d)}</option>`).join('')+`</select>`;}
  let h=`<div class="controls"><button class="btn" onclick="entityEdit(null)">+ Add row</button>`+deptSel+
    `<a class="btn sec" href="/api/ref/${DATASUB}/template.csv">Download template</a>`+
    `<label class="btn sec" style="cursor:pointer">Upload CSV<input type="file" accept=".csv" style="display:none" onchange="uploadCSV('${DATASUB}',this)"></label>`+
    `<input type="text" id="dsearch" placeholder="Search…" style="min-width:200px"><span class="small">${r.rows.length} rows`+(cfg.sem?` · Semester ${SEM}`:' · shared')+`</span></div>`;
  h+='<div class="wrap"><table id="dtbl"><tr>'+cfg.labels.map(l=>`<th>${l}</th>`).join('')+'<th></th></tr>';
  h+=r.rows.map(row=>'<tr>'+cfg.cols.map(c=>`<td>${esc(row[c])}</td>`).join('')+
     `<td style="white-space:nowrap"><button class="btn small" onclick="entityEdit(${row._id})">Edit</button> <button class="btn small danger" onclick="entityDel(${row._id})">✕</button></td></tr>`).join('');
  p.innerHTML=h+'</table></div>';
  if(DATASUB==='instructors')wireInstrFilters(); else wireSearch();
}
function wireInstrFilters(){const s=$('dsearch'),d=$('ddept');
  const apply=()=>{const q=(s?s.value.toLowerCase():''),dv=(d?d.value:'All departments');
    document.querySelectorAll('#dtbl tr').forEach((tr,i)=>{if(i===0)return;
      const okq=!q||tr.textContent.toLowerCase().includes(q);
      const okd=(dv==='All departments')||(tr.children[1]&&tr.children[1].textContent===dv);
      tr.style.display=(okq&&okd)?'':'none';});};
  if(s)s.oninput=apply; if(d)d.onchange=apply;}
function wireSearch(){const s=$('dsearch');if(!s)return;s.oninput=()=>{const q=s.value.toLowerCase();
  document.querySelectorAll('#dtbl tr').forEach((tr,i)=>{if(i===0)return;tr.style.display=(!q||tr.textContent.toLowerCase().includes(q))?'':'none';});};}
function entityEdit(rid){
  if(DATASUB==='instructors')return lecturerModal(rid);
  const cfg=REFC[DATASUB];const row=rid==null?{}:DATAROWS.find(x=>x._id===rid)||{};
  $('modal').innerHTML=`<h3>${rid==null?'Add':'Edit'} — ${SUBS.find(s=>s[0]===DATASUB)[1]}</h3>`+
    '<div style="display:flex;flex-direction:column;gap:8px">'+cfg.cols.map((c,i)=>
      `<label style="font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">${cfg.labels[i]}<input type="${cfg.num.includes(c)?'number':'text'}" id="d_${c}" value="${esc(row[c]==null?'':row[c])}"></label>`).join('')+'</div>'+
    `<div style="text-align:right;margin-top:10px"><button class="btn sec" onclick="closeModal()">Cancel</button> <button class="btn" id="d_save">Save</button></div>`;
  $('overlay').classList.add('show');
  const origName=row.name;
  $('d_save').onclick=async()=>{const body={sem:SEM};cfg.cols.forEach(c=>body[c]=$('d_'+c).value);
    if(rid==null)await api(`/ref/${DATASUB}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    else await api(`/ref/${DATASUB}/${rid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(DATASUB==='instructors'&&origName&&body.name&&body.name!==origName){
      await api('/rename/instructor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:origName,new:body.name})});
      toast('Renamed everywhere: '+origName+' → '+body.name);}
    else toast('Saved');
    closeModal();renderDataPanel();
    if(DATASUB==='instructors'||DATASUB==='venues'){await loadData();renderNav();}};
}
async function entityDel(rid){if(!confirm('Delete this row?'))return;await api(`/ref/${DATASUB}/${rid}`,{method:'DELETE'});renderDataPanel();toast('Deleted');}
function uploadCSV(entity,input){const f=input.files[0];if(!f)return;const rd=new FileReader();
  rd.onload=async()=>{const mode=confirm('Replace ALL existing rows with this file?\n\nOK = replace everything · Cancel = add to existing')?'replace':'append';
    let r;try{r=await api(`/ref/${entity}/import`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv:rd.result,mode,sem:SEM})});}catch(e){alert('Import failed: '+e.message);return;}
    input.value='';toast('Imported '+r.imported+' rows');renderDataPanel();
    if(entity==='instructors'||entity==='venues'){await loadData();renderNav();}};
  rd.readAsText(f);}

const SETLBL={max_stream_size:'Max students per stream — “auto” = largest room',seat_tolerance:'Seat tolerance over room capacity',
  module_cap:'Max modules per instructor (hard cap)',daytime_cap:'Max daytime hours / week',evening_cap:'Max evening hours / week',
  soft_modules:'Soft limit — modules',soft_daytime:'Soft limit — daytime hours',soft_evening:'Soft limit — evening hours',
  lab_size:'Typical lab size (from venues)',classroom_size:'Typical classroom size (from venues)',days:'Teaching days'};
const BUILTIN_RULES=[
 'R1 — Each module runs as two 2-hour sessions per week, on different days, per stream.',
 'R2 — The same instructor teaches both sessions of a stream.',
 'R3 — No instructor is double-booked.',
 'R4 — No cohort/stream is double-booked.',
 'R5 — No room loaded beyond capacity (+ tolerance).',
 'R6 — Saba Saba venues end by 17:00.',
 'R7 — Laboratories/smart rooms only for hands-on IT modules.',
 'R8 — Master’s (NTA9) only in the evening or Saturday, in BTA/BTB/BTC.',
 'R9 — Appropriate allocation: Master’s to PhD holders; IT to ICT staff; modules only to capable staff.',
 'R10 — No stream has more than 3 back-to-back (consecutive) sessions in a day.',
 'L1–L3 — Load caps: max modules, daytime hours and evening hours per instructor.'];
R.rules=async function(){const r=await api('/settings');const s=r.settings;
  let vs={largest_hall:0,typical_classroom:0,typical_lab:0}; try{vs=await api(`/${SEM}/venuesizes`);}catch(e){}
  const HINT={max_stream_size:`“auto” uses the largest room in Semester ${SEM} (${vs.largest_hall} seats). Type a smaller number to cap the stream size.`,
    classroom_size:`from your venues, a typical classroom is about ${vs.typical_classroom} seats.`,
    lab_size:`from your venues, a typical lab is about ${vs.typical_lab} seats.`};
  let h=`<h2>Rules &amp; Generation — Semester ${SEM}</h2>`;
  h+='<div class="note warn"><b>Generate a timetable from your data.</b> Using the enrolment, venues, curriculum and teaching-capability you maintain in the <b>Data</b> tab, the system sizes streams, allocates venues and instructors under the rules below, and red-flags anything that cannot be placed. This <b>replaces</b> the current Semester '+SEM+' schedule (use <b>Sessions → Reset to published</b> to restore).</div>';
  h+=`<div class="controls"><button class="btn" style="font-size:14px;padding:10px 18px" onclick="generateTT()">⚙ Generate Semester ${SEM} timetable</button></div>`;
  h+='<h3>Parameters</h3><div class="note">Stream sizes follow your actual <b>venue capacity</b>: leaving “Max students per stream” as <b>auto</b> makes each stream as large as the biggest room, so the number of streams is decided by the rooms you have. Change any value, then <b>Save parameters</b>.</div><div style="display:flex;flex-wrap:wrap;gap:12px;max-width:920px">';
  Object.keys(SETLBL).forEach(k=>{const v=s[k]==null?'':s[k];
    h+=`<label style="flex:1;min-width:240px;font-size:11px;color:#4a5568;display:flex;flex-direction:column;gap:3px">${SETLBL[k]}<input type="text" data-set="${k}" value="${esc(v)}">${HINT[k]?`<span class="small" style="font-size:10px">${esc(HINT[k])}</span>`:''}</label>`;});
  h+='</div><div class="controls"><button class="btn" onclick="saveSettings()">Save parameters</button></div>';
  h+='<h3>Additional requirements</h3><div class="note">Record extra requirements/notes for reviewers (shown here and printable). Structured constraints can be wired into generation on request.</div>';
  h+='<div class="controls"><input type="text" id="newrule" placeholder="e.g. Keep Marketing NTA4 at Saba Saba only…" style="min-width:360px"><button class="btn" onclick="addRule()">+ Add requirement</button></div>';
  h+='<div class="wrap"><table><tr><th>#</th><th>Requirement</th><th></th></tr>'+(r.rules.length?r.rules.map((x,i)=>`<tr><td>${i+1}</td><td>${esc(x.text)}</td><td><button class="btn small danger" onclick="delRule(${x._id})">Remove</button></td></tr>`).join(''):'<tr><td colspan="3" class="small">None yet.</td></tr>')+'</table></div>';
  h+='<h3>Built-in rules (always enforced)</h3><ul class="small" style="line-height:1.7">'+BUILTIN_RULES.map(t=>`<li>${esc(t)}</li>`).join('')+'</ul>';
  $('t-rules').innerHTML=h;};
async function generateTT(){
  if(!confirm('Generate a fresh timetable for Semester '+SEM+' from the current data?\n\nThis REPLACES the current Semester '+SEM+' schedule. You can restore the published one later with Sessions → Reset to published.'))return;
  toast('Generating — this may take a moment…');
  let r;try{r=await api(`/${SEM}/generate`,{method:'POST'});}catch(e){alert('Generation failed: '+e.message);return;}
  await loadData();renderNav();R.rules();
  alert('Generated Semester '+SEM+':\n\n• Streams created: '+r.stats.streams+'\n• Sessions placed: '+r.stats.sessions_placed+' of '+r.stats.sessions_needed+'\n• Red-flagged (need attention): '+r.stats.sessions_flagged+'\n\nOpen Timetable, Sessions, Streams and Red-flags to review.');
}
async function saveSettings(){const s={};document.querySelectorAll('[data-set]').forEach(el=>s[el.dataset.set]=el.value);
  await api('/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:s})});toast('Parameters saved');}
async function addRule(){const el=$('newrule');const t=el.value.trim();if(!t)return;
  await api('/rules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});R.rules();}
async function delRule(id){await api('/rules/'+id,{method:'DELETE'});R.rules();}
async function resetSem(){if(!confirm('Discard ALL edits for Semester '+SEM+' and restore the published timetable?'))return;
  await api(`/${SEM}/reset`,{method:'POST'});await loadData();renderNav();R[CUR]();toast('Semester '+SEM+' restored');}
async function autocompleteR1(){
  if(!confirm('Add a second weekly session for every module/stream that currently has only one?\n\nThis writes to the shared timetable (same lecturer, a different day, earliest free daytime slot). Anything that will not fit is left out and listed.'))return;
  toast('Working — placing second sessions…');
  let r; try{r=await api(`/${SEM}/autocomplete_r1`,{method:'POST'});}catch(e){alert('Something went wrong: '+e.message);return;}
  await loadData();renderNav();R[CUR]();
  alert('Auto-complete finished.\n\nAdded: '+r.added+' new sessions.\nCould not place (rooms or lecturer already full): '+r.unresolved+
    (r.unresolved_sample&&r.unresolved_sample.length?'\n\nExamples that need manual attention:\n• '+r.unresolved_sample.join('\n• '):''));}

// init
(async()=>{try{await setSem('II');}catch(e){$('status').textContent='● cannot reach server';document.querySelector('main').innerHTML='<div class="note warn">Could not connect to the server. Make sure the app is running and reload this page.</div>';}})();
