"""Bounded local indexing workers. Failed jobs retain their reference for review."""
import json
import logging
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from knowledge import ROOT, db, index_pdf, source_path

POOL=ThreadPoolExecutor(max_workers=2)
LOCK=threading.Lock()
JOBS=set()

def background_index(sid):
    with LOCK:
        if sid in JOBS:
            return
        if len(JOBS)>=8:
            raise ValueError('قائمة الفهرسة ممتلئة. أعد المحاولة لاحقًا. / Index queue is full.')
        JOBS.add(sid)
    def run():
        try:
            index_pdf(sid)
            with db() as c:
                missing=c.execute("SELECT COUNT(*) FROM pages WHERE source_id=? AND extraction_status='needs_ocr'",(sid,)).fetchone()[0]
                source=dict(c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone())
            runtime=Path(os.environ.get('RIHLATI_RUNTIME',Path(os.environ.get('USERPROFILE',''))/'.cache/codex-runtimes/codex-primary-runtime/dependencies'))
            node=shutil.which('node') or str(runtime/'node/bin/node.exe')
            if missing and source['language']=='ar' and Path(node).exists() and (ROOT/'data/ocr/lang/ara.traineddata').exists():
                manifest=ROOT/'data/ocr'/f'{sid}-manifest.json'
                manifest.write_text(json.dumps([{'id':sid,'path':str(source_path(source['file_path'])),'page_count':source['page_count']}]),'utf-8')
                with db() as c:
                    c.execute("UPDATE sources SET processing_status='indexing' WHERE id=?",(sid,))
                with open(ROOT/'data/ocr'/f'{sid}.log','a',encoding='utf-8') as log:
                    subprocess.run([node,str(ROOT/'scripts/ocr_books.cjs'),str(manifest)],stdout=log,stderr=log,timeout=7200,check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                index_pdf(sid,json.loads((ROOT/'data/ocr'/f'{sid}.json').read_text('utf-8')))
        except Exception as error:
            logging.getLogger('rihlati').warning('Index failed: %s %s',sid,type(error).__name__)
            with db() as c:
                c.execute("UPDATE sources SET processing_status='failed',processing_error=? WHERE id=?",(type(error).__name__,sid))
        finally:
            with LOCK:
                JOBS.discard(sid)
    POOL.submit(run)
