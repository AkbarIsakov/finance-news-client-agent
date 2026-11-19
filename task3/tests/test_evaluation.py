import copy
import json
from pathlib import Path
import pytest
from evaluation.metrics import ndcg_at_k, measure_news, evaluate_case, summarize
from evaluation.compare import ci_paired, compare_runs
from evaluation.pptx_checks import check_pptx


def test_ndcg_rewards_correct_order():
    relevance={'IRS':3,'Repo':2,'DCD':0}
    assert ndcg_at_k(['IRS','Repo','DCD'],relevance)>ndcg_at_k(['DCD','Repo','IRS'],relevance)


def test_news_unknown_is_not_automatically_negative():
    result=measure_news([1,2,3],[1],[2])
    assert result['judged_precision']==0.5
    assert result['unjudged_count']==1
    assert result['judged_coverage']==pytest.approx(2/3,abs=1e-4)


def test_news_empty_gold_and_empty_results():
    result=measure_news([],[],[])
    assert result['judged_precision']==1
    assert result['known_positive_recall'] is None


def test_bootstrap_identical():
    assert ci_paired([0,0,0])==(0,0)


def test_pptx_checker_handles_broken_file(tmp_path):
    path=tmp_path/'bad.pptx';path.write_text('not a pptx')
    assert not check_pptx(path,'РЖД',[],[])['ok']


def test_comparison_rejects_different_gold(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';a.mkdir();b.mkdir()
    payload={'manifest':{'mode':'demo','gold_sha256':'abc','data_sha256':{}},
             'summary':{'critical_error_count':0},'cases':[]}
    (a/'metrics.json').write_text(json.dumps(payload))
    payload['manifest']['gold_sha256']='different'
    (b/'metrics.json').write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='gold_sha256'):
        compare_runs(a,b,tmp_path/'out')


def test_unsafe_product_penalty():
    relevance={'IRS':3,'Repo':3}
    assert ndcg_at_k(['IRS','Repo'],relevance)==1.0
    assert ndcg_at_k(['DCD','Repo'],relevance)<1


def test_gold_has_all_clients_and_negative_cases():
    gold=json.loads((Path(__file__).parents[1]/'evaluation'/'gold.json').read_text(encoding='utf-8'))
    assert len(gold['clients'])==8
    assert sum(bool(c.get('expected_error')) for c in gold['cases'])>=2


def test_review_requires_valid_score(tmp_path):
    from evaluation.human_review import ingest_review
    run=tmp_path/'run';run.mkdir()
    (run/'metrics.json').write_text(json.dumps({'cases':[
        {'case_id':'rzd','expected_error':False}]}),encoding='utf-8')
    csv_path=run/'review.csv'
    csv_path.write_text('case_id,factuality_1_5\nrzd,6\n',encoding='utf-8')
    with pytest.raises(ValueError, match='must be from'):
        ingest_review(run,csv_path)
