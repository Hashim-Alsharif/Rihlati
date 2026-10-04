import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root=new URL('../',import.meta.url);
const runtime=await readFile(new URL('src/runtime.js',root),'utf8');
const mobile=await readFile(new URL('src/mobile.js',root),'utf8');

function runtimeContext(native=false,origin=''){
  const calls=[],events=[];
  const context=vm.createContext({URL,Headers,Event,location:{origin:'http://localhost:8081',href:'http://localhost:8081/app/'},document:{addEventListener(){}},window:{RIHLATI_APP_CONFIG:{apiOrigin:origin},RihlatiNative:{isNative:native},dispatchEvent:event=>events.push(event.type),fetch:async(url,options)=>{calls.push({url:String(url),options});return new Response(JSON.stringify({ok:true}),{status:200});}}});
  vm.runInContext(runtime,context);return {context,calls,events};
}
test('preview API requests use app-only endpoints and cookies',async()=>{
  const {context,calls}=runtimeContext();
  await context.window.fetch('/api/profile',{headers:{'X-CSRF-Token':'fixture'}});
  assert.equal(calls[0].url,'http://localhost:8081/app-api/profile');
  assert.equal(calls[0].options.credentials,'include');
  assert.equal(calls[0].options.headers.get('X-CSRF-Token'),'fixture');
  assert.equal(calls[0].options.headers.get('X-Rihlati-Client'),'app');
});
test('external URLs never receive rewritten URLs or automatic credentials',async()=>{
  const {context,calls}=runtimeContext();
  await context.window.fetch('https://unrelated.example/api/test');
  assert.equal(calls[0].url,'https://unrelated.example/api/test');
  assert.equal(calls[0].options.credentials,undefined);
});
test('native builds use only configured HTTPS origin',async()=>{
  const {context,calls}=runtimeContext(true,'https://rihlati.example');
  await context.window.fetch('/api/audio/speech',{method:'POST'});
  assert.equal(calls[0].url,'https://rihlati.example/app-api/audio/speech');
  assert.throws(()=>runtimeContext(true,'http://unsafe.example'),/HTTPS/);
  await assert.rejects(runtimeContext(true).context.window.fetch('/api/profile'),/Configure/);
});
test('all six mobile locales are complete',()=>{
  const block=mobile.slice(mobile.indexOf('const MOBILE_STRINGS='),mobile.indexOf('const mobileIcons='));
  const context=vm.createContext({state:{language:'ar'}});vm.runInContext(block+';globalThis.labels=MOBILE_STRINGS;',context);
  for(const values of Object.values(context.labels)){assert.equal(values.length,6);assert.ok(values.every(v=>typeof v==='string'&&v.length));}
});
test('same logo, local assets, safe areas and reduced motion',async()=>{
  const [original,copy,css,html]=await Promise.all([readFile(new URL('../Rihlati/app/logo-rihlati.svg',root),'utf8'),readFile(new URL('www/logo-rihlati.svg',root),'utf8'),readFile(new URL('src/mobile.css',root),'utf8'),readFile(new URL('src/index.html',root),'utf8')]);
  assert.equal(copy,original);assert.match(css,/safe-area-inset-bottom/);assert.match(css,/prefers-reduced-motion/);assert.match(html,/viewport-fit=cover/);assert.match(html,/فريق سراج/);
});
test('native config does not load a remote site or enable insecure release transport',async()=>{
  const config=JSON.parse(await readFile(new URL('capacitor.config.json',root),'utf8'));
  assert.equal(config.server.url,undefined);assert.equal(config.server.cleartext,undefined);
  assert.equal(config.android.allowMixedContent,false);assert.equal(config.plugins.CapacitorHttp.enabled,true);
});
test('reader disables PDF scripting and uses local worker',async()=>{
  const reader=await readFile(new URL('src/pdf-viewer.js',root),'utf8');
  assert.match(reader,/enableScripting:false/);assert.match(reader,/isEvalSupported:false/);assert.match(reader,/pdf.worker.min.mjs/);
});

test('patched UUID dependency remains compatible with Xcode project generation',()=>{
  const require=createRequire(import.meta.url);
  const xcode=require('xcode');
  const project=xcode.project(fileURLToPath(new URL('ios/App/App.xcodeproj/project.pbxproj',root)));
  project.parseSync();
  const ids=new Set(Array.from({length:100},()=>project.generateUuid()));
  assert.equal(ids.size,100);
  for(const id of ids)assert.match(id,/^[A-F0-9]{24}$/);
  assert.match(project.writeSync(),/PBXProject/);
});
