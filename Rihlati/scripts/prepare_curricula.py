"""Prepare a local, resumable intake. No database writes or external AI calls.

Run with the artifact Python runtime (Pillow, reportlab, pypdf). Word exports
are created separately by convert_curricula_word.ps1. Originals are immutable.
"""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from PIL import Image, ImageOps
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import knowledge as k

INPUT = k.ROOT / 'data/library/مناهج المسلمين الجدد'
OUTPUT = k.ROOT / 'data/library/curricula-pdf'
INTAKE = k.ROOT / 'data/intake/curricula-2026-10'
LANGUAGES = {'English':'en', 'اثيوبي':'am', 'سواحيلي':'sw', 'عربي':'ar', 'فرنسي':'fr', 'فلبيني':'fil'}
SUBJECTS = {'التوحيد':'tawhid', 'توحيد':'tawhid', 'الفقه':'fiqh', 'فقه':'fiqh', 'الحديث':'hadith', 'حديث':'hadith', 'السيرة النبوية':'sirah', 'سيرة':'sirah'}
LABELS = {'ar':'العربية', 'en':'الإنجليزية', 'am':'الأمهرية', 'sw':'السواحيلية', 'fr':'الفرنسية', 'fil':'الفلبينية'}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def metadata(relative):
    language = LANGUAGES[relative.parts[0]]
    stage = 0
    if len(relative.parts) > 2:
        match = re.match(r'0?([1-4])(?:\D|$)', relative.parts[1])
        if match:
            stage = int(match[1])
    match = re.search(r'level[-_ ]?([1-4])', relative.stem, re.I)
    if match:
        stage = int(match[1])
    subject = SUBJECTS.get(relative.stem, 'general')
    label = LABELS[language]
    if relative.suffix.lower() in ('.doc', '.docx'):
        title = f'منهج {relative.stem} — {label} — المرحلة {stage}'
    elif 'approach-new-muslims' in relative.stem:
        title = f'منهج المسلم الجديد — {label} — المرحلة {stage}'
    elif relative.suffix.lower() in ('.jpg', '.jpeg', '.png'):
        title = f'بطاقة تعليمية — {label} — {relative.stem}'
    else:
        title = relative.stem
    return dict(title=title, language=language, level=stage if stage <= 3 else 0,
                curriculum_stage=stage, subject=subject,
                collection='مناهج المسلمين الجدد' + (f' · المرحلة {stage}' if stage else ''))

def convert_image(original, target):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(original) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        width, height = im.size
        # Exact aspect ratio, no crop/stretch/upscale, no retyping content.
        scale = min(595.28 / width, 841.89 / height)
        size = (width * scale, height * scale)
        pdf = canvas.Canvas(str(target), pagesize=size, pageCompression=1)
        pdf.setTitle(original.stem)
        pdf.setCreator('Rihlati local image-to-PDF conversion')
        pdf.drawImage(ImageReader(im), 0, 0, width=size[0], height=size[1])
        pdf.showPage()
        pdf.save()

def prepare():
    INTAKE.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(k.DATABASE.as_uri()+'?mode=ro', uri=True) as c:
        existing = dict(c.execute("SELECT sha256,id FROM sources WHERE sha256!=''"))
    manifest = []
    for original in sorted(INPUT.rglob('*')):
        ext = original.suffix.lower()
        if not original.is_file() or ext not in ('.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'):
            continue
        relative = original.relative_to(INPUT)
        pdf = original if ext == '.pdf' else (OUTPUT / relative).with_suffix('.pdf')
        if ext in ('.jpg', '.jpeg', '.png'):
            convert_image(original, pdf)
        if not pdf.is_file():
            raise FileNotFoundError(f'Convert Word first: {relative}')
        sha = digest(pdf)
        record = dict(metadata(relative), original=original.relative_to(k.ROOT).as_posix(),
                      original_sha256=digest(original), path=pdf.relative_to(k.ROOT).as_posix(),
                      sha256=sha, id=existing.get(sha, 'book-'+sha[:18]), existing=sha in existing)
        reader = PdfReader(pdf)
        pages = []
        for number, page in enumerate(reader.pages, 1):
            text = k.clean(page.extract_text() or '')
            pages.append(dict(page=number, text=text, confidence=None, method='embedded-text'))
        record['page_count'] = len(pages)
        # Word has its own original-text extraction, with physical PDF page
        # boundaries. Do not OCR it or trust old PDF font Unicode mappings.
        record['ocr_pages'] = [p['page'] for p in pages if
            ext in ('.jpg', '.jpeg', '.png') or
            (record['language'] == 'am' and k.classify(p['text']) == 'sparse')]
        record['ocr_language'] = 'amh+ara' if record['language'] == 'am' else 'ara'
        record['extracted_pages'] = sum(k.classify(p['text']) != 'sparse' for p in pages)
        extracted_path = INTAKE / (record['id']+'.embedded.json')
        extracted_path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest.append(record)
        print(json.dumps({key:record[key] for key in ('original','id','page_count','extracted_pages','existing')}, ensure_ascii=False), flush=True)
    target = INTAKE / 'manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PREPARED', len(manifest), 'files;', sum(x['page_count'] for x in manifest), 'pages;',
          sum(len(x['ocr_pages']) for x in manifest), 'OCR pages;', sum(x['existing'] for x in manifest), 'duplicates')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', required=True)
    parser.parse_args()
    prepare()
