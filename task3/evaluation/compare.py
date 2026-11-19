"""Paired version comparison, with reproducibility checks and bootstrap uncertainty."""
from __future__ import annotations
import html
import json
from pathlib import Path
import random
import statistics


def ci_paired(diffs, n_iter=3000, seed=28):
    if not diffs:
        return 0.0,0.0
    rng=random.Random(seed)
    n=len(diffs)
    samples=sorted(sum(diffs[rng.randrange(n)] for _ in range(n))/n for i in range(n_iter))
    return round(samples[int(n_iter*0.025)],4),round(samples[int(n_iter*0.975)],4)


def compare_runs(base_dir:Path,candidate_dir:Path,output_dir:Path):
    b=json.loads((Path(base_dir)/'metrics.json').read_text(encoding='utf-8'))
    c=json.loads((Path(candidate_dir)/'metrics.json').read_text(encoding='utf-8'))
    for key in ('mode','gold_sha256','data_sha256'):
        if b['manifest'][key]!=c['manifest'][key]:
            raise ValueError(f'Incomparable runs: {key} differs. Use identical test set/data/mode.')
    bcases={x['case_id']:x for x in b['cases']}
    ccases={x['case_id']:x for x in c['cases']}
    if set(bcases)!=set(ccases):
        raise ValueError('Incomparable runs: case ids differ')
    rows=[]
    for ident in bcases:
        old,new=bcases[ident],ccases[ident]
        if old['expected_error']:
            diff=(int(new.get('correct_rejection',False)) - int(old.get('correct_rejection',False)))
        else:
            diff=round(new.get('score',0)-old.get('score',0),4)
        rows.append({'case_id':ident,'old_score':old.get('score'),
                     'new_score':new.get('score'),'delta':diff,
                     'old_critical':old.get('critical_errors',0),
                     'new_critical':new.get('critical_errors',0)})
    paired=[r['delta'] for r in rows if r['old_score'] is not None]
    delta=round(sum(paired)/len(paired),4)
    low,high=ci_paired(paired)
    oldcrit=b['summary']['critical_error_count']
    newcrit=c['summary']['critical_error_count']
    if newcrit>oldcrit:
        decision='worse'
        explanation='У новой версии больше критических ошибок.'
    elif newcrit<oldcrit and delta>=-0.01:
        decision='better_on_safety'
        explanation='Критических ошибок стало меньше; общий балл не снизился существенно.'
    elif delta>0.01 and low>0:
        decision='better'
        explanation='Средний балл вырос; 95% bootstrap-интервал парной разницы выше нуля.'
    elif delta< -0.01 and high<0:
        decision='worse'
        explanation='Средний балл снизился; 95% bootstrap-интервал ниже нуля.'
    elif abs(delta)<=0.01 and newcrit==oldcrit:
        decision='no_clear_change'
        explanation='Изменение среднего балла не превышает практический порог 0,01.'
    else:
        decision='inconclusive'
        explanation='Направление разницы есть, но данных недостаточно для уверенного вывода.'
    metrics=sorted(set(b['summary'])&set(c['summary']))
    metric_diffs={key:{'baseline':b['summary'][key], 'candidate':c['summary'][key],
                       'delta':round(c['summary'][key]-b['summary'][key],4)
                       if isinstance(b['summary'][key],(float,int)) and
                          isinstance(c['summary'][key],(float,int)) else None}
                 for key in metrics}
    human_comparison=None
    hp=[Path(base_dir)/'human_review_metrics.json', Path(candidate_dir)/'human_review_metrics.json']
    if all(p.exists() for p in hp):
        b_h,c_h=[json.loads(p.read_text(encoding='utf-8')) for p in hp]
        human_comparison={'baseline_reviewed_cases':b_h['rated_cases'],
                          'candidate_reviewed_cases':c_h['rated_cases'],
                          'metrics':{key:{'baseline':b_h['means'].get(key),
                                          'candidate':c_h['means'].get(key),
                                          'delta':round(c_h['means'][key]-b_h['means'][key],4)
                                          if b_h['means'].get(key) is not None
                                          and c_h['means'].get(key) is not None else None}
                                     for key in b_h['means']}}
    result={'decision':decision,'explanation':explanation,'delta_score':delta,
            'bootstrap_95_ci':[low,high],
            'baseline':str(Path(base_dir).resolve()),
            'candidate':str(Path(candidate_dir).resolve()),
            'metrics':metric_diffs,'cases':rows, 'human_reviews':human_comparison}
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def fmt(x):return '—' if x is None else f'{x:.4f}' if isinstance(x,float) else str(x)
    chosen=('score','product_ndcg_at_3','selected_news_precision_judged',
            'selected_news_known_recall','retrieval_news_known_recall',
            'pptx_valid_rate','narrative_contract_rate','critical_error_count','wrong_known_news_count')
    body='\n'.join('<tr><td>'+html.escape(k)+'</td><td>'+fmt(metric_diffs[k]['baseline'])+
                    '</td><td>'+fmt(metric_diffs[k]['candidate'])+'</td><td>'+fmt(metric_diffs[k]['delta'])+'</td></tr>'
                    for k in chosen if k in metric_diffs)
    per='\n'.join('<tr><td>'+html.escape(r['case_id'])+'</td><td>'+fmt(r['old_score'])+
                  '</td><td>'+fmt(r['new_score'])+'</td><td>'+fmt(r['delta'])+'</td></tr>' for r in rows)
    human_html=''
    if human_comparison:
        human_rows=''.join('<tr><td>'+html.escape(k)+'</td><td>'+fmt(v['baseline'])+'</td><td>'+fmt(v['candidate'])+'</td><td>'+fmt(v['delta'])+'</td></tr>'
                           for k,v in human_comparison['metrics'].items())
        human_html=f'<h2>Экспертная оценка (если заполнена)</h2><table><thead><tr><th>Критерий</th><th>Baseline</th><th>Candidate</th><th>Δ</th></tr></thead><tbody>{human_rows}</tbody></table>'
    doc=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Task 3 · Comparison</title>
<style>body{{font:16px system-ui,Arial,sans-serif;max-width:1100px;margin:36px auto;padding:0 24px;color:#1c2940}}h1{{font-size:28px}}h2{{margin-top:38px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dbe2ea}}thead{{background:#f2f5f9}}.subtitle{{color:#54667b}}.verdict{{font-size:21px;font-weight:bold}}.small{{font-size:13px;color:#54667b}}code{{background:#f2f5f9;padding:2px 4px;border-radius:3px}}</style></head>
<body><h1>Task 3 · Сравнение версий агента</h1>
<p class="verdict">Вердикт: {html.escape(decision)}</p><p>{html.escape(explanation)}</p>
<p class="subtitle">Δ общего балла: {delta:+.4f}; парный bootstrap 95% CI: [{low:+.4f}; {high:+.4f}] · 8 клиентских тестов</p>
<h2>Метрики</h2><table><thead><tr><th>Метрика</th><th>Baseline</th><th>Candidate</th><th>Δ</th></tr></thead><tbody>{body}</tbody></table>
<h2>Сравнение по кейсам</h2><table><thead><tr><th>Кейс</th><th>Baseline</th><th>Candidate</th><th>Δ</th></tr></thead><tbody>{per}</tbody></table>
{human_html}
<p class="small">Метрики качества на ограниченной контрольной разметке: не являются доказательством полной фактической точности. Бинарные проверки помогают обнаруживать технические регрессии; не заменяют экспертный просмотр готовых слайдов. При 8 клиентских кейсах доверительные интервалы могут быть широкими.</p></body></html>'''
    (output_dir/'comparison.html').write_text(doc,encoding='utf-8')
    return result
