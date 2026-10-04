"""Tag verified table-of-contents patterns, retaining text and citation IDs.

Default dry run. --apply only updates page kind for the current intake and
records before/after attribution. Human-reviewed pages are left unchanged.
"""
import argparse
import json
import knowledge as k
from import_curricula import INTAKE, backup

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply',action='store_true')
args=parser.parse_args()
books=json.loads((INTAKE/'manifest.json').read_text(encoding='utf-8'))
changes=[]
with k.db() as c:
    for book in books:
        source=c.execute('SELECT id FROM sources WHERE sha256=?',(book['sha256'],)).fetchone()
        if not source:continue
        for page in c.execute("SELECT page_number,raw_text FROM pages WHERE source_id=? AND kind='content' AND extraction_status!='reviewed'",(source['id'],)):
            if k.classify(page['raw_text'])=='navigation':
                changes.append((source['id'],page['page_number']))
if args.apply and changes:
    print('BACKUP',backup(),flush=True)
    with k.db() as c:
        c.execute('BEGIN IMMEDIATE')
        for sid,number in changes:
            changed=c.execute("UPDATE pages SET kind='navigation' WHERE source_id=? AND page_number=? AND kind='content' AND extraction_status!='reviewed'",(sid,number)).rowcount
            if changed:k.audit(c,'page_kind_classified',f'{sid}:{number}',json.dumps({'before':'content','after':'navigation','method':'source-visible TOC/schedule heading and numeric entries','human_review':False}))
print('APPLIED' if args.apply else 'DRY_RUN',len(changes),'navigation pages')
