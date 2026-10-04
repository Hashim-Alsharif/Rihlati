"""Conversation, source-grounded answers, specialist escalation, and reviewed learning."""
import json
import re
import uuid
from knowledge import ROOT,db,now,normalize,terms,search,approved_correction,audit
import ai_provider as ai

PERSONAL=re.compile(r'فتو[ىي]|طلاق|طلقت|زوجتي|زوجي|ميراث|تكفير|انتحار|هل.*(?:حلال|حرام)|حكم.*(?:حالتي|زواجي)|fatwa|divorc|my (?:wife|husband)|inheritance',re.I)
SPECIALIST=re.compile(r'(?:تحدث|اتحدث|التحدث|اريد|حول|احل|اطلب).*(?:مختص|داعيه|مفتي)|(?:talk|speak|refer|contact).*(?:specialist|scholar|imam)',re.I)
LOCALES={row[0]:dict(zip(('fil','fr','am','sw'),row[1:])) for row in json.loads((ROOT/'app/locales.json').read_text('utf-8'))}

def conversation(cid=None,language='ar'):
    with db() as c:
        row=c.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone() if cid else None
        if row:
            return dict(row)
        cid=uuid.uuid4().hex;lid='guest-'+uuid.uuid4().hex[:16]
        c.execute('INSERT INTO learners VALUES(?,?,?,?,?,?,?)',(lid,'مستفيد تجريبي جديد',language,'بداية الرحلة',0,now(),'active'))
        c.execute('INSERT INTO conversations VALUES(?,?,?,?)',(cid,lid,language,now()))
    return {'id':cid,'learner_id':lid,'language':language}

def messages(cid):
    with db() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY id',(cid,))]
    for row in rows:
        row['citations']=json.loads(row['citations'])
    return rows

def open_ticket(conv,question,reason,message_id=None,context=None):
    with db() as c:
        sql="SELECT id,status FROM tickets WHERE conversation_id=? AND question=? AND status='open'"
        args=[conv['id'],question]
        if 'office_id' in conv:
            sql+=' AND office_id IS ?';args.append(conv['office_id'])
        existing=c.execute(sql+' ORDER BY id DESC',args).fetchone()
        if existing:
            return dict(existing)
        learner=c.execute('SELECT display_name FROM learners WHERE id=?',(conv['learner_id'],)).fetchone()
        cursor=c.execute('''INSERT INTO tickets(learner_id,learner_name,question,language,reason,status,source_context,created_at,updated_at,conversation_id,message_id) VALUES(?,?,?,?,?,'open',?,?,?,?,?)''',(conv['learner_id'],learner['display_name'],question,conv['language'],reason,json.dumps(context or [],ensure_ascii=False),now(),now(),conv['id'],message_id))
        tid=cursor.lastrowid
        if 'office_id' in conv:
            c.execute('UPDATE tickets SET office_id=? WHERE id=?',(conv['office_id'],tid))
        audit(c,'ticket_opened',tid,reason)
    return {'id':tid,'status':'open'}

def result(content,mode='conversation',citations=None,escalate=False,follow_up=''):
    return {'content':content,'mode':mode,'citations':citations or [],'escalate':escalate,'follow_up':follow_up}

def respond(question,language,history):
    response=_respond(question,language,history)
    # Translate fixed interface messages only, never alter a religious excerpt
    # or a reviewed answer. Provider answers already use the requested language.
    if language in ('fil','fr','am','sw'):
        if response['mode'] in ('conversation','escalation'):
            response['content']=LOCALES.get(response['content'],{}).get(language,response['content'])
        elif response['mode']=='library_excerpt':
            prefix,separator,excerpt=response['content'].partition('\n\n')
            response['content']=LOCALES.get(prefix,{}).get(language,prefix)+separator+excerpt
        response['follow_up']=LOCALES.get(response['follow_up'],{}).get(language,response['follow_up'])
    return response

def _respond(question,language,history):
    ar=language=='ar';n=normalize(question).strip(' .!?؟')
    if n in ('السلام عليكم','سلام','مرحبا','اهلا','hi','hello','hey','bonjour','salut','kumusta','habari','hujambo','ሰላም'):
        return result('أهلًا بك في رِحلتي. يسعدني مرافقتك. ما الذي ترغب في تعلمه اليوم: التوحيد، الطهارة، الصلاة، أم لديك سؤال آخر؟' if ar else 'Welcome to Rihlati. What would you like to explore today: faith, purification, prayer, or another question?')
    if n in ('شكرا','شكرا لك','جزاك الله خيرا','thanks','thank you','merci','salamat','asante','አመሰግናለሁ'):
        return result('على الرحب والسعة. هل تريد مساعدة أخرى، أم ترغب في التحدث إلى المختص؟' if ar else 'You are welcome. Is there anything else I can help with, or would you like to speak to a specialist?')
    if SPECIALIST.search(n):
        return result('سأرسل سؤالك وسياق المحادثة إلى المختص.' if ar else 'I will send your question and conversation context to a specialist.','escalation',escalate=True)
    if PERSONAL.search(n):
        return result('هذا السؤال يحتاج نظر المختص في حالتك. سأفتح تذكرة للمكتب وأرفق سؤالك وسياقه.' if ar else 'A specialist needs to review your situation. I will open a ticket with your question and context.','escalation',escalate=True)
    correction=approved_correction(question,language)
    if correction:
        return result(correction['answer'],'reviewed_answer',[{'citation_id':'c'+str(correction['id']),'title':'إجابة راجعها '+correction['reviewer'],'source_note':correction['source_note'],'correction_id':correction['id']}],follow_up='هل تريد توضيحًا آخر أو التحدث إلى المختص؟' if ar else 'Would you like further clarification or a specialist?')
    query=question;configured=bool(ai.key());provider_issue=None
    prior=[m['content'] for m in history if m['role']=='user']
    is_followup=bool(re.search(r'وضح|بسط|المزيد|اكثر|اشرحها|وماذا|وما هي|and what|more|simpl|explain it',n))
    if configured:
        try:
            query=ai.rewrite(question,[{'role':m['role'],'content':m['content']} for m in history[-8:]])
        except ai.ProviderError as error:
            provider_issue=error.message
    elif is_followup and prior:
        query=prior[-1]+' '+question
    # Rewriting may add words absent from an otherwise relevant passage.
    # Retrieve both queries, deduplicate evidence, then let the grounded model
    # judge whether the actual question is answerable from that evidence.
    queries=list(dict.fromkeys([query,question] if configured else [query]))
    candidates={}
    for retrieval_query in queries:
        for match in search(retrieval_query,language=None if configured else language,limit=8):
            if match['coverage']>=.67 and match['score']>=.25:
                old=candidates.get(match['citation_id'])
                if old is None or match['score']>old['score']:
                    candidates[match['citation_id']]=match
    usable=sorted(candidates.values(),key=lambda row:row['score'],reverse=True)[:8]
    if configured and usable and not provider_issue:
        try:
            generated=ai.grounded_answer(question,[{'role':m['role'],'content':m['content']} for m in history[-8:]],usable,language)
            available={p['citation_id']:p for p in usable}
            ids=generated['citation_ids']
            if not generated['needs_specialist'] and ids and all(i in available for i in ids):
                return result(generated['answer'],'ai',[available[i] for i in dict.fromkeys(ids)],follow_up=generated['follow_up'])
            return result('لم أجد في النصوص ما يكفي لإجابة موثوقة عن سؤالك. سأحيله إلى المختص.' if ar else 'The supplied sources do not contain enough evidence for a reliable answer. I will refer your question to a specialist.','escalation',escalate=True)
        except (ai.ProviderError,KeyError,TypeError) as error:
            provider_issue=error.message if isinstance(error,ai.ProviderError) else 'تعذر التحقق من جواب النموذج.'
    # Raw scanned text can corrupt Quran/hadith even at high OCR confidence.
    # Without a validated AI answer, only quote digital or human-reviewed text.
    quotable=[r for r in usable if r['extraction_status'] in ('extracted','reviewed')]
    if quotable:
        best=quotable[0]
        prefix='وجدت هذا المقتطف المرتبط بسؤالك في المكتبة:' if ar else 'I found this related excerpt in the library:'
        follow='هل تريد سؤالًا آخر أو التحدث إلى المختص؟' if ar else 'Do you have another question, or would you like a specialist?'
        output=result(prefix+'\n\n'+best['content'],'library_excerpt',[best],follow_up=follow)
        output['provider_notice']=provider_issue
        return output
    if usable:
        return result('وجدت صفحات مرتبطة بسؤالك، لكن نصها مستخرج آليًا من صور ولم يُراجع بعد. لن أنقل لك نصًا قد يحتوي خطأ؛ سأحيل السؤال للمختص، ويمكنك فتح المرجع الأصلي أدناه.' if ar else 'I found related pages, but their scanned text has not been reviewed. To avoid quoting recognition errors, I will refer your question to a specialist. You can open the original source below.','escalation',[usable[0]],escalate=True)
    return result('لم أجد جوابًا موثوقًا في المراجع المتاحة. سأفتح تذكرة للمختص لمساعدتك.' if ar else 'I could not find a reliable answer in the available references. I will open a specialist ticket for you.','escalation',escalate=True)

def chat(conv,question,language):
    history=messages(conv['id']);conv['language']=language
    response=respond(question,language,history)
    if response.get('follow_up'):
        response['content']+='\n\n'+response['follow_up']
    with db() as c:
        c.execute('UPDATE conversations SET language=? WHERE id=?',(language,conv['id']))
        c.execute('UPDATE learners SET language=?,last_active_at=? WHERE id=?',(language,now(),conv['learner_id']))
        c.execute('INSERT INTO messages(conversation_id,role,content,language,created_at) VALUES(?,?,?,?,?)',(conv['id'],'user',question,language,now()))
        cursor=c.execute('INSERT INTO messages(conversation_id,role,content,language,mode,citations,question,created_at) VALUES(?,?,?,?,?,?,?,?)',(conv['id'],'assistant',response['content'],language,response['mode'],json.dumps(response['citations'],ensure_ascii=False),question,now()))
        message_id=cursor.lastrowid
    if response['escalate']:
        ticket_question=question
        if SPECIALIST.search(normalize(question)):
            previous=[m for m in history if m['role']=='user' and not SPECIALIST.search(normalize(m['content']))]
            if previous:
                ticket_question=previous[-1]['content']
        ticket=open_ticket(conv,ticket_question,'طلب مختص أو عدم كفاية الأدلة',message_id,history[-10:])
        with db() as c:
            c.execute('UPDATE messages SET ticket_id=? WHERE id=?',(ticket['id'],message_id))
        response['ticket_id']=ticket['id']
    return response

def escalate_message(conv,message_id):
    with db() as c:
        message=c.execute("SELECT * FROM messages WHERE id=? AND conversation_id=? AND role='assistant'",(message_id,conv['id'])).fetchone()
        if not message:
            raise ValueError('الرسالة غير موجودة.')
    ticket=open_ticket(conv,message['question'],'طلب المستفيد التحدث إلى مختص',message_id,messages(conv['id'])[-10:])
    with db() as c:
        c.execute('UPDATE messages SET ticket_id=? WHERE id=?',(ticket['id'],message_id))
    return ticket

def reply_ticket(ticket_id,payload):
    answer=str(payload.get('response','')).strip();reviewer=str(payload.get('reviewer','')).strip()
    if not answer or not reviewer:
        raise ValueError('اكتب الرد واسم المختص.')
    with db() as c:
        row=c.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
        if not row:
            raise ValueError('التذكرة غير موجودة.')
        c.execute("UPDATE tickets SET specialist_response=?,assigned_to=?,status='answered',updated_at=? WHERE id=?",(answer,reviewer,now(),ticket_id))
        if row['conversation_id']:
            c.execute('INSERT INTO messages(conversation_id,role,content,language,mode,question,ticket_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(row['conversation_id'],'assistant',answer,row['language'],'specialist',row['question'],ticket_id,now()))
        # Specialist answers enter a review queue; private case rulings are not automatically reusable.
        if payload.get('learn'):
            source_note=str(payload.get('source_note','')).strip()
            if not source_note:
                raise ValueError('أضف توثيق الإجابة قبل ترشيحها للتعلّم.')
            correction=c.execute('INSERT INTO corrections(question,answer,language,source_note,reviewer,origin_ticket_id,created_at) VALUES(?,?,?,?,?,?,?)',(row['question'],answer,row['language'],source_note,reviewer,ticket_id,now()))
            if payload.get('created_by_user_id'):
                c.execute('UPDATE corrections SET created_by_user_id=?,office_id=? WHERE id=?',(payload['created_by_user_id'],payload.get('office_id'),correction.lastrowid))
        audit(c,'specialist_replied',ticket_id,reviewer)

def correction_create(payload):
    values=[str(payload.get(k,'')).strip() for k in ('question','answer','source_note','reviewer')]
    if not all(values):
        raise ValueError('أكمل السؤال والإجابة الصحيحة والتوثيق واسم المراجع.')
    if any(len(v)>12000 for v in values):
        raise ValueError('النص أطول من الحد المسموح.')
    with db() as c:
        mid=payload.get('message_id') or None
        cursor=c.execute('INSERT INTO corrections(question,answer,source_note,reviewer,language,origin_message_id,created_at) VALUES(?,?,?,?,?,?,?)',(*values,payload.get('language','ar'),mid,now()))
        audit(c,'correction_proposed',cursor.lastrowid,values[3])
        return cursor.lastrowid

def correction_status(cid,status):
    if status not in ('approved','rejected','pending'):
        raise ValueError('حالة غير صالحة.')
    with db() as c:
        row=c.execute('SELECT * FROM corrections WHERE id=?',(cid,)).fetchone()
        if not row:
            raise ValueError('التصحيح غير موجود.')
        c.execute('UPDATE corrections SET status=?,approved_at=? WHERE id=?',(status,now() if status=='approved' else None,cid))
        audit(c,'correction_'+status,cid,row['reviewer'])
