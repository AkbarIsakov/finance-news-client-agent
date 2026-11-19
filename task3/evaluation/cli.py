"""Run: python -m evaluation.cli run / compare."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from .compare import compare_runs
from .metrics import evaluate_run
from .human_review import ingest_review

ROOT=Path(__file__).resolve().parents[1]
GOLD=Path(__file__).with_name('gold.json')


def main():
    parser=argparse.ArgumentParser(description='Task3: quality and regression evaluation for Task2')
    sub=parser.add_subparsers(dest='action', required=True)
    run=sub.add_parser('run',help='Run entire test set with a chosen Task2 implementation')
    run.add_argument('--version',required=True)
    run.add_argument('--agent-root',default=str(ROOT.parent / 'task2'),help='Directory containing src/ and data/ of Task2')
    run.add_argument('--mode',choices=['demo','full'],default='demo')
    run.add_argument('--retrieval-news-limit',type=int,default=18)
    run.add_argument('--selected-news-limit',type=int,default=4)
    run.add_argument('--out',default=None)
    run.add_argument('--overwrite',action='store_true')
    comp=sub.add_parser('compare',help='Compare two previously evaluated runs')
    comp.add_argument('--baseline',required=True)
    comp.add_argument('--candidate',required=True)
    comp.add_argument('--out',default=str(ROOT/'evaluation'/'comparison'))
    review=sub.add_parser('review',help='Load optional manual quality scores into a run')
    review.add_argument('--run',required=True)
    review.add_argument('--csv',required=True)
    args=parser.parse_args()
    if args.action=='review':
        print(json.dumps(ingest_review(Path(args.run),Path(args.csv)),ensure_ascii=False,indent=2))
        return
    if args.action=='compare':
        report=compare_runs(Path(args.baseline),Path(args.candidate),Path(args.out))
        print(json.dumps({k:report[k] for k in ('decision','explanation','delta_score','bootstrap_95_ci')},ensure_ascii=False,indent=2))
        print('Full report:',Path(args.out).resolve()/'comparison.html')
        return
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',args.version):
        parser.error('--version must contain only letters, digits, _ . -')
    if not 1<=args.retrieval_news_limit<=1000 or not 1<=args.selected_news_limit<=50:
        parser.error('news limits must be positive')
    target=Path(args.out or ROOT/'evaluation'/'runs'/args.version).resolve()
    if target.exists():
        if not args.overwrite:
            parser.error(f'{target} already exists; use --overwrite')
        shutil.rmtree(target)
    target.mkdir(parents=True)
    cmd=[sys.executable,'-m','evaluation.agent_runner',
         '--agent-root',str(Path(args.agent_root).resolve()),
         '--gold',str(GOLD.resolve()), '--out',str(target),
         '--mode',args.mode,
         '--retrieval-news-limit',str(args.retrieval_news_limit),
         '--selected-news-limit',str(args.selected_news_limit)]
    subprocess.run(cmd,check=True,cwd=ROOT)
    metrics=evaluate_run(target,GOLD)
    print(json.dumps(metrics['summary'],ensure_ascii=False,indent=2))
    print('Metrics:', target/'metrics.json')

if __name__=='__main__':
    main()
