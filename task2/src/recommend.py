"""Transparent evidence-based product and news selection."""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .data import client_pattern, norm_text

RECOMMENDED = ('может подойти', 'подходит', 'уместен', 'уместна', 'релевантен',
               'релевантна', 'сильной идеей', 'стоит', 'основной акцент', 'логично')
CAUTION = ('только если', 'только при', 'не стоит', 'не является', 'не выносить',
           'не ставить', 'вторич', 'осторож', 'без подтвержден', 'без дополнительных',
           'только как дополнитель', 'при наличии', 'после определения',
           'не выглядит', 'менее приоритет', 'лучше не', 'не рекоменд')


def sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+', str(text)) if x.strip()]


def note_sentences(note: str, product_name: str) -> list[str]:
    pat = re.compile(r'(?<![\w])' + re.escape(product_name) + r'(?![\w])', re.I)
    return [x for x in sentences(note) if pat.search(x)]


def rank_products(profile: dict, note: dict | None, products: list[dict], limit=3) -> list[dict]:
    """Client notes are authoritative; similarity only ranks ties or missing notes."""
    note_text = note['content'] if note else ''
    context = profile['content'] + ' ' + note_text
    descriptions = [p['content'] for p in products]
    if not products:
        return []
    vectors = TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5)).fit_transform(
        [context] + descriptions
    )
    sims = cosine_similarity(vectors[0], vectors[1:]).ravel()
    candidates = []
    for product, sim in zip(products, sims):
        name = product['product_name']
        evidence = note_sentences(note_text, name)
        # Phrase scoring: primary positive note takes precedence over generic similarity.
        score = float(sim) * 2
        caution = False
        if evidence:
            score += 5
            first_pos = note_text.casefold().find(name.casefold())
            if first_pos >= 0:
                score += max(0, 1.5 - first_pos / max(len(note_text),1))
            for quote in evidence:
                q = norm_text(quote)
                if any(x in q for x in RECOMMENDED):
                    score += 1.2
                if any(x in q for x in CAUTION):
                    caution = True
                    score -= 4.0
        quote = evidence[0] if evidence else ''
        if quote:
            # Split joined clauses such as 'FX Forward ... , Option Collar ...'
            names = sorted((x['product_name'] for x in products), key=len, reverse=True)
            separate = r',\s*(?=(?:' + '|'.join(map(re.escape, names)) + r')\b)'
            segments = re.split(separate, quote, flags=re.I)
            own = next((s for s in segments if re.search(
                r'(?<![\w])' + re.escape(name) + r'(?![\w])', s, flags=re.I)), quote)
            quote = own.strip(' ,')
        candidates.append({
            'name':name,'definition':product['content'],
            'evidence':quote,
            'product_source':product['id'],
            'note_source': note['id'] if evidence and note else '',
            'conditional':caution, 'score':score,
        })
    candidates.sort(key=lambda x:(-x['score'], x['conditional'], x['name']))
    # If a note exists, avoid proposing products it explicitly discourages.
    if note_text:
        # Drop clearly discouraged products, keep conditional ones as explicitly marked.
        declined = ('не выглядит', 'не является', 'не стоит', 'не ставить')
        candidates = [p for p in candidates if not (
            p['evidence'] and any(x in norm_text(p['evidence']) for x in declined)
        )]
    return candidates[:limit]


def pick_news(docs: list[dict], client: str, limit=4) -> list[dict]:
    """Select news where the client is a real subject, not part of a sidebar or roundup."""
    pattern = client_pattern(client)
    scored = []
    for doc in docs:
        title, body = doc.get('title', ''), doc.get('content','')
        if len(body.strip()) < 120:  # lists of names without an actual story
            continue
        title_hit = bool(pattern.search(norm_text(title)))
        lead_hit = bool(pattern.search(norm_text(body[:520])))
        if not (title_hit or lead_hit):
            continue
        # Deprioritize generic market roundups.
        score = (6 if title_hit else 1) + min(len(body), 900)/900
        if len(title) > 220 or title.count('📝') or 'основные события' in norm_text(title):
            score -= 3
        scored.append((score,doc))
    scored.sort(key=lambda x:-x[0])
    selected=[]
    for _,d in scored:
        title=norm_text(d['title'])
        if any(fuzz.ratio(title, norm_text(x['title'])) > 78 or
               fuzz.token_set_ratio(title, norm_text(x['title'])) > 88
               for x in selected):
            continue
        selected.append(d)
        if len(selected)>=limit:
            break
    return selected


def risk_points(profile: str, limit=4) -> list[str]:
    m = re.search(r'Основные финансовые риски\s*:\s*(.*?)(?:\.\s|$)', profile, re.I)
    if m:
        risks = [x.strip(' .;') for x in m.group(1).split(',') if x.strip()]
        return risks[:limit]
    # Some source profiles describe sensitivity rather than an explicit risk list.
    sensitive = re.search(r'чувствительностью к\s+(.+?)\.', profile, re.I)
    if sensitive:
        text = sensitive.group(1).replace(' и ', ', ')
        return [x.strip(' .;') for x in text.split(',') if x.strip()][:limit]
    sentences_ = sentences(profile)
    return [x for x in sentences_[:2] if x]
