"""Optional human ratings; blanks and missing cases are excluded, never invented."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from .metrics import mean

FIELDS=('factuality_1_5','client_specificity_1_5','readability_1_5',
        'product_fit_1_5','news_relevance_1_5')


def ingest_review(run_dir:Path, csv_path:Path):
    run_dir=Path(run_dir);csv_path=Path(csv_path)
    known={x['case_id'] for x in json.loads((run_dir/'metrics.json').read_text(encoding='utf-8'))['cases']
           if not x['expected_error']}
    rows=[]
    with csv_path.open(newline='',encoding='utf-8-sig') as fh:
        for row in csv.DictReader(fh):
            case=row['case_id'].strip()
            if case not in known:
                raise ValueError('Unknown review case: '+case)
            ratings={}
            for field in FIELDS:
                val=row.get(field,'').strip()
                if val:
                    number=float(val)
                    if not 1<=number<=5:
                        raise ValueError(f'{case}: {field} must be from 1 to 5')
                    ratings[field]=number
            if ratings:
                rows.append({'case_id':case,'ratings':ratings,
                             'reviewer':row.get('reviewer',''),
                             'comments':row.get('comments','')})
    if len({r['case_id'] for r in rows})!=len(rows):
        raise ValueError('Duplicate reviewed cases: use one row per case')
    result={'rated_cases':len(rows),'expected_cases':len(known),
            'means':{field:mean(r['ratings'].get(field) for r in rows) for field in FIELDS},
            'case_ratings':rows}
    (run_dir/'human_review_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
