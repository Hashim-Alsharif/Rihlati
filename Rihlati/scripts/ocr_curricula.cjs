/* Resumable local OCR. No book/page is transmitted to an AI service.
 * Uses pinned local Tesseract weights; never downloads at runtime.
 * Each cached result is bound to the PDF SHA256 and page number.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const intake = path.join(root, 'data/intake/curricula-2026-10');
const languages = path.join(root, 'data/ocr/lang');
const runtime = process.env.RIHLATI_RUNTIME || path.join(process.env.USERPROFILE || '', '.cache/codex-runtimes/codex-primary-runtime/dependencies');
let createWorker;
try { ({createWorker} = require('tesseract.js')); }
catch { ({createWorker} = require(path.join(runtime,'node/node_modules/tesseract.js'))); }
const poppler = process.env.RIHLATI_PDFTOPPM || path.join(runtime, 'native/poppler/Library/bin/pdftoppm.exe');
const group = process.argv[2] || 'all';
async function main() {
  const manifest = JSON.parse(fs.readFileSync(path.join(intake,'manifest.json'), 'utf8'));
  const workers = new Map();
  try {
    for (const book of manifest) {
      if (!book.ocr_pages.length || (group !== 'all' && group !== book.ocr_language)) continue;
      const pdf = path.resolve(root, book.path);
      if (!pdf.startsWith(root+path.sep)) throw new Error('PDF outside project');
      if (crypto.createHash('sha256').update(fs.readFileSync(pdf)).digest('hex') !== book.sha256) throw new Error('PDF changed');
      const target = path.join(intake, book.id+'.ocr.json');
      const cached = fs.existsSync(target) ? JSON.parse(fs.readFileSync(target,'utf8')) : {sha256:book.sha256, pages:[]};
      if (cached.sha256 !== book.sha256) throw new Error('Stale OCR cache');
      const langs = book.ocr_language.split('+');
      for (const lang of langs) if (!fs.existsSync(path.join(languages,lang+'.traineddata'))) throw new Error('Missing local OCR language: '+lang);
      let worker = workers.get(book.ocr_language);
      if (!worker) {
        worker = await createWorker(langs, 1, {langPath:languages,gzip:false,cachePath:languages});
        await worker.setParameters({preserve_interword_spaces:'0', tessedit_pageseg_mode:'3'});
        workers.set(book.ocr_language, worker);
      }
      for (const number of book.ocr_pages) {
        if (cached.pages.some(p=>p.page===number)) continue;
        const prefix = path.join(intake, book.id+'-render');
        const render = spawnSync(poppler, ['-f',String(number),'-l',String(number),'-r','200','-singlefile','-png',pdf,prefix], {windowsHide:true,timeout:120000});
        if (render.status !== 0) throw new Error('PDF render failed: '+String(render.stderr));
        const {data} = await worker.recognize(prefix+'.png');
        cached.pages.push({page:number,text:data.text,confidence:data.confidence,method:'tesseract-'+book.ocr_language});
        const temporary = target+'.tmp';
        fs.writeFileSync(temporary,JSON.stringify(cached,null,2),'utf8');
        fs.renameSync(temporary,target);
        console.log(`${book.id} ${number}/${book.page_count} confidence=${data.confidence}`);
      }
    }
  } finally { for (const worker of workers.values()) await worker.terminate(); }
  console.log('OCR_COMPLETE '+group);
}
main().catch(error=>{ console.error(error); process.exitCode=1; });
