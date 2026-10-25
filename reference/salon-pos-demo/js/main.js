/* App start: load data, restore session, route */
loadBiz('kids');try{const t=localStorage.getItem(KEY+'.theme');if(t)document.documentElement.dataset.theme=t}catch(e){}
$('q').oninput=renderPOS;
try{const e=sessionStorage.getItem(KEY+'.me');ME=PLAT_USERS.find(u=>u.email===e)||null;if(!ME&&e){const f=findUser(e);if(f){loadBiz(f[0]);ME=S.staff.find(x=>x.id===f[1])}}}catch(e){}
function route(){const h=location.hash;const site=h.startsWith('#/pricing'),app=h.startsWith('#/app');$('site').hidden=!site;$('capp').hidden=!app;if(site||app){if(app){const t=h.split('/')[2];if(BIZ_META[t]&&t!==BIZ){loadBiz(t);CA.phone=CA.phone}else applyTheme(BIZ)}else applyTheme('');$('app').hidden=true;$('loginScreen').hidden=true;site?renderSite():renderCApp();scrollTo(0,0);return}ME?start():renderLogin()}
window.addEventListener('hashchange',route);route();
