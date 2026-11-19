"""PPTX structural validation. Does not claim to measure visual aesthetics."""
from __future__ import annotations
from pathlib import Path
from pptx import Presentation

SECTIONS = (
    'Финансовые риски',
    'Подходящие финансовые продукты',
    'Новости, относящиеся к клиенту',
    'Источники и ограничения',
)


def check_pptx(path: str | Path, client: str, products: list[str], news: list[dict]) -> dict:
    file = Path(path)
    base = dict(ok=False, slide_count=0, missing_sections=list(SECTIONS),
                text_out_of_bounds=0, tiny_text_runs=0, missing_product_names=[],
                missing_news_headlines=[], reason='')
    if not file.is_file() or file.stat().st_size == 0:
        base['reason'] = 'pptx missing or empty'
        return base
    try:
        prs = Presentation(str(file))
        slides = list(prs.slides)
        text = '\n'.join(
            shape.text for slide in slides for shape in slide.shapes
            if shape.has_text_frame
        )
        out = 0
        tiny = 0
        for slide in slides:
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                if shape.text.strip() and (shape.left < 0 or shape.top < 0 or
                    shape.left + shape.width > prs.slide_width + 10000 or
                    shape.top + shape.height > prs.slide_height + 10000):
                    out += 1
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        if run.text.strip() and run.font.size and run.font.size.pt < 9:
                            tiny += 1
        # Compare short headline stems: the slide intentionally shortens long titles.
        missing_titles = [item['title'] for item in news if
                          item['title'][:min(35, len(item['title']))] not in text]
        base.update(slide_count=len(slides),
                    missing_sections=[section for section in SECTIONS if section not in text],
                    text_out_of_bounds=out, tiny_text_runs=tiny,
                    missing_product_names=[p for p in products if p not in text],
                    missing_news_headlines=missing_titles,
                    client_mentioned=client.casefold() in text.casefold(),
                    file_bytes=file.stat().st_size)
        base['ok'] = (5 <= len(slides) <= 12 and not base['missing_sections'] and
                      not out and not base['missing_product_names'] and
                      not base['missing_news_headlines'] and base['client_mentioned'])
        if not base['ok']:
            base['reason'] = 'structural PPTX check failed'
    except Exception as exc:
        base['reason'] = f'cannot parse PPTX: {type(exc).__name__}: {exc}'
    return base
