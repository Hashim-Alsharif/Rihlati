import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import sharp from 'sharp';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=path.join(root,'..','Rihlati','app');
const output=path.join(root,'www');
const isNative=process.argv.includes('--native');
const origin=(process.env.RIHLATI_API_ORIGIN||'').replace(/\/$/,'');
const debug=process.env.RIHLATI_LOCAL_DEBUG==='1';
if(isNative&&!origin)throw new Error('Set RIHLATI_API_ORIGIN to the shared HTTPS server origin. No server URL or key is invented.');
if(origin){
  const url=new URL(origin);
  if(url.origin!==origin||url.username||url.password||url.pathname!=='/')throw new Error('RIHLATI_API_ORIGIN must be an origin without credentials or path');
  if(url.protocol!=='https:'&&!(debug&&['localhost','127.0.0.1'].includes(url.hostname)))throw new Error('Only HTTPS is allowed except explicit loopback debugging');
}
await mkdir(output,{recursive:true});
for(const name of ['app.js','accounts.js','i18n.js','locales.json','logo-rihlati.svg'])await copyFile(path.join(source,name),path.join(output,name));
// Bundle only the shared client code; no server files, credentials or database.
const css=(await readFile(path.join(source,'styles.css'),'utf8')).replace(/^@import[^;]+;\s*/,'');
await writeFile(path.join(output,'styles.css'),css);
for(const name of ['runtime.js','mobile.js','mobile.css'])await copyFile(path.join(root,'src',name),path.join(output,name));
for(const language of ['arabic','latin'])await copyFile(path.join(root,'node_modules/@fontsource-variable/readex-pro/files',`readex-pro-${language}-wght-normal.woff2`),path.join(output,`font-${language}.woff2`));
for(const name of ['native','pdf-viewer'])await build({entryPoints:[path.join(root,'src',name+'.js')],outfile:path.join(output,name+'.js'),bundle:true,format:'iife',target:['es2022'],minify:true,legalComments:'eof'});
await copyFile(path.join(root,'node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs'),path.join(output,'pdf.worker.min.mjs'));
const csp=`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ${origin}; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'`;
await writeFile(path.join(output,'index.html'),(await readFile(path.join(root,'src/index.html'),'utf8')).replace('__CSP__',csp));
await writeFile(path.join(output,'app-config.js'),'window.RIHLATI_APP_CONFIG='+JSON.stringify({apiOrigin:origin,allowLocalDebug:debug,version:'1.0.0'})+';\n');
await writeFile(path.join(output,'manifest.webmanifest'),JSON.stringify({name:'رِحلتي — فريق سراج',short_name:'رِحلتي',id:'./',start_url:'./',scope:'./',display:'standalone',background_color:'#f4f8fc',theme_color:'#f4f8fc',lang:'ar',dir:'rtl',icons:[{src:'icon-192.png',sizes:'192x192',type:'image/png'},{src:'icon-512.png',sizes:'512x512',type:'image/png',purpose:'any maskable'}]},null,2));
const logo=await readFile(path.join(source,'logo-rihlati.svg'));
for(const size of [192,512,1024]){
  const mark=await sharp(logo).resize(Math.round(size*.66)).png().toBuffer();
  const target=size===1024?path.join(root,'assets','icon.png'):path.join(output,`icon-${size}.png`);
await mkdir(path.dirname(target),{recursive:true});
  await sharp({create:{width:size,height:size,channels:4,background:'#091a39'}}).composite([{input:mark,gravity:'center'}]).png().toFile(target);
}
await mkdir(path.join(root,'docs/licenses'),{recursive:true});
await copyFile(path.join(root,'node_modules/@fontsource-variable/readex-pro/LICENSE'),path.join(root,'docs/licenses/Readex-Pro-OFL.txt'));
console.log(`Built Rihlati app (${isNative?'native':'web preview'}); same server/database; no secrets bundled.`);
