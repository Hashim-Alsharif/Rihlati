"""Read-only post-import checks; the AI provider is explicitly disabled."""
from collections import Counter
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
import knowledge as k
import assistant_engine as engine
import ai_provider as ai
from import_curricula import INTAKE, checked_file

manifest = json.loads((INTAKE/'manifest.json').read_text(encoding='utf-8'))
report_path = sorted(INTAKE.glob('import-*.json'))[-1]
report = json.loads(report_path.read_text(encoding='utf-8'))
backup = k.ROOT/report['backup']
def connect(path):
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    return c

with connect(k.DATABASE) as live, connect(backup) as before:
    preserved = {}
    for table in ('users','learners','offices','member_offices','tickets','conversations','messages','corrections','lessons_completed'):
        one={tuple(r) for r in before.execute('SELECT * FROM '+table)}
        two={tuple(r) for r in live.execute('SELECT * FROM '+table)}
        preserved[table] = one == two
    assert all(preserved.values()), 'A protected table changed; investigate before delivery'
    print('PROTECTED_TABLES_UNCHANGED',json.dumps(preserved))
    integrity=live.execute('PRAGMA integrity_check').fetchone()[0]
    assert integrity=='ok' and not live.execute('PRAGMA foreign_key_check').fetchall()
    seen=set();searchable=0
    for book in manifest:
        checked_file(book['original'],book['original_sha256'])
        checked_file(book['path'],book['sha256'])
        rows=live.execute('SELECT id,status,language FROM sources WHERE sha256=?',(book['sha256'],)).fetchall()
        assert len(rows)==1, 'Missing/duplicate file'
        sid=rows[0]['id'];assert sid not in seen;seen.add(sid)
        assert live.execute('SELECT count(*) FROM pages WHERE source_id=?',(sid,)).fetchone()[0]==book['page_count']
        sample=live.execute("SELECT p.content FROM passages p JOIN pages g ON p.source_id=g.source_id AND p.page_number=g.page_number WHERE p.source_id=? AND g.kind='content' AND g.extraction_status IN ('extracted','ocr','reviewed') ORDER BY p.id LIMIT 1",(sid,)).fetchone()
        if rows[0]['status']=='approved' and sample:
            query=' '.join(k.terms(sample['content'])[:4])
            hits=k.search(query,language=book['language'],source_id=sid)
            assert hits and all(h['source_id']==sid and 1<=h['page_number']<=book['page_count'] for h in hits)
            searchable+=1
    print('ALL_FILES_ACCOUNTED_FOR',len(seen),'SEARCHABLE_REFERENCES',searchable,'INTEGRITY',integrity)
    pending=[dict(r) for r in live.execute("SELECT s.title,p.source_id,p.page_number,p.extraction_status,p.confidence FROM pages p JOIN sources s ON s.id=p.source_id WHERE p.source_id IN ("+','.join('?' for _ in seen)+") AND p.extraction_status IN ('needs_review','needs_ocr') ORDER BY s.title,p.page_number",list(seen))]
    print('PENDING_PAGE_COUNT',len(pending))

queries={'ar':'ما معنى التوحيد؟','en':'What is prayer?','fil':'Ano ang Salah?','fr':'prière','sw':'swala','am':'ሠላት'}
checks=[]
with patch.object(ai,'key',return_value=''):
    for language,question in queries.items():
        result=engine.respond(question,language,[])
        assert result['citations'], 'No citation for '+language
        assert result['mode'] != 'ai', 'Must not call a provider in this verification'
        checks.append(dict(language=language,question=question,mode=result['mode'],citations=[
            {field:c.get(field) for field in ('source_id','page_number','citation_id','title')} for c in result['citations']]))
        print('LOCAL_RETRIEVAL',json.dumps(checks[-1],ensure_ascii=False))
result=dict(protected_tables_unchanged=preserved,original_files_unchanged=True,files=len(seen),
            searchable_sources=searchable,integrity=integrity,queries=checks,pending_pages=pending,
            provider_calls=0,verification='Local retrieval, not a live AI/audio test')
(INTAKE/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('VERIFICATION_COMPLETE')
