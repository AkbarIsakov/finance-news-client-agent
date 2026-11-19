"""Isolated runner importing Task 2 code from an explicitly chosen directory.

Launched as a subprocess by evaluation.cli; never exposes credentials.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--agent-root', required=True)
    p.add_argument('--gold', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--mode', choices=['demo', 'full'], required=True)
    p.add_argument('--retrieval-news-limit', type=int, default=18)
    p.add_argument('--selected-news-limit', type=int, default=4)
    args = p.parse_args()
    root = Path(args.agent_root).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    from src.data import read_data, resolve_client, all_documents
    from src.retrieval import LocalRetriever, OpenSearchRetriever
    from src.recommend import rank_products, pick_news, risk_points
    from src.writer import simple_text, build_text_gigachat
    from src.presentation import build_pptx

    gold = json.loads(Path(args.gold).read_text(encoding='utf-8'))
    data = read_data()
    documents = all_documents(data)
    all_ids = {doc['id'] for doc in documents}
    news_ids = {int(doc['news_row']):doc for doc in documents if doc['kind']=='news'}
    products_ids = {doc['product_name'] for doc in documents if doc['kind']=='product'}
    retriever = LocalRetriever(data) if args.mode == 'demo' else OpenSearchRetriever()
    observations = []
    for case in gold['cases']:
        result = {'case_id': case['id'], 'request': case['request'],
                  'client': case.get('client'), 'expected_error':bool(case.get('expected_error')),
                  'status': 'error'}
        try:
            name = resolve_client(case['request'], list(data['clients']))
            context = retriever.get_context(name, limit_news=args.retrieval_news_limit)
            products = rank_products(context['profile'], context['note'], context['products'])
            news = pick_news(context['news'], name, limit=args.selected_news_limit)
            if not products:
                raise RuntimeError('No products')
            narrative = (simple_text(name, context['profile'], products, context['note'])
                         if args.mode=='demo' else
                         build_text_gigachat(name, context['profile'], context['note'], products, news))
            pptx_path = out / 'decks' / f"{case['id']}.pptx"
            pptx_path.parent.mkdir(parents=True, exist_ok=True)
            build_pptx(name, context['profile'], context['note'], products, news, narrative,
                       risk_points(context['profile']['content']), pptx_path)
            result.update(status='success', resolved_client=name, pptx=str(pptx_path),
                          retrieved={'profile_id':context['profile']['id'],
                                     'note_id':context['note']['id'] if context['note'] else None,
                                     'product_ids':[x['id'] for x in context['products']],
                                     'news_ids':[x['id'] for x in context['news']],
                                     'news_rows':[x['news_row'] for x in context['news']],
                                     'backend':context['backend']},
                          products=[{'name':x['name'], 'conditional':x['conditional'],
                                     'source_ids':[x['product_source'], x['note_source']],
                                     'evidence':x['evidence']} for x in products],
                          news=[{'news_row':x['news_row'],'id':x['id'],
                                 'title':x['title'],'source':x['source'],
                                 'client_ids':x['client_ids']} for x in news],
                          narrative=narrative)
        except Exception as e:
            result.update(error_type=type(e).__name__, error_message=str(e)[:600])
        observations.append(result)
        print(f"{case['id']}: {result['status']}", flush=True)

    (out / 'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
    # Whitelist configuration; never store auth credentials or .env contents.
    experiment_defaults = {
        'OPENSEARCH_INDEX_NAME': 'task2_client_knowledge_v1',
        'NEWS_QUERY_MODE': 'balanced',
        'NEWS_TITLE_BOOST': '4',
        'NEWS_CONTENT_BOOST': '1',
        'NEWS_CHUNK_SIZE': '0',
        'NEWS_CHUNK_OVERLAP': '100',
        'GIGACHAT_PROMPT_FILE': '',
        'GIGACHAT_MODEL': 'GigaChat',
        'PPTX_THEME': 'teal',
    }
    experiment_config = {
        name: os.getenv(name, default)
        for name, default in experiment_defaults.items()
    }
    changed_files = ('src/writer.py', 'src/retrieval.py', 'src/recommend.py',
                     'src/presentation.py', 'src/data.py')
    file_hashes = {name: sha(root / name) for name in changed_files
                   if (root / name).exists()}
    prompt_path = os.getenv('GIGACHAT_PROMPT_FILE', '').strip()
    if prompt_path:
        prompt_path = Path(prompt_path).expanduser()
        if not prompt_path.is_absolute():
            prompt_path = root / prompt_path
        if prompt_path.exists():
            file_hashes['prompt_file'] = sha(prompt_path)
    manifest = {'mode':args.mode,
                'config':{'retrieval_news_limit':args.retrieval_news_limit,
                          'selected_news_limit':args.selected_news_limit},
                'experiment_config': experiment_config,
                'code_sha256': file_hashes,
                'data_sha256':{n:sha(root/'data'/n) for n in
                    ('clients.json','products.json','internal_notes.json','news.csv')},
                'gold_sha256':sha(Path(args.gold)),
                'agent_root':str(root), 'all_document_ids_count':len(all_ids),
                'all_product_names_count':len(products_ids)}
    try:
        manifest['git_commit'] = subprocess.check_output(
            ['git','-C',str(root),'rev-parse','HEAD'], stderr=subprocess.DEVNULL,
            text=True, timeout=3).strip()
    except Exception:
        manifest['git_commit'] = None
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
