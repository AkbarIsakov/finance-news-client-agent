from pathlib import Path
from evaluation.cli import ROOT


def test_task3_points_to_task2_sibling():
    assert (ROOT.parent/'task2'/'src'/'cli.py').exists()
    assert (ROOT.parent/'task2'/'data'/'clients.json').exists()
    assert (ROOT/'evaluation'/'gold.json').exists()
