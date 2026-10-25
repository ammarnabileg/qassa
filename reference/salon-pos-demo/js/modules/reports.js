/* reports */
/* ---------- reports ---------- */
let rep='7';
const REPS=[['1','النهارده'],['7','٧ أيام'],['30','٣٠ يوم'],['m','الشهر']];
function repFrom(){const n=new Date();if(rep==='m')return monthStart();const d=new Date(n.getFullYear(),n.getMonth(),n.getDate());d.setDate(d.getDate()-(+rep-1));return d.getTime()}
function bars(el,rows,fmtv){const mx=Math.max(1,...rows.map(r=>r[1]));$(el).innerHTML=rows.length?rows.map(([l,v])=>`<div class="bar"><span>${esc(l)}</span><span class="t"><i style="width:${v/mx*100}%"></i></span>${fmtv?fmtv(v):money(v)}</div>`).join(''):'<div class="empty small">مفيش بيانات في الفترة دي</div>'}
function renderRep(){
  $('repSeg').innerHTML=REPS.map(([k,l])=>`<button class="${rep===k?'on':''}" onclick="rep='${k}';renderRep()">${l}</button>`).join('');
  const from=repFrom();const s=live().filter(x=>x.at>=from);const fk=dkey(from);
  const sales=s.reduce((a,x)=>a+x.total,0),disc=s.reduce((a,x)=>a+x.disc,0);
  const exp=BS('expenses').filter(e=>e.d>=fk).reduce((a,e)=>a+e.v,0);
  const com=s.reduce((a,x)=>a+x.total*((S.staff.find(b=>b.id===x.barber)||{com:0}).com||0)/100,0);
  $('repRange').textContent='من '+new Date(from).toLocaleDateString(LOC())+' لحد النهارده';
  $('repStats').innerHTML=stat('المبيعات',money(sales),`<bdi>${s.length}</bdi> فاتورة`)+stat('متوسط الفاتورة',money(s.length?sales/s.length:0),'لكل طفل')+stat('المصروفات + العمولات',money(exp+com),'')+stat('صافي الربح',money(sales-exp-com),'تقديري');
  const days=[];const d=new Date(from);while(d.getTime()<=Date.now()){days.push(dkey(d));d.setDate(d.getDate()+1)}
  const dv=days.slice(-31).map(k=>[k,s.filter(x=>dkey(x.at)===k).reduce((a,x)=>a+x.total,0)]);const mx=Math.max(1,...dv.map(x=>x[1]));
  $('repDays').innerHTML=dv.map(([k,v])=>`<div title="${k}: ${fmt(v)} د.ك"><span style="height:${v/mx*85}%"></span>${dv.length<=10?`<bdi>${+k.slice(8)}</bdi>`:''}</div>`).join('');
  const it={};s.forEach(x=>x.lines.forEach(l=>{it[l.n]=(it[l.n]||0)+l.p*l.q}));
  bars('repItems',Object.entries(it).sort((a,b)=>b[1]-a[1]).slice(0,7));
  bars('repBarbers',barbers().map(b=>[b.n,s.filter(x=>x.barber===b.id).reduce((a,x)=>a+x.total,0)]).sort((a,b)=>b[1]-a[1]));
  bars('repPay',Object.keys(PAY).map(k=>[PAY[k],s.reduce((a,x)=>a+paidBy(x,k),0)]));
  const hr={};s.forEach(x=>{const h=new Date(x.at).getHours();hr[h]=(hr[h]||0)+1});
  bars('repHours',Object.entries(hr).sort((a,b)=>a[0]-b[0]).map(([h,n])=>[(h%12||12)+(h<12?' ص':' م'),n]),v=>`<span class="small"><bdi>${v}</bdi> طفل</span>`);
  const cogs=s.reduce((a,x)=>a+x.lines.reduce((b,l)=>{const i=S.items.find(y=>y.id===l.id);return b+(i&&i.t==='prd'?(i.cost||0)*l.q:0)},0),0);
  const r=(l,v,b)=>`<div class="tot ${b?'big':''}" style="padding:4px 0"><span class="${b?'':'muted'}">${l}</span>${money(v)}</div>`;
  $('repPL').innerHTML=r('إجمالي المبيعات قبل الخصم',sales+disc)+r('الخصومات',-disc)+r('صافي المبيعات',sales)+r('عمولات الحلاقين',-com)+r('المصروفات',-exp)+r('صافي الربح',sales-com-exp,1)+`<div class="cap muted" style="margin-top:6px">تكلفة المنتجات المباعة في الفترة: ${money(cogs)} (محسوبة ضمن المصروفات لو سجّلت التوريد كمصروف)</div>`;
}
function exportCSV(){const from=repFrom();const rows=[['رقم','التاريخ','الطفل','الموبايل','الحلاق','الكاشير','البنود','قبل الخصم','الخصم','الإجمالي','الدفع','الحالة']];
  BS('sales').filter(x=>x.at>=from).forEach(s=>rows.push([s.no,new Date(s.at).toLocaleString('en-GB'),s.kid,s.phone,staffName(s.barber),staffName(s.cashier),s.lines.map(l=>l.n+' x'+l.q).join(' | '),s.sub,s.disc,s.total,PAY[s.pay],s.void?'ملغاة':'مدفوعة']));
  download('sales-'+today()+'.csv','﻿'+rows.map(r=>r.map(c=>'"'+String(c??'').replace(/"/g,'""')+'"').join(',')).join('\n'),'text/csv')}
function download(n,c,t){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([c],{type:t}));a.download=n;a.click()}
