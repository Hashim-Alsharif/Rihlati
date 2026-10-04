"""Build the Arabic judging guide. No database reads, secrets, or network calls.

Artifact-only dependencies: reportlab, arabic-reshaper, python-bidi, pypdf.
Run with a Unicode font directory via RIHLATI_DOC_FONTS if not on Windows.
Editable source diagrams: WORKFLOW.md. Generated output: output/pdf/.
"""
from pathlib import Path
import os, math
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white

HERE=Path(__file__).resolve().parent
OUT=HERE/'output'/'pdf'
OUT.mkdir(parents=True,exist_ok=True)
FONT=Path(os.environ.get('RIHLATI_DOC_FONTS','C:/Windows/Fonts'))
pdfmetrics.registerFont(TTFont('Arabic',str(FONT/'arial.ttf')))
pdfmetrics.registerFont(TTFont('ArabicBold',str(FONT/'arialbd.ttf')))
W,H=612,792
NAVY='#112748';TEAL='#087C88';CYAN='#33BFD1';GRAY='#586473';LIGHT='#F2F6F8';BORDER='#C7D3DC'
DEST=OUT/'دليل رحلتي للويب والتطبيق والتحكيم.pdf'
c=canvas.Canvas(str(DEST),pagesize=(W,H))
c.setTitle('دليل رحلتي للويب والتطبيق والتحكيم')
c.setAuthor('فريق سراج')
c.setSubject('المخططات والصلاحيات والأدوات وجاهزية التحكيم والاستضافة')
page_no=0

def shaped(text):return get_display(arabic_reshaper.reshape(str(text)))
def width(text,size=12,bold=False):return pdfmetrics.stringWidth(shaped(text),'ArabicBold' if bold else 'Arabic',size)
def text(t,x,y,size=12,color=NAVY,bold=False,align='right'):
    c.setFillColor(HexColor(color));c.setFont('ArabicBold' if bold else 'Arabic',size)
    s=shaped(t)
    {'right':c.drawRightString,'left':c.drawString,'center':c.drawCentredString}[align](x,y,s)

def wrap(t,max_width,size=12,bold=False):
    result=[]
    for raw in str(t).split('\n'):
        line=''
        for word in raw.split():
            candidate=(line+' '+word).strip()
            if line and width(candidate,size,bold)>max_width:result.append(line);line=word
            else:line=candidate
        result.append(line)
    return result

def para(t,y,x=564,w=516,size=12.3,color=NAVY,bold=False,leading=19):
    for line in wrap(t,w,size,bold):text(line,x,y,size,color,bold);y-=leading
    assert y>45, f'Page {page_no} overflow: {t[:70]}'
    return y-8

def heading(t,y):text(t,564,y,16,'#111111',True);return y-29
def page(title,sub=''):
    global page_no
    if page_no:c.showPage()
    page_no+=1
    c.setFillColor(HexColor(TEAL));c.rect(48,752,516,3,fill=1,stroke=0)
    text('رِحلتي  |  فريق سراج',564,730,10,GRAY)
    text('04 OCT 2026',48,730,9,GRAY,align='left')
    text(title,564,688,24,'#111111',True)
    if sub:para(sub,662,size=11,color=GRAY,leading=17)
    c.setStrokeColor(HexColor(BORDER));c.line(48,44,564,44)
    text('بناء وتطوير فريق سراج  •  وثيقة مراجعة قبل النشر',564,27,9,GRAY)
    text(f'{page_no:02d}',48,27,10,TEAL,True,align='left')

def node(t,x,y,w=160,h=50,kind='box',dark=False):
    c.setLineWidth(1);c.setStrokeColor(HexColor(TEAL if dark else BORDER));c.setFillColor(HexColor(NAVY if dark else LIGHT))
    if kind=='decision':
        p=c.beginPath();p.moveTo(x+w/2,y+h);p.lineTo(x+w,y+h/2);p.lineTo(x+w/2,y);p.lineTo(x,y+h/2);p.close();c.drawPath(p,fill=1,stroke=1)
    else:c.roundRect(x,y,w,h,9,fill=1,stroke=1)
    lines=wrap(t,w-18,11.5,True)
    if len(lines)*16>h-8:raise ValueError('Node text too tall: '+t)
    for i,line in enumerate(lines):text(line,x+w/2,y+h/2+(len(lines)-1)*8-i*16-4,11.5,'#FFFFFF' if dark else NAVY,True,'center')

def arrow(points,label=None,labelpos=None):
    c.setStrokeColor(HexColor(TEAL));c.setFillColor(HexColor(TEAL));c.setLineWidth(1.5)
    p=c.beginPath();p.moveTo(*points[0])
    for pt in points[1:]:p.lineTo(*pt)
    c.drawPath(p)
    a,b=points[-2:];angle=math.atan2(b[1]-a[1],b[0]-a[0]);s=6
    p=c.beginPath();p.moveTo(*b);p.lineTo(b[0]-s*math.cos(angle-.45),b[1]-s*math.sin(angle-.45));p.lineTo(b[0]-s*math.cos(angle+.45),b[1]-s*math.sin(angle+.45));p.close();c.drawPath(p,fill=1,stroke=0)
    if label:text(label,*labelpos,10,TEAL,True,'center')

def table(headers,rows,y,widths,size=11):
    # Logical column order is right-to-left. Explicit light borders on every cell.
    assert sum(widths)==516
    for rowno,row in enumerate([headers]+rows):
        cells=[wrap(t,w-16,size,rowno==0) for t,w in zip(row,widths)]
        rh=max(len(lines) for lines in cells)*16+18
        assert y-rh>55, f'Table overflow on {page_no}'
        x=564
        for lines,w in zip(cells,widths):
            c.setFillColor(HexColor(NAVY if rowno==0 else ('#F2F6F8' if rowno%2==0 else '#FFFFFF')))
            c.setStrokeColor(HexColor(BORDER));c.setLineWidth(.55);c.rect(x-w,y-rh,w,rh,fill=1,stroke=1)
            for j,line in enumerate(lines):text(line,x-8,y-20-j*16,size,'#FFFFFF' if rowno==0 else NAVY,rowno==0)
            x-=w
        y-=rh
    return y-20

def link(label,url,y):
    text(label,564,y,11.5,TEAL,True)
    c.linkURL(url,(48,y-4,564,y+13),relative=0,thickness=0)
    c.setFont('Helvetica',8.5);c.setFillColor(HexColor(GRAY));c.drawString(48,y-16,url)
    return y-43

# 1
page('دليل رِحلتي','الويب والتطبيق • الفلوشارت والأدوات والصلاحيات ومراجعة متطلبات التحكيم')
icon=HERE.parents[1]/'rihlatiApp'/'assets'/'icon.png'
if icon.exists():c.drawImage(str(icon),436,490,width=128,height=128,mask='auto')
text('رحلة المسلم الجديد',564,456,26,'#111111',True)
text('معرفة موثقة ورعاية بشرية',564,420,21,TEAL,True)
y=para('نطوّر في فريق سراج منصة تجمع التعلم والمحادثة الموثقة والمتابعة مع مكاتب الدعوة. يستخدم الويب والتطبيق الحسابات والبيانات نفسها، وتبقى الإدارة المركزية على الويب فقط.',375,size=14,leading=22)
y=heading('حالة النسخة',y-8)
y=para('التشغيل المحلي متاح. أضيف تطبيق Capacitor ومشروعا Android وiOS، وبُني APK تجريبي لأندرويد. لم يُنشر رابط عام أو مستودع GitHub، ولم تُبنَ نسخة iOS موقعة أو تُختبر كل الأجهزة.',y)
y=para('هذه الوثيقة تصف ما نُفذ وما يحتاج استكمالًا قبل التحكيم. ليست شهادة أمنية أو اعتمادًا شرعيًا، ولا تتضمن أسرارًا أو بيانات أعضاء.',y,color=GRAY)
text('المسارات الواردة نسبية إلى المجلدين Rihlati وrihlatiApp',564,112,11,GRAY)
text('الفكرة الأساسية محفوظة في وثيقة أساس هيكلة الفكرة',564,88,11,GRAY)

# 2
page('بنية المنظومة المشتركة','واجهتان وحسابات واحدة • لا توجد نسخة منفصلة من قاعدة بيانات المستفيدين')
node('واجهة الويب\nRihlati/app',394,565,170,55,dark=True)
node('واجهة الهاتف وتجربتها\nrihlatiApp و /app/',48,565,210,55,dark=True)
node('جلسة ويب\n/api/',399,467,160,52)
node('جلسة تطبيق مستقلة\n/app-api/',73,467,160,52)
arrow([(479,565),(479,519)]);arrow([(153,565),(153,519)])
node('الخادم المشترك\nالصلاحيات والنطاق وCSRF',191,358,230,62,dark=True)
arrow([(479,467),(479,445),(306,445),(306,420)])
arrow([(153,467),(153,445),(306,445)])
node('SQLite\nبيانات المنصة',403,237,161,57)
node('ملفات خاصة\nكتب وصور',225,237,161,57)
node('المعرفة والمساعد\nوالصوت',48,237,161,57)
arrow([(306,358),(306,330),(483,330),(483,294)])
arrow([(306,330),(306,294)]);arrow([(306,330),(128,330),(128,294)])
y=para('الموقع يعرض تجربة التطبيق على /app/، بينما يوجّه التطبيق المثبت طلباته إلى عنوان HTTPS المعتمد. تُفحص هوية الحساب وصلاحياته في الخادم لكل عملية، وليس في شكل الواجهة وحده.',190)
para('SQLite مناسبة لنسخة خادم واحدة بحمل محدود. التوسع إلى عدة خوادم يحتاج خطة مستقلة للقاعدة والملفات وطابور الفهرسة. مفتاح المزود لا يدخل حزمة التطبيق.',y,color=GRAY)

# 3
page('فلوشارت الويب','الأعضاء ومكاتب الدعوة والإدارة المركزية')
node('فتح الويب\nدخول أو تسجيل',206,573,200,52,dark=True)
node('نوع العضوية',226,470,160,63,kind='decision')
arrow([(306,573),(306,533)])
node('مستفيد\nاختيار 1 إلى 3 مكاتب',402,362,162,58)
node('مكتب دعوة\nانتظار اعتماد الإدارة',225,362,162,58)
node('أدمن\nصلاحيات مفصلة',48,362,162,58)
arrow([(386,501),(483,501),(483,420)],'مستفيد',(479,513))
arrow([(306,470),(306,420)],'مكتب',(329,445))
arrow([(226,501),(129,501),(129,420)],'أدمن',(130,513))
node('الرحلة والشات\nالشائعة والتذاكر',402,255,162,60,dark=True)
node('متابعة المستفيدين\nالتذاكر والمكتبة',225,255,162,60,dark=True)
node('الإدارة المركزية\nالحسابات والاعتماد',48,255,162,60,dark=True)
for x in (483,306,129):arrow([(x,362),(x,315)])
y=para('يشترط التسجيل الاسم وكلمة المرور، ويمكن للإدارة إلزام البريد والجوال. لكل حساب بيانات وصورة وتغيير كلمة مرور. كلمات المرور الجديدة 8–128 خانة مع حرف لاتيني كبير ورقم ورمز خاص.',207)
para('الأدمن الرئيسي محمي من الحذف والإيقاف وخفض الصلاحيات. ربط المستفيد لا يفتح محادثاته الخاصة للمكاتب؛ يرى المكتب نطاقه والتذاكر الموجهة إليه.',y,color=GRAY)

# 4
page('فلوشارت التطبيق','الهاتف والتابلت • نفس العضويات والبيانات مع فصل الإدارة')
node('تشغيل تطبيق رِحلتي\nAndroid أو iOS أو تجربة الويب',188,563,236,60,dark=True)
node('الدور من الخادم',226,464,160,63,kind='decision')
arrow([(306,563),(306,527)])
node('أدمن\nرسالة استخدم الويب',48,351,161,58)
node('مكتب معتمد\nمساحة عمل المكتب',225,351,161,58)
node('مستفيد\nالرئيسية والتقدم',403,351,161,58)
arrow([(226,495),(128,495),(128,409)])
arrow([(306,464),(306,409)])
arrow([(386,495),(483,495),(483,409)])
node('انتقال إلى الويب\nلا جلسة إدارة بالتطبيق',48,245,161,60,dark=True)
node('متابعة وردود\nمراجع وجودة وفريق',225,245,161,60,dark=True)
node('كتب وأسئلة وصوت\nمختص وحسابي',403,245,161,60,dark=True)
for x in (128,306,483):arrow([(x,351),(x,305)])
y=para('المكتب غير المعتمد يبقى في انتظار التنشيط. منع الأدمن مطبق في مسارات /app-api/ وجلسات الخادم، ولا يمكن تجاوزه بإظهار زر مخفي أو إعادة استخدام جلسة ويب.',205)
para('فُحص التخطيط بعروض هاتف وتابلت وسطح مكتب. بناء APK تجريبي لا يعني اكتمال اختبار الميكروفون والجلسات والرفع على أجهزة حقيقية. نسخة iOS تحتاج Mac وXcode وتوقيعًا واختبارًا.',y,color=GRAY)

# 5
page('فلوشارت السؤال والمختص','الاسترجاع الموثق يسبق الجواب • لا نجيب دون دليل كافٍ')
node('سؤال كتابة أو صوت\nمراجعة التفريغ قبل الإرسال',194,570,224,58,dark=True)
node('سياق ولغة ثم استرجاع\nمصادر وتصحيحات معتمدة',194,476,224,58)
arrow([(306,570),(306,534)])
node('دليل كافٍ',226,373,160,66,kind='decision')
arrow([(306,476),(306,439)])
node('جواب بمصدر وصفحة\nوزر الاستماع',390,269,174,61,dark=True)
node('تذكرة للمكتب المختار\nأو الإدارة المركزية',48,269,205,61,dark=True)
arrow([(386,406),(477,406),(477,330)],'نعم',(477,417))
arrow([(226,406),(150,406),(150,330)],'لا',(150,417))
arrow([(390,299),(253,299)],'بطلب المستخدم',(322,314))
node('رد المختص للمستفيد\nواقتراح معرفة عند ملاءمتها',48,172,205,61)
arrow([(150,269),(150,233)])
text('أو متابعة المحادثة',477,240,11,TEAL,True,'center')
para('عند تفعيل المزود: إعادة صياغة السؤال، استرجاع الأدلة، توليد مقيد بها، ثم مراجعة آلية ثانية. دون المزود: مقتطفات صالحة أو تصعيد. التحقق الآلي ليس اعتمادًا بشريًا، والفتاوى الخاصة لا تعمم.',126,size=11.5,leading=18)

# 6
page('فلوشارت المعرفة والتعلّم المراجع','توسيع المكتبة لا يعني تدريب أوزان النموذج تلقائيًا')
node('رفع PDF وتحديد اللغة\nوالمستوى والموضوع',392,559,172,62,dark=True)
node('نسبة المرجع للرافع\nثم استخراج أو OCR',219,559,153,62)
node('مراجعة الصفحات\nوجودة النص',48,559,151,62)
arrow([(392,590),(372,590)]);arrow([(219,590),(199,590)])
node('اعتماد المخوّل',49,449,151,64,kind='decision')
arrow([(124,559),(124,513)])
node('معرفة متاحة للاسترجاع\nمصدر وصفحة ومراجع',265,454,299,57,dark=True)
arrow([(200,481),(265,481)],'نعم',(232,493))
node('يبقى خارج الإجابات\nحتى اكتمال المراجعة',48,349,190,61)
arrow([(124,449),(124,410)],'لا',(144,430))
y=para('رد المختص العام يحتاج توثيقًا واعتمادًا قبل إعادة استخدامه. سحب الاعتماد يستبعد المعرفة من الإجابات مع بقاء أثر المراجعة.',321)
y=heading('جرد المكتبة الحالية',y)
y=table(['البيان','الموجود'],[
    ['المراجع والصفحات والمقاطع','13 مرجعًا، 640 صفحة، 1080 مقطعًا'],
    ['لغات المصادر','العربية والإنجليزية والتغالوغ'],
    ['مناهج المستويات','تسعة كتب؛ المستوى الثالث يحتوي السيرة'],
],y,[165,351],10.8)

# 7
page('الأدوات واللغات البرمجية','ملفات منظمة قابلة للنقل دون الاعتماد على مسار جهاز المطور')
y=table(['الجزء','التقنية','وظيفتها'],[
    ['واجهة الويب','HTML / CSS / JavaScript','الرحلة والشات والمكاتب والإدارة'],
    ['تطبيق الهاتف','Capacitor 8','واجهة هاتف وتكامل أصلي مع Android وiOS'],
    ['الخادم','Python + Flask + Waitress','API والجلسات والصلاحيات والتشغيل'],
    ['التخزين','SQLite','قاعدة مشتركة وترحيلات إضافية'],
    ['كلمات المرور','Argon2id','تجزئة مملحة غير قابلة للاسترجاع كنص'],
    ['استرجاع المعرفة','BM25','بحث نصي من المراجع المعتمدة'],
    ['الذكاء والصوت','مزود خادمي','توليد من الأدلة وتفريغ وقراءة النص'],
    ['PDF وOCR','pypdf / PDF.js / Tesseract','استخراج وقراءة وفهرسة مع مراجعة'],
],622,[104,181,231],10.7)
y=heading('تنظيم الملفات',y-4)
y=para('Rihlati: الويب والخادم وملفات التشغيل الخاصة. rihlatiApp: المصدر ومشروعا الهاتف. ناتج www مولّد من قائمة محددة من الكود المشترك ومن واجهة الهاتف؛ لا نعدله يدويًا.',y)
y=para('مفتاح المزود في ملف .enviroment.local خاص بالخادم ومستثنى من Git. الملف ليس مشفرًا بذاته؛ يحتاج صلاحيات ملفات وتشفير قرص ونسخ آمنة. لا مفتاح خدمة أو قاعدة بيانات داخل حزمة الهاتف.',y,color=GRAY)

# 8
page('الصلاحيات وأدوات التحكم','النطاق والتحقق من الخادم أساس حماية حسابات المستفيدين')
y=table(['الوظيفة','المستفيد','مكتب الدعوة','الأدمن بالويب'],[
    ['الرحلة والشات والتذاكر','بياناته','بحسب دوره','وفق الصلاحية'],
    ['متابعة المستفيدين','لا','المرتبطون فقط','وفق الصلاحية'],
    ['الرد على التذاكر','متابعة الرد','الموجهة لمكتبه','وفق الصلاحية'],
    ['رفع المرجع واقتراح تصحيح','لا','ضمن نطاقه','وفق الصلاحية'],
    ['اعتماد المعرفة والمكاتب','لا','لا','صلاحية مخصصة'],
    ['المفتاح وشروط التسجيل','لا','لا','صلاحية مخصصة'],
    ['إدارة الإداريين','لا','لا','الرئيسي محمي'],
    ['الإدارة من تطبيق الهاتف','لا','لا','ممنوعة'],
],621,[166,84,135,131],10.6)
y=heading('ضوابط قائمة وحدود معلنة',y-6)
y=para('جلسات HttpOnly وحماية CSRF، وSecure عند الإنتاج، وفصل سطح التطبيق عن الويب، وفحص نطاق المكتب، وتجزئة كلمات المرور، وقائمة سماح للملفات المعروضة. تغيير كلمة المرور ينهي الجلسات الأخرى.',y)
para('هذه الضوابط واختباراتها لا تثبت غياب جميع الثغرات. قبل النشر نحتاج اختبارًا أمنيًا مستقلاً وخصوصية وموافقة على معالجة الصوت والنص ومراقبة وحماية رفع الملفات.',y,color=GRAY)

# 9
page('مطابقة متطلبات التحدي','البنود الستة في الصورة المرسلة من قائد الفريق')
y=table(['المخرج','حالته الحالية','ما يزال مطلوبًا'],[
    ['حل يعمل بالكامل','وظائف محلية واختبارات وبناء Android تجريبي','اختبار قبول وأجهزة وصوت ثم نشر محكوم'],
    ['GitHub عام بلا أسرار','ترتيب المشروع وتوثيق واستثناءات','ترخيص وفحص الملفات والتاريخ ثم الموافقة والنشر'],
    ['فيديو حتى دقيقتين','سيناريو مقترح؛ لم يسجل فيديو جديد','تسجيل 115 ثانية ومونتاج والتحقق من المدة'],
    ['عرض PDF أو PowerPoint','عرض محدّث بواجهات الويب والتطبيق','مراجعة النتائج وخطة الاستمرار قبل التسليم'],
    ['توثيق المصادر والتحقق','مصدر وصفحة ومسار اعتماد','حقوق وطبعات ومراجعة شرعية ولغوية وتقييم'],
    ['رابط Live Demo','تشغيل محلي فقط','استضافة وHTTPS واختبار من شبكة خارجية'],
],624,[115,189,212],11)
y=heading('نتائج قابلة للإثبات',y)
y=para('81 اختبارًا للخادم و7 اختبارات خاصة بالتطبيق، في بيئات معزولة دون مكالمات AI مدفوعة. بُني APK Debug. فُحص تسجيل العضو وقارئ PDF والتصعيد ومنع الأدمن محليًا؛ لا توجد نتائج استخدام ميداني أو نسب دقة بشرية منشورة.',y)
para('المخطط القابل للتعديل في WORKFLOW.md، وسجل النواقص التفصيلي في JUDGING_READINESS.md. يجب تحديثهما عند كل إصدار.',y,size=11,color=GRAY,leading=17)

# 10
page('خيارات الاستضافة لشهرين','تقديرات 4 أكتوبر 2026 • قبل الضريبة والدومين الخاص واستهلاك الذكاء والصوت')
y=table(['الخيار','التكلفة الأساسية','الدومين والقيود'],[
    ['DigitalOcean\n4 GB / 2 CPU / 80 GB','48 دولارًا لشهرين\n62.40 مع نسخ يومية','دومين مستقل؛ إدارة Linux وTLS مطلوبة'],
    ['Render\n1 CPU / 2 GB + 10 GB قرص','55 دولارًا لشهرين\nعلى مساحة Hobby','رابط onrender.com وTLS؛ السعة وOCR يحتاجان قياسًا'],
    ['Hostinger VPS\nKVM 2','السعر الإعلاني 8.99 شهريًا مرتبط بمدة ودفع مقدم','دومين مجاني مع مدة مؤهلة 12 شهرًا أو أكثر؛ تحقق من الإجمالي'],
],624,[160,164,192],11)
y=para('الترشيح التقني: DigitalOcean بذاكرة 4 GB كبداية للمنظومة والفهرسة، مع دومين مستقل. إذا كانت الأولوية لرابط HTTPS دون شراء اسم الآن، فإن Render المدفوع بديل مناسب لتجربة محدودة الحمل بعد التكييف والاختبار.',y)
y=para('حساب Render: 25 دولارًا للحوسبة + 2.50 للقرص شهريًا. مقعد استضافة واحد و5 GB نقل ضمن Hobby؛ الزيادة 0.15 دولار لكل GB. مساحة Pro للفريق تضيف 25 دولارًا شهريًا. لا نستخدم القرص المؤقت لحفظ SQLite.',y,size=11.5,leading=18)
y=para('عرض الدومين المجاني من Hostinger لا يشمل الاشتراك الشهري؛ السعر الشهري المعروض ليس وعدًا بفوترة شهرين فقط. الامتداد وتوافر الاسم وشروط العرض تُحسم وقت الشراء. لم تُشترَ أي خدمة.',y,size=11.5,leading=18,color=GRAY)
text('المراجع والروابط الرسمية في الصفحة 12 وفي HOSTING_OPTIONS.md',564,80,10,GRAY)

# 11
page('خطة الإغلاق قبل الرفع','نحفظ الخصائص الأساسية ونعالج النواقص وفق اختبارات قبول واضحة')
y=heading('التحقق الوظيفي والمحتوى',622)
y=para('تجربة حسابات عضو ومكتب وأدمن؛ ربط 1–3 مكاتب؛ تقدم مشترك بين الويب والتطبيق؛ جواب بمصدر؛ إحالة بلا دليل أو بطلب العضو؛ رد مختص؛ عزل المكتب؛ منع مرجع وتصحيح غير معتمدين. تُسجل النتيجة والتاريخ والمنفذ.',y)
y=para('مراجعة بشرية لعينة أسئلة موثقة وصفحات OCR والمصطلحات واللغات. صُحح توافق رمزي fil وtl للاسترجاع دون إعادة كتابة المصادر. استكمال المراجع الأصلية للغات الناقصة قبل الادعاء بتغطيتها.',y)
y=heading('الأجهزة والاستضافة والأمان',y)
y=para('اختبار Android وiPhone وiPad فعليًا: HTTPS والجلسة والميكروفون والتفريغ والقراءة والرفع وPDF والخلفية والاتجاه وحجم النص. ثم إعداد الخدمة والوكيل والجدار والمراقبة وحدود الإنفاق والنسخ، وتجربة استعادة منفصلة.',y)
y=para('للمستودع العام ننشر الكود المسموح فقط: لا قواعد أو محادثات أو تسجيلات أو أسرار أو مفاتيح توقيع أو كتب بلا إذن. نختار ترخيص الكود ونراجع الملفات المرشحة والتاريخ. استثناء Git وحده لا يكفي.',y)
y=heading('سيناريو الفيديو المقترح',y)
y=table(['الثواني','المشهد'],[
    ['0–15','الشعار ومشكلة متابعة المسلم الجديد'],
    ['15–35','المسار التعليمي على الهاتف'],
    ['35–60','سؤال وجواب موثق واستماع'],
    ['60–85','تصعيد ورد مكتب الدعوة'],
    ['85–105','إضافة مرجع وتصحيح واعتماد'],
    ['105–115','رابط التجربة وهوية فريق سراج'],
],y,[95,421],10.7)

# 12
page('المراجع وخطة الاستمرار','روابط رسمية قابلة للنقر • الأسعار والشروط قابلة للتغيير')
y=622
for label,url in [
    ('أسعار DigitalOcean للحوسبة والنسخ','https://www.digitalocean.com/pricing/droplets'),
    ('أسعار Render للحوسبة والقرص ومساحة العمل','https://render.com/pricing'),
    ('خدمات Render والرابط وشهادات TLS','https://render.com/docs/web-services'),
    ('القرص الدائم وحدوده في Render','https://render.com/docs/disks'),
    ('خطط Hostinger VPS','https://www.hostinger.com/vps-hosting'),
    ('شروط الدومين المجاني في Hostinger','https://www.hostinger.com/support/1583407-how-to-register-a-domain-for-free-at-hostinger/'),
    ('متطلبات بناء Capacitor','https://capacitorjs.com/docs/getting-started/environment-setup'),
]:y=link(label,url,y)
y=heading('تشغيل تجربة التحكيم',y-8)
y=para('قبل الإطلاق التجريبي نختار مسؤول دعم ومراجع محتوى ومدة استضافة تغطي شهرين على الأقل. نستخدم حسابات تحكيم وبيانات اصطناعية قدر الإمكان، ونحدد سقف الإنفاق وآلية التعامل مع تعطل المزود، ونراجع النسخ والاستعادة.',y)
y=para('بعد التحكيم نقيس جودة الاستشهاد والامتناع وجودة الصوت وزمن الاستجابة بأدلة فعلية. التوسع إلى مزيد من اللغات والمراجع والبحث الدلالي والتحليلات ومزايا التربية المتكيفة يحتاج تطويرًا واعتمادًا مستقلًا.',y)
para('مصادر وصف التنفيذ: PROJECT_ARCHITECTURE.md وملفات الخادم والتطبيق واختباراتها. مرجع متطلبات التسليم: الصورة المقدمة من قائد الفريق. هذه الوثيقة لا تستبدل تحديث عرض المسابقة أو تسجيل الفيديو.',y,size=11,color=GRAY,leading=17)
c.save()
print('Created 12-page Arabic guide:',DEST)
