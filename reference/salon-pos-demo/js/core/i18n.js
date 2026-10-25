/* i18n (Arabic / English) */
/* ---------- i18n (Arabic / English) ---------- */
const EN={};EN_PAIRS.split('\n').forEach(l=>{const i=l.indexOf('|');if(i>0)EN[l.slice(0,i)]=l.slice(i+1)});
const EN_RE=new RegExp('(?<![\\u0621-\\u064A])(?:'+Object.keys(EN).sort((a,b)=>b.length-a.length).map(k=>k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')(?![\\u0621-\\u064A])','g');
let LANG=(()=>{try{return localStorage.getItem('salonpos.lang')||'ar'}catch(e){return'ar'}})();
const LOC=()=>LANG==='en'?'en-GB':'ar-EG';
const langBtn=(cls='btn sm')=>`<button type="button" class="${cls}" onclick="setLang(LANG==='en'?'ar':'en')" aria-label="Language" style="color:inherit">🌐 ${LANG==='en'?'عربي':'English'}</button>`;
function setLangAttrs(){document.documentElement.lang=LANG;document.documentElement.dir=LANG==='en'?'ltr':'rtl';document.title=LANG==='en'?'Qassa POS':'قصّة POS'}
function setLang(l){LANG=l;try{localStorage.setItem('salonpos.lang',l)}catch(e){}setLangAttrs();applyTheme._k=null;if(!$('app').hidden)go(view);else route()}
setLangAttrs();
