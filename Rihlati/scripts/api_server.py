"""Rihlati HTTP application. Default: local only; deployment requires HTTPS."""
import io
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4
from flask import Flask, request, g, jsonify, abort, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from PIL import Image, UnidentifiedImageError
import accounts as ac
import ai_provider as ai
import assistant_engine as engine
import config
import knowledge as k
from index_jobs import background_index

CHAT_LOCKS=[threading.Lock() for _ in range(64)]
MOBILE_ADMIN_MESSAGE='لا يمكنك استخدام صلاحيات الأدمن على التطبيق، يمكنك استخدام الويب. / Administrator access is only available on the website.'

def create_app(testing=False):
    COOKIE='rihlati_test_auth' if testing else 'rihlati_auth'
    k.migrate(); ac.migrate()
    app=Flask(__name__,static_folder=None)
    production=config.get('RIHLATI_ENV','local')=='production' and not testing
    public_url=config.get('PUBLIC_URL','http://localhost:8080').rstrip('/')
    parsed=urlsplit(public_url)
    if production and (parsed.scheme!='https' or not parsed.hostname or parsed.hostname in ('localhost','127.0.0.1')):
        raise RuntimeError('Production requires PUBLIC_URL=https://your-domain')
    app.config.update(TESTING=testing,MAX_CONTENT_LENGTH=80*1024*1024,TRUSTED_HOSTS=[parsed.hostname] if production else ['localhost','127.0.0.1'])
    if production:
        with k.db() as c:
            primary=c.execute('SELECT must_change_password FROM users WHERE is_primary=1').fetchone()
        if not primary or primary['must_change_password']:
            raise RuntimeError('Initialize primary admin and change its initial password locally before production')

    def limit(name, maximum, seconds=60):
        # No untrusted forwarding headers: proxy configuration is explicit in deployment.
        bucket=f'{name}:{g.user["id"] if g.user else request.remote_addr}'
        if not ac.rate_limit(bucket,maximum,seconds):
            if name=='upload':
                with k.db() as c:
                    row=c.execute('SELECT expires FROM request_limits WHERE bucket=?',(ac.digest(bucket),)).fetchone()
                g.upload_retry_after=max(1,int(row['expires']-time.time())+1) if row else seconds
            abort(429)

    def payload():
        if (request.content_length or 0)>128*1024:
            abort(413)
        value=request.get_json(silent=True)
        if not isinstance(value,dict):
            raise ValueError('Invalid JSON object')
        return value

    def language(value):
        if value not in ac.LANGUAGES:
            raise ValueError('Unsupported language')
        return value

    def require(permission=None, office=False):
        if not g.user:
            abort(401)
        if permission and not ac.permission(g.user,permission):
            if not (office and g.user['role']=='office'):
                abort(403)
        return g.user

    def actor():
        return g.user['display_name']+' ['+g.user['id']+']'

    def manage_target(row):
        require({'member':'users','office':'offices','admin':'admins'}[row['role']])
        if row['is_primary'] or row['id']==g.user['id']:
            abort(403)
        # An admin-manager may not take over a more privileged administrator.
        if row['role']=='admin' and any(not ac.permission(g.user,p) for p in json.loads(row['permissions'])):
            abort(403)

    def rotation(uid=None):
        with k.db() as c:
            c.execute('DELETE FROM sessions WHERE token_hash=? AND surface=?',(ac.digest(request.cookies.get(g.cookie,'')),g.surface))
        g.new_token,g.csrf=ac.session_create(uid,g.surface)

    @app.before_request
    def protect():
        g.user=None;g.session=None;g.new_token=None;g.csrf=''
        g.mobile=request.path.startswith('/app-api/')
        g.surface='app' if g.mobile else 'web'
        g.cookie=COOKIE+'_app' if g.mobile else COOKIE
        api_path='/api/'+request.path[len('/app-api/'):] if g.mobile else request.path
        # Trigger trusted-host validation before any request processing.
        host=request.host
        if api_path=='/api/health' or not api_path.startswith('/api/'):
            return
        token=request.cookies.get(g.cookie,'')
        if len(token)<200:
            with k.db() as c:
                row=c.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>? AND surface=?',(ac.digest(token),time.time(),g.surface)).fetchone()
                g.session=dict(row) if row else None
                if row and row['user_id']:
                    user=c.execute('SELECT * FROM users WHERE id=? AND status=\'active\'',(row['user_id'],)).fetchone()
                    g.user=dict(user) if user else None
        if g.session:
            g.csrf=g.session['csrf']
        if g.mobile and g.user and g.user['role']=='admin':
            rotation()
            return jsonify(error=MOBILE_ADMIN_MESSAGE,code='admin_web_only'),403
        # Mobile sessions never authenticate web endpoints, even if a cookie is copied.
        # Native fetch uses the platform HTTP bridge, not permissive browser CORS.
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('Origin')
            expected=public_url if production else request.host_url.rstrip('/')
            allowed_origins={expected}
            if g.mobile:
                allowed_origins.update(('capacitor://localhost','https://localhost'))
            if (origin and origin not in allowed_origins) or (request.headers.get('Sec-Fetch-Site')=='cross-site' and not (g.mobile and origin in allowed_origins)):
                abort(403)
            if not g.session or not secrets.compare_digest(g.csrf,request.headers.get('X-CSRF-Token','')):
                abort(403)
        public=('/api/auth/session','/api/auth/login','/api/auth/register')
        if g.mobile and (api_path.startswith('/api/admin/') or api_path.startswith('/api/settings')):
            return jsonify(error=MOBILE_ADMIN_MESSAGE,code='admin_web_only'),403
        if api_path not in public:
            require()
            if g.user['must_change_password'] and api_path not in ('/api/auth/logout','/api/profile','/api/profile/password'):
                return jsonify(error='أكمل بيانات الحساب وغيّر كلمة المرور المؤقتة أولًا. / Update your profile and temporary password first.',code='password_change_required'),403
            if g.user['role']=='member' and api_path in ('/api/bootstrap','/api/ask','/api/tickets','/api/lessons/complete'):
                with k.db() as c:
                    available=c.execute("SELECT 1 FROM offices WHERE status='approved'").fetchone()
                    linked=c.execute("SELECT 1 FROM member_offices m JOIN offices o ON o.id=m.office_id WHERE m.user_id=? AND o.status='approved'",(g.user['id'],)).fetchone()
                if available and not linked:
                    return jsonify(error='اختر من مكتب واحد إلى ثلاثة مكاتب معتمدة من حسابك. / Select one to three approved offices in My account.',code='office_selection_required'),403
            if g.user['role']=='office':
                with k.db() as c:
                    office=c.execute('SELECT status FROM offices WHERE id=?',(g.user['office_id'],)).fetchone()
                if (not office or office['status']!='approved') and not api_path.startswith(('/api/profile','/api/auth/')):
                    return jsonify(error='عضوية المكتب بانتظار الاعتماد أو موقوفة. / Office approval required.',code='office_pending'),403

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Permissions-Policy']='camera=(), microphone=(self), geolocation=()'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        if production:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        if getattr(g,'new_token',None):
            response.set_cookie(g.cookie,g.new_token,httponly=True,secure=production,samesite='Lax',max_age=43200,path='/')
        return response

    @app.errorhandler(Exception)
    def errors(error):
        if isinstance(error,ai.ProviderError):
            return jsonify(error=error.message,code=error.code),503
        if isinstance(error,HTTPException):
            if error.code==429 and getattr(g,'upload_retry_after',None):
                remaining=g.upload_retry_after
                minutes=max(1,(remaining+59)//60)
                message=f'وصلت إلى حد رفع المراجع: 10 محاولات في الساعة. الكتب التي رُفعت سابقًا محفوظة؛ لا تعد رفعها. يمكنك المحاولة بعد نحو {minutes} دقيقة. / Reference upload limit: 10 attempts per hour. Previously uploaded books are saved; do not re-upload them. Try again in about {minutes} minutes.'
                response=jsonify(error=message,code='upload_rate_limited',retry_after=remaining)
                response.status_code=429;response.headers['Retry-After']=str(remaining)
                return response
            labels={400:'Invalid request',401:'Sign in required / سجّل الدخول',403:'Access denied / غير مصرح',404:'Not found',413:'File or request too large',429:'Too many requests; retry later / حاول لاحقًا'}
            return jsonify(error=labels.get(error.code,'Request failed')),error.code
        if isinstance(error,(ValueError,UnidentifiedImageError,Image.DecompressionBombError)):
            return jsonify(error=str(error)[:400]),400
        if isinstance(error,sqlite3.IntegrityError):
            return jsonify(error='تعارض في البيانات. تحقق من القيم وحاول مجددًا. / Conflicting data.'),409
        app.logger.error('Request failed: %s',type(error).__name__)
        return jsonify(error='تعذر إكمال العملية. / Unable to complete request.'),500

    @app.get('/')
    def index():
        return send_from_directory(k.ROOT/'app','index.html')

    @app.get('/app/')
    @app.get('/app/<path:name>')
    def mobile_app(name='index.html'):
        # Serve only the generated public bundle, never the sibling project root.
        allowed=('index.html','app.js','accounts.js','i18n.js','locales.json','styles.css',
                 'logo-rihlati.svg','mobile.js','mobile.css','runtime.js','native.js',
                 'pdf-viewer.js','pdf.worker.min.mjs','app-config.js','manifest.webmanifest',
                 'icon-192.png','icon-512.png','font-arabic.woff2','font-latin.woff2')
        if name not in allowed:
            abort(404)
        mime='text/javascript' if name.endswith(('.js','.mjs')) else ('application/manifest+json' if name=='manifest.webmanifest' else None)
        return send_from_directory(k.ROOT.parent/'rihlatiApp'/'www',name,mimetype=mime)

    @app.get('/<path:name>')
    def static(name):
        # An explicit allowlist prevents secrets, data, scripts and docs being served.
        if name not in ('app.js','styles.css','accounts.js','i18n.js','locales.json','logo-rihlati.svg','logo-siraj.png','favicon.ico'):
            abort(404)
        return send_from_directory(k.ROOT/'app',name)

    @app.get('/api/health')
    def health():
        return {'app':'rihlati','status':'ok'}

    @app.get('/api/auth/session')
    def session():
        if not g.session:
            limit('anonymous-session',60)
            rotation()
        with k.db() as c:
            offices=[dict(r) for r in c.execute("SELECT id,name FROM offices WHERE status='approved' ORDER BY name")]
        return {'user':ac.public(g.user),'csrf':g.csrf,'registration':ac.rules(),'offices':offices,'languages':list(ac.LANGUAGES)}

    @app.post('/api/auth/login')
    def login():
        limit('login',12,900)
        p=payload();username=ac.text(p.get('username',''),80,True);secret=ac.secret_input(p.get('password'))
        if not ac.rate_limit('login-name:'+username.casefold(),20,900):
            abort(429)
        with k.db() as c:
            row=c.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone()
            user=dict(row) if row else None
        good=ac.verify(secret,user['password_hash'] if user else ac.DUMMY_HASH)
        if not good or not user or user['status']!='active' or (user['password_expires'] and user['password_expires']<time.time()):
            return jsonify(error='بيانات الدخول غير صالحة أو الحساب غير متاح. / Invalid credentials or unavailable account.'),401
        if g.mobile and user['role']=='admin':
            return jsonify(error=MOBILE_ADMIN_MESSAGE,code='admin_web_only'),403
        if ac.HASHER.check_needs_rehash(user['password_hash']):
            with k.db() as c:
                c.execute('UPDATE users SET password_hash=? WHERE id=?',(ac.HASHER.hash(secret),user['id']))
        rotation(user['id'])
        return {'user':ac.public(user),'csrf':g.csrf}

    @app.post('/api/auth/register')
    def register():
        limit('register',6,3600)
        p=payload();role=p.get('role','member')
        if role not in ('member','office'):
            abort(403)
        # Links are selected after registration so an invalid choice cannot leave
        # a partially registered response. No office privileges until approval.
        uid=ac.create_user(p,role)
        rotation(uid)
        with k.db() as c:
            user=dict(c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
        return {'user':ac.public(user),'csrf':g.csrf},201

    @app.post('/api/auth/logout')
    def logout():
        rotation()
        return {'ok':True,'csrf':g.csrf}

    @app.route('/api/profile',methods=['GET','POST'])
    def profile():
        if request.method=='POST':
            p=payload();display=ac.text(p.get('display_name',''),100,True)
            email,phone=ac.contact(p,g.user['role'],False)
            lang=language(p.get('language',g.user['language']))
            with k.db() as c:
                c.execute('UPDATE users SET display_name=?,email=?,phone=?,language=? WHERE id=?',(display,email,phone,lang,g.user['id']))
                c.execute('UPDATE learners SET display_name=?,language=? WHERE id=?',(display,lang,g.user['learner_id']))
                k.audit(c,'profile_updated',g.user['id'])
                g.user=dict(c.execute('SELECT * FROM users WHERE id=?',(g.user['id'],)).fetchone())
        return {'user':ac.public(g.user)}

    @app.post('/api/profile/password')
    def change_password():
        limit('password',6,900);p=payload()
        if not ac.verify(ac.secret_input(p.get('current_password')),g.user['password_hash']):
            abort(403)
        if g.user['is_primary'] and (not g.user['email'] or not g.user['phone']):
            raise ValueError('أضف بريد الأدمن الرئيسي وجواله أولًا. / Primary admin email and phone required.')
        new=ac.password(p.get('password'))
        if ac.verify(new,g.user['password_hash']):
            raise ValueError('اختر كلمة مرور جديدة. / Choose a different password.')
        encoded=ac.HASHER.hash(new)
        with k.db() as c:
            c.execute('UPDATE users SET password_hash=?,must_change_password=0,password_expires=NULL WHERE id=?',(encoded,g.user['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(g.user['id'],))
            k.audit(c,'password_changed',g.user['id'])
        rotation(g.user['id'])
        return {'ok':True,'csrf':g.csrf}

    @app.post('/api/profile/avatar')
    def avatar_upload():
        limit('avatar',8,3600)
        if (request.content_length or 0)>2*1024*1024:
            abort(413)
        content=request.get_data()
        with Image.open(io.BytesIO(content)) as original:
            if original.format not in ('PNG','JPEG','WEBP') or original.width*original.height>16000000:
                raise ValueError('Use PNG, JPEG or WebP up to 2 MB / صورة حتى 2 ميغابايت')
            original.load(); picture=original.convert('RGB');picture.thumbnail((512,512))
        directory=k.ROOT/'data/avatars';directory.mkdir(parents=True,exist_ok=True)
        name=uuid4().hex+'.png';picture.save(directory/name,'PNG')
        with k.db() as c:
            c.execute('UPDATE users SET avatar=? WHERE id=?',(name,g.user['id']))
        return {'ok':True}

    @app.get('/api/profile/avatar')
    def avatar_read():
        if not g.user['avatar']:
            abort(404)
        return send_from_directory(k.ROOT/'data/avatars',g.user['avatar'])

    @app.post('/api/profile/offices')
    def own_links():
        if g.user['role']!='member':
            abort(403)
        ac.set_links(g.user['id'],payload().get('office_ids'),g.user['id'])
        return {'ok':True}

    def conv(p=None):
        value={'id':g.user['conversation_id'],'learner_id':g.user['learner_id'],'language':g.user['language']}
        if (p or {}).get('language'):
            value['language']=language(p['language'])
        with k.db() as c:
            ids=[r[0] for r in c.execute("SELECT m.office_id FROM member_offices m JOIN offices o ON o.id=m.office_id WHERE m.user_id=? AND o.status='approved' ORDER BY m.office_id",(g.user['id'],))]
        selected=(p or {}).get('office_id')
        if selected and selected not in ids:
            abort(403)
        value['office_id']=(selected or None) if 'office_id' in (p or {}) else (ids[0] if len(ids)==1 else None)
        return value

    def visible_library():
        data=k.library()
        with k.db() as c:
            for source in data['sources']:
                who=c.execute('SELECT display_name,role FROM users WHERE id=?',(source.get('uploaded_by_user_id'),)).fetchone()
                office=c.execute('SELECT name FROM offices WHERE id=?',(source.get('uploaded_by_office_id'),)).fetchone()
                source['uploaded_by']=office['name'] if office else (who['display_name'] if who else 'الإدارة · فريق سراج')
        data['sources']=[s for s in data['sources'] if (ac.permission(g.user,'library') or s['status']=='approved' or (g.user['role']=='office' and s.get('uploaded_by_office_id')==g.user['office_id'] and s['status']!='deleted'))]
        data['stats']={'sources':len(data['sources']),'passages':sum(s['passage_count'] for s in data['sources']),'pages':sum(s['page_count'] for s in data['sources']),'review_pages':sum(s['review_pages'] for s in data['sources'])}
        return data

    def source_access(sid,edit=False):
        with k.db() as c:
            row=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not row:
            abort(404)
        owned=g.user['role']=='office' and row['uploaded_by_office_id']==g.user['office_id']
        if edit:
            if not ac.permission(g.user,'library') and not (owned and row['status']=='pending_review'):
                abort(403)
        elif not (row['status']=='approved' or ac.permission(g.user,'library') or (owned and row['status']!='deleted')):
            abort(403)
        return dict(row)

    @app.get('/api/bootstrap')
    def bootstrap():
        value=conv()
        with k.db() as c:
            learner=dict(c.execute('SELECT * FROM learners WHERE id=?',(value['learner_id'],)).fetchone())
            completed=[r[0] for r in c.execute('SELECT source_id FROM lessons_completed WHERE learner_id=?',(value['learner_id'],))]
            tickets=[dict(r) for r in c.execute('SELECT * FROM tickets WHERE learner_id=? ORDER BY id DESC',(value['learner_id'],))]
        return {'learner':learner,'messages':engine.messages(value['id']),'tickets':tickets,'completed':completed,'ai':public_ai(),**visible_library()}

    def public_ai():
        status=ai.status()
        return status if ac.permission(g.user,'settings') else {key:status[key] for key in ('configured','audio_configured','provider')}

    @app.get('/api/sources')
    def sources():
        return visible_library()

    @app.get('/api/status')
    def status():
        return public_ai()

    @app.get('/api/sources/<sid>/file')
    def source_file(sid):
        row=source_access(sid)
        return send_file(k.source_path(row['file_path']),mimetype='application/pdf',download_name=row['file_name'])

    @app.get('/api/sources/<sid>/pages')
    def source_pages(sid):
        require('library',office=True);source_access(sid)
        with k.db() as c:
            return {'pages':[dict(r) for r in c.execute('SELECT * FROM pages WHERE source_id=? ORDER BY page_number',(sid,))]}

    @app.get('/api/search')
    def search():
        require('quality',office=True);limit('search',60)
        q=request.args
        return {'results':k.search(ac.text(q.get('q',''),2000),q.get('language'),q.get('source_id'),q.get('level'),q.get('subject'),12,q.get('exercises')=='1')}

    @app.get('/api/dashboard')
    def dashboard():
        if g.user['role'] not in ('office','admin'):
            abort(403)
        with k.db() as c:
            if g.user['role']=='office':
                oid=g.user['office_id']
                learners=[dict(r) for r in c.execute('SELECT l.* FROM learners l JOIN users u ON u.learner_id=l.id JOIN member_offices m ON m.user_id=u.id WHERE m.office_id=? AND u.status=\'active\'',(oid,))]
                tickets=[dict(r) for r in c.execute('SELECT t.* FROM tickets t JOIN users u ON u.learner_id=t.learner_id JOIN member_offices m ON m.user_id=u.id AND m.office_id=t.office_id WHERE t.office_id=? AND u.status=\'active\' ORDER BY t.id DESC',(oid,))]
                corrections=[dict(r) for r in c.execute('SELECT * FROM corrections WHERE office_id=?',(oid,))]
                answers=[];audit=[]
            else:
                learners=[dict(r) for r in c.execute('SELECT * FROM learners ORDER BY last_active_at DESC')] if ac.permission(g.user,'users') else []
                tickets=[dict(r) for r in c.execute('SELECT * FROM tickets ORDER BY id DESC')] if ac.permission(g.user,'tickets') else []
                corrections=[dict(r) for r in c.execute('SELECT * FROM corrections ORDER BY id DESC')] if ac.permission(g.user,'quality') else []
                answers=[dict(r) for r in c.execute("SELECT * FROM messages WHERE role='assistant' AND question!='' ORDER BY id DESC LIMIT 50")] if ac.permission(g.user,'quality') else []
                audit=[dict(r) for r in c.execute('SELECT id,action,entity_id,created_at FROM audit ORDER BY id DESC LIMIT 30')] if g.user['is_primary'] else []
            for answer in answers:
                answer['citations']=json.loads(answer['citations'])
        return {'learners':learners,'tickets':tickets,'corrections':corrections,'answers':answers,'audit':audit,'ai':public_ai(),**visible_library()}

    @app.post('/api/ask')
    def ask():
        limit('ai',15,300);p=payload();question=ac.text(p.get('question',''),2000,True);lang=language(p.get('language','ar'))
        value=conv(p)
        with CHAT_LOCKS[int(value['id'][:8],16)%len(CHAT_LOCKS)]:
            engine.chat(value,question,lang)
        return {'messages':engine.messages(value['id'])}

    @app.post('/api/tickets')
    def tickets_create():
        limit('ticket',20,3600);p=payload();value=conv(p)
        if p.get('message_id'):
            ticket=engine.escalate_message(value,int(p['message_id']))
        else:
            ticket=engine.open_ticket(value,ac.text(p.get('question',''),2000,True),'طلب مباشر من المستفيد',context=engine.messages(value['id'])[-10:])
        return {'ticket':ticket}

    def ticket_access(tid):
        require('tickets',office=True)
        with k.db() as c:
            row=c.execute('SELECT * FROM tickets WHERE id=?',(tid,)).fetchone()
            if not row:
                abort(404)
            if g.user['role']=='office':
                linked=c.execute('SELECT 1 FROM member_offices m JOIN users u ON u.id=m.user_id WHERE u.learner_id=? AND u.status=\'active\' AND m.office_id=?',(row['learner_id'],g.user['office_id'])).fetchone()
                if row['office_id']!=g.user['office_id'] or not linked:
                    abort(403)
            return dict(row)

    @app.post('/api/tickets/<int:tid>/reply')
    def ticket_reply(tid):
        ticket_access(tid);p=payload();p['reviewer']=actor();p['response']=ac.text(p.get('response',''),12000,True)
        p['created_by_user_id']=g.user['id'];p['office_id']=g.user['office_id']
        engine.reply_ticket(tid,p)
        with k.db() as c:
            c.execute('UPDATE tickets SET replied_by_user_id=? WHERE id=?',(g.user['id'],tid))
        return {'ok':True}

    @app.post('/api/admin/tickets/<int:tid>/assign')
    def ticket_assign(tid):
        require('tickets');row=ticket_access(tid);p=payload();oid=p.get('office_id') or None
        with k.db() as c:
            if oid and not c.execute("SELECT 1 FROM users u JOIN member_offices m ON m.user_id=u.id JOIN offices o ON o.id=m.office_id WHERE u.learner_id=? AND m.office_id=? AND o.status='approved'",(row['learner_id'],oid)).fetchone():
                raise ValueError('المكتب غير مرتبط بالمستفيد أو غير معتمد. / Office is not linked and approved.')
            c.execute('UPDATE tickets SET office_id=? WHERE id=?',(oid,tid));k.audit(c,'ticket_assigned',tid,actor())
        return {'ok':True}

    @app.post('/api/corrections')
    def correction():
        require('quality',office=True);p=payload();p['reviewer']=actor();p['language']=language(p.get('language','ar'))
        mid=p.get('message_id')
        if mid and not ac.permission(g.user,'quality'):
            abort(403)
        cid=engine.correction_create(p)
        with k.db() as c:
            c.execute('UPDATE corrections SET created_by_user_id=?,office_id=? WHERE id=?',(g.user['id'],g.user['office_id'],cid))
        return {'id':cid},201

    @app.post('/api/corrections/<int:cid>/status')
    def correction_status(cid):
        require('quality');engine.correction_status(cid,payload().get('status'))
        with k.db() as c:
            c.execute('UPDATE corrections SET approved_by_user_id=? WHERE id=?',(g.user['id'],cid));k.audit(c,'correction_reviewer',cid,actor())
        return {'ok':True}

    @app.post('/api/evaluate')
    def evaluate():
        require('quality',office=True);limit('ai',15,300);p=payload()
        return engine.respond(ac.text(p.get('question',''),2000,True),language(p.get('language','ar')),[])

    @app.post('/api/sources/upload')
    def upload_source():
        require('library',office=True);limit('upload',10,3600)
        lang=language(request.headers.get('X-Language','ar'));level=int(request.headers.get('X-Level','0'))
        if level not in (0,1,2,3):
            raise ValueError('Invalid level')
        subject=request.headers.get('X-Subject','general')
        if subject not in ('general','tawhid','fiqh','hadith','sirah'):
            raise ValueError('Invalid subject')
        filename=ac.text(unquote(request.headers.get('X-Filename','')),240,True).replace('\\','/').split('/')[-1]
        data=request.get_data()
        if not data.startswith(b'%PDF') or not filename.lower().endswith('.pdf'):
            raise ValueError('ملف PDF صالح مطلوب. / Valid PDF required.')
        reader=k.PdfReader(io.BytesIO(data))
        if reader.is_encrypted or not 1<=len(reader.pages)<=2000:
            raise ValueError('PDF must be unencrypted, 1–2000 pages')
        directory=k.ROOT/'references';directory.mkdir(exist_ok=True)
        file=directory/(uuid4().hex+'.pdf');file.write_bytes(data)
        sid,created=k.register_pdf(file,filename[:-4],lang,level,subject,'مكتبة رِحلتي')
        if created:
            with k.db() as c:
                c.execute('UPDATE sources SET uploaded_by_user_id=?,uploaded_by_office_id=? WHERE id=?',(g.user['id'],g.user['office_id'],sid))
            background_index(sid)
        else:
            # Only the newly-created redundant upload is removed; original is retained.
            file.unlink()
        return {'id':sid,'duplicate':not created},201

    @app.post('/api/sources/<sid>/pages/<int:page>')
    def page_review(sid,page):
        require('library',office=True);source_access(sid,True)
        k.review_page(sid,page,ac.text(payload().get('text',''),30000,True),actor())
        return {'ok':True}

    @app.post('/api/sources/<sid>/approve')
    def approve(sid):
        require('library');row=source_access(sid,True)
        with k.db() as c:
            count=c.execute('SELECT COUNT(*) FROM passages WHERE source_id=?',(sid,)).fetchone()[0]
            if row['processing_status'] in ('queued','indexing'):
                return jsonify(error='الفهرسة لم تكتمل بعد. حدّث الحالة بعد انتهاء المعالجة. / Indexing is still running. Refresh when processing finishes.',code='source_processing'),409
            if row['processing_status']=='failed':
                return jsonify(error='تعذرت الفهرسة. أعد الفهرسة أو راجع نص الصفحات قبل الاعتماد. / Indexing failed. Reindex or review the page text before approval.',code='source_processing_failed'),409
            if not count:
                page=c.execute("SELECT page_number FROM pages WHERE source_id=? ORDER BY CASE WHEN extraction_status IN ('needs_ocr','needs_review','sparse') THEN 0 ELSE 1 END,page_number LIMIT 1",(sid,)).fetchone()
                return jsonify(error='لا توجد مقاطع نصية صالحة بعد. افتح مراجعة النص، وقارنه بالأصل، ثم احفظ النص الصحيح قبل اعتماد المرجع. / No usable text passages yet. Review the original page and save its correct text before approving the source.',code='source_requires_review',review_page=page[0] if page else None),409
            c.execute("UPDATE sources SET status='approved' WHERE id=?",(sid,));k.audit(c,'source_approved',sid,actor())
        return {'ok':True}

    @app.post('/api/sources/<sid>/status')
    def source_status(sid):
        require('library');source_access(sid,True);p=payload()
        status=p.get('status')
        if status not in ('pending_review','deleted'):
            raise ValueError('Invalid status')
        with k.db() as c:
            c.execute('UPDATE sources SET status=? WHERE id=?',(status,sid));k.audit(c,'source_'+status,sid,actor())
        return {'ok':True}

    @app.post('/api/sources/<sid>/reindex')
    def reindex(sid):
        require('library');source_access(sid,True);background_index(sid)
        return {'ok':True}

    @app.post('/api/settings')
    def settings():
        require('settings');p=payload();result=ai.save_settings(p)
        with k.db() as c:
            k.audit(c,'provider_settings_changed',g.user['id'])
        return result

    @app.post('/api/settings/test')
    def test_ai():
        require('settings');limit('provider-test',3,300)
        value=ai.model_json('Return status=ok. This is a connection test.',{}, {'type':'object','properties':{'status':{'type':'string'}},'required':['status'],'additionalProperties':False})
        return {'ok':value.get('status')=='ok'}

    @app.post('/api/audio/speech')
    def speech():
        limit('speech',30,300);p=payload()
        return app.response_class(ai.speak(ac.text(p.get('text',''),3800,True),language(p.get('language','ar'))),mimetype='audio/mpeg')

    @app.post('/api/audio/transcribe')
    def transcribe():
        limit('transcribe',12,300)
        if not 0<(request.content_length or 0)<=20*1024*1024:
            abort(413)
        return ai.transcribe(request.get_data(),request.content_type,language(request.headers.get('X-Language','ar')))

    @app.post('/api/lessons/complete')
    def complete():
        value=conv();sid=payload().get('source_id')
        with k.db() as c:
            row=c.execute("SELECT level FROM sources WHERE id=? AND status='approved'",(sid,)).fetchone()
            if not row:
                abort(404)
            c.execute('INSERT OR IGNORE INTO lessons_completed VALUES(?,?,?)',(value['learner_id'],sid,k.now()))
            done=c.execute('SELECT COUNT(*) FROM lessons_completed lc JOIN sources s ON s.id=lc.source_id WHERE lc.learner_id=? AND s.level>0 AND s.status=\'approved\'',(value['learner_id'],)).fetchone()[0]
            total=c.execute("SELECT COUNT(*) FROM sources WHERE level>0 AND status='approved'").fetchone()[0]
            if row['level']>0:
                c.execute('UPDATE learners SET progress=?,learning_stage=?,last_active_at=? WHERE id=?',(min(100,round(done/max(1,total)*100)),f'المستوى {row["level"]}',k.now(),value['learner_id']))
            else:
                # Supplementary reading is recorded without changing curriculum progress/stage.
                c.execute('UPDATE learners SET last_active_at=? WHERE id=?',(k.now(),value['learner_id']))
        return {'ok':True}

    @app.get('/api/admin/accounts')
    def admin_accounts():
        if not any(ac.permission(g.user,p) for p in ('users','offices','admins')):
            abort(403)
        with k.db() as c:
            users=[dict(r) for r in c.execute('SELECT * FROM users ORDER BY created_at DESC')]
            offices=[dict(r) for r in c.execute('SELECT * FROM offices')] if ac.permission(g.user,'offices') else []
        users=[u for u in users if ac.permission(g.user,{'member':'users','office':'offices','admin':'admins'}[u['role']])]
        return {'users':[ac.public(u) for u in users],'offices':offices,'permissions':list(ac.PERMISSIONS),'registration':ac.rules()}

    @app.post('/api/admin/users/<uid>')
    def update_user(uid):
        with k.db() as c:
            row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not row:
            abort(404)
        manage_target(row)
        p=payload()
        status=p.get('status',row['status'])
        if status not in ('active','suspended','deleted'):
            raise ValueError('Invalid status')
        perms=p.get('permissions',json.loads(row['permissions']))
        if not isinstance(perms,list) or any(i not in ac.PERMISSIONS or not ac.permission(g.user,i) for i in perms):
            abort(403)
        email,phone=ac.contact({'email':p.get('email',row['email']),'phone':p.get('phone',row['phone'])},row['role'],False)
        with k.db() as c:
            c.execute('UPDATE users SET display_name=?,status=?,permissions=?,email=?,phone=? WHERE id=?',(ac.text(p.get('display_name',row['display_name']),100,True),status,json.dumps(perms),email,phone,uid))
            c.execute('UPDATE learners SET display_name=?,status=? WHERE id=?',(p.get('display_name',row['display_name']),status,row['learner_id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));k.audit(c,'account_updated',uid,actor())
        return {'ok':True}

    @app.post('/api/admin/users/<uid>/temporary-password')
    def temporary_password(uid):
        limit('temporary-password',10,3600)
        with k.db() as c:
            row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not row:
            abort(404)
        manage_target(row)
        secret=ac.generate_temporary_password()
        with k.db() as c:
            c.execute('UPDATE users SET password_hash=?,must_change_password=1,password_expires=? WHERE id=?',(ac.HASHER.hash(secret),time.time()+86400,uid))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));k.audit(c,'temporary_password_issued',uid,actor())
        return {'temporary_password':secret,'expires_in_hours':24}

    @app.post('/api/admin/users/<uid>/offices')
    def admin_links(uid):
        require('users');ac.set_links(uid,payload().get('office_ids'),g.user['id'])
        return {'ok':True}

    @app.post('/api/admin/offices/<oid>')
    def admin_office(oid):
        require('offices');p=payload();status=p.get('status')
        if status not in ('approved','pending','suspended','deleted'):
            raise ValueError('Invalid status')
        with k.db() as c:
            row=c.execute('SELECT * FROM offices WHERE id=?',(oid,)).fetchone()
            if not row:
                abort(404)
            c.execute('UPDATE offices SET name=?,status=? WHERE id=?',(ac.text(p.get('name',row['name']),160,True),status,oid))
            if status!='approved':
                c.execute("UPDATE tickets SET office_id=NULL WHERE office_id=? AND status='open'",(oid,))
                c.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE office_id=?)',(oid,))
            k.audit(c,'office_'+status,oid,actor())
        return {'ok':True}

    @app.post('/api/admin/admins')
    def create_admin():
        require('admins');p=payload();perms=p.get('permissions',[])
        if not isinstance(perms,list) or any(i not in ac.PERMISSIONS or not ac.permission(g.user,i) for i in perms):
            abort(403)
        uid=ac.create_user(p,'admin',permissions=perms)
        with k.db() as c:
            c.execute('UPDATE users SET must_change_password=1 WHERE id=?',(uid,));k.audit(c,'admin_created',uid,actor())
        return {'id':uid},201

    @app.route('/api/office/staff',methods=['GET','POST'])
    def office_staff():
        if g.user['role']!='office' or not g.user['office_owner']:
            abort(403)
        if request.method=='POST':
            uid=ac.create_user(payload(),'office',g.user['office_id'])
            with k.db() as c:
                c.execute('UPDATE users SET must_change_password=1 WHERE id=?',(uid,))
            return {'id':uid},201
        with k.db() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM users WHERE office_id=?',(g.user['office_id'],))]
        return {'users':[ac.public(r) for r in rows]}

    @app.post('/api/admin/registration')
    def registration_rules():
        require('settings');p=payload();value={}
        for role,fields in ac.DEFAULT_RULES.items():
            value[role]={field:bool(p.get(role,{}).get(field,False)) for field in fields}
        with k.db() as c:
            c.execute("UPDATE platform_settings SET value=? WHERE name='registration'",(json.dumps(value),));k.audit(c,'registration_changed',g.user['id'])
        return {'registration':value}

    # Aliases call the same domain handlers and database, with isolated scoped sessions.
    for rule in list(app.url_map.iter_rules()):
        if rule.rule.startswith('/api/'):
            app.add_url_rule('/app-api/'+rule.rule[len('/api/'):],
                             endpoint='mobile_'+rule.endpoint,
                             view_func=app.view_functions[rule.endpoint],methods=list(rule.methods))
    return app

if __name__=='__main__':
    from waitress import serve
    from server_settings import waitress_options
    options=waitress_options()
    application=create_app()
    print('Rihlati: http://localhost:'+config.get('PORT','8080'),flush=True)
    serve(application,**options)
