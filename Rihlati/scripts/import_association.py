"""Resumable import of the supplied three-level curriculum; existing data survives."""
import argparse
import json
import sqlite3
from pathlib import Path
from knowledge import ROOT, DATABASE, db, migrate, register_pdf, index_pdf, classify

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    backup=ROOT/'data/backups/before-association.sqlite3'
    backup.parent.mkdir(parents=True,exist_ok=True)
    if DATABASE.exists() and not backup.exists():
        with sqlite3.connect(DATABASE) as source, sqlite3.connect(backup) as target:
            source.backup(target)
    migrate()
    manifest=[]
    levels={'المستوى الأول':1,'المستوى الثاني':2,'المستوى الثالث':3}
    for path in sorted((ROOT/'data/library/كتب جمعية العنايه بالمسلمين الجدد').rglob('*.pdf')):
        level=levels[path.parent.name]
        subject=next((value for key,value in [('التوحيد','tawhid'),('فقه','fiqh'),('حديث','hadith'),('السيرة','sirah')] if key in path.name),'general')
        title={'tawhid':'التوحيد','fiqh':'الفقه','hadith':'الحديث','sirah':'السيرة'}[subject]+' — '+path.parent.name
        sid,_=register_pdf(path,title=title,level=level,subject=subject,collection='جمعية العناية بالمسلمين الجدد',approved=True)
        with db() as c:
            count=c.execute('SELECT page_count FROM sources WHERE id=?',(sid,)).fetchone()[0]
        manifest.append({'id':sid,'path':path.relative_to(ROOT).as_posix(),'title':title,'page_count':count})
        if not args.prepare:
            pages=json.loads((ROOT/'data/ocr'/f'{sid}.json').read_text('utf-8'))
            index_pdf(sid,pages)
            print(f'Indexed {sid}: {len(pages)} pages',flush=True)
    (ROOT/'data/ocr/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    with db() as c:
        for row in c.execute('SELECT source_id,page_number,raw_text FROM pages').fetchall():
            c.execute('UPDATE pages SET kind=? WHERE source_id=? AND page_number=?',(classify(row['raw_text']),row['source_id'],row['page_number']))
    print(f'Books: {len(manifest)}, pages: {sum(b["page_count"] for b in manifest)}',flush=True)

if __name__=='__main__':
    main()
