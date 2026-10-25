/* invoices */
/* ---------- invoices ---------- */
function renderSales(){
  if(!$('salesDate').value)$('salesDate').value=today();const d=$('salesDate').value;
  const rows=BS('sales').filter(s=>dkey(s.at)===d).reverse();
  $('salesBody').innerHTML=rows.length?rows.map(s=>`<tr><td><bdi>#${s.no}</bdi></td><td>${tm(s.at)}</td><td>${esc(s.kid||'—')}</td><td>${esc(staffName(s.barber))}</td><td class="small">${s.lines.map(l=>esc(l.n)+(l.q>1?' ×'+l.q:'')).join('، ')}</td><td>${PAY[s.pay]}</td><td>${money(s.total)}</td><td class="small">${esc(staffName(s.cashier))}</td><td>${s.void?'<span class="pill bad">ملغاة</span>':'<span class="pill good">مدفوعة</span>'}</td>
  <td><button class="btn sm ghost" onclick="printReceipt(S.sales.find(x=>x.no===${s.no}))">طباعة</button>${waBtn('waSale('+s.no+')')}${s.void||!isAdmin()?'':`<button class="btn sm ghost danger" onclick="voidSale(${s.no})">إلغاء</button>`}</td></tr>`).join(''):emptyRow(10,'مفيش فواتير في اليوم ده');
}
function voidSale(no){dialog('إلغاء الفاتورة #'+no,'<p style="margin:0">الفاتورة هتفضل في السجل بحالة "ملغاة"، والمنتجات هترجع للمخزون، ومش هتدخل في الحسابات. متأكد؟</p>',okFoot('إلغاء الفاتورة'),()=>{const s=S.sales.find(s=>s.no===no);s.void=true;s.voidBy=ME.id;s.lines.forEach(l=>{const it=S.items.find(i=>i.id===l.id);if(it&&it.t==='prd')it.stock+=l.q});save();renderSales();toast('تم إلغاء الفاتورة')})}
