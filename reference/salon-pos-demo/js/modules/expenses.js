/* expenses */
/* ---------- expenses ---------- */
function renderExp(){if(!$('expMonth').value)$('expMonth').value=today().slice(0,7);const m=$('expMonth').value;
  const ex=BS('expenses').filter(e=>e.d.startsWith(m)).sort((a,b)=>b.d.localeCompare(a.d)||b.at-a.at);const tot=ex.reduce((a,e)=>a+e.v,0);
  $('expSum').innerHTML='إجمالي الشهر: '+money(tot);
  $('expBody').innerHTML=ex.length?ex.map(e=>`<tr><td>${dt(e.d)}</td><td>${esc(e.cat)}</td><td class="small muted">${esc(e.note||'')}</td><td>${e.cash?'<span class="pill mute">الدرج</span>':'<span class="pill info">بنك</span>'}</td><td>${money(e.v)}</td><td><button class="btn sm ghost danger" onclick="delExp(${e.at})">حذف</button></td></tr>`).join(''):emptyRow(6,'مفيش مصروفات في الشهر ده');
  const by={};ex.forEach(e=>by[e.cat]=(by[e.cat]||0)+e.v);bars('expBars',Object.entries(by).sort((a,b)=>b[1]-a[1]))}
function openExpense(){dialog('مصروف جديد',`<label class="field">البند<select class="input" id="eCat">${EXP.map(x=>`<option>${x}</option>`).join('')}</select></label><label class="field">المبلغ<input class="input" id="eV" type="number" step="any" min="0"></label><label class="field">التاريخ<input class="input" id="eD" type="date" value="${today()}"></label><label class="field">ملاحظة<input class="input" id="eN"></label><label class="row small"><input type="checkbox" id="eCash" checked> مدفوع من درج الكاشير (نقدي)</label>`,okFoot(),()=>{const v=+$('eV').value;if(!(v>0))return toast('اكتب مبلغ صحيح');S.expenses.push({br:CUR,at:Date.now(),d:$('eD').value||today(),cat:$('eCat').value,v,note:$('eN').value,cash:$('eCash').checked,by:ME.id});save();renderExp();toast('تم تسجيل المصروف')})}
function delExp(at){S.expenses=BS('expenses').filter(e=>e.at!==at);save();renderExp()}
