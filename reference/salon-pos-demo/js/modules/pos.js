/* POS */
/* ---------- POS ---------- */
let cart=[],cat='all',pay='cash',fromBooking=null;
function renderPOS(){
  $('posDate').textContent='الكاشير: '+ME.n+' — '+new Date().toLocaleDateString(LOC(),{weekday:'long',day:'numeric',month:'long'});
  $('cats').innerHTML=[['all','الكل'],['offers','🎁 العروض'],...Object.entries(CATS)].map(([k,l])=>`<button class="${cat===k?'on':''}" onclick="cat='${k}';renderPOS()">${l}</button>`).join('');
  const q=$('q').value.trim();const list=S.items.filter(i=>(cat==='all'||i.c===cat)&&(!q||i.n.includes(q)));
  $('items').innerHTML=cat==='offers'?offerTiles():list.length?list.map(i=>{const out=i.t==='prd'&&i.stock<=0;return`<button class="item" ${out?'disabled':''} onclick="add(${i.id})">${i.t==='svc'&&artKey(i.id)?svcArt(i.id,48):`<span class="ic">${esc(i.e||'✂️')}</span>`}${i.t==='prd'?`<span class="stk pill ${i.stock<=i.min?'warn':'mute'}"><bdi>${i.stock}</bdi></span>`:''}<b>${esc(i.n)}</b>${money(i.p)}</button>`}).join(''):'<div class="empty" style="grid-column:1/-1">مفيش نتائج</div>';
  const cur=$('barber').value;$('barber').innerHTML=barbers().map(b=>`<option value="${b.id}">${esc(b.n)}</option>`).join('');if(cur)$('barber').value=cur;
  $('pay').hidden=false;$('kidsList').innerHTML=S.kids.map(k=>`<option value="${esc(k.n)}">${esc(k.phone)}</option>`).join('');
  $('pay').innerHTML=Object.entries(PAY).filter(([k])=>k!=='online').map(([k,l])=>`<button class="${pay===k?'on':''}" onclick="pay='${k}';renderPOS()">${l}</button>`).join('');
  renderCart();tRender();
}
function fillPhone(){const k=S.kids.find(x=>x.n===$('kid').value.trim());if(k&&!$('phone').value)$('phone').value=k.phone;renderCart()}
function add(id){const it=S.items.find(i=>i.id===id);if(it.var)return varPick(id);const l=cart.find(c=>c.id===id);if(it.t==='prd'&&(l?l.q:0)>=it.stock)return toast('الكمية المتاحة خلصت');l?l.q++:cart.push({id,n:it.n,p:it.p,q:1});renderCart()}
function qty(id,d){const l=cart.find(c=>c.id===id);if(d>0){const it=S.items.find(i=>i.id===id);if(it&&it.t==='prd'&&l.q>=it.stock)return toast('الكمية المتاحة خلصت')}l.q+=d;if(l.q<=0)cart=cart.filter(c=>c!==l);renderCart()}
function clearCart(){cart=[];fromBooking=null;coupon=null;redeem=0;if($('cpIn'))$('cpIn').value='';['kid','phone','paid'].forEach(i=>$(i).value='');$('disc').value=0;renderCart()}
let coupon=null,redeem=0;
function couponErr(c,sub){if(!c)return'الكود ده مش موجود';if(!c.active)return'الكوبون موقوف';const t=today();if(t<c.from||t>c.to)return'الكوبون منتهي أو لسه مبدأش';if(c.limit&&c.used>=c.limit)return'الكوبون وصل للحد الأقصى';if(sub<c.min)return'أقل فاتورة للكوبون ده '+fmt(c.min)+' د.ك';return''}
function applyCoupon(){const code=$('cpIn').value.trim().toUpperCase();if(!code){coupon=null;return renderCart()}const c=S.coupons.find(x=>x.code===code);const sub=cart.reduce((a,l)=>a+l.p*l.q,0);const e=couponErr(c,sub);if(e){coupon=null;toast(e)}else{coupon=c.code;toast('تم تطبيق الكوبون')}renderCart()}
function calc(){const sub=cart.reduce((a,l)=>a+l.p*l.q,0);let d=+$('disc').value||0;if($('discType').value==='p')d=sub*Math.min(d,100)/100;d=Math.min(Math.max(d,0),sub);
  let a=sub-d,cd=0;const c=coupon&&S.coupons.find(x=>x.code===coupon);if(c&&!couponErr(c,sub)){cd=Math.min(a,c.type==='p'?a*c.val/100:c.val)}a-=cd;
  const rv=Math.min(a,redeem*S.loyal.value);a-=rv;return{sub,disc:d,cd,rv,total:a}}
function addOffer(id){const o=S.offers.find(x=>x.id===id);const l=cart.find(c=>c.id===-id);l?l.q++:cart.push({id:-id,n:o.n,p:o.price,q:1});renderCart()}
function kidVisits(n,p){const k=kidKey(n,p);return live().filter(s=>kidKey(s.kid,s.phone)===k&&k).length}
function renderCart(){
  $('lines').innerHTML=cart.length?cart.map(l=>`<div class="line"><b class="small">${esc(l.n)}</b><span class="small">${money(l.p*l.q)}</span><span class="cap muted">${money(l.p)} للوحدة</span><span class="qty"><button onclick="qty(${l.id},-1)" aria-label="نقص">−</button><bdi>${l.q}</bdi><button onclick="qty(${l.id},1)" aria-label="زود">+</button></span></div>`).join(''):'<div class="empty small">اضغط على خدمة لإضافتها للفاتورة</div>';
  const kk=$('kid').value.trim()?kidKey($('kid').value,$('phone').value):'';const lp=kk&&S.loyal.on?kidPoints(kk):null;
  $('loyalHint').innerHTML=lp?`<div class="row sb small" style="background:var(--brand-soft);padding:8px 10px;border-radius:var(--r-md)"><span>${lp.tier.e} ${lp.tier.n} — رصيد <b><bdi>${lp.bal}</bdi></b> نقطة</span>${redeem?`<button class="btn sm" type="button" onclick="redeem=0;renderCart()">إلغاء الاستبدال</button>`:lp.bal>=S.loyal.minRedeem?`<button class="btn sm" type="button" onclick="redeem=${lp.bal};renderCart()">استبدل بـ ${fmt(lp.bal*S.loyal.value)} د.ك</button>`:`<span class="cap muted">الاستبدال من ${S.loyal.minRedeem} نقطة</span>`}</div>`:'';
  const c=calc();$('sub').innerHTML=money(c.sub);$('discV').innerHTML=money(c.disc+c.cd+c.rv);$('total').innerHTML=money(c.total);
  $('cpMsg').innerHTML=coupon?`<div class="row sb small"><span class="pill good">${esc(coupon)}</span><span>خصم كوبون ${money(c.cd)} <button class="btn sm ghost danger" type="button" onclick="coupon=null;$('cpIn').value='';renderCart()">شيل</button></span></div>`:'';
  if(c.rv)$('cpMsg').innerHTML+=`<div class="row sb small"><span class="pill info">نقاط <bdi>${redeem}</bdi></span><span>${money(c.rv)}</span></div>`;
  const pb=fromBooking&&S.bookings.find(x=>x.id===fromBooking);const pre=pb&&pb.paid?Math.min(pb.payAmt,c.total):0;if(pre){$('total').innerHTML=money(c.total-pre);$('cpMsg').innerHTML+=`<div class="notice" style="margin:6px 0 0;background:var(--good-bg);color:var(--good-ink)">${ic('circle-check')}<span>مدفوع أونلاين ${money(pb.payAmt)} (${esc(pb.payMethod)}). ${c.total-pre>0?'حصّل الفرق بس.':'متحصلش حاجة — اضغط تسجيل.'}</span></div>`}
  const cash=pay==='cash';$('paidWrap').style.display=$('changeRow').style.display=cash?'':'none';
  const paid=+$('paid').value||0;const ch=paid-(c.total-pre);
  $('change').innerHTML=paid?(ch>=0?money(ch):`<span style="color:var(--danger)">ناقص ${money(-ch)}</span>`):'—';
  $('checkout').disabled=!cart.length||(cash&&paid&&ch<0);$('checkout').textContent=pre&&c.total-pre<=0?'تسجيل الفاتورة (مدفوعة أونلاين)':'تحصيل وطباعة الإيصال';tCart();
}
function checkout(){
  if(!cart.length)return;const c=calc();const kid=$('kid').value.trim(),phone=$('phone').value.trim();
  const kk=kid?kidKey(kid,phone):'';const tierMul=kk?kidPoints(kk).tier.mul:1;
  const sale={no:++S.seq,br:CUR,at:Date.now(),kid,phone,barber:+$('barber').value,cashier:ME.id,lines:cart.map(l=>({...l})),sub:c.sub,disc:c.disc+c.cd+c.rv,coupon:coupon&&c.cd?coupon:'',cdisc:c.cd,ptsU:c.rv?redeem:0,ptsE:kid&&S.loyal.on?Math.floor(c.total/S.loyal.per*tierMul):0,total:c.total,prepaid:(()=>{const pb=fromBooking&&S.bookings.find(x=>x.id===fromBooking);return pb&&pb.paid?Math.min(pb.payAmt,c.total):0})(),pay,paid:pay==='cash'?(+$('paid').value||c.total):c.total};
  if(sale.coupon)S.coupons.find(x=>x.code===sale.coupon).used++;coupon=null;redeem=0;$('cpIn').value='';
  S.sales.push(sale);
  sale.lines.forEach(l=>{const it=S.items.find(i=>i.id===l.id);if(it&&it.t==='prd')it.stock-=l.q});
  if(kid&&!S.kids.find(k=>kidKey(k.n,k.phone)===kidKey(kid,phone)))S.kids.push({id:nid(S.kids),n:kid,phone,age:'',parent:'',notes:''});
  if(fromBooking){const b=S.bookings.find(x=>x.id===fromBooking);if(b){b.st='done';b.sale=sale.no}}
  save();document.body.classList.remove('sheet');printReceipt(sale);if(S.settings.waAuto&&sale.phone)waDirect(sale.phone,saleText(sale),'فاتورة #'+sale.no);clearCart();renderPOS();toast('تم تسجيل الفاتورة #'+sale.no);
}
function receiptHTML(s){
  return `<div id="receipt"><div class="rc"><b style="font-size:16px">${esc(S.shop.name)}</b>${s.br?'<div>فرع '+esc(brName(s.br))+'</div>':''}${S.shop.addr?`<div>${esc(S.shop.addr)}</div>`:''}<div>فاتورة رقم <bdi>#${s.no}</bdi></div><div><bdi>${new Date(s.at).toLocaleString(LOC())}</bdi></div></div><hr>
  ${s.kid?`<div class="r"><span>الطفل</span><span>${esc(s.kid)}</span></div>`:''}<div class="r"><span>الحلاق</span><span>${esc(staffName(s.barber))}</span></div><div class="r"><span>الكاشير</span><span>${esc(staffName(s.cashier))}</span></div><hr>
  ${s.lines.map(l=>`<div class="r"><span>${esc(l.n)} × <bdi>${l.q}</bdi></span>${money(l.p*l.q)}</div>`).join('')}<hr>
  <div class="r"><span>الإجمالي</span>${money(s.sub)}</div>${s.disc?`<div class="r"><span>خصم</span>${money(s.disc)}</div>`:''}
  <div class="r" style="font-weight:700;font-size:15px"><span>المطلوب</span>${money(s.total)}</div><div class="r"><span>الدفع</span><span>${PAY[s.pay]}</span></div>
  ${s.pay==='cash'&&s.paid>s.total?`<div class="r"><span>مدفوع</span>${money(s.paid)}</div><div class="r"><span>الباقي</span>${money(s.paid-s.total)}</div>`:''}
  ${s.coupon?`<div class="r"><span>كوبون ${esc(s.coupon)}</span>${money(s.cdisc)}</div>`:''}${s.ptsE&&S.settings.showPts?`<div class="r"><span>نقاط مكتسبة</span><bdi>+${s.ptsE}</bdi></div>`:''}${s.prepaid?`<div class="r"><span>مدفوع أونلاين</span>${money(s.prepaid)}</div>`:''}${s.void?'<div class="rc"><b>— ملغاة —</b></div>':''}<hr><div class="rc">${esc(S.shop.foot)}</div></div>`;
}
function printReceipt(s){dialog('الإيصال',receiptHTML(s),`<button class="btn brand" type="button" onclick="$('dlg').close();waSale(${s.no})">${ic('whatsapp')} واتساب</button><button class="btn primary" type="button" onclick="doPrint()">${ic('printer')} طباعة</button><button class="btn" value="x">إغلاق</button>`);$('printArea').innerHTML=receiptHTML(s)}
function doPrint(){const p=$('printArea');p.hidden=false;$('dlg').close();setTimeout(()=>{print();p.hidden=true},50)}
