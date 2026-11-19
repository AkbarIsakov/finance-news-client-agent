"""Regression tests for independent A/B experiment controls, no API required."""
from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

from src.data import read_data
from src.retrieval import (
    OpenSearchRetriever, config_float, indexed_documents, split_into_chunks,
)


def test_invalid_boost_does_not_silently_pass(monkeypatch):
    monkeypatch.setenv('NEWS_TITLE_BOOST', '-5')
    with pytest.raises(ValueError):
        config_float('NEWS_TITLE_BOOST', 4)


def test_chunking_disabled_preserves_text():
    text = 'Публикация о РЖД и инвестициях.' * 40
    assert split_into_chunks(text, 0, 100) == [text]


def test_chunking_uses_overlap_and_covers_text():
    text = ' '.join(f'слово_{i}' for i in range(150))
    pieces = split_into_chunks(text, chunk_size=180, overlap=30)
    assert len(pieces) > 3
    assert all(piece for piece in pieces)
    assert all(len(piece) <= 180 for piece in pieces)
    assert pieces[0].startswith('слово_0')
    assert pieces[-1].endswith('слово_149')


def test_chunked_documents_still_refer_to_original_articles():
    base = read_data()
    full = indexed_documents(base, chunk_size=0)
    chunks = indexed_documents(base, chunk_size=400, overlap=70)
    assert len(full) == 1906
    assert len(chunks) > len(full)
    c = next(doc for doc in chunks if doc['id'].startswith('news:') and ':chunk:' in doc['id'])
    assert c['full_content']
    assert isinstance(c['news_row'], int)
    assert c['title']
    assert c['publisher']


def fake_retriever():
    instance = OpenSearchRetriever.__new__(OpenSearchRetriever)
    instance.index_name = 'test_only'
    instance.client = SimpleNamespace(indices=SimpleNamespace(exists=lambda index: True))
    instance.check = lambda: None
    instance._one = lambda doc_id: {
        'id': doc_id, 'kind':'profile', 'title':'РЖД', 'content':'профиль'
    } if doc_id == 'profile:РЖД' else None
    captured = []
    def search(query, size):
        captured.append(query)
        if query.get('term', {}).get('kind') == 'product':
            return []
        return [
            {'id':'news:5:chunk:0','news_row':6,'title':'РЖД',
             'content':'кусок A','full_content':'Полная статья','source':'example',
             'publisher':'example','client_ids':['РЖД']},
            {'id':'news:5:chunk:1','news_row':6,'title':'РЖД',
             'content':'кусок B','full_content':'Полная статья','source':'example',
             'publisher':'example','client_ids':['РЖД']},
        ]
    instance._find = search
    return instance, captured


def test_title_only_changes_query_and_deduplicates_chunks(monkeypatch):
    monkeypatch.setenv('NEWS_QUERY_MODE','title_only')
    monkeypatch.setenv('NEWS_CHUNK_SIZE','400')
    instance, captured = fake_retriever()
    context = instance.get_context('РЖД',limit_news=2)
    q = captured[-1]['bool']
    assert len(q['should']) == 1
    assert q['minimum_should_match'] == 1
    assert len(context['news']) == 1
    assert context['news'][0]['id'] == 'news:5'
    assert context['news'][0]['content'] == 'Полная статья'


def test_balanced_query_uses_both_fields(monkeypatch):
    monkeypatch.setenv('NEWS_QUERY_MODE','balanced')
    monkeypatch.setenv('NEWS_TITLE_BOOST','8')
    monkeypatch.setenv('NEWS_CONTENT_BOOST','1')
    monkeypatch.setenv('NEWS_CHUNK_SIZE','0')
    instance, captured = fake_retriever()
    instance.get_context('РЖД')
    should = captured[-1]['bool']['should']
    assert len(should) == 2
    assert should[0]['match']['title']['boost'] == 8
    assert should[1]['match']['content']['boost'] == 1


def test_unknown_news_query_mode_is_an_error(monkeypatch):
    monkeypatch.setenv('NEWS_QUERY_MODE','magic')
    instance, _ = fake_retriever()
    with pytest.raises(ValueError, match='NEWS_QUERY_MODE'):
        instance.get_context('РЖД')
