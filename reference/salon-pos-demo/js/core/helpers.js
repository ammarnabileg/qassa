/* helpers */
/* ---------- helpers ---------- */
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>(Math.round(n*1000)/1000).toLocaleString('en-US',{minimumFractionDigits:3,maximumFractionDigits:3});
const money=n=>`<span class="money"><bdi>${fmt(n)}</bdi> د.ك</span>`;
const dkey=d=>{d=new Date(d);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
const today=()=>dkey(Date.now());
const tm=d=>new Date(d).toLocaleTimeString(LOC(),{hour:'2-digit',minute:'2-digit'});
const dt=d=>new Date(d).toLocaleDateString(LOC(),{day:'numeric',month:'short'});
const staffName=id=>(S.staff.find(b=>b.id==id)||{n:'—'}).n;
const barbers=()=>S.staff.filter(s=>s.role==='barber'&&(CUR==null||s.br===CUR));
const live=()=>S.sales.filter(s=>!s.void&&(CUR==null||s.br===CUR));
const isAdmin=()=>ME&&(ME.role==='admin'||ME.role==='co');
const monthStart=()=>{const n=new Date();return new Date(n.getFullYear(),n.getMonth(),1).getTime()};
const nid=a=>Math.max(0,...a.map(x=>x.id))+1;
const kidKey=(n,p)=>(p||'').trim()||(n||'').trim();
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('on');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('on'),2400)}
function dialog(title,body,foot,onOk,wide){$('dlgT').textContent=title;$('dlgB').innerHTML=body;$('dlgF').innerHTML=foot;const d=$('dlg');d.classList.toggle('wide',!!wide);d.onclose=()=>{if(d.returnValue==='ok'&&onOk)onOk()};d.returnValue='';d.showModal()}
const okFoot=(t='حفظ')=>`<button class="btn primary" value="ok">${t}</button><button class="btn" value="x">إلغاء</button>`;
const stat=(l,v,h)=>`<div class="card stat"><div class="small muted">${l}</div><div class="v">${v}</div><div class="cap muted">${h||''}</div></div>`;
const emptyRow=(n,t)=>`<tr><td colspan="${n}" class="empty">${t}</td></tr>`;
