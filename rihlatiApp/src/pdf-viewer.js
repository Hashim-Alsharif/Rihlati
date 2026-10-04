import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc=new URL('pdf.worker.min.mjs',location.href).href;
let documentTask=null,pdf=null,pageNumber=1,renderTask=null,generation=0;
async function draw(){
  if(!pdf)return;
  if(renderTask){renderTask.cancel();await renderTask.promise.catch(()=>{});}
  const current=generation,page=await pdf.getPage(pageNumber);
  if(current!==generation)return;
  const canvas=document.getElementById('reader-canvas'),container=document.querySelector('.reader-content');
  const viewport=page.getViewport({scale:1});
  const scale=Math.min((container.clientWidth-32)/viewport.width,2),ratio=Math.min(devicePixelRatio||1,2);
  const scaled=page.getViewport({scale:scale*ratio});
  canvas.width=scaled.width;canvas.height=scaled.height;canvas.style.width=scaled.width/ratio+'px';canvas.style.height=scaled.height/ratio+'px';
  document.getElementById('reader-page').textContent=pageNumber+' / '+pdf.numPages;
  document.getElementById('reader-prev').disabled=pageNumber===1;
  document.getElementById('reader-next').disabled=pageNumber===pdf.numPages;
  renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport:scaled});
  await renderTask.promise.catch(error=>{if(error.name!=='RenderingCancelledException')throw error;});
}
window.RihlatiPdf={
  async open(bytes,page=1){
    await this.close();const current=generation;
    const task=pdfjs.getDocument({data:bytes,isEvalSupported:false,enableScripting:false});documentTask=task;
    const loaded=await task.promise;
    if(current!==generation){await loaded.destroy();return;}
    pdf=loaded;pageNumber=Math.min(Math.max(1,page),pdf.numPages);
    document.getElementById('reader-status').textContent='';await draw();
  },
  async close(){generation++;const task=documentTask;documentTask=null;pdf=null;renderTask?.cancel();renderTask=null;await task?.destroy();document.getElementById('reader-canvas').width=0;},
  async step(delta){if(pdf){pageNumber=Math.min(pdf.numPages,Math.max(1,pageNumber+delta));await draw();}},
  resize:draw
};
let resizeTimer;
addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(pdf)draw().catch(()=>{});},180);});
