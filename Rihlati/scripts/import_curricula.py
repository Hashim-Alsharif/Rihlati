"""Incremental, auditable import of the supplied curricula; local OCR only.

Default: read-only validation. --apply --approve-supplied-sources creates a
consistent backup, imports verified files and approves only usable passages.
Existing approved/extracted/reviewed pages, users and conversations are kept.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path
import knowledge as k

INTAKE = k.ROOT / 'data/intake/curricula-2026-10'

def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def checked_file(relative, expected):
    path = (k.ROOT / relative).resolve()
    if not path.is_relative_to(k.ROOT) or not path.is_file() or sha256(path) != expected:
        raise ValueError('Missing/changed intake file: '+relative)
    return path

def page_record(item, book):
    text = k.clean(item['text'])
    kind = k.classify(text)
    method = item['method']
    confidence = item.get('confidence')
    letters = [c for c in text if c.isalpha()]
    private_glyphs = sum(unicodedata.category(c) == 'Co' or c == '\ufffd' for c in text)
    bad_mapping = private_glyphs > max(3, len(letters) * .02)
    if method in ('embedded-text', 'word-native'):
        confidence = None
        status = 'needs_ocr' if kind == 'sparse' else 'extracted'
    elif method.startswith('tesseract-') and isinstance(confidence, (float, int)) and 0 <= confidence <= 100:
        status = 'ocr' if confidence >= 70 else 'needs_review'
        if kind == 'sparse':
            # Blank book pages can be sparse, but a supplied image with no
            # usable OCR remains explicitly awaiting review, not "complete".
            status = 'needs_review' if Path(book['original']).suffix.lower() in ('.jpg','.jpeg','.png') else 'sparse'
    else:
        raise ValueError('Unknown extraction method/confidence')
    if bad_mapping:
        status = 'needs_review'
    if book['language'] == 'am' and letters and kind != 'sparse':
        if sum('\u1200' <= c <= '\u137f' for c in letters) / len(letters) < .25:
            status = 'needs_review'
    return dict(page=int(item['page']), text=text, confidence=confidence, status=status, kind=kind, method=method)

def load_pages(book, intake=INTAKE):
    checked_file(book['original'], book['original_sha256'])
    checked_file(book['path'], book['sha256'])
    embedded = json.loads((intake / (book['id']+'.embedded.json')).read_text(encoding='utf-8'))
    pages = {p['page']:p for p in embedded}
    if Path(book['original']).suffix.lower() in ('.doc','.docx'):
        native_path = intake / (book['id']+'.native-word.json')
        if not native_path.is_file():
            raise ValueError('Extract original Word pages first: '+book['id'])
        native = json.loads(native_path.read_text(encoding='utf-8-sig'))
        if native['sha256'] != book['sha256'] or native['original_sha256'] != book['original_sha256']:
            raise ValueError('Stale Word page cache')
        native_pages = {p['page']:p for p in native['pages']}
        if set(native_pages) != set(range(1,book['page_count']+1)) or any(p['method']!='word-native' for p in native_pages.values()):
            raise ValueError('Word page boundaries incomplete')
        return [page_record(native_pages[n],book) for n in sorted(native_pages)]
    ocr_path = intake / (book['id']+'.ocr.json')
    ocr = json.loads(ocr_path.read_text(encoding='utf-8')) if ocr_path.is_file() else None
    if book['ocr_pages']:
        if not ocr or ocr['sha256'] != book['sha256']:
            raise ValueError('OCR is not complete: '+book['id'])
        recognized = {p['page']:p for p in ocr['pages']}
        if not set(book['ocr_pages']).issubset(recognized):
            raise ValueError('OCR pages are missing: '+book['id'])
        pages.update({n:recognized[n] for n in book['ocr_pages']})
    if set(pages) != set(range(1, book['page_count']+1)):
        raise ValueError('Page count mismatch')
    return [page_record(pages[n], book) for n in sorted(pages)]

def backup():
    folder = k.ROOT / 'data/backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('before-curricula-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
    with k.db() as source, sqlite3.connect(path) as target:
        source.backup(target)
    return path.relative_to(k.ROOT).as_posix()

def apply_book(book, records, actor_id=None):
    sid, created = k.register_pdf(k.ROOT/book['path'], title=book['title'], language=book['language'],
        level=book['level'], subject=book['subject'], collection=book['collection'], approved=False)
    # IDs for a previously imported PDF are authoritative; don't duplicate it.
    with k.db() as c:
        c.execute('BEGIN IMMEDIATE')
        source = c.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
        if source['language'] not in k.language_aliases(book['language']):
            raise ValueError('Existing source language differs; manual review required')
        columns = {r[1] for r in c.execute('PRAGMA table_info(sources)')}
        if created and actor_id and 'uploaded_by_user_id' in columns:
            c.execute('UPDATE sources SET uploaded_by_user_id=? WHERE id=?', (actor_id, sid))
        recorded = c.execute("SELECT details FROM audit WHERE action='curriculum_intake' AND entity_id=? ORDER BY id LIMIT 1", (sid,)).fetchone()
        created_here = created or bool(recorded and json.loads(recorded['details']).get('created_here'))
        if not recorded:
            k.audit(c, 'curriculum_intake', sid, json.dumps({
                'actor_user_id':actor_id, 'authorization':'User requested local curriculum import', 'created_here':created,
                'original':book['original'], 'original_sha256':book['original_sha256'],
                'pdf_sha256':book['sha256'], 'curriculum_stage':book['curriculum_stage'],
                'conversion':'original PDF' if Path(book['original']).suffix.lower()=='.pdf' else 'local PDF conversion',
                'extraction_methods':sorted({p['method'] for p in records}),
                'ocr':'local Tesseract for scanned/image pages only; no external provider', 'human_text_review':False,
            }, ensure_ascii=False))
        changed = 0
        for item in records:
            old = c.execute('SELECT extraction_status FROM pages WHERE source_id=? AND page_number=?', (sid,item['page'])).fetchone()
            # Preserve reviewed text AND stable citations for existing good pages.
            if old and old['extraction_status'] not in ('needs_ocr','needs_review'):
                continue
            # Re-running an intake must not repeatedly rewrite pending pages.
            if old:
                previous = c.execute('SELECT raw_text,confidence,kind,extraction_status FROM pages WHERE source_id=? AND page_number=?', (sid,item['page'])).fetchone()
                if tuple(previous) == (item['text'],item['confidence'],item['kind'],item['status']):
                    continue
                k.audit(c, 'curriculum_page_extracted', f"{sid}:{item['page']}", json.dumps({
                    'method':item['method'], 'previous_status':previous['extraction_status'],
                    'previous_text':previous['raw_text'], 'human_text_review':False}, ensure_ascii=False))
                c.execute('DELETE FROM passages WHERE source_id=? AND page_number=?', (sid,item['page']))
                c.execute('DELETE FROM pages WHERE source_id=? AND page_number=?', (sid,item['page']))
            c.execute('INSERT INTO pages(source_id,page_number,extraction_status,raw_text,confidence,kind,extraction_method) VALUES(?,?,?,?,?,?,?)',
                      (sid,item['page'],item['status'],item['text'],item['confidence'],item['kind'],item['method']))
            if item['status'] in ('extracted','ocr') and item['kind'] not in ('sparse',):
                for index, chunk in enumerate(k.chunks(item['text'])):
                    c.execute('INSERT INTO passages(source_id,page_number,chunk_index,language,content,normalized_content) VALUES(?,?,?,?,?,?)',
                              (sid,item['page'],index,source['language'],chunk,k.normalize(chunk)))
            changed += 1
        total = c.execute('SELECT COUNT(*) FROM passages WHERE source_id=?', (sid,)).fetchone()[0]
        usable = c.execute("SELECT COUNT(*) FROM passages p JOIN pages g ON p.source_id=g.source_id AND p.page_number=g.page_number WHERE p.source_id=? AND g.kind='content'", (sid,)).fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM pages WHERE source_id=? AND extraction_status IN ('needs_ocr','needs_review')", (sid,)).fetchone()[0]
        # Existing blocked/rejected sources are never silently approved. A new
        # supplied source can be used only if it has a searchable content page.
        if source['status']=='pending_review' and usable and created_here:
            c.execute("UPDATE sources SET status='approved' WHERE id=?", (sid,))
            k.audit(c, 'source_approved', sid, json.dumps({'actor_user_id':actor_id,'basis':'User-authorized supplied references; low-confidence pages excluded','human_text_review':False}))
        if created or changed:
            c.execute('UPDATE sources SET processing_status=?,processing_error=? WHERE id=?',
                      ('needs_review' if pending else 'ready', '', sid))
            k.audit(c, 'curriculum_indexed', sid, json.dumps({'changed_pages':changed,'passages':total,'pending_pages':pending}))
        status = c.execute('SELECT status,processing_status FROM sources WHERE id=?',(sid,)).fetchone()
    return dict(id=sid, created=created, changed_pages=changed, passages=total, usable_passages=usable,
                pending_pages=pending, status=status['status'], processing_status=status['processing_status'],
                original=book['original'], pdf=book['path'], language=book['language'], pages=book['page_count'])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-supplied-sources', action='store_true')
    args = parser.parse_args()
    if args.apply and not args.approve_supplied_sources:
        parser.error('--apply requires --approve-supplied-sources')
    manifest = json.loads((INTAKE/'manifest.json').read_text(encoding='utf-8'))
    prepared = [(book,load_pages(book)) for book in manifest]
    print('VALIDATED', len(prepared), 'files;', sum(len(pages) for _,pages in prepared), 'pages', flush=True)
    if not args.apply:
        print('READ_ONLY: no database changes')
        return
    backup_path = backup()
    print('BACKUP', backup_path, flush=True)
    k.migrate()  # additive extraction provenance column; only AFTER backup
    with k.db() as c:
        row = c.execute('SELECT id FROM users WHERE is_primary=1').fetchone()
        actor_id = row['id'] if row else None
        before = {table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('sources','pages','passages','users','tickets','messages')}
    results = []
    for book, pages in prepared:
        result = apply_book(book, pages, actor_id)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    with k.db() as c:
        after = {table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in before}
        integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys = len(c.execute('PRAGMA foreign_key_check').fetchall())
    report = dict(timestamp=k.now(), backup=backup_path, before=before, after=after,
                  integrity=integrity, foreign_key_errors=foreign_keys, files=results,
                  note='Only local extraction and OCR. No live OpenAI/audio call or model training performed.')
    target = INTAKE / ('import-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SUMMARY', json.dumps(dict(new=sum(x['created'] for x in results), existing=sum(not x['created'] for x in results),
        approved=sum(x['status']=='approved' for x in results), pending_pages=sum(x['pending_pages'] for x in results),
        counts=after, integrity=integrity, report=target.relative_to(k.ROOT).as_posix()), ensure_ascii=False))

if __name__ == '__main__':
    main()
