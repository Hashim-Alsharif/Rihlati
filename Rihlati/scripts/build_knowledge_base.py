"""Incrementally import the original two books; never recreate the database."""
from knowledge import ROOT, db, migrate, register_pdf, index_pdf

SOURCES=('المختصر المفيد للمسلم الجديد','الوجيز للمسلم الجديد')

def main():
    migrate()
    for title in SOURCES:
        filename=title+'.pdf'
        with db() as c:
            existing=c.execute('SELECT id FROM sources WHERE file_name=?',(filename,)).fetchone()
        if existing:
            print('Preserved existing source: '+existing['id'])
            continue
        candidates=list((ROOT/'data/library').rglob(filename))
        if len(candidates)!=1:
            raise ValueError('Provide exactly one matching PDF in data/library: '+filename)
        sid,created=register_pdf(candidates[0],title=title,approved=False)
        if created:
            index_pdf(sid)
        print('Imported for administrator review: '+sid)

if __name__=='__main__':main()
