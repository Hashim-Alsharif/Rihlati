/* Local Arabic OCR. Only model weights are downloaded; books stay on this PC. */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const runtime = process.env.RIHLATI_RUNTIME || path.join(process.env.USERPROFILE || process.env.HOME || '', '.cache/codex-runtimes/codex-primary-runtime/dependencies');
let createWorker;
try { ({ createWorker } = require('tesseract.js')); }
catch { ({ createWorker } = require(path.join(runtime, 'node/node_modules/tesseract.js'))); }
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'data/ocr');
const manifest = JSON.parse(fs.readFileSync(process.argv[2] || path.join(out, 'manifest.json'), 'utf8'));
const bundledPoppler=path.join(runtime, 'native/poppler/Library/bin/pdftoppm.exe');
const poppler = process.env.RIHLATI_PDFTOPPM || (fs.existsSync(bundledPoppler)?bundledPoppler:'pdftoppm');

async function main() {
  const worker = await createWorker('ara', 1, {langPath:path.join(out,'lang'), gzip:false, cachePath:path.join(out,'lang')});
  await worker.setParameters({preserve_interword_spaces:'0', tessedit_pageseg_mode:'3'});
  for (const book of manifest) {
    const target = path.join(out, book.id + '.json');
    const pages = fs.existsSync(target) ? JSON.parse(fs.readFileSync(target, 'utf8')) : [];
    for (let p = pages.length + 1; p <= book.page_count; p++) {
      const prefix = path.join(out, book.id + '-current');
      const render = spawnSync(poppler, ['-f',String(p),'-l',String(p),'-r','180','-singlefile','-png',path.resolve(root,book.path),prefix], {windowsHide:true,timeout:120000});
      if(render.status !== 0) throw new Error('Page render failed: '+book.id+'/'+p+' '+render.stderr+' '+render.error+' binary='+poppler);
      const {data} = await worker.recognize(prefix + '.png');
      pages.push({page:p,text:data.text,confidence:data.confidence,method:'tesseract-ara'});
      fs.writeFileSync(target, JSON.stringify(pages,null,2), 'utf8');
      console.log(`${book.id} ${p}/${book.page_count} confidence=${data.confidence}`);
    }
  }
  await worker.terminate();
  console.log('OCR_COMPLETE');
}
main().catch(error => {console.error(error);process.exitCode=1;});
