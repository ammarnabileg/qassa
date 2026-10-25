/* Navigation, icons, roles, payment methods and constants */
let LOGO=`<svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="18" fill="var(--brand)"/><path d="M20 15l4-5 4 5 4-5 4 5 4-5 4 5v4H20z" fill="var(--sun)"/><g fill="none" stroke="#081510" stroke-width="4" stroke-linecap="round"><circle cx="23" cy="46" r="6"/><circle cx="41" cy="46" r="6"/><path d="M27 41 41 24M37 41 23 24"/></g></svg>`;
const logoHTML=()=>`${LOGO}<div><b>${esc(shopName())}</b><span>${CUR?'فرع '+esc(brName(CUR)):'صالون حلاقة أطفال'}</span></div>`;
const ic=(n,c='')=>`<svg class="icon ${c}"><use href="#i-${n}"/></svg>`;
const PAGES=[
 ['الرئيسية',[['home','الرئيسية','home'],['pos','الكاشير','cart'],['book','الحجوزات','calendar'],['sales','الفواتير','receipt']]],
 ['العملاء والتسويق',[['kids','العملاء','users'],['offers','العروض والكوبونات','tag'],['loyal','النقاط والولاء','award']]],
 ['الخدمات',[['svc','الخدمات','sparkle'],['stock','المخزون','box']]],
 ['الحسابات',[['staff','الموظفين','user'],['exp','المصروفات','wallet'],['cash','الخزينة','bank'],['rep','التقارير','chart']]],
 ['النظام',[['set','الإعدادات','settings']]]];
const PPAGES=[['المنصة',[['p-home','نظرة عامة','chart'],['p-ten','الشركات العملاء','store'],['p-plans','الباقات','layers'],['p-bill','الاشتراكات والفواتير','receipt'],['p-sup','الدعم الفني','support']]],['النظام',[['p-set','إعدادات المنصة','settings']]]];
const CASHIER_PAGES=['home','pos','book','sales','kids','loyal'];
const PAY={cash:'نقدي',card:'كي نت',wallet:'محفظة',online:'أونلاين (التطبيق)'};
const paidBy=(x,k)=>k==='online'?(x.prepaid||0)+(x.pay==='online'?x.total-(x.prepaid||0):0):(x.pay===k?x.total-(x.prepaid||0):0);
let CATS={boys:'قصات أولاد',girls:'قصات بنات',care:'غسيل وسشوار وعناية',shop:'منتجات'};
const ROLES={co:'صاحب الشركة',admin:'مدير فرع',cashier:'كاشير',barber:'حلاق'};
const EXP=['إيجار','مرتبات','كهرباء ومياه','أدوات ومستلزمات','بضاعة للبيع','صيانة','دعاية','أخرى'];
