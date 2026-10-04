"""Render converted PDFs to contact sheets for local visual inspection."""
import json
import math
import os
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw
import knowledge as k

intake = k.ROOT/'data/intake/curricula-2026-10'
runtime = Path(os.environ['USERPROFILE'])/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
poppler = runtime/'native/poppler/Library/bin/pdftoppm.exe'
folder = intake/'visual-qa'
folder.mkdir(exist_ok=True)
manifest = json.loads((intake/'manifest.json').read_text(encoding='utf-8'))

def render(book):
    if book['original'].lower().endswith('.pdf'):return
    output = folder/book['id']
    output.mkdir(exist_ok=True)
    prefix = output/'page'
    result = subprocess.run([str(poppler),'-scale-to','800','-png',str(k.ROOT/book['path']),str(prefix)],capture_output=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
    pages = sorted(output.glob('page-*.png'))
    if len(pages)!=book['page_count']:raise ValueError('Rendered page count differs')
    width, height = 340, 500
    columns = min(4,len(pages))
    sheet = Image.new('RGB',(columns*width,math.ceil(len(pages)/columns)*height),'#dfe7e9')
    draw = ImageDraw.Draw(sheet)
    for i,page in enumerate(pages):
        with Image.open(page) as im:
            im.thumbnail((width-16,height-34))
            x=(i%columns)*width+(width-im.width)//2;y=(i//columns)*height+25
            sheet.paste(im,(x,y))
            draw.text(((i%columns)*width+8,(i//columns)*height+5),f'{i+1} / {len(pages)}',fill='black')
    sheet.save(folder/(book['id']+'.jpg'),quality=85)
    print(book['id'],len(pages),'rendered',flush=True)

with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(render,manifest))
print('VISUAL_QA_RENDER_COMPLETE')
