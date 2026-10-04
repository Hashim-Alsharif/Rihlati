'use strict';
/* Mobile-specific navigation and presentation; shared forms, chat and domain logic. */
const MOBILE_STRINGS={
  home:['الرئيسية','Home','Home','Accueil','መነሻ','Mwanzo'],
  web:['الويب','Website','Website','Site web','ድረ ገጽ','Tovuti'],
  hello:['أهلًا بك','Welcome','Maligayang pagdating','Bienvenue','እንኳን ደህና መጡ','Karibu'],
  today:['خطوة صغيرة اليوم، أثر جميل غدًا','A little learning. A meaningful journey.','Kaunting pag-aaral. Makabuluhang paglalakbay.','Un petit pas, un beau parcours.','ትንሽ ትምህርት፣ ትርጉም ያለው ጉዞ።','Hatua ndogo, safari yenye maana.'],
  hero:['لست وحدك في رحلتك','You are not alone on your journey','Hindi ka nag-iisa sa iyong paglalakbay','Vous n’êtes pas seul dans votre parcours','በጉዞዎ ብቻዎን አይደሉም','Hauko peke yako katika safari yako'],
  heroCopy:['تعلّم، اسأل، وتواصل مع من يرشدك. كل خطوة لها قيمة.','Learn, ask, and connect with someone who cares. Every step matters.','Matuto, magtanong, at kumonekta sa gagabay sa iyo. Mahalaga ang bawat hakbang.','Apprenez, posez vos questions et échangez avec un guide. Chaque pas compte.','ይማሩ፣ ይጠይቁ እና ከሚመራዎት ጋር ይገናኙ። እያንዳንዱ እርምጃ ዋጋ አለው።','Jifunze, uliza na wasiliana na anayekuelekeza. Kila hatua ina thamani.'],
  start:['بماذا تفكّر اليوم؟','What is on your mind?','Ano ang nasa isip mo?','À quoi pensez-vous ?','ስለ ምን እያሰቡ ነው?','Unafikiria nini leo?'],
  ask:['اسأل مساعد رحلتي','Ask Rihlati','Tanungin ang Rihlati','Demander à Rihlati','ሪሕላቲን ይጠይቁ','Uliza Rihlati'],
  path:['مسارك التعليمي','Your learning path','Iyong landas sa pag-aaral','Votre parcours','የትምህርት መንገድዎ','Njia yako ya kujifunza'],
  continue:['تابع رحلتك','Continue your journey','Ipagpatuloy ang paglalakbay','Poursuivre le parcours','ጉዞዎን ይቀጥሉ','Endelea na safari'],
  completed:['كتب أتممتها','Books completed','Mga aklat na natapos','Livres terminés','የተጠናቀቁ መጻሕፍት','Vitabu vilivyokamilika'],
  explore:['استكشف وتعلّم','Explore and learn','Tuklasin at matuto','Explorer et apprendre','ያስሱ እና ይማሩ','Gundua na ujifunze'],
  all:['عرض الكل','View all','Tingnan lahat','Tout voir','ሁሉንም ይመልከቱ','Ona vyote'],
  support:['هناك من يصغي لك','Someone is here to listen','May handang makinig sa iyo','Quelqu’un est là pour vous écouter','እርስዎን የሚያዳምጥ ሰው አለ','Kuna mtu wa kukusikiliza'],
  office:['مكتبي','My office','Aking tanggapan','Mon bureau','ቢሮዬ','Ofisi yangu'],
  workspace:['مساحة الرعاية والمتابعة','Care and follow-up','Pag-aalaga at pagsubaybay','Accompagnement et suivi','እንክብካቤ እና ክትትል','Huduma na ufuatiliaji'],
  openOffice:['افتح مساحة المكتب','Open office workspace','Buksan ang tanggapan','Ouvrir l’espace du bureau','የቢሮ ቦታ ይክፈቱ','Fungua eneo la ofisi'],
  adminTitle:['الإدارة عبر الويب فقط','Administration is web-only','Sa website lamang ang administrasyon','Administration sur le web uniquement','አስተዳደር በድረ ገጽ ብቻ','Usimamizi kupitia tovuti pekee'],
  adminCopy:['لا يمكنك استخدام صلاحيات الأدمن على التطبيق، يمكنك استخدام الويب.','You cannot use administrator privileges in the app. Please use the website.','Hindi magagamit ang pribilehiyo ng admin sa app. Gamitin ang website.','Les droits administrateur ne sont pas disponibles dans l’application. Utilisez le site web.','የአስተዳዳሪ ፈቃዶችን በመተግበሪያው መጠቀም አይችሉም። ድረ ገጹን ይጠቀሙ።','Huwezi kutumia ruhusa za msimamizi katika programu. Tumia tovuti.'],
  offline:['أنت غير متصل. سنحافظ على ما تكتبه؛ أعد المحاولة عند عودة الاتصال.','You are offline. Your draft stays here; retry when connected.','Offline ka. Mananatili ang draft; subukan kapag konektado na.','Vous êtes hors ligne. Votre brouillon reste ici ; réessayez une fois connecté.','ከመስመር ውጭ ነዎት። ረቂቁ እዚህ ይቆያል፤ ሲገናኙ እንደገና ይሞክሩ።','Huna mtandao. Rasimu yako inabaki hapa; jaribu ukipata mtandao.'],
  rights:['بناء وتطوير فريق سراج · جميع الحقوق محفوظة','Built by Team Siraj · All rights reserved','Binuo ng Team Siraj · Nakalaan ang lahat ng karapatan','Créé par l’équipe Siraj · Tous droits réservés','በሲራጅ ቡድን የተገነባ · መብቶች በሙሉ የተጠበቁ ናቸው','Imejengwa na Timu Siraj · Haki zote zimehifadhiwa'],
  reading:['جارٍ فتح المرجع…','Opening the reference…','Binubuksan ang sanggunian…','Ouverture de la référence…','ማጣቀሻው በመክፈት ላይ…','Inafungua rejea…'],
  noBooks:['تظهر هنا المراجع بعد اعتمادها من الإدارة.','References appear here after approval.','Lalabas ang mga sanggunian pagkatapos aprubahan.','Les références apparaîtront après validation.','ማጣቀሻዎች ከጸደቁ በኋላ እዚህ ይታያሉ።','Marejeo yataonekana hapa baada ya kuidhinishwa.']
};
const mt=key=>MOBILE_STRINGS[key]?.[['ar','en','fil','fr','am','sw'].indexOf(state.language)]||MOBILE_STRINGS[key]?.[1]||key;
const mobileIcons={home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',path:'<path d="M7 4h8a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h8"/><circle cx="5" cy="4" r="2"/><path d="m15 17 3 3-3 3"/>',ticket:'<path d="M4 4h16v5a3 3 0 0 0 0 6v5H4v-5a3 3 0 0 0 0-6zM14 7v2m0 3v2m0 3v1"/>',office:'<path d="M4 21V3h12v18M16 9h4v12M2 21h20M8 7h4M8 11h4M8 15h4M8 21v-3h4v3"/>',spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',logout:'<path d="M9 4H4v16h5m5-12 4 4-4 4M8 12h12"/>'};
const mi=name=>mobileIcons[name]?`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${mobileIcons[name]}</svg>`:icon(name);
let lastMobileUser=null,readerModule=null,readerEpoch=0,avatarURL=null;
state.mobileHistory=[];

function mobileNavigation(){
  const office=state.user?.role==='office';
  const items=[['home','home',mt('home')],[office?'admin':'journey',office?'office':'path',office?mt('office'):tr('مساري التعليمي','Learning path')],['chat','chat',tr('مساعد رِحلتي','Assistant')],['tickets','ticket',tr('تذاكري','My tickets')],['profile','person',tr('حسابي','My account')]];
  return items.map(([view,glyph,label])=>`<button type="button" data-mobile-view="${view}" class="mobile-nav-item ${state.view===view?'selected':''} ${view==='chat'?'nav-assistant':''}" ${state.view===view?'aria-current="page"':''}><span>${mi(glyph)}</span><small>${label}</small></button>`).join('');
}
function mobileHome(){
  const data=state.data,u=state.user,office=u.role==='office';
  const books=data.sources.filter(s=>s.status==='approved'),progress=Math.max(0,Math.min(100,Number(data.learner.progress)||0));
  const tickets=data.tickets.filter(t=>t.status==='open').length;
  return `<section class="home-greeting"><div><p class="eyebrow">${mt('today')}</p><h1>${mt('hello')}، <span>${esc(u.display_name)}</span> <span class="greeting-star" aria-hidden="true">✦</span></h1></div><button class="avatar-button" data-mobile-view="profile" aria-label="${tr('حسابي','My account')}">${esc(Array.from(u.display_name)[0]||'ر')}</button></section>
  <div class="home-grid"><section class="home-hero"><div class="hero-copy"><span class="hero-tag"><i></i> ${tr('معك، خطوة بخطوة','With you, step by step')}</span><h2>${mt('hero')}</h2><p>${mt('heroCopy')}</p><button class="hero-cta" data-mobile-view="chat">${mi('spark')}${mt('ask')}<span>↗</span></button></div><div class="hero-art" aria-hidden="true"><span class="orbit orbit-one"></span><span class="orbit orbit-two"></span><span class="orbit-dot"></span><img src="logo-rihlati.svg" alt=""><span class="hero-step one">01</span><span class="hero-step two">02</span><span class="hero-step three">03</span></div></section>
  <section class="home-progress"><div class="section-kicker">${mi(office?'office':'path')}<span>${office?mt('workspace'):mt('path')}</span></div><div class="progress-content"><div><h2>${office?esc(u.office?.name||mt('office')):tr('رحلتك، خطوة بخطوة','Your journey, step by step')}</h2><p>${office?tr('متابعة المستفيدين، رعاية أسئلتهم، وتحسين المعرفة.','Follow learners, support their questions, and improve the knowledge base.'):`<strong>${data.completed.length}</strong> ${mt('completed')}`}</p></div>${!office?`<div class="progress-orbit" style="--progress:${progress}%" role="progressbar" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100" aria-label="${mt('path')}"><span>${progress}<small>%</small></span></div>`:''}</div><button class="progress-link" data-mobile-view="${office?'admin':'journey'}">${office?mt('openOffice'):mt('continue')}<span>←</span></button></section></div>
  <section class="quick-section"><div class="mobile-section-heading"><h2>${mt('start')}</h2><span class="subtle-line"></span></div><div class="quick-grid">${[
    ['chat','chat',tr('مساعد رِحلتي','Rihlati assistant'),tr('كتابة وصوت','Text & voice'),'blue'],
    ['journey','book',mt('path'),tr('مصادر موثقة','Cited sources'),'cyan'],
    ['faq','spark',tr('الأسئلة الشائعة','Common questions'),tr('بدايتي','Getting started'),'violet'],
    [office?'admin':'tickets',office?'office':'person',office?mt('office'):tr('المختص','Specialist'),tr('متابعة المختص','Specialist support'),'peach']
  ].map(([view,glyph,label,copy,color])=>`<button class="quick-tile ${color}" data-mobile-view="${view}"><span class="tile-icon">${mi(glyph)}</span><strong>${label}</strong><small>${copy}</small><span class="tile-arrow">↗</span></button>`).join('')}</div></section>
  <div class="home-bottom-grid"><section class="home-library"><div class="mobile-section-heading"><h2>${mt('explore')}</h2><button class="text-link" data-mobile-view="journey">${mt('all')} ←</button></div><div class="home-books">${books.slice(0,3).map((s,index)=>`<a class="home-book" href="/api/sources/${encodeURIComponent(s.id)}/file"><span class="book-cover tone-${index}">${mi('book')}<small>${subject(s.subject)}</small></span><span class="book-info"><small>${s.level?tr('المستوى','Level')+' '+s.level:subject(s.subject)} · ${esc(s.language.toUpperCase())}</small><strong>${esc(s.title)}</strong><small>${esc(s.uploaded_by||'')} ${s.page_count?'· '+s.page_count+' '+tr('صفحة','pages'):''}</small></span><span class="book-arrow">↗</span></a>`).join('')||`<p class="muted">${mt('noBooks')}</p>`}</div></section>
  <section class="home-support"><span class="support-icon">${mi('person')}</span><h2>${mt('support')}</h2><p>${tr('يمكنك طلب المختص من أي إجابة أو فتح تذكرة مباشرة.','Ask for a specialist from any answer, or open a ticket.')}</p><button class="secondary" data-action="new-ticket">${tr('فتح تذكرة','Open a ticket')} ↗</button>${tickets?`<button class="ticket-count" data-mobile-view="tickets"><i></i>${tickets} ${tr('بانتظار المختص','Awaiting specialist')}</button>`:''}<span class="support-seal">${mi('shield')}${tr('مساحة عمل بصلاحيات','Access-controlled workspace')}</span></section></div>`;
}
function showAdminBlock(){
  const dialog=$('#admin-web-dialog');
  $('#admin-web-title').textContent=mt('adminTitle');$('#admin-web-copy').textContent=mt('adminCopy');
  $('#admin-web-link').textContent=mt('web')+' ↗';$('#admin-web-close').textContent=tr('إغلاق','Close');
  if(!dialog.open)dialog.showModal();
}
function connectionState(){const banner=$('#connection-banner');banner.hidden=navigator.onLine;banner.textContent=mt('offline');}

render=function mobileRender(){
  document.documentElement.lang=state.language;document.documentElement.dir=state.language==='ar'?'rtl':'ltr';
  $('#language-toggle').value=state.language;$('#brand-sub').textContent=tr('معك، خطوة بخطوة','With you, step by step');
  document.querySelectorAll('.web-link').forEach(link=>link.textContent=mt('web')+' ↗');
  $('#mobile-credit').textContent=mt('rights');connectionState();
  if(state.user?.role==='admin'){resetPrivateState();showAdminBlock();}
  const ready=accountReady();document.body.classList.toggle('signed-in',!!state.user);document.body.classList.toggle('account-ready',ready);
  if(!state.user){lastMobileUser=null;state.mobileHistory=[];$('#mobile-nav').hidden=true;$('#app').innerHTML=authPage();bindAccountForms();document.body.dataset.view='auth';return;}
  if(ready&&lastMobileUser!==state.user.id){lastMobileUser=state.user.id;state.view='home';state.mobileHistory=[];}
  if(!ready)state.view='profile';
  $('#mobile-nav').hidden=!ready;$('#mobile-nav').innerHTML=mobileNavigation();document.body.dataset.view=state.view;
  if(state.view==='profile'||!ready){
    $('#app').innerHTML=profilePage().replace('src="/api/profile/avatar"','data-mobile-avatar')+`<div class="account-exit"><button class="secondary" data-action="logout">${mi('logout')}${tr('خروج','Sign out')}</button><a class="quiet" href="/" data-open-web>${mt('web')} ↗</a></div>`;bindAccountForms();hydrateAvatar();return;
  }
  if(!state.data)return;
  if(state.view==='admin'&&state.user.role!=='office'){state.view='home';}
  $('#app').innerHTML=({home:mobileHome,chat:chatPage,journey:journeyPage,faq:faqPage,tickets:userTickets,admin:adminPage}[state.view]||mobileHome)();
  bindForms();bindAccountForms();decorateControls();
  if(state.view==='chat'){$('#messages').scrollTop=$('#messages').scrollHeight;}
};
const originalSwitchView=switchView;
switchView=async function mobileSwitch(view){
  if(view==='admin'&&state.user?.role!=='office'){showAdminBlock();return;}
  const previous=state.view;
  if(previous!==view){state.mobileHistory.push(previous);if(state.mobileHistory.length>30)state.mobileHistory.shift();}
  await originalSwitchView(view);
  if(view!=='chat'){window.scrollTo({top:0,behavior:'instant'});$('#app').focus({preventScroll:true});}
};
const originalReset=resetPrivateState;
resetPrivateState=function mobileReset(){readerEpoch++;window.RihlatiPdf?.close();$('#reader-dialog')?.close();if(avatarURL){URL.revokeObjectURL(avatarURL);avatarURL=null;}lastMobileUser=null;originalReset();state.mobileHistory=[];};
async function hydrateAvatar(){
  const picture=$('.profile-avatar');if(!picture)return;
  picture.removeAttribute('src');const epoch=state.authEpoch;
  try{const response=await fetch('/api/profile/avatar');if(!response.ok)return;const blob=await response.blob();if(epoch!==state.authEpoch||!picture.isConnected)return;if(avatarURL)URL.revokeObjectURL(avatarURL);avatarURL=URL.createObjectURL(blob);picture.src=avatarURL;}catch{}
}
async function closeReader(){readerEpoch++;$('#reader-dialog').close();await window.RihlatiPdf?.close();}
async function openReference(link){
  const url=new URL(link.getAttribute('href'),location.href);
  if(url.origin!==location.origin||!/^\/api\/sources\/[^/]+\/file$/.test(url.pathname))return;
  const epoch=state.authEpoch,reading=++readerEpoch;
  $('#reader-title').textContent=link.querySelector('strong')?.textContent||link.textContent.trim();
  $('#reader-status').textContent=mt('reading');$('#reader-page').textContent='';$('#reader-dialog').showModal();
  try{
    const response=await fetch(url.pathname,{credentials:'include'});if(!response.ok)throw new Error(tr('تعذر إكمال الطلب.','Request failed.'));
    const bytes=new Uint8Array(await response.arrayBuffer());
    if(!readerModule)readerModule=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='pdf-viewer.js';script.onload=resolve;script.onerror=()=>{readerModule=null;script.remove();reject(new Error('Reader unavailable'));};document.head.append(script);});
    await readerModule;if(reading!==readerEpoch||epoch!==state.authEpoch)return;
    await window.RihlatiPdf.open(bytes,Number(new URLSearchParams(url.hash.slice(1)).get('page'))||1);
  }catch(error){if(reading===readerEpoch)$('#reader-status').textContent=error.message;}
}
document.addEventListener('click',async event=>{
  const nav=event.target.closest('[data-mobile-view]');
  if(nav){event.preventDefault();try{await window.RihlatiNative?.tap();await switchView(nav.dataset.mobileView);}catch(error){toast(error.message);}return;}
  const link=event.target.closest('a[href]');
  if(link&&/^\/api\/sources\//.test(link.getAttribute('href'))){event.preventDefault();await openReference(link);}
  if(event.target.closest('[data-close-dialog]'))$('#admin-web-dialog').close();
  if(event.target.closest('[data-close-reader]'))await closeReader();
  if(event.target.closest('#reader-prev'))window.RihlatiPdf?.step(-1).catch(error=>toast(error.message));
  if(event.target.closest('#reader-next'))window.RihlatiPdf?.step(1).catch(error=>toast(error.message));
});
$('#reader-dialog').addEventListener('cancel',()=>{readerEpoch++;window.RihlatiPdf?.close();});
window.addEventListener('rihlati-admin-blocked',showAdminBlock);
window.addEventListener('offline',connectionState);window.addEventListener('online',connectionState);
window.addEventListener('rihlati-pause',()=>{stopAudio();if(state.recorder?.state==='recording'){state.recorder.onstop=null;state.recorder.stop();}state.recordStream?.getTracks().forEach(t=>t.stop());state.recognition?.abort();state.recording=false;});
window.addEventListener('rihlati-resume',()=>{if(!state.busy)load().then(render).catch(error=>toast(error.message));});
window.addEventListener('rihlati-back',async()=>{
  if($('#reader-dialog').open){await closeReader();return;}
  if($('#admin-web-dialog').open){$('#admin-web-dialog').close();return;}
  const previous=state.mobileHistory.pop();if(previous){await originalSwitchView(previous);}else if(state.view!=='home'&&accountReady()){await originalSwitchView('home');}
});
// On narrow browser previews, keep navigation out of the virtual keyboard's way.
window.visualViewport?.addEventListener('resize',()=>document.body.classList.toggle('keyboard-open',window.innerHeight-window.visualViewport.height>150));
