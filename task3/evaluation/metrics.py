"""Version-aware, conservative evaluation metrics for Task 2.

Manual labels are partial; we report judged coverage rather than treating
unlabeled articles as irrelevant. Heuristics are not factuality proofs.
"""
from __future__ import annotations
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
from .pptx_checks import check_pptx


def mean(values):
    values = [float(x) for x in values if x is not None]
    return round(sum(values)/len(values), 4) if values else None


def ndcg_at_k(selected, relevance, k=3):
    def dcg(vals):
        return sum((2**rel-1)/math.log2(i+2) for i,rel in enumerate(vals))
    actual=[int(relevance.get(name,0)) for name in selected[:k]]
    ideal=sorted([int(v) for v in relevance.values()],reverse=True)[:k]
    maximum=dcg(ideal)
    return round(dcg(actual)/maximum,4) if maximum else 1.0


def measure_news(selected_rows, positives, negatives):
    pos,neg=set(map(int,positives)),set(map(int,negatives))
    selected=set(map(int,selected_rows))
    judged_selected=selected & (pos | neg)
    judged_precision=(len(selected&pos)/len(judged_selected) if judged_selected else
                      (1.0 if not pos and not selected else 0.0 if pos and not selected else None))
    return {
        'judged_precision': round(judged_precision,4) if judged_precision is not None else None,
        'known_positive_recall': round(len(selected&pos)/len(pos),4) if pos else None,
        'judged_coverage':round(len(judged_selected)/len(selected),4) if selected else 1.0,
        'known_false_positive_count':len(selected&neg),
        'known_true_positive_count':len(selected&pos),
        'unjudged_count':len(selected-(pos|neg)),
    }


def unsupported_number_alerts(narrative, evidence_text):
    # Numeric-only fact check; no claim that semantic hallucinations are detected.
    pattern=r'(?<!\w)\d+(?:[.,]\d+)?(?!\w)'
    source_numbers=set(re.findall(pattern,evidence_text))
    generated=[str(narrative.get('summary',''))]
    generated+=list(narrative.get('product_fit',{}).values())
    return sorted(set().union(*(set(re.findall(pattern,t)) for t in generated)) - source_numbers)


def evaluate_case(case, obs, gold_client, dataset, docs):
    result = {'case_id':case['id'], 'client':case.get('client',''), 'request':case['request'],
              'expected_error':bool(case.get('expected_error')), 'status':obs.get('status','missing')}
    if case.get('expected_error'):
        result.update(correct_rejection=obs.get('status')=='error',
                      critical_errors=0 if obs.get('status')=='error' else 1)
        return result

    if obs.get('status')!='success':
        result.update(score=0.0, critical_errors=1, error=obs.get('error_message','missing observation'),
                      deck_ok=False, case_passed=False)
        return result

    products=obs['products']
    product_names=[p['name'] for p in products]
    relevance=gold_client['products']
    strict_relevant={p for p,s in relevance.items() if s>=2}
    positive=sum(p in strict_relevant for p in product_names)
    result['product_precision_at_3']=round(positive/max(len(product_names),1),4)
    result['product_recall_at_3']=round(positive/max(min(3,len(strict_relevant)),1),4)
    result['product_ndcg_at_3']=ndcg_at_k(product_names,relevance)
    result['unsafe_product_count']=sum(p in set(gold_client['avoid']) for p in product_names)
    result['condition_mismatch_count']=sum(p['name'] in gold_client['conditional'] and not p['conditional'] for p in products)

    all_products=set(dataset['products'])
    all_rows=set(range(1,len(dataset['news'])+1))
    source_errors=0
    for p in products:
        if p['name'] not in all_products or f"product:{p['name']}" not in p.get('source_ids',[]):
            source_errors+=1
        for ref in p.get('source_ids',[]):
            if ref and ref not in docs:
                source_errors+=1
    news=obs.get('news',[])
    rows=[int(n.get('news_row',-1)) for n in news]
    for n in news:
        row=n.get('news_row')
        if row not in all_rows:
            source_errors+=1
        else:
            real=dataset['news'].iloc[int(row)-1]
            if n.get('title')!=str(real['title']) or n.get('source')!=str(real['source']):
                source_errors+=1
    if len(rows)!=len(set(rows)):
        source_errors+=1
    r=obs.get('retrieved',{})
    if r.get('profile_id')!=f"profile:{case['client']}":
        source_errors+=1
    if r.get('note_id') not in (f"note:{case['client']}",None):
        source_errors+=1
    for doc_id in r.get('news_ids',[]):
        if doc_id not in docs:
            source_errors+=1
    result['source_error_count']=source_errors
    result['retrieval_news']=measure_news(r.get('news_rows',[]),gold_client['news_positive'],gold_client['news_negative'])
    result['selected_news']=measure_news(rows,gold_client['news_positive'],gold_client['news_negative'])
    result['retrieved_news_count']=len(r.get('news_rows',[]))
    result['selected_news_count']=len(rows)
    result['pptx']=check_pptx(obs.get('pptx',''),case['client'],product_names,news)
    result['deck_ok']=result['pptx']['ok']
    evidence = (dataset['clients'][case['client']]+' '+
                next((x for x in dataset['notes'] if case['client'].casefold() in x[:100].casefold()),'') +
                ' '.join(dataset['products'].get(p['name'],'') for p in products))
    result['numeric_fact_alerts']=unsupported_number_alerts(obs.get('narrative',{}),evidence)
    narrative=obs.get('narrative',{})
    generated_fit=narrative.get('product_fit',{}) if isinstance(narrative.get('product_fit'),dict) else {}
    question_list=narrative.get('questions',[]) if isinstance(narrative.get('questions'),list) else []
    result['narrative_contract_ok']=(
        isinstance(narrative.get('summary'),str)
        and 0<len(narrative['summary'])<=300
        and set(generated_fit)==set(product_names)
        and all(isinstance(v,str) and 0<len(v)<=280 for v in generated_fit.values())
        and 2<=len(question_list)<=3
        and all(isinstance(q,str) and 0<len(q)<=230 for q in question_list)
    )

    # This score is a decision aid, not a calibrated probability of correctness.
    # Missing relevant news on a client with no judged positives is neutral, not a hallucination.
    news_p=result['selected_news']['judged_precision']
    if news_p is None:
        news_p=0.5  # unjudged selected items; signal uncertainty, not success
    news_r=result['selected_news']['known_positive_recall']
    if news_r is None:
        news_r=1.0 if not rows else 0.5
    deck=1.0 if result['deck_ok'] else 0.0
    sourced=1.0 if not source_errors else 0.0
    # Presentation and narrative quality both contribute to the structural dimension.
    contract=1.0 if result['narrative_contract_ok'] else 0.0
    score=(0.30*result['product_ndcg_at_3']+0.15*result['product_recall_at_3']+
           0.16*news_p+0.16*news_r+0.08*deck+0.05*contract+0.10*sourced)
    # Negative recommendations and failed conditional disclosures are explicit penalties.
    score=max(0, score-0.12*result['unsafe_product_count']-
                   0.05*result['condition_mismatch_count'])
    result['score']=round(score,4)
    result['critical_errors']=source_errors + int(not result['deck_ok']) + result['unsafe_product_count'] + int(not result['narrative_contract_ok'])
    result['case_passed']=result['critical_errors']==0
    return result


def load_dataset(agent_root:Path):
    import pandas as pd
    return dict(clients=json.loads((agent_root/'data/clients.json').read_text(encoding='utf-8')),
                products=json.loads((agent_root/'data/products.json').read_text(encoding='utf-8')),
                notes=json.loads((agent_root/'data/internal_notes.json').read_text(encoding='utf-8')),
                news=pd.read_csv(agent_root/'data/news.csv').fillna(''))


def summarize(cases):
    valid=[c for c in cases if not c['expected_error']]
    rejected=[c for c in cases if c['expected_error']]
    metrics={'case_count':len(valid), 'successful_decks':sum(c['status']=='success' for c in valid),
             'negative_request_passed':sum(c.get('correct_rejection',False) for c in rejected),
             'negative_request_total':len(rejected),
             'critical_error_count':sum(c.get('critical_errors',0) for c in cases)}
    for m in ('score','product_precision_at_3','product_recall_at_3','product_ndcg_at_3'):
        metrics[m]=mean(c.get(m,0.0) for c in valid)
    metrics['selected_news_precision_judged']=mean((c.get('selected_news') or {}).get('judged_precision') for c in valid)
    metrics['selected_news_known_recall']=mean((c.get('selected_news') or {}).get('known_positive_recall') for c in valid)
    metrics['selected_news_judged_coverage']=mean((c.get('selected_news') or {}).get('judged_coverage') for c in valid)
    metrics['retrieval_news_known_recall']=mean((c.get('retrieval_news') or {}).get('known_positive_recall') for c in valid)
    metrics['pptx_valid_rate']=mean(1 if c.get('deck_ok') else 0 for c in valid)
    metrics['narrative_contract_rate']=mean(1 if c.get('narrative_contract_ok') else 0 for c in valid)
    metrics['retrieval_news_precision_judged']=mean((c.get('retrieval_news') or {}).get('judged_precision') for c in valid)
    metrics['retrieval_news_judged_coverage']=mean((c.get('retrieval_news') or {}).get('judged_coverage') for c in valid)
    metrics['wrong_known_news_count']=sum((c.get('selected_news') or {}).get('known_false_positive_count',0) for c in valid)
    metrics['conditional_mismatch_count']=sum(c.get('condition_mismatch_count',0) for c in valid)
    metrics['numeric_fact_alert_count']=sum(len(c.get('numeric_fact_alerts',[])) for c in valid)
    return metrics


def evaluate_run(run_dir:Path, gold_path:Path):
    run_dir=Path(run_dir)
    gold=json.loads(Path(gold_path).read_text(encoding='utf-8'))
    obs=json.loads((run_dir/'observations.json').read_text(encoding='utf-8'))
    obs_by_id={o['case_id']:o for o in obs}
    if len(obs_by_id)!=len(obs):
        raise ValueError('Duplicate case_id in observations')
    manifest=json.loads((run_dir/'manifest.json').read_text(encoding='utf-8'))
    if manifest['gold_sha256'] != hashlib.sha256(Path(gold_path).read_bytes()).hexdigest():
        raise ValueError('Gold file changed during the run')
    agent_root=Path(manifest['agent_root'])
    dataset=load_dataset(agent_root)
    docs=set(f'product:{p}' for p in dataset['products'])
    docs|=set(f'profile:{c}' for c in dataset['clients'])
    docs|=set(f'note:{c}' for c in dataset['clients'])
    docs|=set(f'news:{i}' for i in range(len(dataset['news'])))
    cases=[]
    for case in gold['cases']:
        if case['id'] not in obs_by_id:
            raise ValueError(f"Missing result for {case['id']}")
        c=evaluate_case(case,obs_by_id[case['id']],gold['clients'].get(case.get('client')),dataset,docs)
        cases.append(c)
    summary=summarize(cases)
    report={'manifest':manifest,'summary':summary,'cases':cases}
    (run_dir/'metrics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['case_id','client','status','score','product_ndcg_at_3','product_precision_at_3',
            'product_recall_at_3','selected_news_count','retrieved_news_count',
            'deck_ok','source_error_count','unsafe_product_count','condition_mismatch_count',
            'critical_errors','correct_rejection']
    # Human scores stay blank until a person reviews each actual PPTX.
    with (run_dir/'human_review_template.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        review=csv.writer(fh)
        review.writerow(['case_id','factuality_1_5','client_specificity_1_5',
                         'readability_1_5','product_fit_1_5','news_relevance_1_5',
                         'reviewer','comments'])
        for case in gold['cases']:
            if not case.get('expected_error'):
                review.writerow([case['id'],'','','','','','',''])
    with (run_dir/'metrics.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.DictWriter(fh,fieldnames=fields)
        writer.writeheader()
        for c in cases:
            writer.writerow({k:c.get(k,'') for k in fields})
    return report
