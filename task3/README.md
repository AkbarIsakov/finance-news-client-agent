# Task 3. Валидация агента и сравнение версий

## Код и тестовый набор

- `evaluation/gold.json` — 8 клиентских сценариев + 2 негативных запроса, градации релевантности продуктов 0–3, частичная экспертная разметка новостей.
- `evaluation/agent_runner.py` — запускает код из `../task2/` в отдельном процессе; забирает его собственные `src/`, `data/`, `.env`, параметры API и OpenSearch.
- `evaluation/metrics.py` — Precision/Recall@3, NDCG@3 по продуктам, релевантность новостей, проверки поддержки источниками, контракт текста и интегральная эвристическая метрика.
- `evaluation/pptx_checks.py` — `.pptx` открывается, есть основные разделы, тексты в границах слайдов.
- `evaluation/compare.py` — парное сравнение двух прогонов, bootstrap-интервал, HTML-отчёт.
- `evaluation/human_review.py` — опциональные экспертные баллы 1–5.
- `evaluation/cli.py` — команды `run`, `compare`, `review`.
- `results/comparison_prompt/` и `results/comparison_retriever/` — базовые эксперименты по изменению промпта и retriever.

## Установка и запуск

```bash
# из корня task3 (а не task2)
cd task3
# используй окружение с зависимостями из task2
python -m pip install -r requirements.txt
python -m pytest -q tests

# проверка без внешних сервисов
python -m evaluation.cli run --version baseline_demo --mode demo
python -m evaluation.cli run --version shallow_demo --mode demo --retrieval-news-limit 1
python -m evaluation.cli compare \
  --baseline evaluation/runs/baseline_demo \
  --candidate evaluation/runs/shallow_demo \
  --out evaluation/comparison
```

**Полный контур (RAG + OpenSearch + GigaChat):** для двух запусков используй `--mode full`. OpenSearch должен работать, а `.env` настроен в `../task2/`. Указание `--agent-root` не требуется — в этом репозитории путь по умолчанию уже `../task2/`. При тестировании другого клона агента можно передать `--agent-root /absolute/path/to/task2`.

Для настоящих изменений промпта/поиска `demo` не подходит: он не обращается ни к GigaChat, ни к OpenSearch.

## Как сравнивать метрики

Одни и те же запросы/исходные данные/gold; изменяем **один фактор**; запускаем baseline, candidate; сравниваем `metrics.json`, HTML-отчёт и примеры `.pptx`. В `manifest.json` остаются hash кода и данных, имя индекса и разрешённые параметры (без API-ключей).

Ключевые метрики: продуктов NDCG@3, Recall@3, Precision@3; новости — precision по размеченным и recall известных положительных; ошибки источников и противопоказанные предложения; доля корректных PPTX; независимая ручная оценка фактической точности, пригодности клиенту и дизайна.

Полный воспроизводимый протокол для A/B-экспериментов — [EXPERIMENTS.md](EXPERIMENTS.md).
