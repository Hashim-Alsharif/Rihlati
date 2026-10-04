"""Read-only inventory of the user-supplied curriculum and existing references."""
import hashlib
import json
import sqlite3
from pathlib import Path
from pypdf import PdfReader
from PIL import Image
from knowledge import ROOT, DATABASE

folder=ROOT/'data/library/مناهج المسلمين الجدد'
with sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True) as c:
    sources=c.execute('SELECT id,title,language,sha256,status,processing_status FROM sources').fetchall()
    print('EXISTING',json.dumps(sources,ensure_ascii=False),flush=True)
    print('EXISTING_COUNTS',json.dumps({table:c.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('sources','pages','passages','users','tickets','messages')},ensure_ascii=False),flush=True)
digests={row[3]:row[0] for row in sources if row[3]}
for file in sorted(folder.rglob('*')):
    if not file.is_file() or file.suffix.lower()=='.dat':continue
    record={'file':file.relative_to(folder).as_posix(),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
    record['existing']=digests.get(record['sha256'])
    if file.suffix.lower()=='.pdf':
        reader=PdfReader(file);record['pages']=len(reader.pages)
        record['samples']=[{'page':i+1,'text':(reader.pages[i].extract_text() or '')[:900]} for i in sorted({0,min(2,len(reader.pages)-1),len(reader.pages)//2})]
    elif file.suffix.lower() in ('.jpg','.png','.jpeg'):
        with Image.open(file) as img:record['size']=img.size
    print(json.dumps(record,ensure_ascii=False),flush=True)
