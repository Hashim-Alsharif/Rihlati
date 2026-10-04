"""Security/tenancy integration tests: isolated SQLite, mocked provider, no live calls."""
import io
import json
import string
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import knowledge as k
import accounts as ac
import ai_provider as ai
from api_server import create_app

PASSWORD='Test-only-strong-password-2030!'

class PasswordPolicyTests(unittest.TestCase):
    def test_length_boundaries_and_character_categories(self):
        for secret in ('Abcdef1!', 'ABCDEFG1!', 'A1!'+('a'*125), '  Abcd1!  '):
            with self.subTest(secret=secret):
                self.assertEqual(ac.password(secret),secret)
        for secret in (None, 12345678, '', 'Abcde1!', 'abcdef1!', 'Abcdefg!',
                       'Abcdef12', 'Abcdef1 ', 'عربي123!', 'Abcdef١!',
                       'Abcdef1ع', 'Abcdef1😀', 'A1!'+('a'*126)):
            with self.subTest(secret=secret),self.assertRaises(ValueError):
                ac.password(secret)

    def test_special_symbols_include_all_ascii_punctuation(self):
        for symbol in string.punctuation:
            self.assertEqual(ac.password('Abcdef1'+symbol),'Abcdef1'+symbol)

    def test_generated_temporary_password_always_meets_policy(self):
        values={ac.generate_temporary_password() for _ in range(100)}
        self.assertEqual(len(values),100)
        for secret in values:
            self.assertEqual(ac.password(secret),secret)

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rihlati-security-')
        self.old_db=k.DATABASE;k.DATABASE=Path(self.temp.name)/'isolated.sqlite3'
        self.provider=patch.object(ai,'key',return_value='');self.provider.start()
        self.app=create_app(testing=True)
        ac.seed_primary(PASSWORD)
        with k.db() as c:
            c.execute("UPDATE users SET must_change_password=0,email='admin@example.test',phone='+966555555555' WHERE is_primary=1")
            self.root=c.execute('SELECT id FROM users WHERE is_primary=1').fetchone()[0]
        self.admin=self.client('admin')
        self.member_id=self.new_user('member')
        self.member=self.client('member')

    def tearDown(self):
        self.provider.stop();k.DATABASE=self.old_db;self.temp.cleanup()

    def new_user(self,name,role='member',permissions=()):
        return ac.create_user({'username':name,'display_name':name,'password':PASSWORD,'office_name':'Office '+name},role,permissions=permissions)

    def client(self,name=None):
        client=self.app.test_client();result=client.get('/api/auth/session').get_json();client.csrf=result['csrf']
        if name:
            result=self.post(client,'/api/auth/login',{'username':name,'password':PASSWORD})
            self.assertEqual(result.status_code,200,result.get_json())
        return client

    def post(self,client,url,data=None,**kwargs):
        response=client.post(url,json=data or {},headers={'X-CSRF-Token':client.csrf},**kwargs)
        if response.is_json and response.get_json().get('csrf'):
            client.csrf=response.get_json()['csrf']
        return response

    def office(self,name):
        uid=self.new_user(name,'office')
        with k.db() as c:
            oid=c.execute('SELECT office_id FROM users WHERE id=?',(uid,)).fetchone()[0]
        self.assertEqual(self.post(self.admin,'/api/admin/offices/'+oid,{'status':'approved'}).status_code,200)
        return oid,self.client(name),uid

    def test_unauthenticated_routes_and_static_secrets(self):
        client=self.client()
        for path in ('/api/bootstrap','/api/dashboard','/api/sources','/api/admin/accounts'):
            self.assertEqual(client.get(path).status_code,401)
        for path in ('/.enviroment.local','/data/rihlati.sqlite3','/scripts/config.py','/../.enviroment.local'):
            self.assertEqual(client.get(path).status_code,404)
        self.assertEqual(client.get('/api/health').get_json()['status'],'ok')

    def test_csrf_and_origin_rejected(self):
        self.assertEqual(self.member.post('/api/profile',json={}).status_code,403)
        response=self.member.post('/api/profile',json={},headers={'X-CSRF-Token':self.member.csrf,'Origin':'https://evil.example'})
        self.assertEqual(response.status_code,403)

    def test_host_header_rejected(self):
        self.assertEqual(self.app.test_client().get('/api/health',headers={'Host':'evil.example'}).status_code,400)

    def test_member_cannot_use_office_or_admin(self):
        self.assertEqual(self.member.get('/api/dashboard').status_code,403)
        for path in ('/api/settings','/api/corrections','/api/evaluate','/api/admin/admins','/api/admin/registration'):
            self.assertEqual(self.post(self.member,path).status_code,403)

    def test_password_hashes_are_salted_and_never_returned(self):
        self.new_user('same-password')
        with k.db() as c:
            values=[r[0] for r in c.execute('SELECT password_hash FROM users')]
        self.assertTrue(all(v.startswith('$argon2id$') for v in values));self.assertEqual(len(values),len(set(values)))
        data=self.admin.get('/api/admin/accounts').get_data(as_text=True)
        self.assertNotIn('password_hash',data);self.assertNotIn(PASSWORD,data)

    def test_pending_office_cannot_access_workspace(self):
        self.new_user('pending','office');client=self.client('pending')
        self.assertEqual(client.get('/api/dashboard').status_code,403)
        self.assertEqual(client.get('/api/profile').status_code,200)

    def test_tenant_isolation_and_explicit_ticket_routing(self):
        first,one,_=self.office('one');second,two,_=self.office('two')
        ac.set_links(self.member_id,[first,second],self.member_id)
        response=self.post(self.member,'/api/tickets',{'question':'private question','office_id':first})
        tid=response.get_json()['ticket']['id']
        self.assertEqual(len(one.get('/api/dashboard').get_json()['tickets']),1)
        self.assertEqual(two.get('/api/dashboard').get_json()['tickets'],[])
        self.assertEqual(self.post(two,f'/api/tickets/{tid}/reply',{'response':'wrong office'}).status_code,403)
        self.assertEqual(self.post(one,f'/api/tickets/{tid}/reply',{'response':'Reviewed reply','reviewer':'forged reviewer','learn':True,'source_note':'Test p. 1'}).status_code,200)
        data=self.member.get('/api/bootstrap').get_json();self.assertEqual(data['messages'][-1]['content'],'Reviewed reply')
        with k.db() as c:
            row=c.execute('SELECT * FROM corrections').fetchone()
            self.assertEqual(row['status'],'pending');self.assertEqual(row['office_id'],first);self.assertNotEqual(row['reviewer'],'forged reviewer')

    def test_unlinked_office_cannot_see_learner(self):
        oid,office,_=self.office('unlinked')
        self.assertEqual(office.get('/api/dashboard').get_json()['learners'],[])
        self.assertEqual(self.post(self.member,'/api/tickets',{'question':'private','office_id':oid}).status_code,403)

    def test_max_three_offices_and_approved_only(self):
        ids=[self.office('office'+str(i))[0] for i in range(4)]
        self.assertEqual(self.post(self.member,'/api/profile/offices',{'office_ids':ids}).status_code,400)
        self.assertEqual(self.post(self.member,'/api/profile/offices',{'office_ids':ids[:3]}).status_code,200)
        self.assertEqual(self.post(self.member,'/api/profile/offices',{'office_ids':[]}).status_code,400)
        self.new_user('pending','office')
        with k.db() as c:
            pending=c.execute("SELECT office_id FROM users WHERE username='pending'").fetchone()[0]
        self.assertEqual(self.post(self.member,'/api/profile/offices',{'office_ids':[pending]}).status_code,400)

    def test_unlink_revokes_ticket_access_and_returns_open_ticket(self):
        oid,office,_=self.office('one');other,_,_=self.office('two');ac.set_links(self.member_id,[oid],self.member_id)
        tid=self.post(self.member,'/api/tickets',{'question':'question','office_id':oid}).get_json()['ticket']['id']
        ac.set_links(self.member_id,[other],self.root)
        self.assertEqual(office.get('/api/dashboard').get_json()['tickets'],[])
        with k.db() as c:self.assertIsNone(c.execute('SELECT office_id FROM tickets WHERE id=?',(tid,)).fetchone()[0])

    def test_primary_cannot_be_changed_or_reset(self):
        for path,p in [(f'/api/admin/users/{self.root}',{'status':'deleted'}),(f'/api/admin/users/{self.root}/temporary-password',{})]:
            self.assertEqual(self.post(self.admin,path,p).status_code,403)
        with k.db() as c:
            with self.assertRaises(Exception):c.execute('DELETE FROM users WHERE is_primary=1')

    def test_restricted_admin_cannot_escalate_or_reset_full_admin(self):
        limited=self.new_user('limited','admin',('admins',));full=self.new_user('full','admin',ac.PERMISSIONS);client=self.client('limited')
        self.assertEqual(self.post(client,'/api/admin/admins',{'display_name':'evil','username':'evil','password':PASSWORD,'permissions':['settings']}).status_code,403)
        self.assertEqual(self.post(client,f'/api/admin/users/{full}/temporary-password').status_code,403)
        self.assertEqual(self.post(client,f'/api/admin/users/{full}',{'permissions':['admins']}).status_code,403)
        self.assertEqual(self.post(client,'/api/settings',{}).status_code,403)

    def test_temporary_password_forces_change_and_revokes_old_session(self):
        response=self.post(self.admin,f'/api/admin/users/{self.member_id}/temporary-password').get_json()
        self.assertEqual(ac.password(response['temporary_password']),response['temporary_password'])
        self.assertEqual(self.member.get('/api/bootstrap').status_code,401)
        client=self.client();login=self.post(client,'/api/auth/login',{'username':'member','password':response['temporary_password']})
        self.assertEqual(login.status_code,200);self.assertEqual(client.get('/api/bootstrap').status_code,403)
        changed=self.post(client,'/api/profile/password',{'current_password':response['temporary_password'],'password':'Changed-test-password-2031!'})
        self.assertEqual(changed.status_code,200);self.assertEqual(client.get('/api/bootstrap').status_code,200)

    def test_registration_required_fields_are_server_enforced(self):
        self.post(self.admin,'/api/admin/registration',{'member':{'email':True,'phone':True},'office':{'email':True}})
        client=self.client();response=self.post(client,'/api/auth/register',{'display_name':'new','password':PASSWORD})
        self.assertEqual(response.status_code,400)
        response=self.post(client,'/api/auth/register',{'display_name':'new','password':PASSWORD,'email':'new@example.test','phone':'+966555555555'})
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.post(self.client(),'/api/auth/register',{'role':'admin','display_name':'evil','password':PASSWORD}).status_code,403)

    def test_member_records_do_not_adopt_legacy_conversation(self):
        import assistant_engine as engine
        legacy=engine.conversation();engine.chat(legacy,'hello','en')
        data=self.member.get('/api/bootstrap').get_json()
        self.assertEqual(data['messages'],[]);self.assertNotEqual(data['learner']['id'],legacy['learner_id'])

    def test_cannot_escalate_someone_elses_message(self):
        self.new_user('other');other=self.client('other')
        messages=self.post(other,'/api/ask',{'question':'hello','language':'en'}).get_json()['messages']
        self.assertEqual(self.post(self.member,'/api/tickets',{'message_id':messages[-1]['id']}).status_code,400)

    def test_office_staff_stays_in_own_office(self):
        oid,owner,_=self.office('owner')
        response=self.post(owner,'/api/office/staff',{'display_name':'Staff','username':'staff','password':PASSWORD,'office_id':'forged'})
        self.assertEqual(response.status_code,201)
        with k.db() as c:
            row=c.execute("SELECT office_id,office_owner,must_change_password FROM users WHERE username='staff'").fetchone()
        self.assertEqual(row['office_id'],oid);self.assertFalse(row['office_owner']);self.assertTrue(row['must_change_password'])

    def test_logout_revokes_session(self):
        self.post(self.member,'/api/auth/logout');self.assertEqual(self.member.get('/api/bootstrap').status_code,401)

    def test_security_headers_and_cookie(self):
        result=self.app.test_client().get('/api/auth/session')
        self.assertTrue(result.headers['Set-Cookie'].startswith('rihlati_test_auth='))
        self.assertIn('HttpOnly',result.headers['Set-Cookie']);self.assertIn('SameSite=Lax',result.headers['Set-Cookie'])
        self.assertEqual(result.headers['X-Content-Type-Options'],'nosniff');self.assertIn("frame-ancestors 'none'",result.headers['Content-Security-Policy'])

    def test_invalid_avatar_is_rejected(self):
        result=self.member.post('/api/profile/avatar',data=b'<svg onload="alert(1)"/>',headers={'X-CSRF-Token':self.member.csrf,'Content-Type':'image/svg+xml'})
        self.assertEqual(result.status_code,400)

    def test_language_validation_and_unicode_search(self):
        self.assertEqual(self.post(self.member,'/api/ask',{'question':'test','language':'zz'}).status_code,400)
        self.assertIn('እምነት',k.terms('እምነት'));self.assertIn('prière',k.terms('prière'))

    def test_migrations_preserve_existing_records(self):
        self.post(self.member,'/api/tickets',{'question':'retained'})
        k.migrate();ac.migrate()
        self.assertEqual(len(self.member.get('/api/bootstrap').get_json()['tickets']),1)

    def test_suspend_user_revokes_session(self):
        self.post(self.admin,f'/api/admin/users/{self.member_id}',{'status':'suspended'})
        self.assertEqual(self.member.get('/api/bootstrap').status_code,401)

    def test_wrong_password_is_generic(self):
        client=self.client();a=self.post(client,'/api/auth/login',{'username':'member','password':'incorrect-password'})
        b=self.post(client,'/api/auth/login',{'username':'missing','password':'incorrect-password'})
        self.assertEqual(a.status_code,401);self.assertEqual(a.get_json(),b.get_json())

    def test_password_whitespace_is_preserved_at_login_and_change(self):
        secret='  Test password with spaces 1!  '
        ac.create_user({'display_name':'spaces','username':'spaces','password':secret})
        client=self.client()
        self.assertEqual(self.post(client,'/api/auth/login',{'username':'spaces','password':secret}).status_code,200)
        self.assertEqual(self.post(client,'/api/profile/password',{'current_password':secret,'password':'  New password with spaces 2!  '}).status_code,200)

    def test_member_and_office_registration_enforce_new_password_policy(self):
        for role in ('member','office'):
            client=self.client()
            payload={'role':role,'display_name':'new-'+role,'username':'new-'+role,'office_name':'New office','password':'abcdef1!'}
            self.assertEqual(self.post(client,'/api/auth/register',payload).status_code,400)
            payload['password']='Abcdef1!'
            self.assertEqual(self.post(client,'/api/auth/register',payload).status_code,201)
            self.assertEqual(self.post(self.client(),'/api/auth/login',{'username':payload['username'],'password':payload['password']}).status_code,200)

    def test_admin_and_staff_creation_enforce_new_password_policy(self):
        _,owner,_=self.office('owner')
        for client,path,name in ((self.admin,'/api/admin/admins','admin-new'),(owner,'/api/office/staff','staff-new')):
            payload={'display_name':name,'username':name,'password':'Abcdef12','permissions':['tickets']}
            self.assertEqual(self.post(client,path,payload).status_code,400)
            payload['password']='Abcdef1!'
            self.assertEqual(self.post(client,path,payload).status_code,201)

    def test_legacy_password_login_and_change_remain_available(self):
        # Simulate a previously stored password that does not meet the new policy.
        legacy='  legacy password with spaces  '
        with k.db() as c:
            c.execute('UPDATE users SET password_hash=? WHERE id=?',(ac.HASHER.hash(legacy),self.member_id))
        client=self.client()
        self.assertEqual(self.post(client,'/api/auth/login',{'username':'member','password':legacy}).status_code,200)
        self.assertEqual(self.post(client,'/api/profile/password',{'current_password':legacy,'password':'abcdef1!'}).status_code,400)
        self.assertEqual(self.post(client,'/api/profile/password',{'current_password':legacy,'password':'Abcdef1!'}).status_code,200)
        self.assertEqual(self.post(self.client(),'/api/auth/login',{'username':'member','password':'Abcdef1!'}).status_code,200)

    def test_member_must_choose_an_approved_office_when_available(self):
        oid,_,_=self.office('available')
        self.assertEqual(self.member.get('/api/bootstrap').get_json()['code'],'office_selection_required')
        self.assertEqual(self.post(self.member,'/api/profile/offices',{'office_ids':[oid]}).status_code,200)
        self.assertEqual(self.member.get('/api/bootstrap').status_code,200)

    def test_ticket_deduplication_does_not_override_chosen_office(self):
        a,_,_=self.office('a');b,_,_=self.office('b');ac.set_links(self.member_id,[a,b],self.member_id)
        first=self.post(self.member,'/api/tickets',{'question':'same','office_id':a}).get_json()['ticket']['id']
        second=self.post(self.member,'/api/tickets',{'question':'same','office_id':b}).get_json()['ticket']['id']
        self.assertNotEqual(first,second)

    def test_explicit_central_ticket_does_not_go_to_single_office(self):
        oid,office,_=self.office('one');ac.set_links(self.member_id,[oid],self.member_id)
        result=self.post(self.member,'/api/tickets',{'question':'central','office_id':None})
        self.assertEqual(result.status_code,200)
        self.assertEqual(office.get('/api/dashboard').get_json()['tickets'],[])

    def test_office_cannot_approve_its_own_correction(self):
        _,office,_=self.office('one')
        p={'question':'general question','answer':'documented answer','source_note':'source p1','reviewer':'forged','language':'en'}
        cid=self.post(office,'/api/corrections',p).get_json()['id']
        self.assertEqual(self.post(office,f'/api/corrections/{cid}/status',{'status':'approved'}).status_code,403)
        self.assertEqual(self.post(self.admin,f'/api/corrections/{cid}/status',{'status':'approved'}).status_code,200)
        with k.db() as c:
            row=c.execute('SELECT * FROM corrections WHERE id=?',(cid,)).fetchone()
            self.assertEqual(row['approved_by_user_id'],self.root);self.assertTrue(row['created_by_user_id'])

    def test_source_upload_attribution_and_private_review_scope(self):
        from pypdf import PdfWriter
        oid,office,uid=self.office('one');_,other,_=self.office('two')
        writer=PdfWriter();writer.add_blank_page(width=72,height=72);stream=io.BytesIO();writer.write(stream)
        # PDF bytes and metadata are isolated, and no OCR subprocess is started.
        with patch('api_server.background_index'),patch.object(k,'ROOT',Path(self.temp.name)):
            response=office.post('/api/sources/upload',data=stream.getvalue(),headers={'X-CSRF-Token':office.csrf,'X-Filename':'test.pdf','X-Language':'en','X-Level':'1','X-Subject':'fiqh'})
            self.assertEqual(response.status_code,201,response.get_json());sid=response.get_json()['id']
            with k.db() as c:
                row=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
                self.assertEqual(row['uploaded_by_user_id'],uid);self.assertEqual(row['uploaded_by_office_id'],oid);self.assertEqual(row['status'],'pending_review')
            self.assertEqual(other.get(f'/api/sources/{sid}/pages').status_code,403)
            self.assertEqual(self.post(office,f'/api/sources/{sid}/approve').status_code,403)

    def test_source_without_text_opens_review_before_approval(self):
        sid='review-fixture'
        with k.db() as c:
            c.execute('INSERT INTO sources(id,title,language,file_name,page_count,imported_at,status,processing_status) VALUES(?,?,?,?,?,?,?,?)',(sid,'Synthetic review','en','fixture.pdf',2,k.now(),'pending_review','needs_review'))
            c.execute('INSERT INTO pages(source_id,page_number,extraction_status,raw_text) VALUES(?,?,?,?)',(sid,1,'extracted',''))
            c.execute('INSERT INTO pages(source_id,page_number,extraction_status,raw_text,confidence) VALUES(?,?,?,?,?)',(sid,2,'needs_review','unclear',62))
        rejected=self.post(self.admin,f'/api/sources/{sid}/approve')
        self.assertEqual(rejected.status_code,409)
        self.assertEqual(rejected.get_json()['code'],'source_requires_review')
        self.assertEqual(rejected.get_json()['review_page'],2)
        self.assertEqual(self.post(self.member,f'/api/sources/{sid}/pages/2',{'text':'Not allowed'}).status_code,403)
        self.assertEqual(self.post(self.admin,f'/api/sources/{sid}/pages/2',{'text':'too short'}).status_code,400)
        reviewed='Synthetic review fixture: a sufficiently long original transcription for local test verification only.'
        result=self.post(self.admin,f'/api/sources/{sid}/pages/2',{'text':reviewed,'reviewer':'Forged identity'})
        self.assertEqual(result.status_code,200,result.get_json())
        self.assertNotIn(sid,[s['id'] for s in self.member.get('/api/bootstrap').get_json()['sources']],'Review alone does not approve')
        self.assertEqual(self.post(self.admin,f'/api/sources/{sid}/approve').status_code,200)
        self.assertIn(sid,[s['id'] for s in self.member.get('/api/bootstrap').get_json()['sources']])
        with k.db() as c:
            page=c.execute('SELECT * FROM pages WHERE source_id=? AND page_number=2',(sid,)).fetchone()
            self.assertEqual(page['raw_text'],reviewed);self.assertEqual(page['extraction_status'],'reviewed')
            audit=c.execute("SELECT * FROM audit WHERE action='page_reviewed'").fetchone()
            self.assertIn(self.root,str(dict(audit)));self.assertNotIn('Forged identity',str(dict(audit)))

    def test_general_reading_preserves_curriculum_progress_and_scope(self):
        with k.db() as c:
            for sid,level,status in [('general',0,'approved'),('lesson',1,'approved'),('pending',0,'pending_review')]:
                c.execute('INSERT INTO sources(id,title,language,file_name,page_count,imported_at,status,level) VALUES(?,?,?,?,?,?,?,?)',(sid,'Synthetic reading','en','fixture.pdf',1,k.now(),status,level))
        self.assertEqual(self.post(self.member,'/api/lessons/complete',{'source_id':'pending'}).status_code,404)
        self.assertEqual(self.post(self.member,'/api/lessons/complete',{'source_id':'general'}).status_code,200)
        first=self.member.get('/api/bootstrap').get_json()
        self.assertEqual(first['completed'],['general']);self.assertEqual(first['learner']['progress'],0)
        self.assertEqual(self.post(self.member,'/api/lessons/complete',{'source_id':'lesson'}).status_code,200)
        self.assertEqual(self.post(self.member,'/api/lessons/complete',{'source_id':'general'}).status_code,200)
        data=self.member.get('/api/bootstrap').get_json()
        self.assertEqual(len(data['completed']),2);self.assertEqual(data['learner']['progress'],100)
        self.assertEqual(data['learner']['learning_stage'],'المستوى 1')
        self.assertEqual(self.admin.get('/api/bootstrap').get_json()['completed'],[])

    def test_source_processing_states_do_not_allow_approval(self):
        with k.db() as c:
            c.execute('INSERT INTO sources(id,title,language,file_name,page_count,imported_at,status,processing_status) VALUES(?,?,?,?,?,?,?,?)',('busy-source','Synthetic','en','fixture.pdf',1,k.now(),'pending_review','queued'))
        for status,code in [('queued','source_processing'),('indexing','source_processing'),('failed','source_processing_failed')]:
            with k.db() as c:c.execute('UPDATE sources SET processing_status=? WHERE id=?',(status,'busy-source'))
            response=self.post(self.admin,'/api/sources/busy-source/approve')
            self.assertEqual(response.status_code,409);self.assertEqual(response.get_json()['code'],code)

    def test_upload_limit_explains_retry_without_removing_protection(self):
        for _ in range(10):self.assertTrue(ac.rate_limit('upload:'+self.root,10,3600))
        with patch('api_server.background_index') as indexer:
            response=self.admin.post('/api/sources/upload',data=b'%PDF-not-written',headers={'X-CSRF-Token':self.admin.csrf})
            self.assertEqual(response.status_code,429)
            self.assertEqual(response.get_json()['code'],'upload_rate_limited')
            self.assertIn('10',response.get_json()['error'])
            self.assertIn('محفوظة',response.get_json()['error'])
            self.assertTrue(1<=int(response.headers['Retry-After'])<=3600)
            indexer.assert_not_called()
        self.assertFalse(ac.rate_limit('upload:'+self.root,10,3600))

    def test_localized_fallback_and_greetings_in_four_new_languages(self):
        import assistant_engine as engine
        for language,greeting in [('fil','kumusta'),('fr','bonjour'),('am','ሰላም'),('sw','habari')]:
            result=engine.respond(greeting,language,[])
            self.assertEqual(result['mode'],'conversation');self.assertFalse(result['content'].startswith('Welcome'))
            result=engine.respond('unanswerable question',language,[])
            self.assertTrue(result['escalate']);self.assertFalse(result['content'].startswith('I could not'))

    def test_all_static_ui_labels_have_four_translations(self):
        from check_locales import labels
        self.assertEqual(labels(),[])
        rows=json.loads((k.ROOT/'app/locales.json').read_text('utf-8'))
        self.assertTrue(all(len(r)==5 and all(isinstance(s,str) and s for s in r) for r in rows))

    def test_production_requires_changed_primary_password(self):
        with k.db() as c:c.execute('UPDATE users SET must_change_password=1 WHERE is_primary=1')
        with patch('api_server.config.get',side_effect=lambda name,default='':{'RIHLATI_ENV':'production','PUBLIC_URL':'https://rihlati.example'}.get(name,default)):
            with self.assertRaises(RuntimeError):create_app()

    def test_production_sessions_use_secure_cookie_and_hsts(self):
        with patch('api_server.config.get',side_effect=lambda name,default='':{'RIHLATI_ENV':'production','PUBLIC_URL':'https://rihlati.example'}.get(name,default)):
            app=create_app();response=app.test_client().get('/api/auth/session',base_url='https://rihlati.example')
            self.assertTrue(response.headers['Set-Cookie'].startswith('rihlati_auth='))
            self.assertEqual(response.status_code,200);self.assertIn('Secure',response.headers['Set-Cookie'])
            self.assertIn('max-age=',response.headers['Strict-Transport-Security'])

if __name__=='__main__':
    unittest.main()
