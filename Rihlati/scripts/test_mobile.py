"""App/web parity and server-enforced mobile isolation. Temporary data, no paid calls."""
import unittest
from unittest.mock import patch
import accounts as ac
import knowledge as k
import test_accounts as fixtures

class MobileTests(unittest.TestCase):
    setUp=fixtures.AccountTests.setUp
    tearDown=fixtures.AccountTests.tearDown
    new_user=fixtures.AccountTests.new_user
    client=fixtures.AccountTests.client
    post=fixtures.AccountTests.post
    office=fixtures.AccountTests.office

    def mobile_client(self,name=None):
        client=self.app.test_client()
        client.csrf=client.get('/app-api/auth/session').get_json()['csrf']
        if name:
            response=self.post(client,'/app-api/auth/login',{'username':name,'password':fixtures.PASSWORD})
            self.assertEqual(response.status_code,200,response.get_json())
        return client

    def test_admin_login_blocked_without_affecting_web_session(self):
        mobile=self.mobile_client()
        response=self.post(mobile,'/app-api/auth/login',{'username':'admin','password':fixtures.PASSWORD})
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.get_json()['code'],'admin_web_only')
        self.assertIsNone(mobile.get('/app-api/auth/session').get_json()['user'])
        self.assertEqual(self.admin.get('/api/admin/accounts').status_code,200)

    def test_admin_restriction_does_not_disclose_role_for_wrong_password(self):
        response=self.post(self.mobile_client(),'/app-api/auth/login',{'username':'admin','password':'not-the-password'})
        self.assertEqual(response.status_code,401)
        self.assertNotIn('admin_web_only',response.get_data(as_text=True))

    def test_mobile_and_web_sessions_cannot_be_replayed_across_surfaces(self):
        mobile=self.mobile_client('member')
        app_cookie=mobile.get_cookie('rihlati_test_auth_app').value
        mobile.set_cookie('rihlati_test_auth',app_cookie)
        self.assertEqual(mobile.get('/api/bootstrap').status_code,401)
        web_cookie=self.admin.get_cookie('rihlati_test_auth').value
        mobile.set_cookie('rihlati_test_auth_app',web_cookie)
        self.assertEqual(mobile.get('/app-api/admin/accounts').status_code,403)
        self.assertIsNone(mobile.get('/app-api/auth/session').get_json()['user'])

    def test_mobile_session_cannot_gain_admin_if_account_role_changes(self):
        mobile=self.mobile_client('member')
        with k.db() as c:c.execute("UPDATE users SET role='admin' WHERE id=?",(self.member_id,))
        response=mobile.get('/app-api/profile')
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.get_json()['code'],'admin_web_only')
        self.assertIsNone(mobile.get('/app-api/auth/session').get_json()['user'])

    def test_same_member_profile_progress_and_tickets_on_web_and_app(self):
        mobile=self.mobile_client('member')
        self.assertEqual(self.post(mobile,'/app-api/profile',{'display_name':'Shared identity','language':'fr'}).status_code,200)
        self.assertEqual(self.member.get('/api/profile').get_json()['user']['display_name'],'Shared identity')
        tid=self.post(mobile,'/app-api/tickets',{'question':'shared app ticket'}).get_json()['ticket']['id']
        self.assertEqual(self.member.get('/api/bootstrap').get_json()['tickets'][0]['id'],tid)
        with k.db() as c:c.execute("INSERT INTO sources(id,title,file_name,page_count,status,level,language,imported_at) VALUES('lesson','Test book','test.pdf',1,'approved',1,'en',?)",(k.now(),))
        self.assertEqual(self.post(mobile,'/app-api/lessons/complete',{'source_id':'lesson'}).status_code,200)
        self.assertIn('lesson',self.member.get('/api/bootstrap').get_json()['completed'])

    def test_office_can_follow_reply_and_propose_but_not_use_central_admin(self):
        oid,web_office,_=self.office('office')
        ac.set_links(self.member_id,[oid],self.root)
        mobile=self.mobile_client('office')
        tid=self.post(self.member,'/api/tickets',{'question':'web member inquiry','office_id':oid}).get_json()['ticket']['id']
        self.assertEqual(mobile.get('/app-api/dashboard').get_json()['tickets'][0]['id'],tid)
        self.assertEqual(self.post(mobile,f'/app-api/tickets/{tid}/reply',{'response':'App office answer','source_note':'Reviewed source p1','learn':True}).status_code,200)
        self.assertEqual(self.member.get('/api/bootstrap').get_json()['messages'][-1]['content'],'App office answer')
        self.assertEqual(web_office.get('/api/dashboard').get_json()['tickets'][0]['status'],'answered')
        with k.db() as c:self.assertEqual(c.execute('SELECT status FROM corrections').fetchone()[0],'pending')
        for path in ('/app-api/admin/accounts','/app-api/settings','/app-api/admin/registration'):
            response=mobile.get(path) if path.endswith('accounts') else self.post(mobile,path,{})
            self.assertEqual(response.status_code,403)

    def test_mobile_office_tenant_isolation_and_pending_approval(self):
        first,_,_=self.office('first');second,_,_=self.office('second')
        ac.set_links(self.member_id,[first],self.root)
        self.post(self.member,'/api/tickets',{'question':'first only','office_id':first})
        self.assertEqual(self.mobile_client('second').get('/app-api/dashboard').get_json()['tickets'],[])
        self.new_user('pending','office')
        self.assertEqual(self.mobile_client('pending').get('/app-api/dashboard').status_code,403)

    def test_shared_registration_and_password_validation(self):
        mobile=self.mobile_client()
        self.assertEqual(self.post(mobile,'/app-api/auth/register',{'display_name':'app-member','password':'weak'}).status_code,400)
        result=self.post(mobile,'/app-api/auth/register',{'display_name':'app-member','password':'Abcdef1!'} )
        self.assertEqual(result.status_code,201)
        self.assertEqual(self.post(self.client(),'/api/auth/login',{'username':'app-member','password':'Abcdef1!'}).status_code,200)

    def test_mobile_csrf_origin_and_cookie_controls(self):
        mobile=self.mobile_client('member')
        self.assertEqual(mobile.post('/app-api/profile',json={}).status_code,403)
        response=mobile.post('/app-api/profile',json={'display_name':'member'},headers={'Origin':'https://evil.example','X-CSRF-Token':mobile.csrf})
        self.assertEqual(response.status_code,403)
        native=mobile.post('/app-api/profile',json={'display_name':'member'},headers={'Origin':'capacitor://localhost','X-CSRF-Token':mobile.csrf})
        self.assertEqual(native.status_code,200)
        response=mobile.get('/app-api/profile',headers={'Origin':'https://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin',response.headers)

    def test_mobile_audio_uses_same_server_provider_with_mocks_only(self):
        mobile=self.mobile_client('member')
        with patch('api_server.ai.speak',return_value=b'test-mp3') as speech:
            response=self.post(mobile,'/app-api/audio/speech',{'text':'test','language':'en'})
            self.assertEqual(response.status_code,200);speech.assert_called_once_with('test','en')
        with patch('api_server.ai.transcribe',return_value={'text':'test'}) as transcribe:
            response=mobile.post('/app-api/audio/transcribe',data=b'fake-audio',headers={'X-CSRF-Token':mobile.csrf,'Content-Type':'audio/mp4','X-Language':'ar'})
            self.assertEqual(response.status_code,200);transcribe.assert_called_once()

    def test_mobile_bundle_allowlist_does_not_expose_project_files(self):
        for path in ('/app/package.json','/app/capacitor.config.json','/app/../.enviroment.local','/app/scripts/build.mjs','/app/node_modules/anything','/app-api/../.enviroment.local'):
            self.assertIn(self.app.test_client().get(path).status_code,(401,404))

    def test_additive_session_migration_keeps_existing_web_login(self):
        ac.migrate();ac.migrate()
        self.assertEqual(self.member.get('/api/bootstrap').status_code,200)
        with k.db() as c:self.assertTrue(c.execute("SELECT 1 FROM sessions WHERE surface='web' AND user_id=?",(self.member_id,)).fetchone())

    def test_mobile_module_worker_has_javascript_mime(self):
        from pathlib import Path
        bundle=Path(__file__).resolve().parents[2]/'rihlatiApp'/'www'
        if not (bundle/'pdf.worker.min.mjs').is_file():
            self.skipTest('Build rihlatiApp before bundle integration tests')
        response=self.app.test_client().get('/app/pdf.worker.min.mjs')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'text/javascript')
        response.close()

if __name__=='__main__':unittest.main()
