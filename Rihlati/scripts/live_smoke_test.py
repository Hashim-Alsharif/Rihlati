"""Small opt-in live provider checks via the local app; never reads the API key.

Uses the non-persistent evaluation endpoint, not learners' conversations.
Audio is a synthetic test sentence, never a user's microphone recording.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
import urllib.error
import argparse
import getpass
import http.cookiejar

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'verification'
BASE = 'http://localhost:8080'
CSRF=''
OPENER=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def post(path, payload=None, body=None, content_type='application/json', binary=False):
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=body, headers={
        'Content-Type': content_type, 'X-Rihlati-Client': 'web', 'X-Language': 'ar','X-CSRF-Token':CSRF}, method='POST')
    try:
        with OPENER.open(req, timeout=180) as response:
            data = response.read()
        return data if binary else json.loads(data)
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode('utf-8', errors='replace')) from None


def question_test(question, language):
    value = post('/api/evaluate', {'question': question, 'language': language})
    return {'question': question, 'language': language, 'mode': value['mode'],
            'answer': value['content'], 'follow_up': value.get('follow_up'),
            'escalate': value['escalate'], 'provider_notice': value.get('provider_notice'),
            'citations': [{k: p.get(k) for k in ('citation_id', 'title', 'page_number')}
                          for p in value['citations']]}


def audio_test():
    sentence = 'أهلًا بك في رِحلتي. يمكنك السؤال عن الطهارة والوضوء والصلاة، أو التحدث إلى المختص.'
    data = post('/api/audio/speech', {'text': sentence, 'language': 'ar'}, binary=True)
    if len(data) < 1000:
        raise ValueError('Unexpectedly small audio response')
    path = OUT / 'arabic-voice-test.mp3'
    path.write_bytes(data)
    transcript = post('/api/audio/transcribe', body=data, content_type='audio/mpeg')
    return {'original': sentence, 'transcript': transcript.get('text'), 'bytes': len(data), 'path': str(path)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='PAID provider checks. Sends synthetic questions and relevant excerpts to OpenAI.')
    parser.add_argument('--live',action='store_true',help='explicitly enable paid calls')
    args=parser.parse_args()
    if not args.live:
        parser.error('Use --live only after approving paid provider calls and source-excerpt transmission.')
    with OPENER.open(BASE+'/api/auth/session') as response:
        CSRF=json.load(response)['csrf']
    result=post('/api/auth/login',{'username':input('Admin login name: '),'password':getpass.getpass('Password: ')})
    CSRF=result['csrf']
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [('arabic', pool.submit(question_test, 'كيف أتعلم الوضوء؟', 'ar')),
                ('english', pool.submit(question_test, 'What is the meaning of tawhid?', 'en')),
                ('audio_round_trip', pool.submit(audio_test))]
        report = {}
        for name, job in jobs:
            try:
                report[name] = job.result()
            except Exception as error:
                report[name] = {'error': str(error)}
            print(json.dumps({name: report[name]}, ensure_ascii=False), flush=True)
    (OUT / 'live-smoke-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
