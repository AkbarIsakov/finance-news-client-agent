"""Command line application. Example: python -m src.cli demo 'Подготовь презентацию о РЖД'."""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from .data import PROJECT_ROOT, read_data, resolve_client
from .recommend import rank_products, pick_news, risk_points
from .retrieval import LocalRetriever, OpenSearchRetriever
from .writer import simple_text, build_text_gigachat
from .presentation import build_pptx


def generate(request: str, *, demo: bool = False, output: str | None = None) -> dict:
    """Run retrieval -> selection -> (GigaChat planning) -> PPTX."""
    load_dotenv(PROJECT_ROOT / '.env')
    dataset = read_data()
    client_name = resolve_client(request, list(dataset['clients']))
    retriever = LocalRetriever(dataset) if demo else OpenSearchRetriever()
    context = retriever.get_context(client_name)
    products = rank_products(context['profile'], context['note'],context['products'])
    news = pick_news(context['news'], client_name)
    risks = risk_points(context['profile']['content'])
    if not products:
        raise RuntimeError(f'Для {client_name} не найдено подходящих продуктов')
    if demo:
        narrative = simple_text(client_name,context['profile'],products,context['note'])
    else:
        narrative = build_text_gigachat(client_name,context['profile'],
                                       context['note'],products,news)
    target=Path(output) if output else PROJECT_ROOT / 'outputs' / f'{client_name}_{datetime.now():%Y%m%d}.pptx'
    build_pptx(client_name,context['profile'],context['note'],products,news,narrative,
               risks,target)
    # Decision trace is useful for audit and not part of the PPTX.
    report = {
        'client':client_name, 'pptx':str(target), 'mode':narrative['mode'],
        'retrieval':context['backend'],
        'products':[{'name':p['name'], 'conditional':p['conditional'],
                     'source_ids':[p['product_source'],p['note_source']]} for p in products],
        'news':[{'title':n['title'],'source':n['source'],'news_row':n['news_row']}
                for n in news],
        'retrieved_news_count':len(context['news']),
    }
    report_path=target.with_suffix('.json')
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main(argv: list[str] | None=None) -> None:
    parser=argparse.ArgumentParser(description='RAG-agent: OpenSearch + GigaChat -> PPTX')
    subs=parser.add_subparsers(dest='command',required=True)
    subs.add_parser('index',help='Re-create and populate OpenSearch index')
    subs.add_parser('list-clients',help='Show available clients')
    for action in ('generate','demo'):
        p=subs.add_parser(action)
        p.add_argument('request',help='e.g. Подготовь презентацию о РЖД')
        p.add_argument('--output',help='Optional pptx output path')
    args=parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / '.env')
    if args.command=='index':
        retriever=OpenSearchRetriever()
        n=retriever.index_all(read_data())
        print(f'OpenSearch: индекс создан, документов: {n}')
    elif args.command=='list-clients':
        for n in read_data()['clients']:
            print(n)
    else:
        result=generate(args.request,demo=args.command=='demo',output=args.output)
        print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
