"""Consistent, readable 16:9 PPTX layout using python-pptx."""
from __future__ import annotations
from datetime import datetime
import os
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

W,H = 13.333,7.5
NAVY='111E36'
DARK='17253E'
TEAL='376BD8' if os.getenv('PPTX_THEME','teal').lower() == 'blue' else '0DAEAB'
GOLD='E6A243'
INK='1A2B42'
SOFT='5D6980'
WHITE='FFFFFF'
PALE='F6F8FB'
BORDER='E5EAF1'


def rgb(hexcolor):
    return RGBColor.from_string(hexcolor)


def rectangle(slide,x,y,w,h,fill,radius=False,line=None):
    shape=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                Inches(x),Inches(y),Inches(w),Inches(h))
    shape.fill.solid();shape.fill.fore_color.rgb=rgb(fill)
    shape.line.fill.background() if line is None else None
    if line:
        shape.line.color.rgb=rgb(line);shape.line.width=Pt(0.7)
    if radius and shape.adjustments:
        shape.adjustments[0]=0.09
    return shape


def textbox(slide,text,x,y,w,h,size=16,bold=False,color=INK,align=None,
            valign=MSO_ANCHOR.TOP,margin=.04,maxlines=None):
    shape=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h))
    tf=shape.text_frame
    tf.clear();tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(margin)
    tf.margin_top=tf.margin_bottom=Inches(margin)
    tf.vertical_anchor=valign
    # single paragraph; text may contain intentional line breaks
    for ix,line in enumerate(str(text).split('\n')):
        p=tf.paragraphs[0] if ix==0 else tf.add_paragraph()
        p.text=line
        p.font.name='Aptos'
        p.font.size=Pt(size)
        p.font.bold=bold
        p.font.color.rgb=rgb(color)
        if align is not None:p.alignment=align
        p.space_after=Pt(2)
    return shape


def shorten(s: str,n: int) -> str:
    s=' '.join(str(s).split())
    if len(s)<=n:return s
    cut=s[:n-1].rsplit(' ',1)[0]
    return (cut if len(cut)>n*.55 else s[:n-1])+'…'


def chrome(prs,title,kicker,page,mode):
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    rectangle(slide,0,0,W,H,PALE)
    rectangle(slide,0,0,W,.12,TEAL)
    textbox(slide,'CLIENT INTELLIGENCE  /  ПОДГОТОВКА К ВСТРЕЧЕ',.7,.28,9,.24,10,True,TEAL)
    textbox(slide,title,.7,.70,11.75,.66,28,True,INK)
    rectangle(slide,.7,7.00,11.95,.015,BORDER)
    textbox(slide,'По предоставленным данным  •  Не является офертой',.72,7.09,8,.2,9,False,SOFT)
    textbox(slide,f'{page:02d}',12.05,7.09,.5,.2,9,True,SOFT,PP_ALIGN.RIGHT)
    return slide


def card(slide,x,y,w,h,fill=WHITE):
    return rectangle(slide,x,y,w,h,fill,radius=True,line=BORDER if fill==WHITE else None)


def build_pptx(client_name: str, profile: dict, note: dict | None,
               products: list[dict], news: list[dict], narrative: dict,
               risks: list[str], outfile: Path) -> Path:
    prs=Presentation()
    prs.slide_width=Inches(W);prs.slide_height=Inches(H)
    now=datetime.now().strftime('%d.%m.%Y')
    mode=narrative.get('mode','unknown')

    # 1. Cover
    s=prs.slides.add_slide(prs.slide_layouts[6]);rectangle(s,0,0,W,H,NAVY)
    rectangle(s,.0,.0,.16,H,TEAL)
    rectangle(s,10.35,0,2.98,H,DARK)
    rectangle(s,10.62,1.25,1.9,.08,TEAL)
    rectangle(s,11.25,1.65,1.3,.08,GOLD)
    rectangle(s,10.82,2.05,1.7,.08,TEAL)
    textbox(s,'CLIENT INTELLIGENCE',.85,.85,8,.3,14,True,TEAL)
    textbox(s,client_name,.82,2.02,9.2,1.25,44,True,WHITE)
    textbox(s,'Финансовые решения и новости для клиентской встречи',.87,3.58,8.8,.92,23,False,WHITE)
    rectangle(s,.88,5.40,6.4,.015,'436074')
    textbox(s,'Подготовлено по закрытой учебной базе данных',.89,5.61,8,.33,13,False,'BBC5D2')
    textbox(s,f'{now}   •   {"Демонстрационная версия" if mode=="deterministic-demo" else "GigaChat + OpenSearch"}',.89,6.35,9,.3,11,False,'BBC5D2')

    # 2. Client brief
    s=chrome(prs,'Клиент: бизнес-контекст', 'profile',2,mode)
    card(s,.7,1.63,11.9,2.07)
    rectangle(s,.7,1.63,.07,2.07,TEAL)
    textbox(s,'КЛЮЧЕВАЯ ХАРАКТЕРИСТИКА',1.05,1.94,10,.3,11,True,TEAL)
    textbox(s,shorten(profile['content'].split('. ')[0],280),1.02,2.39,11.1,1.01,20,False,INK)
    card(s,.7,3.94,11.9,1.83)
    textbox(s,'ФОКУС ВСТРЕЧИ',1.05,4.22,10,.24,11,True,TEAL)
    textbox(s,shorten(narrative['summary'],365),1.03,4.63,11,1.0,18,False,INK)
    textbox(s,'Основание: clients.json  •  внутренние заметки — internal_notes.json',.86,6.30,11,.35,11,False,SOFT)

    # 3. Risks
    s=chrome(prs,'Финансовые риски и задачи','risks',3,mode)
    subtitle='Приоритеты обсуждения из клиентского профиля — не утверждение о совершённых сделках'
    textbox(s,subtitle,.73,1.42,11.8,.35,13,False,SOFT)
    items=(risks or ['Требуется уточнить финансовые потребности клиента'])[:4]
    if len(items)<4:
        items=items+['Требуется уточнить фактический объём и горизонт риска']*(4-len(items))
    for i,txt in enumerate(items):
        x=.7+(i%2)*6.05;y=1.95+(i//2)*2.12
        card(s,x,y,5.83,1.87)
        textbox(s,f'{i+1:02d}',x+.22,y+.20,.8,.41,21,True,TEAL)
        textbox(s,shorten(txt[:1].upper()+txt[1:],165),x+1.1,y+.24,4.45,1.38,17,True,INK)

    # 4. Product recommendations
    s=chrome(prs,'Подходящие финансовые продукты','products',4,mode)
    textbox(s,'Подбор обоснован профилем, описаниями продуктов и внутренней заметкой',.74,1.42,12,.34,12,False,SOFT)
    for i,p in enumerate(products[:3]):
        y=1.87+i*1.52
        card(s,.7,y,11.9,1.34)
        rectangle(s,.7,y,.09,1.34,GOLD if p['conditional'] else TEAL)
        textbox(s,f'{i+1:02d}',.95,y+.20,.55,.46,17,True,TEAL)
        textbox(s,p['name'],1.58,y+.14,3.2,.39,20,True,INK)
        tag='После проверки условий' if p['conditional'] else 'Для обсуждения'
        textbox(s,tag,9.65,y+.22,2.55,.27,10,True,GOLD if p['conditional'] else TEAL,PP_ALIGN.RIGHT)
        why=narrative.get('product_fit',{}).get(p['name']) or p['evidence'] or p['definition']
        textbox(s,shorten(why,245),1.58,y+.58,10.55,.66,13.5,False,SOFT)
    textbox(s,'Предложения предварительные; условия применимости и риск-профиль уточняются с клиентом.',.80,6.62,11.6,.25,10.5,False,SOFT)

    # 5. News
    s=chrome(prs,'Новости, относящиеся к клиенту','news',5,mode)
    textbox(s,'Из предоставленного news.csv; дата отдельных сообщений может отсутствовать',.74,1.42,11.9,.3,12,False,SOFT)
    if not news:
        card(s,.7,1.95,11.9,2.45)
        textbox(s,'В исходной новостной выгрузке не найдено надёжных упоминаний клиента.',1.03,2.55,11.1,.95,20,False,INK)
    else:
        height=min(1.25,4.65/max(len(news),1)-.12)
        for i,n in enumerate(news[:4]):
            y=1.85+i*(height+.16)
            card(s,.7,y,11.9,height)
            textbox(s,f'N{i+1}',.91,y+.17,.55,.30,12,True,TEAL)
            textbox(s,shorten(n['title'],170),1.60,y+.12,10.55,.63,17,True,INK)
            textbox(s,shorten('Источник ленты: '+n['publisher'],135),1.61,y+height-.36,10.4,.23,10.5,False,SOFT)
    textbox(s,'Подбор — упоминания клиента, а не все новости отрасли.',.77,6.65,11.6,.22,10,False,SOFT)

    # 6. Meeting
    s=chrome(prs,'Что выяснить на встрече','meeting',6,mode)
    textbox(s,'Вопросы помогают проверить применимость финансовых инструментов',.74,1.43,11.6,.35,13,False,SOFT)
    for i,q in enumerate(narrative.get('questions',[])[:3]):
        y=1.92+i*1.50
        card(s,.7,y,11.9,1.29)
        textbox(s,f'{i+1:02d}',.96,y+.35,.70,.48,22,True,TEAL)
        textbox(s,shorten(q,210),1.79,y+.30,10.55,.78,17,False,INK)

    # 7. Sources
    s=chrome(prs,'Источники и ограничения','references',7,mode)
    textbox(s,'ИСПОЛЬЗОВАННЫЕ МАТЕРИАЛЫ',.76,1.55,11,.32,12,True,TEAL)
    sources=['[P] clients.json — профиль компании',
             '[I] internal_notes.json — внутренние комментарии по клиенту',
             '[F] products.json — описания финансовых инструментов',
             '[N] news.csv — новости и ссылки на RSS / Telegram-ленты']
    for i,entry in enumerate(sources):
        textbox(s,entry,.82,2.02+i*.46,11.8,.37,15,False,INK)
    textbox(s,'НОВОСТНЫЕ ИСТОЧНИКИ В ЭТОЙ ПРЕЗЕНТАЦИИ',.76,4.10,11.5,.27,12,True,TEAL)
    for i,n in enumerate(news[:4]):
        url=n.get('source','')
        textbox(s,shorten(f'[N{i+1}] {url}',115),.82,4.48+i*.33,11.6,.3,11,False,SOFT)
    textbox(s, 'Ограничения: в исходных материалах нет полноценной финансовой отчётности, '
             'подтверждённых валютных позиций, объёмов сделок и дат всех новостей. '
             'Рекомендации предварительные и требуют согласования.',.81,6.07,11.75,.65,11.1,False,SOFT)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(outfile))
    return outfile
