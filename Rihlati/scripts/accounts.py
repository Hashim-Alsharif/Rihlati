"""Account domain and additive migrations; no HTTP or provider calls."""
import hashlib
import json
import re
import secrets
import string
import time
import uuid
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from knowledge import db, now, audit

LANGUAGES = ('ar', 'en', 'fil', 'fr', 'am', 'sw')
PERMISSIONS = ('users', 'offices', 'tickets', 'library', 'quality', 'settings', 'admins')
HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
DEFAULT_RULES = {'member': {'email': False, 'phone': False}, 'office': {'email': False}}

def migrate():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS offices(id TEXT PRIMARY KEY,name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT NOT NULL COLLATE NOCASE UNIQUE,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,office_id TEXT REFERENCES offices(id),office_owner INTEGER NOT NULL DEFAULT 0,email TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',language TEXT NOT NULL DEFAULT 'ar',status TEXT NOT NULL DEFAULT 'active',is_primary INTEGER NOT NULL DEFAULT 0,permissions TEXT NOT NULL DEFAULT '[]',must_change_password INTEGER NOT NULL DEFAULT 0,password_expires REAL,avatar TEXT,learner_id TEXT UNIQUE,conversation_id TEXT UNIQUE,created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_primary_admin ON users(is_primary) WHERE is_primary=1;
        CREATE TABLE IF NOT EXISTS member_offices(user_id TEXT NOT NULL REFERENCES users(id),office_id TEXT NOT NULL REFERENCES offices(id),PRIMARY KEY(user_id,office_id));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS session_users ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS platform_settings(name TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS request_limits(bucket TEXT PRIMARY KEY,count INTEGER NOT NULL,expires REAL NOT NULL);
        CREATE TRIGGER IF NOT EXISTS protect_primary_delete BEFORE DELETE ON users WHEN OLD.is_primary=1 BEGIN SELECT RAISE(ABORT,'primary admin protected'); END;
        CREATE TRIGGER IF NOT EXISTS protect_primary_update BEFORE UPDATE ON users WHEN OLD.is_primary=1 AND (NEW.is_primary!=1 OR NEW.role!='admin' OR NEW.status!='active') BEGIN SELECT RAISE(ABORT,'primary admin protected'); END;
        CREATE TRIGGER IF NOT EXISTS max_three_offices BEFORE INSERT ON member_offices WHEN (SELECT COUNT(*) FROM member_offices WHERE user_id=NEW.user_id)>=3 BEGIN SELECT RAISE(ABORT,'maximum three offices'); END;
        ''')
        for table, fields in {
            'sessions': {'surface': "TEXT NOT NULL DEFAULT 'web'"},
            'tickets': {'office_id': 'TEXT', 'replied_by_user_id': 'TEXT'},
            'sources': {'uploaded_by_user_id': 'TEXT', 'uploaded_by_office_id': 'TEXT'},
            'corrections': {'created_by_user_id': 'TEXT', 'office_id': 'TEXT', 'approved_by_user_id': 'TEXT'},
        }.items():
            existing = {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
            for field, spec in fields.items():
                if field not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {field} {spec}')
        c.execute('INSERT OR IGNORE INTO platform_settings VALUES(?,?)', ('registration', json.dumps(DEFAULT_RULES)))

def rules():
    with db() as c:
        return json.loads(c.execute("SELECT value FROM platform_settings WHERE name='registration'").fetchone()[0])

def permission(user, name):
    return user and user['role'] == 'admin' and (user['is_primary'] or name in json.loads(user['permissions']))

def public(user):
    if not user:
        return None
    allowed = ('id','username','display_name','role','office_id','office_owner','email','phone','language','status','is_primary','must_change_password','avatar','created_at')
    result = {k:user[k] for k in allowed}
    result['permissions'] = list(PERMISSIONS) if user['is_primary'] else json.loads(user['permissions'])
    with db() as c:
        result['office_ids'] = [r[0] for r in c.execute('SELECT office_id FROM member_offices WHERE user_id=?', (user['id'],))]
        office = c.execute('SELECT name,status FROM offices WHERE id=?',(user['office_id'],)).fetchone()
        result['office'] = dict(office) if office else None
    return result

def password(value):
    if (not isinstance(value,str) or not 8 <= len(value) <= 128
            or not re.search(r'[A-Z]',value) or not re.search(r'[0-9]',value)
            or not any(char in string.punctuation for char in value)):
        raise ValueError('كلمة المرور: من 8 إلى 128 خانة، تشمل حرفًا لاتينيًا كبيرًا (A–Z) ورقمًا (0–9) ورمزًا خاصًا مثل ! أو @ أو #. / Password: 8–128 characters, including an uppercase Latin letter (A–Z), a digit (0–9) and a special symbol such as !, @ or #.')
    return value

def generate_temporary_password():
    # Keep 144 random bits, and guarantee every required character category.
    return (secrets.token_urlsafe(18) + secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.digits) + secrets.choice('!@#$%&*?'))

def secret_input(value):
    # Passwords are opaque: never trim, normalize, truncate or change case.
    if not isinstance(value,str) or not 1<=len(value)<=128:
        raise ValueError('Invalid password input / كلمة مرور غير صالحة')
    return value

def verify(value, encoded):
    try:
        return HASHER.verify(encoded, value)
    except (VerificationError, InvalidHashError, TypeError):
        return False

def text(value, maximum=120, required=False):
    if not isinstance(value,str):
        raise ValueError('Invalid text')
    value = value.strip()
    if len(value)>maximum or (required and not value):
        raise ValueError('أكمل الحقول المطلوبة ضمن الطول المسموح. / Invalid field length.')
    return value

def contact(payload, role, enforce=True):
    email=text(payload.get('email',''),254)
    phone=text(payload.get('phone',''),24)
    required=rules().get(role,{}) if enforce else {}
    if (email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)) or (required.get('email') and not email):
        raise ValueError('أدخل بريدًا إلكترونيًا صالحًا. / Valid email required.')
    if (phone and not re.fullmatch(r'\+?[0-9 ()-]{7,24}',phone)) or (required.get('phone') and not phone):
        raise ValueError('أدخل رقم جوال صالحًا. / Valid phone required.')
    return email,phone

def create_user(payload, role='member', office_id=None, owner=False, primary=False, permissions=()):
    display=text(payload.get('display_name',''),100,True)
    username=text(payload.get('username',display),80,True)
    if re.search(r'[\x00-\x1f\x7f]',username):
        raise ValueError('Invalid username')
    email,phone=contact(payload,role)
    lang=payload.get('language','ar')
    if lang not in LANGUAGES:
        raise ValueError('Invalid language')
    encoded=HASHER.hash(password(payload.get('password')))
    uid=uuid.uuid4().hex; lid='user-'+uid; cid=uuid.uuid4().hex
    with db() as c:
        if c.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone():
            raise ValueError('اسم الدخول مستخدم بالفعل؛ اختر اسمًا آخر. / Login name is already used.')
        if role=='office' and not office_id:
            office_id=uuid.uuid4().hex;owner=True
            c.execute('INSERT INTO offices(id,name,created_at) VALUES(?,?,?)',(office_id,text(payload.get('office_name',''),160,True),now()))
        c.execute('INSERT INTO users(id,username,display_name,password_hash,role,office_id,office_owner,email,phone,language,is_primary,permissions,must_change_password,learner_id,conversation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid,username,display,encoded,role,office_id,int(owner),email,phone,lang,int(primary),json.dumps(list(permissions)),int(primary),lid,cid,now()))
        c.execute('INSERT INTO learners VALUES(?,?,?,?,?,?,?)',(lid,display,lang,'بداية الرحلة',0,now(),'active'))
        c.execute('INSERT INTO conversations VALUES(?,?,?,?)',(cid,lid,lang,now()))
        audit(c,'account_created',uid,role)
    return uid

def seed_primary(secret):
    with db() as c:
        if c.execute('SELECT 1 FROM users WHERE is_primary=1').fetchone():
            return False
    create_user({'display_name':'أدمن فريق سراج','username':'admin','password':secret},'admin',primary=True,permissions=PERMISSIONS)
    return True

def set_links(uid, ids, actor):
    if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(ids)>3 or len(set(ids))!=len(ids):
        raise ValueError('اختر حتى ثلاثة مكاتب فقط. / Choose at most three offices.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        user=c.execute("SELECT learner_id FROM users WHERE id=? AND role='member' AND status!='deleted'",(uid,)).fetchone()
        if not user:
            raise ValueError('Member not found')
        for oid in ids:
            if not c.execute("SELECT 1 FROM offices WHERE id=? AND status='approved'",(oid,)).fetchone():
                raise ValueError('يمكن اختيار المكاتب المعتمدة فقط. / Approved offices only.')
        if not ids and c.execute("SELECT 1 FROM offices WHERE status='approved'").fetchone():
            raise ValueError('اختر مكتبًا معتمدًا واحدًا على الأقل. / Select at least one approved office.')
        old=[r[0] for r in c.execute('SELECT office_id FROM member_offices WHERE user_id=?',(uid,))]
        c.execute('DELETE FROM member_offices WHERE user_id=?',(uid,))
        c.executemany('INSERT INTO member_offices VALUES(?,?)',[(uid,i) for i in ids])
        # Revoked offices lose access; unfinished tickets return to central triage.
        for removed in set(old)-set(ids):
            c.execute("UPDATE tickets SET office_id=NULL WHERE learner_id=? AND office_id=? AND status='open'",(user['learner_id'],removed))
        audit(c,'member_offices_changed',uid,json.dumps({'actor':actor,'before':old,'after':ids}))

def session_create(uid=None, surface='web'):
    if surface not in ('web','app'):
        raise ValueError('Invalid session surface')
    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires,surface) VALUES(?,?,?,?,?)',(digest(token),uid,csrf,time.time()+(43200 if uid else 3600),surface))
    return token,csrf

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def rate_limit(bucket, maximum, seconds):
    timestamp=time.time()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM request_limits WHERE expires<?',(timestamp,))
        c.execute('INSERT OR IGNORE INTO request_limits VALUES(?,0,?)',(digest(bucket),timestamp+seconds))
        row=c.execute('SELECT count FROM request_limits WHERE bucket=?',(digest(bucket),)).fetchone()
        if row[0]>=maximum:
            return False
        c.execute('UPDATE request_limits SET count=count+1 WHERE bucket=?',(digest(bucket),))
    return True
