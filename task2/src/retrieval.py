"""OpenSearch BM25 retrieval and a visibly labelled local demo backend."""
from __future__ import annotations
import os
from typing import Protocol
from .data import all_documents

INDEX_NAME = 'task2_client_knowledge_v1'


def config_float(name: str, default: float) -> float:
    """Read an explicitly named retrieval weight from the environment."""
    value = float(os.getenv(name, str(default)))
    if not 0 <= value <= 100:
        raise ValueError(f'{name} must be between 0 and 100')
    return value


def split_into_chunks(content: str, chunk_size: int, overlap: int) -> list[str]:
    """Produce overlapping character chunks with a word-boundary preference.

    size=0 disables chunking. This is an experimental OpenSearch indexing
    choice, not an LLM context window. Preserve source attribution per chunk.
    """
    if chunk_size == 0 or len(content) <= chunk_size:
        return [content]
    if chunk_size < 100 or overlap < 0 or overlap >= chunk_size:
        raise ValueError('NEWS_CHUNK_SIZE >= 100 and 0 <= NEWS_CHUNK_OVERLAP < size')
    pieces, start = [], 0
    while start < len(content):
        end = min(start + chunk_size, len(content))
        if end < len(content):
            sep = content.rfind(' ', start + chunk_size // 2, end)
            if sep > start:
                end = sep + 1
        piece = content[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(content):
            break
        start = max(start + 1, end - overlap)
    return pieces


def indexed_documents(dataset: dict, chunk_size: int = 0, overlap: int = 0) -> list[dict]:
    """Optional chunking affects retrieval; returned articles retain original IDs."""
    documents = all_documents(dataset)
    if not chunk_size:
        return documents
    output = []
    for document in documents:
        if document['kind'] != 'news':
            output.append(document)
            continue
        chunks = split_into_chunks(document['content'], chunk_size, overlap)
        for index, chunk in enumerate(chunks):
            clone = document.copy()
            clone['id'] = f"{document['id']}:chunk:{index}"
            clone['content'] = chunk
            clone['full_content'] = document['content']
            output.append(clone)
    return output


class Retriever(Protocol):
    def get_context(self, client_name: str, limit_news: int = 18) -> dict: ...


class LocalRetriever:
    """For demos/tests only: deterministic local filtering, no OpenSearch."""
    def __init__(self, dataset: dict):
        self.docs = all_documents(dataset)

    def get_context(self, client_name: str, limit_news: int = 18) -> dict:
        by_id = {doc['id']: doc for doc in self.docs}
        return {
            'profile': by_id[f'profile:{client_name}'],
            'note': by_id.get(f'note:{client_name}'),
            'products': [x for x in self.docs if x['kind'] == 'product'],
            'news': [x for x in self.docs if x['kind'] == 'news'
                     and client_name in x['client_ids']][:limit_news],
            'backend': 'local-demo',
        }


class OpenSearchRetriever:
    def __init__(self, url: str | None = None):
        try:
            from opensearchpy import OpenSearch
        except ImportError as e:
            raise RuntimeError('Установи зависимости: pip install -r requirements.txt') from e
        self.index_name = os.getenv('OPENSEARCH_INDEX_NAME', INDEX_NAME)
        self.client = OpenSearch(hosts=[url or os.getenv('OPENSEARCH_URL', 'http://localhost:9200')],
                                 timeout=30)

    def check(self):
        try:
            if not self.client.ping():
                raise ConnectionError('OpenSearch не отвечает')
        except Exception as e:
            raise RuntimeError('Нет подключения к OpenSearch. Запусти docker compose up -d') from e

    def index_all(self, dataset: dict) -> int:
        from opensearchpy.helpers import bulk
        self.check()
        if self.client.indices.exists(index=self.index_name):
            self.client.indices.delete(index=self.index_name)
        self.client.indices.create(index=self.index_name, body={
            'settings': {'number_of_shards': 1, 'number_of_replicas': 0},
            'mappings': {'properties': {
                'kind': {'type':'keyword'},
                'client_id': {'type':'keyword'},
                'client_ids': {'type':'keyword'},
                'product_name': {'type':'keyword'},
                'news_row': {'type':'integer'},
                'title': {'type':'text', 'analyzer':'russian'},
                'content': {'type':'text', 'analyzer':'russian'},
                'full_content': {'type':'text', 'index':False},
                'source': {'type':'keyword', 'ignore_above':2048},
                'publisher': {'type':'keyword'},
            }},
        })
        chunk_size = int(os.getenv('NEWS_CHUNK_SIZE', '0'))
        overlap = int(os.getenv('NEWS_CHUNK_OVERLAP', '100'))
        docs = indexed_documents(dataset, chunk_size, overlap)
        actions = ({'_index': self.index_name, '_id': doc['id'], '_source': doc}
                   for doc in docs)
        count, errors = bulk(self.client, actions, chunk_size=200, request_timeout=120,
                             raise_on_error=False)
        if errors:
            raise RuntimeError(f'Ошибки индексации: {errors[:2]}')
        self.client.indices.refresh(index=self.index_name)
        return count

    def _one(self, doc_id: str) -> dict | None:
        try:
            return self.client.get(index=self.index_name, id=doc_id)['_source']
        except Exception as exc:
            if getattr(exc, 'status_code', None) == 404:
                return None
            raise

    def _find(self, query: dict, size: int) -> list[dict]:
        res = self.client.search(index=self.index_name,
                                 body={'size':size,'query':query}, request_timeout=30)
        return [hit['_source'] for hit in res['hits']['hits']]

    def get_context(self, client_name: str, limit_news: int = 18) -> dict:
        self.check()
        if not self.client.indices.exists(index=self.index_name):
            raise RuntimeError('Нет индекса. Сначала выполни python -m src.cli index')
        profile = self._one(f'profile:{client_name}')
        if not profile:
            raise ValueError(f'Клиент {client_name} отсутствует в индексе')
        note = self._one(f'note:{client_name}')
        products = self._find({'term': {'kind': 'product'}}, size=100)
        query_mode = os.getenv('NEWS_QUERY_MODE', 'balanced').lower()
        if query_mode not in {'balanced', 'title_only'}:
            raise ValueError('NEWS_QUERY_MODE must be balanced or title_only')
        should = [
            {'match': {'title': {'query': client_name, 'boost': config_float('NEWS_TITLE_BOOST', 4.0)}}},
        ]
        if query_mode == 'balanced':
            should.append({'match': {'content': {'query': client_name, 'boost': config_float('NEWS_CONTENT_BOOST', 1.0)}}})
        news = self._find({
            'bool': {
                'filter': [
                    {'term': {'kind': 'news'}},
                    {'term': {'client_ids': client_name}},
                ],
                'should': should,
                'minimum_should_match': 1,
            }
        }, size=min(limit_news * (4 if int(os.getenv('NEWS_CHUNK_SIZE', '0')) else 1), 1000))
        # Different chunks of one article must NOT be counted as different news.
        unique_news = []
        seen_rows = set()
        for doc in news:
            row = int(doc['news_row'])
            if row in seen_rows:
                continue
            seen_rows.add(row)
            normalized = doc.copy()
            normalized['id'] = f'news:{row - 1}'
            normalized['content'] = doc.get('full_content', doc['content'])
            unique_news.append(normalized)
            if len(unique_news) >= limit_news:
                break
        news = unique_news
        return {'profile':profile,'note':note,'products':products,'news':news,
                'backend':'opensearch-bm25'}
