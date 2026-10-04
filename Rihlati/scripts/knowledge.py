"""Persistent, provenance-aware knowledge library. Imports never reset learner data."""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DATABASE = Path(os.environ.get('RIHLATI_DATABASE', ROOT / 'data/rihlati.sqlite3'))

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    connection = sqlite3.connect(DATABASE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def migrate():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,title TEXT NOT NULL,language TEXT NOT NULL,file_name TEXT NOT NULL,page_count INTEGER NOT NULL,imported_at TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pages(source_id TEXT NOT NULL,page_number INTEGER NOT NULL,extraction_status TEXT NOT NULL,raw_text TEXT NOT NULL,PRIMARY KEY(source_id,page_number),FOREIGN KEY(source_id) REFERENCES sources(id));
        CREATE TABLE IF NOT EXISTS passages(id INTEGER PRIMARY KEY AUTOINCREMENT,source_id TEXT NOT NULL,page_number INTEGER NOT NULL,chunk_index INTEGER NOT NULL,language TEXT NOT NULL,content TEXT NOT NULL,normalized_content TEXT NOT NULL,FOREIGN KEY(source_id,page_number) REFERENCES pages(source_id,page_number));
        CREATE TABLE IF NOT EXISTS learners(id TEXT PRIMARY KEY,display_name TEXT NOT NULL,language TEXT NOT NULL,learning_stage TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,last_active_at TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,learner_id TEXT,learner_name TEXT NOT NULL,question TEXT NOT NULL,language TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',source_context TEXT,specialist_response TEXT,assigned_to TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,learner_id TEXT NOT NULL,language TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,language TEXT NOT NULL,mode TEXT NOT NULL DEFAULT '',citations TEXT NOT NULL DEFAULT '[]',question TEXT NOT NULL DEFAULT '',ticket_id INTEGER,created_at TEXT NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(id));
        CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY AUTOINCREMENT,question TEXT NOT NULL,answer TEXT NOT NULL,language TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',source_note TEXT NOT NULL,reviewer TEXT NOT NULL,origin_message_id INTEGER,origin_ticket_id INTEGER,created_at TEXT NOT NULL,approved_at TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,entity_id TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id,id);
        CREATE INDEX IF NOT EXISTS idx_corrections_status_language ON corrections(status,language);
        CREATE INDEX IF NOT EXISTS idx_tickets_learner ON tickets(learner_id,id);
        CREATE INDEX IF NOT EXISTS idx_passages_source_page ON passages(source_id,page_number);
        CREATE TABLE IF NOT EXISTS lessons_completed(learner_id TEXT NOT NULL,source_id TEXT NOT NULL,completed_at TEXT NOT NULL,PRIMARY KEY(learner_id,source_id));
        ''')
        additions = {
            'sources': {'level':'INTEGER DEFAULT 0','subject':"TEXT DEFAULT 'general'",'collection':"TEXT DEFAULT ''",'file_path':"TEXT DEFAULT ''",'sha256':"TEXT DEFAULT ''",'processing_status':"TEXT DEFAULT 'ready'",'processing_error':"TEXT DEFAULT ''"},
            'pages': {'confidence':'REAL','kind':"TEXT DEFAULT 'content'",'extraction_method':"TEXT NOT NULL DEFAULT ''"},
            'tickets': {'conversation_id':'TEXT','message_id':'INTEGER'},
        }
        for table, columns in additions.items():
            existing = {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
            for name, spec in columns.items():
                if name not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')
        for source in c.execute('SELECT id,file_name,file_path FROM sources').fetchall():
            stored=Path(source['file_path']) if source['file_path'] else Path(source['file_name'])
            candidates=[ROOT/stored, ROOT/'references'/stored.name]
            candidates.extend((ROOT/'data/library').rglob(source['file_name']))
            for i,part in enumerate(stored.parts):
                if part.startswith('كتب '):
                    candidates.insert(0,ROOT/'data/library'/Path(*stored.parts[i:]))
            for candidate in candidates:
                resolved=candidate.resolve()
                if resolved.is_relative_to(ROOT) and resolved.is_file():
                    c.execute('UPDATE sources SET file_path=? WHERE id=?',(resolved.relative_to(ROOT).as_posix(),source['id']))
                    break
        c.execute("UPDATE sources SET processing_status='needs_review' WHERE processing_status='ready' AND EXISTS (SELECT 1 FROM pages WHERE source_id=sources.id AND extraction_status IN ('needs_ocr','needs_review'))")

def audit(c, action, entity_id, details=''):
    c.execute('INSERT INTO audit(action,entity_id,details,created_at) VALUES(?,?,?,?)',(action,str(entity_id),details,now()))

def source_path(value):
    path=(ROOT/str(value)).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('ملف المرجع غير متاح. / Source file unavailable.')
    return path

def normalize(text):
    text = unicodedata.normalize('NFKC', text).lower().replace('ـ','')
    text = re.sub(r'[\u0610-\u061a\u064b-\u065f\u0670]', '', text)
    return re.sub(r'\s+',' ',re.sub('[إأآٱ]','ا',text).replace('ى','ي').replace('ة','ه')).strip()

STOP = set(normalize('ما ماذا كيف هل من في عن على إلى أنا ان هو هي هذا هذه ذلك مع ثم او لا لي لدي اريد أريد معنى اشرح شرح ساعدني اعرف تعلم اتعلم ممكن كتاب كتب سؤال اسئلة the a an what how is are to of and please explain me can you i').split())
def terms(text):
    words = re.findall(r'[^\W\d_]{2,}', normalize(text), re.UNICODE)
    result = []
    for word in words:
        if word in STOP:
            continue
        if word.startswith('وال') and len(word)>5:
            word = word[3:]
        elif word.startswith('ال') and len(word)>4:
            word = word[2:]
        result.append(word)
    return result

def clean(text):
    text = unicodedata.normalize('NFKC',text).replace('\u00ad','').replace('\x00','')
    text = re.sub(r'[\u200e\u200f\u202a-\u202e]', '',text)
    return re.sub(r'\n{3,}','\n\n',re.sub(r'[ \t]+',' ',text)).strip()

def chunks(text, limit=950):
    lines = [line.strip() for line in text.splitlines() if line.strip() and not re.fullmatch(r'[\d\W]+',line.strip())]
    output, current = [], ''
    for line in lines:
        while len(line)>limit:
            cut = line.rfind(' ',0,limit)
            cut = cut if cut>0 else limit
            if current:
                output.append(current)
                current=''
            output.append(line[:cut])
            line=line[cut:].strip()
        if len(current)+len(line)>limit and current:
            output.append(current)
            current=''
        current = (current+'\n'+line).strip()
    if current:
        output.append(current)
    return output

def classify(text):
    n=normalize(text)
    if sum(char.isalpha() for char in text)<35:
        return 'sparse'
    # Navigation/lesson schedules are not evidence for answering a question.
    # Require multiple numeric entries as well as a source-visible heading,
    # so a paragraph merely mentioning a table of contents stays searchable.
    toc_markers=('توزيع المنهج على أسابيع الدراسة','contents page','table of contents',
                 'le contenu la page','ang nilalaman ang pahina')
    if sum(bool(re.search(r'\d',line)) for line in text.splitlines())>=5 and any(normalize(marker) in n for marker in toc_markers):
        return 'navigation'
    if ('مستوي التقييم' in n or 'اسئله تقويميه' in n or 'اختر الاجابه الصحيحه' in n or 'الوقتالفقراتالجلسه' in n or n.count('هل تستطيع')>=3 or n.count('هل تعرف')>=3 or ('فهرس' in n and len(text)<1800)):
        return 'exercise'
    return 'content'

def register_pdf(path, title=None, language='ar', level=0, subject='general', collection='', approved=False):
    path=Path(path).resolve()
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with db() as c:
        existing=c.execute('SELECT id FROM sources WHERE sha256=?',(digest,)).fetchone()
        if existing:
            return existing['id'],False
        sid='book-'+digest[:18]
        reader=PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('الملف محمي بكلمة مرور.')
        c.execute('INSERT INTO sources(id,title,language,file_name,page_count,imported_at,status,level,subject,collection,file_path,sha256,processing_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (sid,title or path.stem,language,path.name,len(reader.pages),now(),'approved' if approved else 'pending_review',level,subject,collection,path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),digest,'queued'))
        audit(c,'reference_added',sid,path.name)
    return sid,True

def index_pdf(sid, ocr_pages=None):
    with db() as c:
        source=dict(c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone())
        c.execute("UPDATE sources SET processing_status='indexing',processing_error='' WHERE id=?",(sid,))
    try:
        reader=PdfReader(ROOT/source['file_path'])
        records=[]
        for i,page in enumerate(reader.pages,1):
            if ocr_pages is not None:
                item=next((p for p in ocr_pages if p['page']==i),None)
                if item is None:
                    raise ValueError('OCR did not finish all pages')
                text=clean(item['text']); confidence=item['confidence']
                status='ocr' if confidence>=70 else 'needs_review'
            else:
                text=clean(page.extract_text() or ''); confidence=None; status='extracted'
            kind=classify(text)
            if kind=='sparse':
                status='needs_ocr' if ocr_pages is None else 'sparse'
            records.append((i,text,confidence,status,kind))
        with db() as c:
            # Read inside the write transaction: retain office reviews made even
            # while OCR was running, together with their stable citation IDs.
            # Original Word text was extracted against physical PDF pages.
            # Old Word PDF fonts can have a broken Unicode map: retain that
            # lossless original extraction, without calling it a human review.
            reviewed={row[0] for row in c.execute("SELECT page_number FROM pages WHERE source_id=? AND (extraction_status='reviewed' OR extraction_method='word-native')",(sid,))}
            c.execute("DELETE FROM passages WHERE source_id=? AND page_number NOT IN (SELECT page_number FROM pages WHERE source_id=? AND (extraction_status='reviewed' OR extraction_method='word-native'))",(sid,sid))
            c.execute("DELETE FROM pages WHERE source_id=? AND extraction_status!='reviewed' AND extraction_method!='word-native'",(sid,))
            for i,text,confidence,status,kind in records:
                if i in reviewed:
                    continue
                c.execute('INSERT INTO pages(source_id,page_number,extraction_status,raw_text,confidence,kind,extraction_method) VALUES(?,?,?,?,?,?,?)',(sid,i,status,text,confidence,kind,'ocr' if ocr_pages is not None else 'embedded-text'))
                if status in ('extracted','ocr') and kind!='sparse':
                    for j,chunk in enumerate(chunks(text)):
                        c.execute('INSERT INTO passages(source_id,page_number,chunk_index,language,content,normalized_content) VALUES(?,?,?,?,?,?)',(sid,i,j,source['language'],chunk,normalize(chunk)))
            incomplete=c.execute("SELECT COUNT(*) FROM pages WHERE source_id=? AND extraction_status IN ('needs_ocr','needs_review')",(sid,)).fetchone()[0]
            c.execute('UPDATE sources SET processing_status=? WHERE id=?',('needs_review' if incomplete else 'ready',sid))
            audit(c,'reference_indexed',sid,str(len(records)))
    except Exception as e:
        with db() as c:
            c.execute("UPDATE sources SET processing_status='failed',processing_error=? WHERE id=?",(type(e).__name__,sid))
        raise

def language_aliases(language):
    # Legacy Tagalog imports and the Filipino UI describe the same language.
    # Keep original source metadata; do not rewrite imported records.
    return ('fil','tl') if language in ('fil','tl') else (language,)

def search(query,language=None,source_id=None,level=None,subject=None,limit=8,include_exercises=False):
    query_terms=set(terms(query))
    if not query_terms:
        return []
    sql="""SELECT p.id,p.source_id,p.page_number,p.content,s.title,s.language,s.level,s.subject,s.collection,g.extraction_status,g.confidence,g.kind FROM passages p JOIN sources s ON s.id=p.source_id JOIN pages g ON g.source_id=p.source_id AND g.page_number=p.page_number WHERE s.status='approved'"""
    args=[]
    if language not in (None,'','all'):
        aliases=language_aliases(language)
        sql+=' AND s.language IN ('+','.join('?' for _ in aliases)+')';args.extend(aliases)
    for clause,value in [('s.id',source_id),('s.level',level),('s.subject',subject)]:
        if value not in (None,'','all'):
            sql+=f' AND {clause}=?';args.append(value)
    if not include_exercises:
        sql+=" AND g.kind NOT IN ('exercise','sparse','navigation')"
    with db() as c:
        rows=[dict(r) for r in c.execute(sql,args)]
        if not source_id and level in (None,'','all') and subject in (None,'','all'):
            for correction in c.execute("SELECT * FROM corrections WHERE status='approved'"):
                if language not in (None,'','all') and correction['language'] not in language_aliases(language):
                    continue
                rows.append({'id':correction['id'],'source_id':None,'page_number':None,'content':correction['question']+'\n'+correction['answer'],'title':'إجابة راجعها '+correction['reviewer'],'language':correction['language'],'level':0,'subject':'general','collection':'إجابات المختصين المعتمدة','extraction_status':'reviewed','confidence':100,'kind':'content','correction_id':correction['id'],'source_note':correction['source_note']})
    docs=[Counter(terms(r['content'])) for r in rows]
    if not docs:
        return []
    avg=sum(sum(d.values()) for d in docs)/len(docs) or 1
    idf={t:math.log(1+(len(docs)-sum(t in d for d in docs)+.5)/(sum(t in d for d in docs)+.5)) for t in query_terms}
    scored=[]
    for row,d in zip(rows,docs):
        hits=query_terms & d.keys()
        if not hits:
            continue
        score=sum(idf[t]*(d[t]*2.5)/(d[t]+1.5*(.25+.75*sum(d.values())/avg)) for t in hits)
        score*=len(hits)/len(query_terms)
        if any(term in normalize(query) for term in ('معني','تعريف','ما هو','ما هي','what is')):
            text=normalize(row['content'])
            # Boost a definition of the requested subject, not an unrelated occurrence of "meaning".
            for term in query_terms:
                if re.search(r'(?:معني|تعريف)\s+(?:ال)?'+re.escape(term)+r'\b',text):
                    score*=2.5
                elif re.search(r'(?:^|\s)(?:ال)?'+re.escape(term)+r'\s*(?:هو|هي)\b',text):
                    score*=1.5
        row.update(score=round(score,3),coverage=round(len(hits)/len(query_terms),3),citation_id=('c' if row.get('correction_id') else 'p')+str(row['id']))
        if row['source_id']:
            row['pdf_url']=f"/api/sources/{row['source_id']}/file#page={row['page_number']}"
        scored.append(row)
    return sorted(scored,key=lambda r:r['score'],reverse=True)[:limit]

def review_page(source_id,page_number,text,reviewer):
    text=clean(text)
    if len(text)<35 or not reviewer.strip():
        raise ValueError('اكتب النص المراجع واسم المراجع. يجب ألا يقل النص عن 35 حرفًا.')
    if len(text)>30000:
        raise ValueError('نص الصفحة أطول من الحد المسموح.')
    with db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone()
        old=c.execute('SELECT * FROM pages WHERE source_id=? AND page_number=?',(source_id,page_number)).fetchone()
        if not old or not source:
            raise ValueError('الصفحة غير موجودة.')
        # Preserve the previous text in the audit trail for reversal and provenance.
        audit(c,'page_reviewed',f'{source_id}:{page_number}',json.dumps({'reviewer':reviewer,'previous_text':old['raw_text'],'previous_status':old['extraction_status']},ensure_ascii=False))
        c.execute("UPDATE pages SET raw_text=?,extraction_status='reviewed',kind=? WHERE source_id=? AND page_number=?",(text,classify(text),source_id,page_number))
        c.execute('DELETE FROM passages WHERE source_id=? AND page_number=?',(source_id,page_number))
        for j,chunk in enumerate(chunks(text)):
            c.execute('INSERT INTO passages(source_id,page_number,chunk_index,language,content,normalized_content) VALUES(?,?,?,?,?,?)',(source_id,page_number,j,source['language'],chunk,normalize(chunk)))
        remaining=c.execute("SELECT COUNT(*) FROM pages WHERE source_id=? AND extraction_status IN ('needs_review','needs_ocr')",(source_id,)).fetchone()[0]
        c.execute('UPDATE sources SET processing_status=? WHERE id=?',('needs_review' if remaining else 'ready',source_id))

def library():
    with db() as c:
        sources=[dict(r) for r in c.execute('''SELECT s.*, (SELECT COUNT(*) FROM passages p WHERE p.source_id=s.id) AS passage_count,(SELECT COUNT(*) FROM pages p WHERE p.source_id=s.id AND p.extraction_status IN ('needs_ocr','needs_review')) AS review_pages FROM sources s ORDER BY s.collection,s.level,s.subject''')]
        for source in sources:
            source.pop('file_path',None)
        stats={'sources':len(sources),'passages':c.execute('SELECT COUNT(*) FROM passages').fetchone()[0],'pages':c.execute('SELECT COUNT(*) FROM pages').fetchone()[0], 'review_pages':c.execute("SELECT COUNT(*) FROM pages WHERE extraction_status IN ('needs_ocr','needs_review')").fetchone()[0]}
    return {'sources':sources,'stats':stats}

def approved_correction(question,language):
    q=normalize(question).strip(' .!?؟')
    with db() as c:
        aliases=language_aliases(language)
        rows=c.execute("SELECT * FROM corrections WHERE status='approved' AND language IN ("+','.join('?' for _ in aliases)+") ORDER BY approved_at DESC",aliases).fetchall()
    for row in rows:
        # Reuse only the same question; context-specific specialist rulings must not generalize.
        # Bag-of-words equivalence loses negation and can reverse the meaning.
        if q and q==normalize(row['question']).strip(' .!?؟'):
            return dict(row)
    return None
