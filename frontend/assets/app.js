'use strict';
/* ================= helpers ================= */
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
const FINE=matchMedia('(pointer:fine)').matches;
const sleep=ms=>new Promise(r=>setTimeout(r,RM?Math.min(ms,50):ms));
const frame=()=>new Promise(r=>requestAnimationFrame(()=>r()));
const el=h=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstElementChild};
const money=n=>'$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const pad2=n=>n<100?String(n).padStart(2,'0'):n.toLocaleString('en-IN');
function rng(seed){let a=seed>>>0;return()=>{a=(a+0x6D2B79F5)|0;let t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296}}
const band=r=>r>=80?'high':r>=55?'med':'low';
const bandName={high:'High',med:'Medium',low:'Low'};
const uncLabel=u=>u<=12?'Low':u<=36?'Medium':'High';
const CHK='<svg viewBox="0 0 12 12" width="11" height="11"><path d="M2.5 6.2l2.4 2.4 4.6-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const WARN='<svg width="18" height="18" viewBox="0 0 18 18"><path d="M9 2.2L16.4 15H1.6L9 2.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 7v4M9 12.8v.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
const ARR='<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 7h10M8 3l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function toast(m){const t=el(`<div class="toast">${m}</div>`);$('#toasts').appendChild(t);setTimeout(()=>{t.style.transition='opacity .3s';t.style.opacity=0;setTimeout(()=>t.remove(),300)},2800)}
function animNum(node,to,fmt=v=>String(v),dur=900){
  if(!node)return;const from=parseFloat(node.dataset.v||0);node.dataset.v=to;
  if(RM||from===to){node.textContent=fmt(to);return}
  const t0=performance.now();(function s(t){const p=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-p,3);node.textContent=fmt(Math.round(from+(to-from)*e));if(p<1)requestAnimationFrame(s)})(t0);
}

/* ================= api and case store ================= */
let TOKEN=localStorage.getItem('argus_token')||'',USER=null,LIST=[],STATS=null,PENDING=null;
const HERO_ID='HHG-001';
const GC={customer:'#3F4FD1',account:'#22307F',tx:'#B87A08',device:'#0F9C96',ip:'#667085',merchant:'#4C7FB8',case:'#D9463F'};
const GL={customer:'Customer',account:'Card',tx:'Transaction',device:'Device',ip:'IP address',merchant:'Product',case:'Case'};
async function api(path,opts={}){
  const r=await fetch('/api'+path,{method:opts.method||'GET',headers:{'Content-Type':'application/json',...(TOKEN?{Authorization:'Bearer '+TOKEN}:{})},body:opts.body!==undefined?JSON.stringify(opts.body):undefined});
  let j={};try{j=await r.json()}catch(e){}
  if(r.status===401&&TOKEN&&!opts.quiet){signOut(true);throw new Error(j.detail||'Please sign in again.')}
  if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:('Request failed ('+r.status+')'));
  return j}
const errToast=e=>toast(String(e&&e.message||e).replace(/[<>]/g,''));
const store=new Map();
function newState(){return{started:false,done:false,stage:'new',risk:0,conf:0,unc:100,suff:0,rec:'Gathering signals',tl:[],act:[],ev:[],fnd:[],prior:[],gap:null,lit:new Set(),depth:1,agentDepth:0,before:null,after:null,addEv:null,outcome:null,action:null,approval:null,adverse:null,needsApproval:false,suffShown:0,_sig:{}}}
function caseObj(id){if(!store.has(id))store.set(id,{id,S:newState(),G:null,poll:null});return store.get(id)}
const hash=s=>{let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return Math.abs(h)};
function keepSeen(next,key,old){const m=new Map(old.map(x=>[x[key],x]));return next.map(x=>({...x,seen:!!(m.get(x[key])&&m.get(x[key]).seen)}))}
function applyDetail(c,d){
  const S=c.S,dt=new Date(d.opened_at);
  Object.assign(c,{amount:d.amount,merchant:d.merchant,pattern:d.pattern,trigger:d.trigger,bm:d.bm,tx:d.tx,account:d.account,status:d.status,resolved:d.stage==='resolved'});
  c.date=dt.toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});c.time=dt.toTimeString().slice(0,5);
  S.stage=d.stage;S.started=d.stage!=='new';S.done=!['new','investigating'].includes(d.stage);
  Object.assign(S,{risk:d.risk,conf:d.conf,unc:d.unc,suff:d.suff,rec:d.rec,gap:d.gap,before:d.before,after:d.after,addEv:d.add_ev,outcome:d.outcome,action:d.action,approval:d.approval,adverse:d.adverse===null?null:!!d.adverse,needsApproval:d.needs_approval,threshold:d.threshold,requests:d.requests});
  S.tl=keepSeen(d.timeline,'seq',S.tl);S.act=keepSeen(d.activity,'seq',S.act);S.ev=keepSeen(d.evidence,'seq',S.ev);
  S.fnd=d.findings;S.prior=d.prior;S.lit=new Set(d.lit);S.autoDepth=d.depth;
  mergeGraph(c,d.graph);
}
function mergeGraph(c,g){
  const old=c.G?c.G.map:{},per={},idx={},nodes=[],map={};
  g.nodes.forEach(n=>per[n.depth]=(per[n.depth]||0)+1);
  g.nodes.forEach(n=>{let o=old[n.id];
    if(!o){idx[n.depth]=(idx[n.depth]||0)+1;const a=(idx[n.depth]/per[n.depth])*Math.PI*2+n.depth*.7+(hash(n.id)%100)/100*.3,R=n.depth*105;
      o={id:n.id,type:n.type,depth:n.depth,risk:n.risk,label:n.label,tx:n.tx,s:n.depth===0?1:0,lit:false,litAt:-1e9,vx:0,vy:0,x:Math.cos(a)*R,y:Math.sin(a)*R}}
    else{o.risk=n.risk;o.label=n.label;o.depth=n.depth;o.tx=n.tx}
    nodes.push(o);map[n.id]=o});
  const edges=g.edges.map(e=>{const ex=c.G&&c.G.edges.find(x=>x.a.id===e.a&&x.b.id===e.b);return ex||{a:map[e.a],b:map[e.b],label:e.label,ph:(hash(e.a+e.b)%100)/100,lit:false,g:0}}).filter(e=>e.a&&e.b);
  c.G={nodes,edges,map};
}

/* ================= graph engine ================= */
const GR={cv:null,ctx:null,c:null,D:1,z:1,px:0,py:0,W:0,H:0,dpr:1,alpha:1,peek:null,sel:null,running:false,drag:null,tw:null,peekT:null,t:0};
const now=()=>performance.now();
function poly(x,y,r,n,rot){const c=GR.ctx;c.beginPath();for(let i=0;i<n;i++){const a=rot+i*2*Math.PI/n;i?c.lineTo(x+r*Math.cos(a),y+r*Math.sin(a)):c.moveTo(x+r*Math.cos(a),y+r*Math.sin(a))}c.closePath()}
function rrect(x,y,w,h,r){const c=GR.ctx;c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath()}
function shape(t,x,y,r){const c=GR.ctx;switch(t){case'account':rrect(x-r,y-r,2*r,2*r,5);break;case'tx':poly(x,y,r*1.15,4,0);break;case'device':poly(x,y,r*1.05,6,0);break;case'ip':poly(x,y,r*1.15,3,-Math.PI/2);break;case'merchant':poly(x,y,r*1.08,5,-Math.PI/2);break;default:c.beginPath();c.arc(x,y,r,0,Math.PI*2)}}
const vis=()=>GR.c.G.nodes.filter(n=>n.depth<=GR.D);
function fitZoom(D){return Math.max(.5,Math.min(1.15,(Math.min(GR.H-150,GR.W)*.6)/(D*105+40)))}
function tween(to,ms=550){const f={z:GR.z,px:GR.px,py:GR.py},t0=now();GR.tw={f,to,t0,ms:RM?1:ms}}
function graphLoad(c){
  GR.c=c;GR.D=c.S.depth;GR.sel=null;GR.peek=null;GR.alpha=1;
  const G=c.G;G.nodes.forEach(n=>{n.lit=c.S.lit.has(n.id);n.litAt=-1e9;n.s=n.depth<=GR.D?1:0});
  G.edges.forEach(e=>{e.lit=e.a.lit&&e.b.lit;e.g=e.lit?1:0});
  GR.z=fitZoom(GR.D);GR.px=0;GR.py=-20;$('#dp').value=GR.D;$('#dpv').textContent=GR.D;$('#ncard').classList.remove('on');
}
function graphSync(){
  if(!GR.c||!GR.c.G)return;
  const c=GR.c,G=c.G,t=now();
  G.nodes.forEach(n=>{const l=c.S.lit.has(n.id);if(l&&!n.lit){n.lit=true;n.litAt=t}});
  G.edges.forEach(e=>{const l=e.a.lit&&e.b.lit;if(l&&!e.lit){e.lit=true;e.g=RM?1:0}});
  GR.alpha=Math.max(GR.alpha,.6);
}
function setDepth(c,d,auto){
  d=Math.max(1,Math.min(4,d));c.S.depth=d;
  if(GR.c===c){GR.D=d;GR.alpha=1;$('#dp').value=d;$('#dpv').textContent=d;const v=vis();
    if(auto)tween({z:fitZoom(d),px:0,py:-20});
    // spawn newly visible nodes next to a visible neighbour
    c.G.nodes.forEach(n=>{if(n.depth<=d&&n.s===0){const e=c.G.edges.find(e=>(e.a===n&&e.b.depth<=d&&e.b.s>0)||(e.b===n&&e.a.depth<=d&&e.a.s>0));const p=e&&(e.a===n?e.b:e.a);if(p){n.x=p.x+(Math.random()-.5)*30;n.y=p.y+(Math.random()-.5)*30}}});}
}
function graphStep(){
  const G=GR.c.G,V=vis(),t=now();
  G.nodes.forEach(n=>{const tg=n.depth<=GR.D?1:0;n.s+=(tg-n.s)*(RM?1:.12);if(Math.abs(tg-n.s)<.01)n.s=tg});
  G.edges.forEach(e=>{if(e.lit&&e.g<1)e.g=Math.min(1,e.g+(RM?1:.03))});
  if(GR.alpha>.02){
    for(let i=0;i<V.length;i++){const a=V[i];
      for(let j=i+1;j<V.length;j++){const b=V[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.5;if(d2>60000)continue;const f=4200/d2,d=Math.sqrt(d2);dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}
      const r=Math.hypot(a.x,a.y)+.01,R=a.depth*105;if(a.depth===0){a.vx-=a.x*.05;a.vy-=a.y*.05}else{const k=(r-R)*.012;a.vx-=a.x/r*k;a.vy-=a.y/r*k}}
    G.edges.forEach(e=>{const a=e.a,b=e.b;if(a.depth>GR.D||b.depth>GR.D)return;const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)+.01,k=(d-92)*.018;a.vx+=dx/d*k;a.vy+=dy/d*k;b.vx-=dx/d*k;b.vy-=dy/d*k});
    V.forEach(n=>{n.vx*=.8;n.vy*=.8;if(!(GR.drag&&GR.drag.node===n)){n.x+=n.vx*GR.alpha;n.y+=n.vy*GR.alpha}});
    GR.alpha*=.985;
  }else if(!RM){V.forEach(n=>{n.x+=Math.sin(t/1700+n.tx)*.06;n.y+=Math.cos(t/1900+n.tx)*.06})}
  if(GR.tw){const p=Math.min(1,(t-GR.tw.t0)/GR.tw.ms),e=1-Math.pow(1-p,3);['z','px','py'].forEach(k=>GR[k]=GR.tw.f[k]+(GR.tw.to[k]-GR.tw.f[k])*e);if(p>=1)GR.tw=null}
}
const sx=n=>GR.W/2+GR.px+n.x*GR.z,sy=n=>GR.H/2+GR.py+n.y*GR.z;
function graphDraw(){
  const ctx=GR.ctx,c=GR.c,G=c.G,t=now();ctx.setTransform(GR.dpr,0,0,GR.dpr,0,0);ctx.clearRect(0,0,GR.W,GR.H);
  ctx.translate(GR.W/2+GR.px,GR.H/2+GR.py);ctx.scale(GR.z,GR.z);
  const foc=GR.sel,dimAll=!!foc;
  G.edges.forEach(e=>{const ea=Math.min(e.a.s,e.b.s);if(ea<.03)return;const hl=foc&&(e.a===foc||e.b===foc);
    ctx.globalAlpha=ea*(e.lit?(dimAll&&!hl?.18:.9):.3);ctx.lineWidth=(hl?2.4:e.lit?1.6:1)/1;ctx.strokeStyle=hl?'#3F4FD1':e.lit?'#8E98D9':'#B9BCC6';
    ctx.setLineDash(e.lit?[]:[4,4]);const g=e.lit?e.g:1,ex=e.a.x+(e.b.x-e.a.x)*g,ey=e.a.y+(e.b.y-e.a.y)*g;ctx.beginPath();ctx.moveTo(e.a.x,e.a.y);ctx.lineTo(ex,ey);ctx.stroke();ctx.setLineDash([]);
    if(e.lit&&e.g>=1&&!RM&&!(dimAll&&!hl)){const hot=e.a.risk==='high'&&e.b.risk==='high';ctx.fillStyle=hot?'#D9463F':'#3F4FD1';for(let k=0;k<3;k++){const p=((t/2200)+e.ph+k/3)%1;ctx.globalAlpha=ea*.9;ctx.beginPath();ctx.arc(e.a.x+(e.b.x-e.a.x)*p,e.a.y+(e.b.y-e.a.y)*p,2.2,0,6.283);ctx.fill()}}
    if(hl&&GR.z>.6){ctx.globalAlpha=ea;ctx.fillStyle='#3F4FD1';ctx.font='600 10px "Instrument Sans",system-ui,sans-serif';ctx.textAlign='center';ctx.fillText(e.label,(e.a.x+e.b.x)/2,(e.a.y+e.b.y)/2-5)}});
  const nb=new Set();if(foc)G.edges.forEach(e=>{if(e.a===foc)nb.add(e.b);if(e.b===foc)nb.add(e.a)});
  G.nodes.forEach(n=>{if(n.s<.03)return;const col=GC[n.type],hov=GR.peek===n,r=15*n.s*(hov?1.14:1),dim=dimAll&&n!==foc&&!nb.has(n);
    ctx.globalAlpha=n.s*(n.lit?(dim?.28:1):.4);
    const age=t-n.litAt;if(age<1400&&!RM){const p=age/1400;ctx.globalAlpha=(1-p)*.55;ctx.strokeStyle=col;ctx.lineWidth=2;ctx.beginPath();ctx.arc(n.x,n.y,r+4+p*30,0,6.283);ctx.stroke();ctx.globalAlpha=n.s*(dim?.28:1)}
    ctx.save();ctx.shadowColor='rgba(29,34,48,.18)';ctx.shadowBlur=hov?14:6;ctx.shadowOffsetY=2;ctx.fillStyle='#fff';shape(n.type,n.x,n.y,r);ctx.fill();ctx.restore();
    ctx.fillStyle=col+(n.lit?'26':'10');shape(n.type,n.x,n.y,r);ctx.fill();ctx.strokeStyle=col;ctx.lineWidth=n.type==='case'?3:2.2;if(!n.lit)ctx.setLineDash([3,3]);shape(n.type,n.x,n.y,r);ctx.stroke();ctx.setLineDash([]);
    if(n.type==='case'){ctx.lineWidth=1;shape(n.type,n.x,n.y,r*.55);ctx.stroke()}
    if(n.lit&&n.risk==='high'){ctx.strokeStyle='#D9463F';ctx.globalAlpha*=.55;ctx.lineWidth=1.4;ctx.beginPath();ctx.arc(n.x,n.y,r+6,0,6.283);ctx.stroke();ctx.globalAlpha=n.s*(dim?.28:1)}
    if(n===GR.sel){ctx.strokeStyle='#3F4FD1';ctx.lineWidth=2;ctx.beginPath();ctx.arc(n.x,n.y,r+9,0,6.283);ctx.stroke()}
    if(GR.z>.62||hov||n===GR.sel){ctx.fillStyle='#1D2230';ctx.font='500 11px "Instrument Sans",system-ui,sans-serif';ctx.textAlign='center';ctx.fillText(n.label.length>16?n.label.slice(0,15)+'\u2026':n.label,n.x,n.y+r+15)}});
  ctx.globalAlpha=1;
}
function nodeAt(mx,my){const V=vis().filter(n=>n.s>.5);let best=null,bd=1e9;V.forEach(n=>{const d=Math.hypot(sx(n)-mx,sy(n)-my);if(d<(17*GR.z+6)&&d<bd){bd=d;best=n}});return best}
function nodeInfo(n){const G=GR.c.G,nb=G.edges.filter(e=>e.a===n||e.b===n).map(e=>e.a===n?e.b:e.a);
  const acc=nb.filter(x=>x.type==='account').length;return{lbl:n.type==='device'?'Linked accounts':'Linked entities',v:n.type==='device'?acc:nb.length,tx:n.type==='tx'||n.type==='case'?(n.type==='tx'?1:'\u2014'):n.tx,risk:n.risk==='high'?'HIGH':n.risk==='med'?'MEDIUM':'LOW'}}
function cardUpdate(){
  const n=GR.peek||GR.sel,card=$('#ncard');
  if(!n||n.s<.5){card.classList.remove('on');return}
  if(card.dataset.n!==n.id){const i=nodeInfo(n);card.dataset.n=n.id;
    card.innerHTML=`<small>${GL[n.type]}</small><strong>${n.label}</strong><dl><dt>${i.lbl}</dt><dd>${i.v}</dd><dt>Transactions</dt><dd>${i.tx}</dd><dt>Risk associations</dt><dd style="color:${i.risk==='HIGH'?'var(--red)':i.risk==='MEDIUM'?'var(--amber)':'var(--green)'}">${n.lit?i.risk:'Not yet assessed'}</dd></dl><button class="btn primary sm" id="invBtn">Investigate</button>`;
    $('#invBtn').onclick=()=>investigateNode(n)}
  const w=GR.W,x=Math.min(w-226,Math.max(8,sx(n)+22)),y=Math.min(GR.H-260,Math.max(50,sy(n)-30));
  card.style.transform=`translate(${x}px,${y}px)`;card.classList.add('on');
}
function investigateNode(n){
  const c=GR.c;GR.sel=n;if(n.depth>=GR.D&&n.depth<4)setDepth(c,n.depth+1,false);
  c.S.lit.add(n.id);graphSync();tween({z:Math.max(GR.z,1.1),px:-n.x*Math.max(GR.z,1.1),py:-n.y*Math.max(GR.z,1.1)});
  logAct(c,`Analyst expanded ${GL[n.type].toLowerCase()} ${n.label}`);
}
function focusNode(n){GR.sel=n;const z=Math.max(GR.z,1.1);tween({z,px:-n.x*z,py:-n.y*z})}
function graphLoop(){if(!GR.running)return;if(GR.c&&GR.c.G&&GR.c===cur){graphStep();graphDraw();cardUpdate()}else if(GR.ctx&&GR.W)GR.ctx.clearRect(0,0,GR.W,GR.H);requestAnimationFrame(graphLoop)}
function graphResize(){const r=$('#gcard').getBoundingClientRect();if(!r.width)return;GR.dpr=Math.min(2,devicePixelRatio||1);GR.W=r.width;GR.H=r.height;GR.cv.width=r.width*GR.dpr;GR.cv.height=r.height*GR.dpr}
function graphInit(){
  GR.cv=$('#gcv');GR.ctx=GR.cv.getContext('2d');new ResizeObserver(()=>{graphResize();if(GR.c)GR.z=Math.min(GR.z,fitZoom(GR.D)+.4)}).observe($('#gcard'));
  $('#legend').innerHTML=Object.keys(GL).map(k=>`<span><i style="background:${GC[k]}"></i>${GL[k]}</span>`).join('');
  const cv=GR.cv,pos=e=>{const r=cv.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top]};
  const setPeek=n=>{if(n){clearTimeout(GR.peekT);GR.peek=n}else{clearTimeout(GR.peekT);GR.peekT=setTimeout(()=>GR.peek=null,320)}};
  $('#ncard').addEventListener('pointerenter',()=>clearTimeout(GR.peekT));$('#ncard').addEventListener('pointerleave',()=>setPeek(null));
  cv.addEventListener('pointerdown',e=>{const[x,y]=pos(e),n=nodeAt(x,y);GR.drag={x,y,px:GR.px,py:GR.py,moved:false,node:null,hit:n};cv.setPointerCapture(e.pointerId);document.body.dataset.g=n?'node':'grabbing'});
  cv.addEventListener('pointermove',e=>{const[x,y]=pos(e);
    if(GR.drag&&!GR.drag.hit){const dx=x-GR.drag.x,dy=y-GR.drag.y;if(Math.abs(dx)+Math.abs(dy)>3)GR.drag.moved=true;GR.px=GR.drag.px+dx;GR.py=GR.drag.py+dy;GR.tw=null;return}
    const n=nodeAt(x,y);setPeek(n);document.body.dataset.g=n?'node':'grab';cv.style.cursor=FINE?'':n?'pointer':'grab'});
  cv.addEventListener('pointerup',e=>{const d=GR.drag;GR.drag=null;const[x,y]=pos(e),n=nodeAt(x,y);
    if(d&&d.hit&&n===d.hit){GR.sel=GR.sel===n?null:n;setPeek(n)}else if(d&&!d.moved&&!n){GR.sel=null}
    document.body.dataset.g=n?'node':'grab'});
  cv.addEventListener('pointerleave',()=>{setPeek(null);delete document.body.dataset.g});
  cv.addEventListener('wheel',e=>{e.preventDefault();GR.tw=null;GR.z=Math.max(.45,Math.min(2.4,GR.z*(e.deltaY<0?1.1:.91)))},{passive:false});
  $('#zi').onclick=()=>tween({z:Math.min(2.4,GR.z*1.25),px:GR.px*1.25,py:GR.py*1.25},300);
  $('#zo').onclick=()=>tween({z:Math.max(.45,GR.z*.8),px:GR.px*.8,py:GR.py*.8},300);
  $('#zr').onclick=()=>{GR.sel=null;tween({z:fitZoom(GR.D),px:0,py:-20})};
  $('#dp').addEventListener('input',e=>{const v=+e.target.value;setDepth(GR.c,v,true);const c=GR.c;logAct(c,`Analyst set relationship depth to ${v}`)});
}
function discovery(title,text){const g=$('#gnote');g.innerHTML=`<b>${title}</b>${text}`;g.classList.add('on');clearTimeout(discovery.t);discovery.t=setTimeout(()=>g.classList.remove('on'),5200)}


/* ================= case workflow (driven by the server) ================= */
const needsApproval=rec=>rec==='Escalate to analyst';
const recSet=rec=>rec==='Request customer validation'||rec==='Request additional evidence'?['Request evidence']:rec==='Escalate to analyst'?['Escalate to analyst','Block transaction','Create case']:rec==='Monitor account'?['Monitor account','Warn customer']:['Allow transaction','Monitor account'];
const ui=(c,fn)=>{if(cur===c&&view==='case')fn()};
const needPoll=S=>['new','investigating','awaiting','closing'].includes(S.stage);
function logAct(c,text){
  api(`/cases/${c.id}/activity`,{method:'POST',body:{text}}).catch(()=>{});
  const t=new Date().toTimeString().slice(0,8);c.S.act.push({seq:9999+c.S.act.length,t:text,time:t,seen:false});
  ui(c,()=>{c.S._sig.act=null;renderAct(c)})}
function stopPolling(c){if(c&&c.poll){clearInterval(c.poll);c.poll=null}}
function startPolling(c){stopPolling(c);if(!needPoll(c.S))return;c.poll=setInterval(()=>pollTick(c),900)}
async function pollTick(c){
  if(cur!==c||view!=='case'){stopPolling(c);return}
  if(c.busy)return;c.busy=true;
  try{const d=await api('/cases/'+c.id);const prev=c.S.stage;applyDetail(c,d);if(cur===c&&view==='case')onDetail(c,prev)}catch(e){}finally{c.busy=false}}
async function refreshNow(c){const d=await api('/cases/'+c.id);const prev=c.S.stage;applyDetail(c,d);ui(c,()=>onDetail(c,prev));startPolling(c)}
function onDetail(c,prev){
  const S=c.S;
  S.tl.filter(t=>!t.seen&&t.st==='done').forEach(t=>{
    if(t.t==='Graph relationships discovered')discovery('Device relationship',t.d);
    if(t.t==='Prior case retrieved')discovery('Prior case retrieved',t.d)});
  if(S.autoDepth>S.agentDepth){S.agentDepth=S.autoDepth;if(S.depth<S.autoDepth)setDepth(c,S.autoDepth,true)}
  if(prev==='awaiting'&&S.stage!=='awaiting'){dockTab('de');if($('#modal.on [data-wait]'))flyEvidence('Evidence received')}
  paintAll(c);
  if(prev==='closing'&&S.stage==='resolved')showResolved(c);
  if(!needPoll(S))stopPolling(c);
}
function paintLive(c){const S=c.S,l=$('#live'),m={new:['Working',1],investigating:['Working',1],awaiting:['Awaiting evidence',1],closing:['Closing case',1],resolved:['Resolved',0],gap:['Waiting on you',0],ready:['Waiting on you',0]}[S.stage]||['Ready',0];
  l.className='live'+(m[1]?'':' idle');l.textContent=m[0]}
function paintAll(c){
  const S=c.S,sg=S._sig||(S._sig={}),chk=(k,v,fn)=>{if(sg[k]!==v){sg[k]=v;fn()}};
  chk('tl',S.tl.map(t=>t.seq+t.st).join('|'),()=>renderTL(c));
  chk('act',S.act.length+'|'+(S.act[S.act.length-1]||{}).t,()=>renderAct(c));
  chk('fnd',S.fnd.join('|'),()=>renderFnd(c));
  chk('gap',[S.stage,S.gap,S.addEv].join('|'),()=>renderGap(c));
  chk('slot',[S.stage,S.suff,S.rec,S.approval,S.outcome,S.conf,S.adverse].join('|'),()=>renderSlot(c));
  chk('dock',[S.ev.length,S.prior.map(p=>p.id).join(),S.rec,S.stage,S.before&&S.before.risk,S.after&&S.after.risk,S.fnd.length].join('|'),()=>renderDock(c));
  paintMeters(c);paintLive(c);graphSync();
}
/* evidence requests */
function openEvidenceModal(c){
  const opts=[['customer','Customer validation','Ask the customer to confirm the payment','33% \u2192 8%'],['step_up','Step-up authentication','Challenge the customer to verify identity','33% \u2192 15%'],['analyst','Analyst information request','Ask the analyst desk to check the device network','33% \u2192 20%']];
  const used=new Set((c.S.requests||[]).map(r=>r.type));
  modal(`<h3>Request additional evidence</h3><p class="mute">${c.S.gap||'More evidence is needed.'}</p>
  <small style="display:block;margin-top:14px">Recommended evidence</small>
  ${opts.map((o,i)=>`<label class="opt"><input type="radio" name="ev" value="${o[0]}" data-imp="${o[3]}" ${used.has(o[0])?'disabled':''}><span><b>${o[1]}</b><small>${used.has(o[0])?'Already requested for this case':o[2]}</small></span></label>`).join('')}
  <div class="impact"><span>Estimated impact on uncertainty</span><b id="imp">\u2014</b></div>
  <div class="row"><button class="btn" data-x="cancel">Cancel</button><button class="btn primary mag" data-x="go">Request evidence</button></div>`);
  const first=$$('#modal input[name=ev]').find(i=>!i.disabled);if(first){first.checked=true;$('#imp').textContent=first.dataset.imp}
  $$('#modal input[name=ev]').forEach(i=>i.onchange=()=>$('#imp').textContent=i.dataset.imp);
  $('#modal [data-x=cancel]').onclick=closeModal;
  $('#modal [data-x=go]').onclick=()=>{const v=$('#modal input[name=ev]:checked');if(!v){toast('Every evidence type has been requested.');return}closeModal();runEvidence(c,v.value)};
}
async function runEvidence(c,type){
  let r;try{r=await api(`/cases/${c.id}/evidence-requests`,{method:'POST',body:{type}})}catch(e){errToast(e);return}
  try{await refreshNow(c)}catch(e){}
  const answer=async ok=>{$$('#modal button').forEach(b=>b.disabled=true);try{await api(`/evidence-requests/${r.id}/respond`,{method:'POST',body:{authorized:ok}})}catch(e){errToast(e);closeModal();return}
    await flyEvidence('Evidence received');try{await refreshNow(c);dockTab('de')}catch(e){}};
  if(type==='customer'){
    modal(`<div class="phone" data-wait="${r.id}"><small>Transaction validation</small><h3 style="margin-top:6px">Did you authorize this transaction?</h3><div class="amt">${money(c.amount)}</div>
    <dl><dt>Merchant</dt><dd>${c.merchant}</dd><dt>Date</dt><dd>${c.date}</dd><dt>Time</dt><dd>${c.time}</dd></dl>
    <div class="row"><button class="btn primary mag" data-a="y">Yes, I authorized</button><button class="btn danger mag" data-a="n">No, I did not</button></div>
    <p class="mute" style="font-size:12px;margin-top:14px">This is what the customer sees. They can also answer from their own device: <a href="${r.link}" target="_blank" rel="noopener">open the customer link</a>.</p></div>`);
    $('#modal [data-a=y]').onclick=()=>answer(true);$('#modal [data-a=n]').onclick=()=>answer(false);
  }else if(type==='step_up'){
    modal(`<div class="phone" data-wait="${r.id}"><small>Step-up authentication</small><h3 style="margin-top:6px">Verify your identity</h3><p class="mute" style="margin-top:8px">A challenge was sent to the registered device.</p>
    <div class="row" style="margin-top:20px"><button class="btn primary mag" data-a="y">Verification passed</button><button class="btn mag" data-a="n">Verification failed</button></div>
    <p class="mute" style="font-size:12px;margin-top:14px">Or <a href="${r.link}" target="_blank" rel="noopener">open the customer link</a> to answer from another device.</p></div>`);
    $('#modal [data-a=y]').onclick=()=>answer(true);$('#modal [data-a=n]').onclick=()=>answer(false);
  }else{
    modal(`<div class="phone" data-wait="${r.id}"><small>Analyst information request</small><h3 style="margin-top:6px">Waiting for the analyst desk</h3><div style="display:flex;justify-content:center;margin:22px"><div class="spin"></div></div><p class="mute">The desk is checking the device network for this case.</p></div>`);
  }
}
async function flyEvidence(label){
  const dlg=$('#modal .dlg'),from=dlg?dlg.getBoundingClientRect():{left:innerWidth/2-60,top:innerHeight/2,width:120,height:0};closeModal();
  if(RM)return;const f=el(`<div class="flyer">${label}</div>`);f.style.left=(from.left+from.width/2-60)+'px';f.style.top=(from.top+from.height/2)+'px';document.body.appendChild(f);
  await frame();const to=$('#dock').getBoundingClientRect();f.style.transform=`translate(${to.left+to.width/2-(from.left+from.width/2)}px,${Math.min(innerHeight-80,to.top)-(from.top+from.height/2)}px) scale(.8)`;f.style.opacity='.2';await sleep(820);f.remove();
}
/* approval and closing */
function openApproval(c){
  const S=c.S,can=USER&&['approver','admin'].includes(USER.role),act=S.rec==='Escalate to analyst'?'Escalate to fraud analyst and hold the transaction':S.rec;
  modal(`<small>Approval required</small><h3 style="margin-top:4px">${act}</h3>
  <div class="impact" style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div><small>Risk</small><br><b>${S.risk}</b></div><div><small>Evidence</small><br><b>${S.ev.length} signals</b></div><div><small>Confidence</small><br><b>${S.conf}%</b></div><div><small>Policy</small><br><b style="font-size:14px">Human approval required (\u00A76.1)</b></div></div>
  ${can?'':`<p class="mute" style="margin-bottom:8px">You are signed in as ${USER?USER.role:'a guest'}. Approving needs the approver or admin role.</p>`}
  <div class="row" style="justify-content:space-between"><button class="btn ghost" data-x="more">Request more evidence</button><span style="display:flex;gap:10px"><button class="btn" data-x="rej" ${can?'':'disabled'}>Reject</button><button class="btn primary mag" data-x="ok" ${can?'':'disabled'}>Approve action ${ARR}</button></span></div>`);
  const send=async decision=>{try{const d=await api(`/cases/${c.id}/approval`,{method:'POST',body:{decision}});return d}catch(e){errToast(e);return null}};
  $('#modal [data-x=ok]').onclick=async()=>{const d=await send('approve');if(!d)return;closeModal();await refreshNow(c)};
  $('#modal [data-x=rej]').onclick=async()=>{const d=await send('reject');if(!d)return;closeModal();toast('Action rejected. The recommendation stays open.');await refreshNow(c)};
  $('#modal [data-x=more]').onclick=async()=>{const d=await send('more_evidence');if(!d)return;closeModal();await refreshNow(c);setTimeout(()=>openEvidenceModal(c),300)};
}
async function applyAction(c){try{await api(`/cases/${c.id}/apply`,{method:'POST'});await refreshNow(c)}catch(e){errToast(e)}}
async function showResolved(c){
  let n='';try{const s=await api('/stats');STATS=s;n=s.resolved.toLocaleString('en-IN')}catch(e){}
  $('#bellN').textContent=STATS?STATS.approval:0;
  modal(`<div class="resolved"><div class="big">${CHK.replace(/11/g,'30')}</div><small>Case resolved</small><h3 style="margin:4px 0 8px">${c.id}</h3><p class="mute">The record is in case memory${n?', which now holds '+n+' investigations':''}.</p><div class="row" style="justify-content:center"><button class="btn" data-x="rep">View case report</button><button class="btn primary mag" data-x="next">Open another case ${ARR}</button></div></div>`);
  $('#modal [data-x=rep]').onclick=()=>{closeModal();go('report',c)};
  $('#modal [data-x=next]').onclick=async()=>{closeModal();try{const l=await api('/cases');const n=l.filter(x=>x.stage!=='resolved').sort((a,b)=>b.risk-a.risk)[0];if(n)openCase(n.id);else go('center')}catch(e){go('center')}};
}

/* ================= renderers: workspace ================= */
function paintStatus(c){const s=$('#hStat'),m={Investigating:'',New:'',Resolved:'green','Awaiting evidence':'amber','Approval pending':'teal'};s.className='chip '+(m[c.status]||'');s.textContent=c.status}
function paintMeters(c){const S=c.S;
  animNum($('#hRisk'),S.risk);animNum($('#hConf'),S.conf,v=>v+'%');animNum($('#aRisk'),S.risk);animNum($('#aUnc'),S.unc,v=>v+'%');animNum($('#rconf'),S.conf,v=>v+'%');
  $('#hUnc').textContent=S.started?uncLabel(S.unc):'High';$('#rfg').style.strokeDashoffset=326.7*(1-S.conf/100);$('#uMark').style.left=S.unc+'%';$('#aRec').textContent=S.rec;
  const col=band(S.risk);$('#hRisk').style.color=col==='high'?'var(--red)':col==='med'?'var(--amber)':'var(--green)';paintStatus(c)}
function renderTL(c){const S=c.S;$('#tl').innerHTML=S.tl.map(t=>`<li class="tli ${t.st}${t.seen?'':' fresh'}"><span class="dot">${t.st==='done'?CHK:''}</span><div><b>${t.t}</b><small>${t.d||''}</small></div><time>${t.time||''}</time></li>`).join('');S.tl.forEach(t=>t.seen=true)}
function renderAct(c){const S=c.S;$('#act').innerHTML=S.act.map(a=>`<li class="${a.seen?'':'fresh'}"><time>${a.time}</time><span>${a.t}</span></li>`).join('');S.act.forEach(a=>a.seen=true);const u=$('#act');u.scrollTop=u.scrollHeight}
function renderFnd(c){const S=c.S;$('#fnd').innerHTML=S.fnd.length?S.fnd.map(f=>`<li class="${S.fseen&&S.fseen.includes(f)?'':'fresh'}">${CHK}${f}</li>`).join(''):'<li class="mute">No findings yet</li>';S.fseen=S.fnd.slice()}
function renderGap(c){const S=c.S,w=$('#gapWrap');
  if(S.gap)w.innerHTML=`<div class="gapbox">${WARN}<div><b>Evidence gap</b><br>${S.gap}</div></div>`;
  else if(S.done)w.innerHTML=`<div class="gapbox ok">${CHK.replace(/11/g,'16')}<div><b>Evidence sufficient</b><br>${S.addEv?'The requested evidence closed the gap.':'The evidence meets the threshold.'}</div></div>`;
  else w.innerHTML=''}
function renderSlot(c){const S=c.S,sl=$('#slot');
  const suff=`<div class="suff"><small>Evidence sufficiency</small><div class="big"><b id="sfN" data-v="${S.suffShown}">${S.suffShown}</b><span>%</span></div><div class="bar"><u id="sfB" style="width:${S.suffShown}%"></u><s style="left:85%"></s></div></div>`;
  if(!S.done&&(S.stage==='investigating'||S.stage==='new')){sl.innerHTML=`<small>Evaluating evidence sufficiency</small><div class="skel"></div><div class="skel" style="width:70%"></div>`;return}
  if(S.stage==='gap'){sl.innerHTML=suff+`<div class="warn">${WARN}<span>Additional evidence required</span></div><button class="btn primary mag" id="reqEv" style="width:100%">Request additional evidence</button>`;$('#reqEv').onclick=()=>openEvidenceModal(c)}
  else if(S.stage==='awaiting'){sl.innerHTML=suff+`<div class="warn" style="color:var(--slate)"><span class="spin"></span><span>Waiting for evidence to return</span></div>`}
  else if(S.stage==='ready'||S.stage==='closing'||S.stage==='resolved'){
    const adv=S.adverse,why=S.addEv?(adv?['Customer denied the transaction','Connected device network','Historical case similarity','Policy requirement']:['Customer confirmed authorization','Device network remains a watch item','Policy allows release with monitoring']):['Anomalous transaction','Connected device network','Historical case similarity','Policy requirement'],ap=needsApproval(S.rec);
    const title=S.rec==='Escalate to analyst'?'Escalate to fraud analyst':S.rec;
    const btn=S.stage==='ready'?(ap?`<button class="btn" id="revEv">Review evidence</button><button class="btn primary mag" id="reqAp">Request approval</button>`:`<button class="btn" id="revEv">Review evidence</button><button class="btn primary mag" id="apply">Apply action</button>`):S.stage==='closing'?`<span class="spin"></span>`:`<button class="btn" id="viewRep">View case report</button>`;
    sl.innerHTML=(S.stage==='resolved'?`<div class="gapbox ok" style="margin:0 0 12px">${CHK.replace(/11/g,'16')}<div><b>Case resolved</b><br>${S.outcome}. Stored in case memory.</div></div>`:'')+
    `<div class="nba"><small>Next best action</small><h3>${title}</h3><small style="margin-bottom:4px">Why</small><ul>${why.map(w=>`<li>${CHK}${w}</li>`).join('')}</ul><div class="meta"><div><small>Confidence</small><b>${S.conf}%</b></div><div><small>Approval</small><b>${ap?'Required':'Not required'}</b></div></div><div class="btns">${btn}</div></div>`;
    if($('#revEv'))$('#revEv').onclick=()=>{dockTab('ev');$('#dock').scrollIntoView({behavior:RM?'auto':'smooth',block:'center'})};
    if($('#reqAp'))$('#reqAp').onclick=()=>openApproval(c);
    if($('#apply'))$('#apply').onclick=()=>applyAction(c);
    if($('#viewRep'))$('#viewRep').onclick=()=>go('report',c)}
  const nb=$('#sfB'),nn=$('#sfN');if(nb){requestAnimationFrame(()=>{nb.style.width=S.suff+'%'});animNum(nn,S.suff);S.suffShown=S.suff}
}
let dtab='ev';
function dockTab(t){dtab=t;$$('#dtabs button[data-t]').forEach(b=>b.classList.toggle('on',b.dataset.t===t));renderDock(cur)}
function renderDock(c){if(!c)return;const S=c.S,b=$('#dbody');let h='';
  if(dtab==='ev'){h=S.ev.length?`<div class="egrid">${S.ev.map(e=>`<div class="ecard ${e.tone||''} ${e.seen?'':'fresh'}"><b>${e.k}</b><p>${e.v}</p><small>Source: ${e.src}</small></div>`).join('')}</div>`:'<p class="mute">The agent has not collected evidence yet.</p>';S.ev.forEach(e=>e.seen=true)}
  if(dtab==='fi'){h=`<div class="egrid"><div class="ecard teal"><b>Fraud pattern</b><p>${c.pattern}</p><small>Matched against typology library</small></div>${S.fnd.map(f=>`<div class="ecard"><b>Finding</b><p>${f}</p></div>`).join('')}</div>`}
  if(dtab==='pc'){const p=S.prior;h=p.length?p.map(m=>`<div class="pc"><span class="sim">${m.sim}%</span><span><b>${m.id}</b>${m.fresh?' <span class="bm">Added this session</span>':''}<small>${m.pat} \u00B7 ${m.date} \u00B7 ${m.why||''}</small></span><span class="chip ${m.out==='Cleared'?'green':'red'}">${m.out}</span><button class="btn sm" data-h="${m.id}">Show in graph</button></div>`).join(''):'<p class="mute">No similar resolved cases yet.</p>';}
  if(dtab==='po'){const pe=S.ev.find(e=>e.k==='Policy requirement');h=pe?`<div class="pol"><b>${pe.k}</b><p style="margin:6px 0">${pe.v}</p><small>Source: ${pe.src}</small></div><div style="margin-top:12px"><button class="btn sm" id="opPol">Open policy viewer ${ARR}</button></div>`:'<p class="mute">The agent has not retrieved policy evidence yet.</p>'}
  if(dtab==='de'){const a=S.after,b=S.before;
    h=(a&&b?`<div class="evo"><div><small>Before evidence</small><dl><dt>Risk</dt><dd>${b.risk}</dd><dt>Confidence</dt><dd>${b.conf}%</dd><dt>Recommendation</dt><dd style="font-size:15px">${b.rec}</dd></dl></div><div class="arr">${ARR.replace(/14/g,'26')}</div><div class="after"><small>After evidence</small><dl><dt>Risk</dt><dd>${a.risk} <span class="${a.risk>=b.risk?'up':'dn'}">${a.risk>=b.risk?'\u2191':'\u2193'}</span></dd><dt>Confidence</dt><dd>${a.conf}% <span class="dn">\u2191</span></dd><dt>Recommendation</dt><dd style="font-size:15px">${a.rec}</dd></dl></div></div>`:`<p class="mute">The recommendation is <b>${S.rec}</b>. When new evidence arrives, this panel shows how risk, confidence and the recommendation change.</p>`)+
    `<div class="acts">${['Allow transaction','Block transaction','Monitor account','Warn customer','Create case','File report','Request evidence','Escalate to analyst'].map(x=>`<span class="${recSet(S.rec).includes(x)?'rec':''}">${x}</span>`).join('')}</div>`}
  b.innerHTML=h;
  $$('[data-h]',b).forEach(x=>x.onclick=()=>{const m=S.prior.find(z=>z.id===x.dataset.h);showHistory(c,m)});
  if($('#opPol'))$('#opPol').onclick=()=>go('policy',c)}

/* ================= pages ================= */
const F={risk:0,status:'',trigger:'',pattern:'',suff:'',hours:9999};
const STAT=['New','Investigating','Awaiting evidence','Approval pending'];
function chipCls(s){return{'Awaiting evidence':'amber','Approval pending':'teal',Resolved:'green',New:'grey'}[s]||''}
async function renderCenter(){
  const root=$('#v-center');
  if(!LIST.length)root.innerHTML='<div class="skel" style="height:120px"></div><div class="skel" style="height:220px"></div>';
  try{[LIST,STATS]=await Promise.all([api('/cases'),api('/stats')])}catch(e){errToast(e);return}
  $('#bellN').textContent=STATS.approval;
  const act=LIST,maxH=Math.max(72,...act.map(c=>c.hours));if(F.hours===9999)F.hours=maxH;
  const pt=n=>{const r=rng(n);let y=20,p=[];for(let i=0;i<8;i++){y=Math.max(4,Math.min(26,y+(r()-.45)*10));p.push(`${i?'L':'M'}${i*11} ${30-y}`)}return p.join(' ')};
  const M=[['Active investigations',STATS.active,'Open cases in the queue','var(--indigo)'],['High risk',STATS.high,'Requires attention','var(--red)'],['Awaiting evidence',STATS.awaiting,'Customer or analyst pending','var(--amber)'],['Approval queue',STATS.approval,'Human approval needed','var(--teal)'],['Resolved',STATS.resolved,'Recorded in case memory','var(--green)']];
  const uniq=k=>[...new Set(act.map(c=>c[k]))].sort();
  const opt=(arr,all)=>`<option value="">${all}</option>`+arr.map(a=>`<option>${a}</option>`).join('');
  root.innerHTML=`<div class="vh"><div><h2>Investigation center</h2><p>Every open case, ranked by risk. Open one to watch the agent investigate.</p></div></div>
  <div class="metrics">${M.map((m,i)=>`<div class="card metric" style="--mc:${m[3]}"><div class="k">${m[0]}</div><div class="num" data-count="${m[1]}">0</div><div class="sub">${m[2]}</div><svg viewBox="0 0 77 30" aria-hidden="true"><path d="${pt(i+3)}" pathLength="1"/></svg></div>`).join('')}</div>
  <div class="card rd"><div class="rd-h"><b>Risk distribution</b><span id="rdv">Risk \u2265 0</span></div><div class="hist" id="hist"></div><input type="range" id="rmin" min="0" max="100" value="${F.risk}" aria-label="Minimum risk"><div class="scale"><span>Low</span><span>Medium</span><span>High</span></div></div>
  <div class="filters">
   <div class="sel"><select id="fS" aria-label="Status">${opt(STAT,'Status: any')}</select></div>
   <div class="sel"><select id="fT" aria-label="Trigger">${opt(uniq('trigger'),'Trigger: any')}</select></div>
   <div class="sel"><select id="fP" aria-label="Fraud pattern">${opt(uniq('pattern'),'Fraud pattern: any')}</select></div>
   <div class="sel"><select id="fE" aria-label="Evidence sufficiency"><option value="">Evidence: any</option><option value="low">Below threshold</option><option value="ok">Meets threshold</option></select></div>
   <div class="range"><span id="fHv">Opened in last ${F.hours}h</span><input type="range" class="plain" id="fH" min="6" max="${maxH}" step="1" value="${F.hours}" aria-label="Opened within hours"></div>
   <span class="count" id="cnt"></span></div>
  <div class="cgrid" id="cgrid"></div>`;
  $('#fS').value=F.status;$('#fT').value=F.trigger;$('#fP').value=F.pattern;$('#fE').value=F.suff;
  $$('.metric .num').forEach(n=>animNum(n,+n.dataset.count,pad2,1100));
  const upd=()=>{F.risk=+$('#rmin').value;F.status=$('#fS').value;F.trigger=$('#fT').value;F.pattern=$('#fP').value;F.suff=$('#fE').value;F.hours=+$('#fH').value;$('#rdv').textContent='Risk \u2265 '+F.risk;$('#fHv').textContent=`Opened in last ${F.hours}h`;paintGrid()};
  ['rmin','fS','fT','fP','fE','fH'].forEach(i=>$('#'+i).addEventListener('input',upd));
  $('#rdv').textContent='Risk \u2265 '+F.risk;paintGrid(true);
}
function paintGrid(first){
  const act=LIST,b=Array(10).fill(0);act.forEach(c=>b[Math.min(9,Math.floor(c.risk/10))]++);const mx=Math.max(...b,1);
  $('#hist').innerHTML=b.map((n,i)=>{const col=i>=8?'#E8A7A2':i>=5?'#EBCB83':'#A8D8C1';return`<div style="height:${Math.max(6,n/mx*100)}%;background:${col};opacity:${(i+1)*10>F.risk?1:.3}"><span>${n||''}</span></div>`}).join('');
  const list=act.filter(c=>c.risk>=F.risk&&(!F.status||c.status===F.status)&&(!F.trigger||c.trigger===F.trigger)&&(!F.pattern||c.pattern===F.pattern)&&(!F.suff||(F.suff==='low'?c.evidence<STATS_THRESHOLD:c.evidence>=STATS_THRESHOLD))&&c.hours<=F.hours).sort((a,b)=>b.risk-a.risk);
  $('#cnt').textContent=`${list.length} of ${act.length} cases`;
  $('#cgrid').innerHTML=list.length?list.map((c,i)=>{const bd=band(c.risk);return`<article class="ccard ${bd}" tabindex="0" role="button" data-id="${c.id}" aria-label="Open case ${c.id}" style="animation-delay:${first?Math.min(i,10)*40:0}ms">
   <div class="cc-top"><b>${c.id}</b><span class="gauge"><svg viewBox="0 0 44 44"><circle class="bg" cx="22" cy="22" r="17"/><circle class="fg" cx="22" cy="22" r="17" style="stroke-dashoffset:106.8" data-r="${c.risk}"/></svg><span>${c.risk}</span></span></div>
   <div class="cc-tag">${bandName[bd]} risk</div><p>${c.trigger}</p>
   <div class="ev"><span>Evidence</span><i><u data-w="${c.evidence}"></u></i><em>${c.evidence}%</em></div>
   <div class="cc-foot"><span class="chip ${chipCls(c.status)}">${c.status}</span>${c.bm?`<span class="bm">Benchmark ${String(c.bm).padStart(2,'0')}</span>`:''}<span class="open">Open case</span></div></article>`}).join(''):`<div class="empty"><p>No cases match these filters.</p><button class="btn sm" id="rst" style="margin-top:12px">Reset filters</button></div>`;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{$$('.gauge .fg').forEach(g=>g.style.strokeDashoffset=106.8*(1-g.dataset.r/100));$$('.ev u').forEach(u=>u.style.width=u.dataset.w+'%')}));
  $$('.ccard').forEach(a=>{a.onclick=()=>openCase(a.dataset.id,a);a.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openCase(a.dataset.id,a)}}});
  if($('#rst'))$('#rst').onclick=()=>{Object.assign(F,{risk:0,status:'',trigger:'',pattern:'',suff:'',hours:9999});renderCenter()};
}
const STATS_THRESHOLD=85;
async function openCase(id,src){
  const c=caseObj(id);
  if(src&&!RM){const r=src.getBoundingClientRect();src.style.transform='translateY(-6px) scale(1.02)';await sleep(110);
    const g=el('<div class="morph"></div>');Object.assign(g.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});document.body.appendChild(g);
    await frame();g.classList.add('go');await sleep(420);go('case',c);g.style.transition='opacity .35s';g.style.opacity=0;setTimeout(()=>g.remove(),380)}
  else go('case',c)}
function openWorkspace(c){
  cur=c;stopPolling(c);$('#hId').textContent=c.id;
  ['hRisk','hConf','aRisk','aUnc','rconf'].forEach(i=>$('#'+i).dataset.v=0);
  const rf=$('#rfg');rf.style.transition='none';rf.style.strokeDashoffset=326.7;requestAnimationFrame(()=>requestAnimationFrame(()=>rf.style.transition=''));
  $('#tl').innerHTML='';$('#act').innerHTML='';$('#fnd').innerHTML='';$('#gapWrap').innerHTML='';$('#dbody').innerHTML='';
  $('#slot').innerHTML='<div class="skel"></div><div class="skel" style="width:70%"></div>';
  $('#hRisk').textContent='0';$('#hConf').textContent='0%';$('#hUnc').textContent='\u2026';$('#hStat').textContent='Loading';
  GR.c=null;GR.sel=null;GR.peek=null;$('#ncard').classList.remove('on');$('#gnote').classList.remove('on');
  loadCase(c).catch(e=>{errToast(e)});
}
async function loadCase(c){
  let d=await api('/cases/'+c.id);if(cur!==c||view!=='case')return;
  const S=c.S,wasNew=d.stage==='new';
  S.tl=[];S.act=[];S.ev=[];S._sig={};S.suffShown=0;c.G=null;
  applyDetail(c,d);
  S.tl.forEach(t=>t.seen=!wasNew);S.act.forEach(a=>a.seen=true);S.ev.forEach(e=>e.seen=true);S.fseen=S.fnd.slice();
  S.depth=Math.max(1,d.depth);S.agentDepth=d.depth;
  graphResize();graphLoad(c);paintAll(c);
  if(PENDING&&PENDING.cid===c.id)consumePending(c);
  if(wasNew){d=await api('/cases/'+c.id+'/investigate',{method:'POST'});if(cur!==c||view!=='case')return;applyDetail(c,d);paintAll(c)}
  startPolling(c);
}
function consumePending(c){
  const p=PENDING;PENDING=null;const n=c.G.map[p.node];if(!n)return;
  setDepth(c,Math.max(c.S.depth,n.depth),true);graphSync();
  setTimeout(()=>{focusNode(n);discovery(p.title,p.text)},RM?0:450)}
async function renderMemory(){
  const c=cur||caseObj(HERO_ID);let data;
  $('#v-memory').innerHTML='<div class="skel" style="height:160px"></div>';
  try{data=await api(`/memory?case=${c.id}&limit=400`)}catch(e){errToast(e);return}
  let q='',th=40;const list=data.items;
  $('#v-memory').innerHTML=`<div class="vh"><div><h2>Case memory</h2><p>Resolved investigations the agent retrieves when a new case looks familiar.</p></div></div>
  <div class="mem-top"><div class="card"><small>Resolved investigations</small><div class="bigc" data-v="0">0</div></div>
  <div class="card" style="flex:2"><small>Search cases similar to ${data.case}</small><input class="srch" id="mq" placeholder="Case ID, pattern or outcome" aria-label="Search similar cases"><div class="rd-h"><span>Similarity threshold</span><span id="thv" style="font-weight:600;color:var(--indigo)">${th}%</span></div><input type="range" class="plain" id="th" min="0" max="100" value="${th}" aria-label="Similarity threshold"></div></div>
  <div class="card pad" id="mlist"></div>`;
  animNum($('.bigc'),data.total,v=>v.toLocaleString('en-IN'),1100);
  const paint=()=>{const r=list.filter(m=>m.sim>=th&&(m.id+m.pat+m.out).toLowerCase().includes(q)).slice(0,25);
    $('#mlist').innerHTML=r.length?r.map(m=>`<div class="pc"><span class="sim">${m.sim}%</span><span><b>${m.id}</b>${m.fresh?' <span class="bm">Added this session</span>':''}<small>${m.pat} \u00B7 ${m.date} \u00B7 ${m.why}</small></span><span class="chip ${m.out==='Cleared'?'green':'red'}">${m.out}</span><button class="btn sm" data-h="${m.id}">Show in graph ${ARR}</button></div>`).join(''):'<p class="mute" style="padding:20px;text-align:center">No cases at this similarity. Lower the threshold.</p>';
    $$('#mlist [data-h]').forEach(b=>b.onclick=()=>showHistory(c,list.find(z=>z.id===b.dataset.h)))};
  $('#mq').oninput=e=>{q=e.target.value.toLowerCase();paint()};$('#th').oninput=e=>{th=+e.target.value;$('#thv').textContent=th+'%';paint()};paint();
}
async function showHistory(c,m){
  if(!c.S.done){toast('The agent is still working on this case. Try again in a moment.');return}
  try{
    const d=await api(`/cases/${c.id}/history`,{method:'POST',body:{memory_id:m.id}});
    PENDING={cid:c.id,node:m.id,title:`${m.id} is relevant`,text:`${m.why.charAt(0).toUpperCase()+m.why.slice(1)}. Outcome: ${m.out.toLowerCase()}.`};
    if(cur===c&&view==='case'){const prev=c.S.stage;applyDetail(c,d);paintAll(c);consumePending(c);$('#gcard').scrollIntoView({behavior:RM?'auto':'smooth',block:'center'})}
    else go('case',c)
  }catch(e){errToast(e)}
}
async function renderPolicy(){
  const c=cur||caseObj(HERO_ID);let p;
  $('#v-policy').innerHTML='<div class="skel" style="height:200px"></div>';
  try{p=await api(`/cases/${c.id}/policy`)}catch(e){errToast(e);return}
  $('#v-policy').innerHTML=`<div class="vh"><div><h2>Policy evidence</h2><p>What the agent retrieved for ${c.id} through hybrid retrieval, and why.</p></div></div>
  <div class="two"><div class="card doc"><small>Fraud Investigation Policy</small>
  ${p.sections.map((s,i)=>`${i?'<h4>':'<h3>'}Section ${s.id}. ${s.title}${i?'</h4>':'</h3>'}<blockquote>${s.text}</blockquote><small>Retrieved because: ${s.why}. Relevance ${s.score}.</small>`).join('<hr>')}
  <hr><small>Source: Fraud policy dataset. This is sample policy text written for the demonstration.</small></div>
  <div style="display:flex;flex-direction:column;gap:14px"><div class="card sec"><h3>Retrieval path</h3><div class="path"><span>${p.pattern}</span><i>\u2192</i><span>Typology ${p.typology||'n/a'}</span>${p.sections.map(s=>`<i>\u2192</i><span>\u00A7${s.id}</span>`).join('')}</div></div>
  <div class="card sec"><h3>Policy check for ${c.id}</h3><ul class="chk">${p.checks.map(k=>`<li><span class="ic ${k.state==='ok'?'':k.state}">${k.state==='ok'?CHK:k.state==='warn'?'!':''}</span><div><b>${k.title}</b><br><small>${k.detail}</small></div></li>`).join('')}</ul></div></div></div>`}
async function renderBench(){
  let bm;$('#v-bench').innerHTML='<div class="skel" style="height:200px"></div>';
  try{bm=await api('/benchmark')}catch(e){errToast(e);return}
  const total=bm.length,d=bm.filter(b=>b.state==='done').length;
  $('#v-bench').innerHTML=`<div class="vh"><div><h2>Benchmark center</h2><p>The 20 official evaluation cases. Open one to see its investigation record.</p></div></div>
  <div class="metrics" style="max-width:640px"><div class="card metric" style="--mc:var(--indigo)"><div class="k">Official evaluation cases</div><div class="num">${total}</div></div><div class="card metric" style="--mc:var(--green)"><div class="k">Completed</div><div class="num">${d}</div></div><div class="card metric" style="--mc:var(--amber)"><div class="k">Remaining</div><div class="num">${total-d}</div></div></div>
  <div class="pbar" style="max-width:640px;margin:-4px 0 20px"><u style="width:0" data-w="${d/total*100}"></u></div>
  <div class="bgrid">${bm.map(b=>{const st=b.state==='done'?'d':b.state==='progress'?'w':'p';return`<button class="bc" data-id="${b.id}" data-state="${b.state}"><b>Case ${String(b.no).padStart(2,'0')}<span class="tick ${st==='d'?'':st}">${st==='d'?CHK:''}</span></b><small>${b.id}</small><small>${st==='d'?b.outcome:st==='w'?'In progress':'Not started'}</small></button>`}).join('')}</div>`;
  requestAnimationFrame(()=>requestAnimationFrame(()=>$$('.pbar u').forEach(u=>u.style.width=u.dataset.w+'%')));
  $$('.bc').forEach(b=>b.onclick=()=>b.dataset.state==='done'?go('report',caseObj(b.dataset.id)):openCase(b.dataset.id,b));
}
async function renderReport(c){
  c=c||cur||caseObj(HERO_ID);let r,bm=[];
  try{[r,bm]=await Promise.all([api(`/cases/${c.id}/report`),api('/benchmark')])}catch(e){errToast(e);return}
  const ids=[...new Set([c.id,...bm.filter(b=>b.state!=='new').map(b=>b.id)])];
  $('#v-report').innerHTML=`<div class="vh"><div><h2>Case summary</h2><p>The structured investigation record for ${c.id}.</p></div><div class="sel"><select id="rsel" aria-label="Choose case">${ids.map(i=>`<option ${i===c.id?'selected':''}>${i}</option>`).join('')}</select></div></div>
  <div class="card rep">${r.rows.map(x=>`<div class="row"><b>${x[0]}</b><div>${String(x[1]).replace(/</g,'&lt;')}</div></div>`).join('')}</div>
  <div class="card rep" style="margin-top:14px"><div class="row"><b>Audit trail</b><div>${r.audit.length?r.audit.map(a=>`${a.ts.replace('T',' ')}  ${a.actor} (${a.role}): ${a.action}${a.detail?' - '+a.detail:''}`).join('\n'):'No recorded actions yet'}</div></div></div>`;
  $('#rsel').onchange=e=>{cur=caseObj(e.target.value);renderReport(cur)};
}

/* ================= shell ================= */
let cur=null,view='landing';
function modal(html){const m=$('#modal');m.innerHTML=`<div class="scrim"></div><div class="dlg" role="dialog" aria-modal="true">${html}</div>`;m.classList.add('on');modal.t=(modal.t||0)+1;const f=$('#modal button, #modal input');f&&f.focus({preventScroll:true})}
function closeModal(){const m=$('#modal');m.classList.remove('on');const t=++modal.t;setTimeout(()=>{if(t===modal.t)m.innerHTML=''},250)}
addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#modal').classList.contains('on')&&!$('#modal .phone')&&!$('#modal .resolved'))closeModal()});
function go(v,c){
  if(c&&v!=='center')cur=c;
  if(v==='case'&&!cur)cur=caseObj(HERO_ID);
  if(v!=='case')stopPolling(cur);
  view=v;GR.running=false;
  $$('.view').forEach(x=>x.classList.remove('on'));$$('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));
  if(v==='center')renderCenter();if(v==='memory')renderMemory();if(v==='policy')renderPolicy();if(v==='bench')renderBench();if(v==='report')renderReport(c||cur);
  $('#v-'+v).classList.add('on');scrollTo({top:0,behavior:'auto'});
  if(v==='case'){openWorkspace(cur);GR.running=true;requestAnimationFrame(graphLoop)}
}
$$('#nav button').forEach(b=>b.onclick=()=>go(b.dataset.v,b.dataset.v==='case'?(cur||caseObj(HERO_ID)):undefined));
$('#hRep').onclick=()=>go('report',cur);
$('#dtabs').addEventListener('click',e=>{const b=e.target.closest('button[data-t]');if(b)dockTab(b.dataset.t)});
$('#dtg').onclick=()=>{const d=$('#dock');d.classList.toggle('closed');$('#dtg').textContent=d.classList.contains('closed')?'Expand':'Collapse'};
$('#bell').onclick=()=>{F.status='Approval pending';F.risk=0;go('center')};
/* sign in */
function paintUser(){const a=$('#avatar');if(USER){a.textContent=USER.name.split(' ').map(x=>x[0]).join('').slice(0,2).toUpperCase();a.title=USER.name+' ('+USER.role+')'}}
function signOut(expired){TOKEN='';USER=null;localStorage.removeItem('argus_token');if(expired)toast('Please sign in again.');setTimeout(()=>location.reload(),expired?900:0)}
function showLogin(){
  modal(`<h3>Sign in to ARGUS</h3><p class="mute">Use a demo account. The role decides what you can do.</p>
  <div class="acct-pick"><button class="btn sm" data-u="analyst" data-p="analyst123">Analyst</button><button class="btn sm" data-u="approver" data-p="approver123">Approver</button><button class="btn sm" data-u="admin" data-p="admin123">Admin</button></div>
  <label class="fld">Username<input id="lu" autocomplete="username" value="approver"></label>
  <label class="fld">Password<input id="lp" type="password" autocomplete="current-password" value="approver123"></label>
  <p class="mute" style="font-size:12px;margin-top:10px">Analysts investigate and request evidence but cannot approve. Approvers can approve or reject. Admins can also reset the demo data.</p>
  <p id="lerr" style="color:var(--red);min-height:18px;margin-top:6px"></p>
  <div class="row"><button class="btn primary mag" id="lgo">Sign in ${ARR}</button></div>`);
  $$('#modal .acct-pick [data-u]').forEach(b=>b.onclick=()=>{$('#lu').value=b.dataset.u;$('#lp').value=b.dataset.p});
  const submit=async()=>{$('#lerr').textContent='';try{const r=await api('/auth/login',{method:'POST',body:{username:$('#lu').value,password:$('#lp').value},quiet:true});
    TOKEN=r.token;USER=r.user;localStorage.setItem('argus_token',TOKEN);closeModal();paintUser();enterApp()}catch(e){$('#lerr').textContent=e.message}};
  $('#lgo').onclick=submit;$('#lp').onkeydown=e=>{if(e.key==='Enter')submit()};
}
function enterApp(){const l=$('#landing');l.classList.add('out');$('#app').hidden=false;stopLanding=true;setTimeout(()=>{l.hidden=true},650);go('center')}
$('#enter').onclick=()=>{if(TOKEN&&USER)enterApp();else showLogin()};
$('#avatar').onclick=()=>{
  if(!USER)return;
  modal(`<h3>${USER.name}</h3><p class="mute">Signed in as ${USER.username} (${USER.role})</p><div class="row" style="justify-content:flex-start">${USER.role==='admin'?'<button class="btn" id="rst">Reset demo data</button>':''}<button class="btn primary" id="so">Sign out</button></div>`);
  $('#so').onclick=()=>signOut(false);
  if($('#rst'))$('#rst').onclick=async()=>{try{await api('/admin/reset',{method:'POST'});store.clear();LIST=[];closeModal();toast('Demo data reset.');go('center')}catch(e){errToast(e)}};
};
async function boot(){
  if(!TOKEN)return;
  try{USER=await api('/auth/me',{quiet:true});paintUser()}catch(e){TOKEN='';localStorage.removeItem('argus_token')}
}

/* ================= landing network ================= */
let stopLanding=false;
(function(){
  const cv=$('#lcv'),ctx=cv.getContext('2d'),tip=$('#ltip'),r=rng(77),types=Object.keys(GC);let W=0,H=0,dpr=1,mx=-999,my=-999,hov=null;
  const N=[];const build=()=>{N.length=0;const n=Math.round(Math.min(64,Math.max(26,W*H/22000)));for(let i=0;i<n;i++){const t=types[Math.floor(r()*types.length)];N.push({x:r()*W,y:r()*H,vx:(r()-.5)*.22,vy:(r()-.5)*.22,t,id:({customer:'C-',account:'C-',tx:'TX-',device:'DEV-',ip:'IP-',merchant:'P-',case:'HHG-'}[t])+Math.floor(1000+r()*98000),hist:Math.floor(r()*3)+1})}};
  const size=()=>{dpr=Math.min(2,devicePixelRatio||1);W=innerWidth;H=innerHeight;cv.width=W*dpr;cv.height=H*dpr;build()};size();addEventListener('resize',()=>{if(!stopLanding)size()});
  cv.parentElement.addEventListener('pointermove',e=>{mx=e.clientX;my=e.clientY});
  function tick(){if(stopLanding)return;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
    N.forEach(n=>{if(!RM){n.x+=n.vx;n.y+=n.vy;if(n.x<-20)n.x=W+20;if(n.x>W+20)n.x=-20;if(n.y<-20)n.y=H+20;if(n.y>H+20)n.y=-20}});
    let h=null,cnt=0;
    for(let i=0;i<N.length;i++){const a=N[i];for(let j=i+1;j<N.length;j++){const b=N[j],d=Math.hypot(a.x-b.x,a.y-b.y);if(d<150){ctx.strokeStyle=`rgba(63,79,209,${(1-d/150)*.28})`;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}}
      if(Math.hypot(a.x-mx,a.y-my)<16)h=a}
    N.forEach(n=>{const on=n===h;ctx.fillStyle=GC[n.t]+(on?'':'99');ctx.beginPath();ctx.arc(n.x,n.y,on?7:4.2,0,6.283);ctx.fill();if(on){ctx.strokeStyle=GC[n.t];ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(n.x,n.y,13,0,6.283);ctx.stroke()}});
    if(h){cnt=N.filter(o=>o!==h&&Math.hypot(o.x-h.x,o.y-h.y)<150).length;if(hov!==h){tip.innerHTML=`<b>${GL[h.t]}</b><strong>${h.id}</strong><br>${cnt} connected entities<br>${h.hist} historical cases`;}tip.style.left=Math.min(W-200,h.x+16)+'px';tip.style.top=Math.min(H-110,h.y+12)+'px';tip.classList.add('on')}else tip.classList.remove('on');
    hov=h;document.body.dataset.g=h?'node':'';if(!h)delete document.body.dataset.g;requestAnimationFrame(tick)}
  tick();
})();

/* ================= cursor + magnetic ================= */
(function(){
  if(!FINE)return;document.body.classList.add('fine');
  const dot=$('#cur-dot'),ring=$('#cur-ring');let mx=innerWidth/2,my=innerHeight/2,rx=mx,ry=my;
  addEventListener('pointermove',e=>{mx=e.clientX;my=e.clientY;dot.style.transform=`translate(${mx}px,${my}px)`;document.body.classList.add('curon');
    const t=e.target.closest&&e.target.closest('a,button,[role=button],select,summary,label,input');if(t)document.body.dataset.cur='hover';else delete document.body.dataset.cur;
    if(!RM){const m=e.target.closest&&e.target.closest('.mag');if(m){const r=m.getBoundingClientRect();m.style.transform=`translate(${(e.clientX-r.left-r.width/2)*.2}px,${(e.clientY-r.top-r.height/2)*.28}px) scale(1.02)`}}},{passive:true});
  addEventListener('pointerout',e=>{const m=e.target.closest&&e.target.closest('.mag');if(m&&!(e.relatedTarget&&m.contains(e.relatedTarget)))m.style.transform=''});
  document.addEventListener('mouseleave',()=>document.body.classList.remove('curon'));
  (function t(){rx+=(mx-rx)*(RM?1:.2);ry+=(my-ry)*(RM?1:.2);ring.style.transform=`translate(${rx}px,${ry}px)`;requestAnimationFrame(t)})();
})();
graphInit();

boot();
