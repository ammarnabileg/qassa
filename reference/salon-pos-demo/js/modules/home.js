/* home */
/* ---------- home ---------- */
function renderHome(){
  const h=new Date().getHours();$('hello').textContent=(h<12?'صباح الخير':'مساء الخير')+' يا '+ME.n;
  $('homeDate').textContent=new Date().toLocaleDateString(LOC(),{weekday:'long',day:'numeric',month:'long',year:'numeric'});
  const t=live().filter(s=>dkey(s.at)===today());const y=new Date();y.setDate(y.getDate()-1);const yv=live().filter(s=>dkey(s.at)===dkey(y)).reduce((a,s)=>a+s.total,0);
  const tv=t.reduce((a,s)=>a+s.total,0);const diff=yv?Math.round((tv-yv)/yv*100):0;
  const bk=BS('bookings').filter(b=>b.d===today());
  $('homeStats').innerHTML=stat('مبيعات النهارده',money(tv),yv?`${diff>=0?'▲':'▼'} <bdi>${Math.abs(diff)}%</bdi> عن امبارح`:'')+stat('أطفال النهارده',`<bdi>${t.length}</bdi>`,'فاتورة مدفوعة')+stat('في الانتظار',`<bdi>${bk.filter(b=>b.st==='wait').length}</bdi>`,`<bdi>${bk.filter(b=>b.st==='chair').length}</bdi> على الكرسي`)+stat('متوسط الفاتورة',money(t.length?tv/t.length:0),'');
  const low=S.items.filter(i=>i.t==='prd'&&i.stock<=i.min);
  $('homeNotice').innerHTML=low.length&&isAdmin()?`<div class="notice">${ic('alert')}<div style="flex:1"><b>مخزون قليل:</b> ${low.map(i=>esc(i.n)+' (<bdi>'+i.stock+'</bdi>)').join('، ')}</div><button class="btn sm" onclick="go('stock')">المخزون</button></div>`:'';
  const q=bk.filter(b=>b.st==='wait'||b.st==='chair').sort((a,b)=>a.time.localeCompare(b.time));
  $('homeQueue').innerHTML=q.length?q.map(b=>`<div class="li"><span class="av">${esc(b.kid[0]||'؟')}</span><div class="grow"><b class="small">${esc(b.kid)}</b><div class="cap muted">${esc(itemName(b.item))} · ${esc(staffName(b.barber))} · <bdi>${b.time}</bdi></div></div>${b.st==='chair'?'<span class="pill info">على الكرسي</span>':'<span class="pill warn">منتظر</span>'}</div>`).join(''):'<div class="empty small">مفيش حد منتظر دلوقتي</div>';
  $('homeSales').innerHTML=t.length?t.slice(-6).reverse().map(s=>`<div class="li"><div class="grow"><b class="small">${esc(s.kid||'عميل')}</b><div class="cap muted"><bdi>#${s.no}</bdi> · ${tm(s.at)} · ${PAY[s.pay]}</div></div>${money(s.total)}</div>`).join(''):'<div class="empty small">لسه مفيش بيع النهارده</div>';
}
const itemName=id=>(S.items.find(i=>i.id==id)||{n:'—'}).n;
