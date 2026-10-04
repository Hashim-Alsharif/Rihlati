"""Isolated intake tests: no live DB, no provider or OCR call."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfWriter
import knowledge as k
import import_curricula as intake

class CurriculumTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='test-intake-', dir=k.ROOT/'data')
        self.folder = Path(self.temp.name)
        self.original = k.DATABASE
        k.DATABASE = self.folder/'isolated.sqlite3'
        k.migrate()
        path = self.folder/'reference.pdf'
        writer = PdfWriter(); writer.add_blank_page(width=200, height=300)
        with path.open('wb') as out: writer.write(out)
        relative = path.relative_to(k.ROOT).as_posix()
        digest = intake.sha256(path)
        self.book = dict(id='book-'+digest[:18],sha256=digest,path=relative,original=relative,
            original_sha256=digest,language='en',title='Intake test',level=0,curriculum_stage=4,
            subject='general',collection='Test',page_count=1,ocr_pages=[])
        self.page = dict(page=1,text='Prayer is an important daily practice for a new Muslim and is taught in this source.',
                         method='embedded-text',confidence=None)

    def tearDown(self):
        k.DATABASE = self.original
        self.temp.cleanup()

    def test_new_source_is_searchable_and_repeat_preserves_citations(self):
        records = [intake.page_record(self.page,self.book)]
        first = intake.apply_book(self.book,records)
        self.assertTrue(first['created']); self.assertEqual(first['status'],'approved')
        hit = k.search('Prayer',language='en')[0]
        second = intake.apply_book(self.book,records)
        self.assertFalse(second['created']); self.assertEqual(second['changed_pages'],0)
        self.assertEqual(k.search('Prayer',language='en')[0]['citation_id'],hit['citation_id'])
        with k.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM sources').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT count(*) FROM audit WHERE action='curriculum_intake'").fetchone()[0],1)
            self.assertEqual(c.execute('SELECT level FROM sources').fetchone()[0],0)

    def test_reviewed_page_is_never_replaced(self):
        first = intake.apply_book(self.book,[intake.page_record(self.page,self.book)])
        reviewed = 'This text was checked by a specialist and must remain unchanged for future citations.'
        k.review_page(first['id'],1,reviewed,'Test reviewer')
        before = k.search('specialist',language='en')[0]['citation_id']
        intake.apply_book(self.book,[intake.page_record(self.page,self.book)])
        hit = k.search('specialist',language='en')[0]
        self.assertEqual(hit['content'],reviewed); self.assertEqual(hit['citation_id'],before)

    def test_reindex_preserves_native_word_text_and_citation(self):
        result=intake.apply_book(self.book,[intake.page_record(dict(self.page,method='word-native'),self.book)])
        hit=k.search('Prayer',language='en')[0]
        k.index_pdf(result['id'])
        after=k.search('Prayer',language='en')[0]
        self.assertEqual(after['content'],hit['content'])
        self.assertEqual(after['citation_id'],hit['citation_id'])
        self.assertEqual(after['extraction_status'],'extracted')

    def test_low_confidence_is_stored_but_never_searchable(self):
        page = dict(self.page, method='tesseract-ara',confidence=45)
        result = intake.apply_book(self.book,[intake.page_record(page,self.book)])
        self.assertEqual(result['status'],'pending_review'); self.assertEqual(result['passages'],0)
        self.assertEqual(result['pending_pages'],1); self.assertEqual(k.search('Prayer'),[])

    def test_existing_pending_source_not_approved_on_repeat(self):
        k.register_pdf(k.ROOT/self.book['path'],language='en',approved=False)
        records = [intake.page_record(self.page,self.book)]
        for _ in range(2):
            result = intake.apply_book(self.book,records)
            self.assertEqual(result['status'],'pending_review')

    def test_bad_font_mapping_and_wrong_script_are_quarantined(self):
        damaged = dict(self.page,text=self.page['text']+'\ue000'*20)
        self.assertEqual(intake.page_record(damaged,self.book)['status'],'needs_review')
        self.assertEqual(intake.page_record(self.page,dict(self.book,language='am'))['status'],'needs_review')

    def test_hash_and_incomplete_ocr_fail_before_import(self):
        with self.assertRaises(ValueError):intake.checked_file(self.book['path'],'wrong')
        (self.folder/(self.book['id']+'.embedded.json')).write_text(json.dumps([self.page]),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'OCR is not complete'):
            intake.load_pages(dict(self.book,ocr_pages=[1]),self.folder)
        with k.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM sources').fetchone()[0],0)

    def test_unknown_extraction_method_rejected(self):
        with self.assertRaises(ValueError):intake.page_record(dict(self.page,method='generated-answer'),self.book)

    def test_contents_pages_are_not_answers(self):
        for header in ('توزيع المنهج على أسابيع الدراسة','Contents Page','Le contenu La page','Ang Nilalaman Ang\npahina'):
            text=header+'\n'+'\n'.join('Prayer lesson '+str(i) for i in range(1,12))
            self.assertEqual(k.classify(text),'navigation')
        self.assertEqual(k.classify('A table of contents helps readers find a topic, while this paragraph explains prayer.'),'content')
        text='Contents Page\n'+'\n'.join('Prayer '+str(i) for i in range(1,12))
        result=intake.apply_book(self.book,[intake.page_record(dict(self.page,text=text),self.book)])
        with k.db() as c:c.execute("UPDATE sources SET status='approved' WHERE id=?",(result['id'],))
        self.assertEqual(k.search('Prayer',language='en'),[])


    def test_native_word_page_overrides_bad_pdf_mapping(self):
        book=dict(self.book,original=self.book['original']+'.doc',ocr_pages=[])
        path=k.ROOT/book['original'];path.write_bytes(b'isolated mock Word source')
        book['original_sha256']=intake.sha256(path)
        (self.folder/(book['id']+'.embedded.json')).write_text(json.dumps([dict(self.page,text='bad PDF mapping')]),encoding='utf-8')
        native=dict(sha256=book['sha256'],original_sha256=book['original_sha256'],pages=[dict(self.page,method='word-native')])
        (self.folder/(book['id']+'.native-word.json')).write_text(json.dumps(native),encoding='utf-8')
        result=intake.load_pages(book,self.folder)
        self.assertEqual(result[0]['text'],self.page['text'])
        self.assertEqual(result[0]['status'],'extracted')
        native['original_sha256']='changed'
        (self.folder/(book['id']+'.native-word.json')).write_text(json.dumps(native),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Stale Word'):intake.load_pages(book,self.folder)

if __name__=='__main__':unittest.main()
