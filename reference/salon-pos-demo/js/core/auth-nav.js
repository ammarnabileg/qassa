/* login */
/* ---------- login ---------- */
const PLAT_USERS=[{id:'p1',n:'إدارة المنصة',email:'owner@qassa.io',pass:'123456',role:'owner',scope:'platform'}];
const DEMO=[['owner@qassa.io','مالك المنصة','قصّة POS'],['owner@mykids.com','صاحب شركة 🧒','ماي كيدز — أطفال'],['owner@gentle.com','صاحب شركة 💈','جنتلمان كت — رجالي'],['owner@lamsa.com','صاحبة شركة 💅','صالون لمسة — نسائي'],['hawally@mykids.com','مدير فرع','ماي كيدز — حولي'],['cashier@mykids.com','كاشير','ماي كيدز — حولي']];
let IMP=null;
function renderLogin(){applyTheme('');
  $('app').hidden=true;$('loginScreen').hidden=false;$('loginScreen').className='auth';
  $('loginScreen').innerHTML=`<div class="side"><div><div class="logo">${LOGO}<div><b>قصّة POS</b><span>سيستم الصالونات — أطفال، رجالي، نسائي</span></div></div>
  <h2>كل محلاتك في مكان واحد — من الكاشير لحد التقارير.</h2>
  <ul><li>${ic('cart')} كاشير سريع وحجوزات وطابور انتظار</li><li>${ic('award')} نقاط وولاء وكوبونات للعملاء</li><li>${ic('store')} أكتر من محل وفرع تحت حساب واحد</li><li>${ic('chart')} تقارير وعمولات وتقفيل ورديات</li></ul></div>
  <div class="cap" style="color:rgba(255,255,255,.55);position:relative">© ٢٠٢٦ قصّة POS</div></div>
  <div class="form"><form onsubmit="event.preventDefault();tryLogin()"><div style="align-self:flex-end">${langBtn()}</div><div><h1>أهلاً بيك 👋</h1><div class="small muted">سجّل دخولك عشان تكمل</div></div>
  <label class="field">البريد الإلكتروني<input class="input" id="lE" type="email" dir="ltr" autocomplete="username" required></label>
  <label class="field"><span class="row sb">كلمة المرور<a href="#" class="cap" style="color:var(--brand-700)" onclick="event.preventDefault();forgot()">نسيت كلمة المرور؟</a></span><input class="input" id="lP" type="password" dir="ltr" autocomplete="current-password" required></label>
  <label class="row small"><input type="checkbox" checked> افتكرني على الجهاز ده</label>
  <button class="btn primary lg">دخول</button>
  <div class="divider">حسابات تجريبية (كلمة المرور 123456)</div>
  <div class="row" style="justify-content:center;gap:16px"><a class="small" style="color:var(--brand-700)" href="#/pricing">الأسعار والباقات</a></div><div class="row small" style="justify-content:center;gap:10px"><span class="muted">تطبيق العملاء</span>${['kids','men','women'].map(t=>`<a class="btn sm" href="#/app/${t}">${BIZ_META[t].e} ${BIZ_META[t].n}</a>`).join('')}</div><div class="demo">${DEMO.map(([e,r,s])=>`<button type="button" onclick="$('lE').value='${e}';$('lP').value='123456';tryLogin()">${r}<span>${s}</span></button>`).join('')}</div></form></div>`;
}
function forgot(){dialog('استرجاع كلمة المرور','<label class="field">البريد الإلكتروني<input class="input" type="email" dir="ltr"></label><div class="small muted">هيوصلك لينك لتغيير كلمة المرور.</div>',okFoot('إرسال اللينك'),()=>toast('تم إرسال اللينك (تمبلت)'))}
function tryLogin(){const e=$('lE').value.trim().toLowerCase(),p=$('lP').value;
  let u=PLAT_USERS.find(x=>x.email===e&&x.pass===p);if(!u){const f=findUser(e,p);if(f){loadBiz(f[0]);u=S.staff.find(x=>x.id===f[1])}}
  if(!u)return toast('البريد أو كلمة المرور غلط');ME=u;IMP=null;try{sessionStorage.setItem(KEY+'.me',u.email)}catch(e){}start()}
function logout(){document.body.classList.remove('tablet','sheet');TABLET=false;ME=null;IMP=null;CUR=null;try{sessionStorage.removeItem(KEY+'.me')}catch(e){}renderLogin()}
let CUR=null;
const isPlat=()=>ME&&ME.scope==='platform'&&!IMP;
const isCo=()=>ME&&ME.role==='co';
const scope=()=>isPlat()?'platform':isCo()&&CUR==null?'company':'branch';
const brName=id=>(S.branches.find(b=>b.id===id)||{n:'—'}).n;
const BS=k=>S[k].filter(x=>CUR==null||x.br===CUR);
function impersonate(tid){const t=PL.tenants.find(x=>x.id===tid);IMP={t,back:ME};loadBiz(t.type||'kids');ME=S.staff.find(s=>s.role==='co');CUR=null;go('c-home');toast('دخلت على حساب '+t.n)}
function stopImp(){ME=IMP.back;IMP=null;CUR=null;go('p-ten')}
function enterBranch(id){CUR=id;go('home');toast('دخلت فرع '+brName(id))}
function leaveBranch(){CUR=null;go('c-home')}
let view='home';
const MGR_PAGES=['home','pos','book','sales','kids','loyal','stock','staff','exp','cash','rep'];
const CPAGES=[['الشركة',[['c-home','نظرة عامة','chart'],['c-branches','الفروع','store'],['c-rep','تقارير الفروع','trend']]],['إدارة مركزية لكل الفروع',[['svc','الخدمات والأسعار','sparkle'],['offers','العروض والكوبونات','tag'],['loyal','النقاط والولاء','award'],['kids','العملاء','users'],['staff','الموظفين','user']]],['النظام',[['set','الإعدادات والاشتراك','settings']]]];
const allowed=v=>{const sc=scope();if(sc==='platform')return v.startsWith('p-');if(sc==='company')return CPAGES.some(g=>g[1].some(p=>p[0]===v));return(ME.role==='cashier'?CASHIER_PAGES:MGR_PAGES).includes(v)};
const shopName=()=>IMP?IMP.t.n:S.shop.name;
const roleLabel=u=>u.scope==='platform'?'مالك المنصة':u.role==='co'?'صاحب الشركة':u.role==='admin'?'مدير '+brName(u.br):ROLES[u.role]+(u.br?' — '+brName(u.br):'');
function buildNav(){
  const sc=scope(),plat=sc==='platform';$('nav').classList.toggle('plat',plat);
  const waiting=BS('bookings').filter(b=>b.d===today()&&(b.st==='wait'||b.st==='chair')).length;
  const logo=plat?`${LOGO}<div><b>قصّة POS</b><span>لوحة الشركة المالكة للسيستم</span></div>`:`${LOGO}<div><b>${esc(shopName())}</b><span>${CUR?'فرع '+esc(brName(CUR)):'كل الفروع'}</span></div>`;
  const groups=plat?PPAGES:sc==='company'?CPAGES:PAGES;
  $('nav').innerHTML=`<div class="logo">${logo}</div>`+(isCo()&&!plat?`<select class="input" style="margin:0 4px 6px;width:auto" onchange="this.value==='all'?leaveBranch():enterBranch(+this.value)" aria-label="اختيار الفرع"><option value="all">🏢 كل الفروع</option>${S.branches.map(b=>`<option value="${b.id}" ${CUR===b.id?'selected':''}>📍 فرع ${esc(b.n)}</option>`).join('')}</select>`:'')+groups.map(([g,ps])=>{const vis=ps.filter(p=>allowed(p[0]));return vis.length?`<div class="grp">${g}</div>`+vis.map(([k,l,i])=>`<button data-v="${k}" class="${view===k?'on':''}" onclick="go('${k}')">${ic(i)}<span>${l}</span>${k==='book'&&waiting?`<span class="badge">${waiting}</span>`:''}${k==='p-sup'?`<span class="badge">${PL.tickets.filter(t=>t.st!=='closed').length}</span>`:''}</button>`).join(''):''}).join('')+
  `<div class="me"><span class="av">${esc(ME.n[0])}</span><div style="flex:1;line-height:1.4"><b class="small">${esc(ME.n)}</b><div class="cap muted">${esc(roleLabel(ME))}</div></div>${langBtn('btn sm ghost')}<button class="btn sm ghost" onclick="logout()" title="خروج" aria-label="خروج" style="color:inherit">${ic('logout')}</button></div>`;
  $('tbLogo').innerHTML=logo;$('tbLang').innerHTML=langBtn();
  $('impBar').innerHTML=(IMP?`<div class="imp"><span>${ic('eye')} أنت داخل كمالك المنصة على حساب <b>${esc(IMP.t.n)}</b> — أي تعديل هيتسجل باسمك</span><button class="btn sm" onclick="stopImp()">رجوع للوحة المنصة</button></div>`:'')+(isCo()&&CUR?`<div class="imp" style="background:var(--brand-900)"><span>${ic('store')} أنت داخل <b>فرع ${esc(brName(CUR))}</b> كصاحب الشركة</span><button class="btn sm" onclick="leaveBranch()">رجوع للوحة الشركة</button></div>`:'');
}
const R={home:'renderHome',pos:'renderPOS',book:'renderBook',sales:'renderSales',kids:'renderKids',offers:'renderOffers',loyal:'renderLoyal',svc:'renderSvc',stock:'renderStock',staff:'renderStaff',exp:'renderExp',cash:'renderCash',rep:'renderRep',set:'renderSet','p-home':'renderPHome','p-ten':'renderTen','p-plans':'renderPlans','p-bill':'renderBill','p-sup':'renderSup','p-set':'renderPSet','c-home':'renderCHome','c-branches':'renderBranches','c-rep':'renderCRep'};
function noop(){}
const homeOf=()=>({platform:'p-home',company:'c-home',branch:'home'})[scope()];
function go(v){applyTheme(isPlat()?'':BIZ);if(typeof TABLET!=='undefined'&&TABLET&&v!=='pos'){TABLET=false;document.body.classList.remove('tablet','sheet')}if(!allowed(v))v=homeOf();view=v;$('nav').classList.remove('open');buildNav();document.querySelectorAll('.view').forEach(s=>s.classList.toggle('on',s.id==='v-'+v));window[R[v]]();scrollTo(0,0)}
function start(){$('loginScreen').hidden=true;$('app').hidden=false;CUR=ME.br??null;go(homeOf());if(scope()==='branch'&&tabletPref())setTablet(true)}
