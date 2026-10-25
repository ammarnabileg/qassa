/* Tablet / iPad cashier mode — same cart & checkout logic as the desktop POS, touch-first layout */
let TABLET=false,tClock=null;
function setTablet(on){TABLET=!!on;try{localStorage.setItem('salonpos.tablet',on?'1':'0')}catch(e){}document.body.classList.toggle('tablet',TABLET);document.body.classList.remove('sheet');clearInterval(tClock);
  if(TABLET){if(view!=='pos')go('pos');else renderPOS();tClock=setInterval(()=>{const c=document.querySelector('.tbar .clock');if(c)c.textContent=new Date().toLocaleTimeString(LOC(),{hour:'2-digit',minute:'2-digit'})},20000)}}
const tabletPref=()=>{try{const v=localStorage.getItem('salonpos.tablet');if(v!=null)return v==='1'}catch(e){}return ME&&ME.role==='cashier'&&matchMedia('(pointer:coarse)').matches};
function tRender(){if(!TABLET)return;
  const waiting=BS('bookings').filter(b=>b.d===today()&&(b.st==='wait'||b.st==='chair')).sort((a,b)=>a.time.localeCompare(b.time));
  $('tBar').innerHTML=`<div class="logo">${LOGO}<div><b>${esc(shopName())}</b><span>${CUR?'فرع '+esc(brName(CUR)):''}</span></div></div><span class="pill mute">${esc(ME.n)}</span><span class="clock">${new Date().toLocaleTimeString(LOC(),{hour:'2-digit',minute:'2-digit'})}</span>${langBtn('btn sm')}<button class="btn sm" onclick="setTablet(false);go('book')">${ic('calendar')} الحجوزات${waiting.length?` <span class="badge" style="margin:0">${waiting.length}</span>`:''}</button><button class="btn sm" onclick="setTablet(false)">${ic('grid')} القائمة</button>`;
  $('tQueue').innerHTML=waiting.length?`<div class="small muted" style="margin-bottom:6px">الطابور — اضغط لتحويله للفاتورة</div><div class="tq">${waiting.map(b=>`<button class="tqi ${b.st}" onclick="tFromBooking(${b.id})">${artOr(b.item,40)}<span><b>${esc(b.kid)}</b>${esc(itemName(b.item))} · <bdi>${b.time}</bdi>${b.paid?' · 💳':''}${b.home?' · 🏠':''}</span></button>`).join('')}</div>`:'';
  tCart()}
function tFromBooking(id){const b=S.bookings.find(x=>x.id===id);if(b.st==='wait')b.st='chair';save();bkToPOS(id)}
function tCart(){if(!TABLET)return;
  const cur=+$('barber').value;$('tBarbers').innerHTML=barbers().map(b=>`<button type="button" class="${b.id===cur?'on':''}" onclick="$('barber').value=${b.id};tCart()"><span class="av">${esc(b.n[0])}</span>${esc(b.n)}</button>`).join('');
  const c=calc(),n=cart.reduce((a,l)=>a+l.q,0);
  $('tSum').innerHTML=`<span>🧾 ${n} · ${$('total').innerHTML}</span><span class="go">${n?'الدفع ←':'الفاتورة'}</span>`;
  $('tKeys').hidden=pay!=='cash'||!cart.length;
  if(!$('tKeys').hidden&&!$('tKeys').dataset.built){const due=()=>{const m=$('total').textContent.match(/\d[\d,]*(\.\d+)?/);return m?m[0].replace(/,/g,''):''};
    $('tKeys').innerHTML=`<div class="quick"><button type="button" data-k="exact">بالظبط</button><button type="button" data-k="5">5</button><button type="button" data-k="10">10</button><button type="button" data-k="20">20</button></div><div class="pad">${[7,8,9,4,5,6,1,2,3,'.',0,'⌫'].map(k=>`<button type="button" data-k="${k}">${k}</button>`).join('')}</div>`;
    $('tKeys').onclick=e=>{const k=e.target.dataset&&e.target.dataset.k;if(k==null)return;const P=$('paid');if(k==='exact')P.value=due();else if(['5','10','20'].includes(k)&&e.target.closest('.quick'))P.value=k;else if(k==='⌫')P.value=P.value.slice(0,-1);else P.value=(P.value||'')+k;renderCart()};
    $('tKeys').dataset.built=1}}
