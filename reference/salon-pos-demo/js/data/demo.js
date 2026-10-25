/* demo data (first run only) */
/* ---------- demo data (first run only) ---------- */
function demo(){if(S.demoDone)return;const R=a=>a[Math.floor(Math.random()*a.length)];
  const names=S.names||[['يوسف','55123456',5,'أم يوسف'],['مريم','66987654',7,'أبو مريم'],['آدم','99234567',3,'أم آدم'],['ليلى','55544433',6,''],['عمر','66222333',9,''],['جنى','90667778',4,''],['مالك','97998887',2,'']];
  names.forEach((k,i)=>S.kids.push({id:i+1,n:k[0],phone:k[1],age:k[2],parent:k[3],notes:i===2&&BIZ==='kids'?'بيخاف من صوت الماكينة — مقص بس':i===2&&BIZ==='women'?'حساسية من صبغة الأمونيا':''}));
  const svc=S.items.filter(i=>i.t==='svc'&&i.p>0&&i.p<=10),prd=S.items.filter(i=>i.t==='prd'),br=barbers();
  for(let d=20;d>=0;d--){const n=3+Math.floor(Math.random()*7);for(let i=0;i<n;i++){const at=new Date();at.setDate(at.getDate()-d);at.setHours(11+Math.floor(Math.random()*10),Math.floor(Math.random()*60));if(at>Date.now())continue;
    const k=R(names);const lines=[];const pk=R(svc);lines.push({id:pk.id,n:pk.n,p:pk.p,q:1});if(prd.length&&Math.random()<.3){const x=R(prd);lines.push({id:x.id,n:x.n,p:x.p,q:1})}
    const sub=lines.reduce((a,l)=>a+l.p,0);const disc=Math.random()<.12?0.5:0;
    S.sales.push({no:0,at:at.getTime(),kid:k[0],phone:k[1],...(()=>{const B=R([1,1,1,2,2,3]);return{br:B,barber:R(S.staff.filter(x=>x.role==='barber'&&x.br===B)).id,cashier:B===1?R([1,2]):B===2?11:13}})(),lines,sub,disc,total:sub-disc,pay:R(['cash','cash','cash','card','wallet']),paid:sub-disc})}}
  S.sales.sort((a,b)=>a.at-b.at);S.sales.forEach((s,i)=>s.no=1001+i);S.seq=1000+S.sales.length;
  const ago=n=>Date.now()-n*864e5;
  S.expenses.push({br:1,at:ago(6),d:dkey(ago(6)),cat:'أدوات ومستلزمات',v:15,note:'أمواس وكابات',cash:true,by:1},{br:2,at:ago(10),d:dkey(ago(10)),cat:'كهرباء ومياه',v:25,note:'',cash:false,by:1},{br:3,at:ago(3),d:dkey(ago(3)),cat:'دعاية',v:10,note:'إعلان فيسبوك',cash:false,by:1});
  const t=new Date();const hm=o=>{const x=new Date(t.getTime()+o*6e4);return x.toTimeString().slice(0,5)};
  S.bookings.push({id:1,br:1,kid:names[2][0],phone:names[2][1],item:3,barber:3,d:today(),time:hm(-10),st:'chair'},{id:2,br:1,src:'app',paid:true,payAmt:5,payMethod:'كي نت',payRef:'TX40091822',kid:names[5][0],phone:names[5][1],item:10,barber:5,d:today(),time:hm(5),st:'wait'},{id:3,br:1,kid:names[6][0],phone:names[6][1],item:1,barber:4,d:today(),time:hm(30),st:'wait'});
  S.bookings.push({id:4,br:1,src:'app',kid:names[0][0],phone:names[0][1],item:BIZ==='women'?18:BIZ==='men'?2:3,barber:4,d:today(),time:hm(90),st:'wait',home:{area:'بيان',block:'5',street:'12',house:'21',note:'البيت الأبيض على الزاوية'},homeFee:S.settings.homeFee||3});
  S.demoDone=true;save()}
