'use strict';
/* All existing domain requests are routed to the shared server's app-only surface. */
(() => {
  const config=window.RIHLATI_APP_CONFIG||{};
  const native=!!window.RihlatiNative?.isNative;
  const configured=config.apiOrigin||'';
  if(configured&&!/^https:\/\/[^/]+$/.test(configured)&&!config.allowLocalDebug)throw new Error('HTTPS API origin required');
  const base=native?configured:location.origin;
  const originalFetch=window.fetch.bind(window);
  const originalURL=location.href;
  window.RihlatiRuntime={native,base,webURL:base+'/',
    apiURL(path){return base+path.replace(/^\/api\//,'/app-api/');},
    async openWeb(){if(native){if(!base)throw new Error('Build with your HTTPS domain first.');await window.RihlatiNative.openWeb(base+'/');}else location.assign('/');}
  };
  window.fetch=async (resource,options={})=>{
    const url=new URL(typeof resource==='string'?resource:resource.url,originalURL);
    // Never attach credentials or rewrite calls to unrelated origins.
    if(url.origin===location.origin&&url.pathname.startsWith('/api/')){
      if(native&&!base)throw new Error('عنوان الخادم غير مضبوط في نسخة التطبيق. / Configure the app server before building.');
      const headers=new Headers(options.headers||{});headers.set('X-Rihlati-Client','app');
      const response=await originalFetch(window.RihlatiRuntime.apiURL(url.pathname)+url.search,{...options,headers,credentials:'include'});
      if(response.status===403){
        const error=await response.clone().json().catch(()=>({}));
        if(error.code==='admin_web_only')window.dispatchEvent(new Event('rihlati-admin-blocked'));
      }
      return response;
    }
    // The shared language loader expects this absolute path on the web.
    if(url.origin===location.origin&&url.pathname==='/locales.json')return originalFetch(new URL('locales.json',originalURL),options);
    return originalFetch(resource,options);
  };
  document.addEventListener('click',async event=>{
    const web=event.target.closest('[data-open-web]');
    if(web){event.preventDefault();try{await window.RihlatiRuntime.openWeb();}catch(error){window.alert(error.message);}return;}
  });
})();
