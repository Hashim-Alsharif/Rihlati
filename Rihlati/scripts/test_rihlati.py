"""Isolated regression checks. Never touches the user's live database or external APIs."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import knowledge as k
import assistant_engine as engine
import ai_provider as ai

class RihlatiTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='test-',dir=k.ROOT/'data');self.original=k.DATABASE;k.DATABASE=Path(self.temp.name)/'test.sqlite3';k.migrate()
        self.provider=patch.object(ai,'key',return_value='');self.provider.start()
        with k.db() as c:
            c.execute('INSERT INTO sources(id,title,language,file_name,page_count,imported_at,status,level,subject) VALUES(?,?,?,?,?,?,?,?,?)',('test','مرجع اختبار','ar','test.pdf',1,k.now(),'approved',1,'tawhid'))
            c.execute('INSERT INTO pages(source_id,page_number,extraction_status,raw_text) VALUES(?,?,?,?)',('test',1,'extracted','التوحيد هو إفراد الله بالعبادة.'))
            c.execute('INSERT INTO passages(source_id,page_number,chunk_index,language,content,normalized_content) VALUES(?,?,?,?,?,?)',('test',1,0,'ar','التوحيد هو إفراد الله بالعبادة.',k.normalize('التوحيد هو إفراد الله بالعبادة.')))
        self.conv=engine.conversation(language='ar')
    def tearDown(self):
        self.provider.stop();k.DATABASE=self.original;self.temp.cleanup()
    def test_migration_preserves_messages_and_tickets(self):
        engine.chat(self.conv,'سؤال فلكي خارج الكتب','ar');k.migrate()
        self.assertEqual(len(engine.messages(self.conv['id'])),2)
        with k.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM tickets').fetchone()[0],1)
    def test_library_answer_has_real_citation(self):
        response=engine.respond('ما معنى التوحيد؟','ar',[])
        self.assertEqual(response['mode'],'library_excerpt');self.assertEqual(response['citations'][0]['page_number'],1)
    def test_unknown_question_creates_ticket(self):
        response=engine.chat(self.conv,'كيف أصلح محرك السيارة؟','ar')
        self.assertIsNotNone(response.get('ticket_id'))
    def test_sensitive_question_routes_to_specialist(self):
        response=engine.respond('طلقت زوجتي ماذا أفعل؟','ar',[])
        self.assertTrue(response['escalate']);self.assertFalse(response['citations'])
    def test_greeting_needs_no_ticket(self):
        response=engine.chat(self.conv,'السلام عليكم','ar')
        self.assertFalse(response['escalate']);self.assertNotIn('ticket_id',response)
    def test_user_request_preserves_original_question(self):
        engine.chat(self.conv,'ما معنى التوحيد؟','ar');message=engine.messages(self.conv['id'])[-1]
        ticket=engine.escalate_message(self.conv,message['id'])
        with k.db() as c:self.assertEqual(c.execute('SELECT question FROM tickets WHERE id=?',(ticket['id'],)).fetchone()[0],'ما معنى التوحيد؟')
    def test_duplicate_escalation_reuses_ticket(self):
        engine.chat(self.conv,'ما معنى التوحيد؟','ar');message=engine.messages(self.conv['id'])[-1]
        one=engine.escalate_message(self.conv,message['id']);two=engine.escalate_message(self.conv,message['id'])
        self.assertEqual(one['id'],two['id'])
    def test_other_conversation_cannot_escalate_message(self):
        engine.chat(self.conv,'السلام عليكم','ar');message=engine.messages(self.conv['id'])[-1]
        with self.assertRaises(ValueError):engine.escalate_message(engine.conversation(),message['id'])
    def test_pending_correction_is_not_used(self):
        cid=engine.correction_create({'question':'ما تعريف اختبار المعرفة؟','answer':'إجابة الاختبار المعتمدة','source_note':'مرجع اختبار ص 1','reviewer':'مراجع اختبار','language':'ar'})
        self.assertIsNone(k.approved_correction('ما تعريف اختبار المعرفة؟','ar'))
        engine.correction_status(cid,'approved')
        self.assertEqual(engine.respond('ما تعريف اختبار المعرفة؟','ar',[])['mode'],'reviewed_answer')
        engine.correction_status(cid,'pending');self.assertIsNone(k.approved_correction('ما تعريف اختبار المعرفة؟','ar'))
    def test_specialist_reply_reaches_conversation_and_review_queue(self):
        answer=engine.chat(self.conv,'أريد سؤالًا تجريبيًا خارج المصادر','ar')
        engine.reply_ticket(answer['ticket_id'],{'response':'جواب اختبار خاص','reviewer':'مختص اختبار','source_note':'توثيق اختبار','learn':True})
        self.assertEqual(engine.messages(self.conv['id'])[-1]['mode'],'specialist')
        with k.db() as c:self.assertEqual(c.execute('SELECT status FROM corrections').fetchone()[0],'pending')
    def test_general_tawhid_is_not_treated_as_personal_fatwa(self):
        self.assertFalse(engine.respond('ما معنى التوحيد؟','ar',[])['escalate'])
    def test_unreviewed_ocr_is_not_quoted_directly_to_learner(self):
        with k.db() as c:c.execute("UPDATE pages SET extraction_status='ocr',confidence=90")
        response=engine.respond('ما معنى التوحيد؟','ar',[])
        self.assertTrue(response['escalate'])
        self.assertNotIn('إفراد الله بالعبادة',response['content'])
        self.assertTrue(response['citations'])
    def test_correction_does_not_ignore_negation(self):
        cid=engine.correction_create({'question':'هل أصلي؟','answer':'إجابة اختبار عامة','source_note':'مرجع اختبار','reviewer':'مراجع','language':'ar'})
        engine.correction_status(cid,'approved')
        self.assertIsNone(k.approved_correction('هل لا أصلي؟','ar'))
    def test_bad_ai_citations_trigger_escalation(self):
        with patch.object(ai,'key',return_value='mock'),patch.object(ai,'rewrite',return_value='التوحيد'),patch.object(ai,'grounded_answer',return_value={'answer':'test','citation_ids':['made-up'],'needs_specialist':False,'follow_up':''}):
            self.assertTrue(engine.respond('ما معنى التوحيد؟','ar',[])['escalate'])
    def test_valid_ai_answer_uses_citations(self):
        pid=k.search('التوحيد')[0]['citation_id']
        with patch.object(ai,'key',return_value='mock'),patch.object(ai,'rewrite',return_value='التوحيد'),patch.object(ai,'grounded_answer',return_value={'answer':'التوحيد هو إفراد الله بالعبادة.','citation_ids':[pid],'needs_specialist':False,'follow_up':'هل تريد المزيد؟'}):
            self.assertEqual(engine.respond('ما معنى التوحيد؟','ar',[])['mode'],'ai')
    def test_generated_answer_gets_separate_evidence_review(self):
        draft={'answer':'draft','citation_ids':['p1'],'needs_specialist':False,'follow_up':''}
        reviewed={'answer':'checked','citation_ids':['p1'],'needs_specialist':False,'follow_up':''}
        with patch.object(ai,'model_json',side_effect=[draft,reviewed]) as provider:
            answer=ai.grounded_answer('اختبار',[],[{'citation_id':'p1','title':'test','page_number':1,'content':'نص مصدر'}],'ar')
            self.assertEqual(answer['answer'],'checked')
            self.assertEqual(provider.call_count,2)
            self.assertEqual(provider.call_args.args[1]['draft'],draft)
    def test_original_question_recovers_from_overexpanded_rewrite(self):
        pid=k.search('التوحيد')[0]['citation_id']
        with patch.object(ai,'key',return_value='mock'),patch.object(ai,'rewrite',return_value='مصطلحات إضافية كثيرة لا توجد في المرجع'),patch.object(ai,'grounded_answer',return_value={'answer':'جواب من المرجع','citation_ids':[pid],'needs_specialist':False,'follow_up':''}):
            self.assertEqual(engine.respond('ما معنى التوحيد؟','ar',[])['mode'],'ai')
    def test_unapproved_source_not_retrieved(self):
        with k.db() as c:c.execute("UPDATE sources SET status='pending_review'")
        self.assertEqual(k.search('التوحيد'),[])
    def test_filipino_retrieval_includes_legacy_tagalog_without_other_languages(self):
        with k.db() as c:c.execute("UPDATE sources SET language='tl' WHERE id='test'")
        self.assertEqual(k.search('التوحيد',language='fil')[0]['source_id'],'test')
        self.assertEqual(k.search('التوحيد',language='fr'),[])
        cid=engine.correction_create({'question':'Tanong test','answer':'Sagot test','source_note':'Test p1','reviewer':'Test reviewer','language':'fil'})
        engine.correction_status(cid,'approved')
        self.assertEqual(k.approved_correction('Tanong test','tl')['id'],cid)
        self.assertTrue(k.search('Sagot',language='tl'))
        with k.db() as c:self.assertEqual(c.execute("SELECT language FROM sources WHERE id='test'").fetchone()[0],'tl')
    def test_approved_correction_is_also_searchable(self):
        cid=engine.correction_create({'question':'ما معنى الأمانة؟','answer':'الأمانة إجابة عامة للاختبار فقط.','source_note':'مصدر اختبار','reviewer':'مراجع','language':'ar'})
        self.assertEqual(k.search('الأمانة'),[])
        engine.correction_status(cid,'approved')
        self.assertEqual(k.search('الأمانة')[0]['citation_id'],'c'+str(cid))
    def test_page_review_reindexes_and_retains_original_in_audit(self):
        k.review_page('test',1,'هذا نص صفحة مراجع للاختبار يحتوي موضوع الاختبار المختلف والموثق.','مراجع')
        self.assertTrue(k.search('المختلف'))
        with k.db() as c:
            record=json.loads(c.execute("SELECT details FROM audit WHERE action='page_reviewed'").fetchone()[0]);self.assertIn('التوحيد',record['previous_text'])
    def test_chunk_length_is_bounded(self):
        self.assertTrue(all(len(text)<=950 for text in k.chunks('كلمة '*3000)))
    def test_reimport_preserves_reviewed_text_and_citation_id(self):
        text='هذا نص مراجع يدويًا للاختبار يجب أن يبقى محفوظًا عند إعادة استيراد الكتاب.'
        k.review_page('test',1,text,'مراجع')
        before=k.search('محفوظًا')[0]['citation_id']
        with patch.object(k,'PdfReader',return_value=SimpleNamespace(pages=[object()])):
            k.index_pdf('test',[{'page':1,'text':'نص استخراج قديم غير صحيح لا يجوز أن يمسح المراجعة اليدوية.','confidence':50}])
        with k.db() as c:
            page=c.execute('SELECT * FROM pages').fetchone()
            self.assertEqual(page['raw_text'],text)
            self.assertEqual(page['extraction_status'],'reviewed')
        self.assertEqual(k.search('محفوظًا')[0]['citation_id'],before)
        self.assertEqual(k.library()['stats']['review_pages'],0)
    def test_missing_audio_key_is_explicit(self):
        with self.assertRaises(ai.ProviderError) as error:ai.speak('اختبار','ar')
        self.assertEqual(error.exception.code,'not_configured')
    def test_tts_requests_arabic_instructions_and_mp3(self):
        with patch.object(ai,'request',return_value=b'audio') as request:
            self.assertEqual(ai.speak('هذا اختبار للصوت.','ar'),b'audio')
            payload=request.call_args.args[1]
            self.assertEqual(payload['response_format'],'mp3');self.assertIn('الفصحى',payload['instructions'])
    def test_transcription_sends_language_and_supported_format(self):
        with patch.object(ai,'request',return_value={'text':'اختبار'}) as request:
            ai.transcribe(b'recording','audio/mp4','ar')
            body=request.call_args.kwargs['body']
            self.assertIn(b'question.mp4',body);self.assertIn(b'name="language"\r\n\r\nar',body)
    def test_secret_encryption_roundtrip(self):
        if __import__('os').name!='nt':self.skipTest('Windows DPAPI test')
        value=b'not-a-real-api-key-for-a-local-unit-test'
        ciphertext=ai.protect(value)
        self.assertNotEqual(ciphertext,value);self.assertEqual(ai.protect(ciphertext,True),value)
    def test_restart_preserves_conversation_identity(self):
        engine.chat(self.conv,'السلام عليكم','ar');again=engine.conversation(self.conv['id'])
        self.assertEqual(again['learner_id'],self.conv['learner_id']);self.assertEqual(len(engine.messages(again['id'])),2)

if __name__=='__main__':unittest.main(verbosity=2)
