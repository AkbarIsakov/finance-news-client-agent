import json
import pytest
from pptx import Presentation
from src.data import read_data, resolve_client, client_pattern, news_to_documents, publisher
from src.retrieval import LocalRetriever
from src.recommend import rank_products, pick_news
from src.cli import generate


def test_input_files():
    d=read_data()
    assert len(d['clients'])==8
    assert len(d['products'])==10
    assert len(d['news'])==1880


def test_client_resolution():
    names=list(read_data()['clients'])
    assert resolve_client('Подготовь презентацию о РЖД',names)=='РЖД'
    assert resolve_client('Подготовь презентацию об Аэрофлоте',names)=='Аэрофлот'
    with pytest.raises(ValueError):
        resolve_client('Презентация о неизвестной компании',names)


def test_mention_boundaries():
    assert client_pattern('РЖД').search('Капитальные вложения ОАО «РЖД»')
    assert not client_pattern('РЖД').search('подтверждение договора')
    assert client_pattern('Аэрофлот').search('рейсы «Аэрофлота»')


def test_source_normalization():
    assert publisher('https://news.mail.ru/rss/politics/90/') == publisher('https://news.mail.ru/rss/90/')
    assert publisher('https://t.me/s/banksta') != publisher('https://t.me/s/bankrollo')


def test_recommendations_are_client_specific():
    data=read_data()
    r=LocalRetriever(data)
    rzd=r.get_context('РЖД')
    aero=r.get_context('Аэрофлот')
    rr=[p['name'] for p in rank_products(rzd['profile'],rzd['note'],rzd['products'])]
    ar=[p['name'] for p in rank_products(aero['profile'],aero['note'],aero['products'])]
    assert 'IRS' in rr
    assert {'FX Forward','Commodity Hedge'}.issubset(ar)
    assert rr != ar


def test_news_not_mixed_between_clients():
    r=LocalRetriever(read_data())
    for client in ['РЖД','Аэрофлот']:
        context=r.get_context(client)
        news=pick_news(context['news'],client)
        assert news
        assert all(client in item['client_ids'] for item in news)


def test_demo_creates_real_pptx(tmp_path):
    out=tmp_path/'rzd.pptx'
    report=generate('Подготовь презентацию о РЖД',demo=True,output=str(out))
    assert out.exists()
    prs=Presentation(str(out))
    assert len(prs.slides)==7
    texts=' '.join(sh.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert 'РЖД' in texts and 'IRS' in texts
    assert report['mode']=='deterministic-demo'
    assert out.with_suffix('.json').exists()


def test_demo_no_invented_news(tmp_path):
    out=tmp_path/'norilsk.pptx'
    report=generate('Подготовь презентацию о Норникеле',demo=True,output=str(out))
    assert not report['news']
    prs=Presentation(str(out))
    texts=' '.join(sh.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert 'не найдено надёжных упоминаний' in texts
