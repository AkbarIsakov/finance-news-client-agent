"""Loading and cleaning input files; no network calls."""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from difflib import SequenceMatcher
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / 'data'


def read_data(data_dir: Path = DATA_DIR) -> dict:
    with open(data_dir / 'clients.json', encoding='utf-8') as f:
        clients = json.load(f)
    with open(data_dir / 'products.json', encoding='utf-8') as f:
        products = json.load(f)
    with open(data_dir / 'internal_notes.json', encoding='utf-8') as f:
        notes = json.load(f)
    news = pd.read_csv(data_dir / 'news.csv').fillna('')
    required = {'title', 'text', 'source'}
    if not required.issubset(news.columns):
        raise ValueError(f'In news.csv required columns: {sorted(required)}')
    return {'clients': clients, 'products': products, 'notes': notes, 'news': news}


def norm_text(text: str) -> str:
    return re.sub(r'\s+', ' ', str(text).replace('ё', 'е')).strip().casefold()


def client_pattern(name: str) -> re.Pattern:
    """Conservative mention matching. Extend aliases via a curated data file in production."""
    forms = {
        'Аэрофлот': r'аэрофлот(?:а|у|ом|е)?',
        'РусГидро': r'русгидро',
        'Норникель': r'норникел(?:ь|я|ю|ем|е)',
        'РЖД': r'ржд',
        'Магнит': r'магнит(?:а|у|ом|е)?',
        'Лукойл': r'лукойл(?:а|у|ом|е)?',
        'МТС': r'мтс',
        'ФосАгро': r'фосагро',
    }
    pattern = forms.get(name, re.escape(norm_text(name)))
    return re.compile(r'(?<![\w])(?:' + pattern + r')(?![\w])', re.IGNORECASE)


def resolve_client(request: str, names: list[str]) -> str:
    s = norm_text(request)
    matches = []
    for name in names:
        p = client_pattern(name)
        m = p.search(s)
        if m:
            matches.append((m.end()-m.start(), name))
    if len(matches) == 1:
        return matches[0][1]
    if len(matches) > 1:
        raise ValueError('В запросе несколько клиентов: ' + ', '.join(n for _, n in matches))
    raise ValueError('Не удалось определить клиента. Доступны: ' + ', '.join(names))


def note_for_client(name: str, notes: list[str]) -> str:
    for note in notes:
        if client_pattern(name).search(norm_text(note[:100])):
            return note
    return ''


def publisher(source: str) -> str:
    """Publisher identity, not RSS feed. Telegram channels kept separate."""
    try:
        parsed = urlsplit(str(source))
        host = (parsed.hostname or '').casefold().removeprefix('www.')
        if host in {'t.me', 'telegram.me'}:
            parts = [x for x in parsed.path.strip('/').split('/') if x and x != 's']
            return f't.me/{parts[0].casefold()}' if parts else 't.me'
        return host or source.strip()
    except ValueError:
        return source.strip()


def relevant_news(row: dict, name: str) -> tuple[bool,int]:
    """Only client-centric items; avoid incidental mentions far down news roundups."""
    title = str(row['title'])
    text = re.sub(r'\s+', ' ', str(row['text']))
    pattern = client_pattern(name)
    title_hit = bool(pattern.search(norm_text(title)))
    # News usually duplicates title and uses first paragraph for the lead
    lead_hit = bool(pattern.search(norm_text(text[:520])))
    return title_hit or lead_hit, (4 if title_hit else 1)


def news_to_documents(records: pd.DataFrame, clients: dict) -> list[dict]:
    out = []
    for i, row in records.iterrows():
        doc = row.to_dict()
        matched = [name for name in clients if relevant_news(doc, name)[0]]
        out.append({
            'id': f'news:{i}', 'kind': 'news',
            'title': str(doc['title']).strip(),
            'content': str(doc['text']).strip()[:2600],
            'source': str(doc['source']),
            'publisher': publisher(str(doc['source'])),
            'client_ids': matched,
            'news_row': int(i) + 1,
        })
    return out


def all_documents(dataset: dict) -> list[dict]:
    docs = []
    for name, description in dataset['clients'].items():
        docs.append({'id': f'profile:{name}', 'kind':'profile',
                     'client_id':name, 'title':name, 'content':description,
                     'source':'clients.json'})
        note = note_for_client(name, dataset['notes'])
        if note:
            docs.append({'id': f'note:{name}', 'kind':'note',
                         'client_id':name, 'title':f'Внутренние заметки: {name}',
                         'content':note, 'source':'internal_notes.json'})
    for name, description in dataset['products'].items():
        docs.append({'id':f'product:{name}','kind':'product',
                     'product_name':name,'title':name,'content':description,
                     'source':'products.json'})
    docs.extend(news_to_documents(dataset['news'], dataset['clients']))
    return docs
