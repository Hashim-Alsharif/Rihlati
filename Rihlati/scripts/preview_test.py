"""Isolated UI preview. Synthetic accounts only, provider disabled, port 8081."""
import tempfile
from pathlib import Path
from waitress import serve
import accounts as ac
import ai_provider as ai
import knowledge as k
from api_server import create_app

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='rihlati-ui-',dir=k.ROOT/'data') as folder:
        k.DATABASE=Path(folder)/'preview.sqlite3'
        ai.key=lambda:''
        app=create_app(testing=True)
        ac.seed_primary('UI-test-password-2030!')
        ac.create_user({'display_name':'عضو اختبار','username':'member','password':'UI-test-password-2030!'},'member')
        office=ac.create_user({'display_name':'مختص اختبار','username':'office','office_name':'مكتب الاختبار','password':'UI-test-password-2030!'},'office')
        with k.db() as c:
            c.execute('UPDATE users SET must_change_password=0 WHERE is_primary=1')
            c.execute("UPDATE offices SET status='approved'")
            uid=c.execute("SELECT id FROM users WHERE username='member'").fetchone()[0]
            oid=c.execute('SELECT office_id FROM users WHERE id=?',(office,)).fetchone()[0]
        ac.set_links(uid,[oid],'test')
        # Explicitly synthetic references for reader/layout QA; no religious claims.
        from pypdf import PdfWriter
        book=Path(folder)/'ui-test-only.pdf'
        writer=PdfWriter();writer.add_blank_page(width=595,height=842);writer.write(book)
        with k.db() as c:
            for level in (1,2,3):
                c.execute('INSERT INTO sources(id,title,language,file_name,file_path,page_count,imported_at,status,level,subject,collection) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          ('ui-'+str(level),'مرجع واجهة تجريبي — المستوى '+str(level),'ar',book.name,book.relative_to(k.ROOT).as_posix(),1,k.now(),'approved',level,'general','بيانات اختبار فقط'))
            for sid,title,lang,level,status in [('ui-en','English general reference — TEST ONLY','en',0,'approved'),('ui-fil','Filipino reference — TEST ONLY','fil',2,'approved'),('ui-tl','Legacy Tagalog reference — TEST ONLY','tl',3,'approved'),('ui-review','بطاقة اختبار تحتاج مراجعة — ليست مرجعًا دينيًا','am',0,'pending_review')]:
                c.execute('INSERT INTO sources(id,title,language,file_name,file_path,page_count,imported_at,status,level,subject,collection,processing_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(sid,title,lang,book.name,book.relative_to(k.ROOT).as_posix(),1,k.now(),status,level,'general','بيانات اختبار فقط','needs_review' if status=='pending_review' else 'ready'))
            c.execute('INSERT INTO pages(source_id,page_number,extraction_status,raw_text,confidence) VALUES(?,?,?,?,?)',('ui-review',1,'needs_review','Synthetic text awaiting local test review.',62))
        print('Isolated preview http://localhost:8081; no live database or provider.',flush=True)
        serve(app,host='127.0.0.1',port=8081,threads=4)
