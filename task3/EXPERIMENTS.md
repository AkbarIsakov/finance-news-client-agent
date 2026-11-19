# Как воспроизвести A/B-сравнение агента Task 2

Здесь **A/B** означает контролируемый *offline paired evaluation*: два варианта агента A (baseline) и B (candidate) получают **одни и те же тестовые запросы**, а валидатор сравнивает продукты, новости, PowerPoint и ответы GigaChat.

Реализация: `task3/evaluation/cli.py`, `agent_runner.py`, `metrics.py`, `compare.py`. Тестовый набор: `task3/evaluation/gold.json` — 8 клиентов и 2 негативных запроса.

## 0. Подготовка — однажды

Работай из **корня `task3/`**. Сначала настрой в `../task2/.env` ключ GigaChat и OpenSearch (см. `../task2/README.md`), открой Docker Desktop, запусти OpenSearch и один раз выполни `index` в папке Task 2:

```bash
cd task2                              # из корня общего проекта
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # если ещё нет настроенного .env
# заполни GIGACHAT_CREDENTIALS и сертификаты локально

docker compose up -d
python -m src.cli index

cd ../task3
python -m pytest -q tests
```

Те же Python-библиотеки из окружения `task2/.venv` используются и в Task 3. **Не создавай второй `.env` в Task 3**: валидатор по умолчанию читает `../task2/.env` и импортирует код `../task2/src`.

Проверочный прогон без GigaChat и OpenSearch:

```bash
python -m evaluation.cli run --version smoke_local --mode demo
```

Он проверяет техническую работоспособность, но **НЕ подходит для вывода о качестве промптов или OpenSearch**, потому что demo использует локальный поиск и шаблонные тексты.

### Общее правило корректного сравнения

1. Зафиксируй **гипотезу**, одну изменяемую переменную и основную метрику (primary metric).
2. Сохраняй неизменными `task2/data/*`, `evaluation/gold.json`, набор запросов, версию GigaChat, индекс (кроме эксперимента с чанкингом), остальные настройки и критерии экспертной оценки.
3. Проводи A и B в **полном режиме** (`--mode full`), если меняются промпт, retrieval или чанкинг. Для презентационного макета без LLM допускается demo.
4. В `evaluation/runs/<name>/` сохраняются `observations.json`, `manifest.json`, `metrics.json`, `metrics.csv`, `decks/*.pptx` и форма экспертной оценки.
5. Команда `compare` создаёт `comparison.html` и `comparison.json`; она может отклонить прогон с другим набором данных/эталоном. Сравнение имеет смысл только на одинаковых тестах.
6. После оценки вручную перепроверь обоснования продуктов, цитируемые новости, факты, читабельность слайдов и оформление.
7. Если GigaChat недетерминирован, повтори каждую конфигурацию с разными именами версий, оцени разброс; один прогон на восьми клиентах не доказывает статистическую значимость.

## Эксперимент 1 — промпт GigaChat

**Гипотеза:** более строгая инструкция по соответствию продуктов клиентским рискам уменьшит неподтверждённые обоснования, не ухудшая релевантность.

Базовый system prompt находится в `task2/src/writer.py`. Альтернативный вариант — `task2/config/prompts/strict_risk_first.txt`. Файл промпта обязан сохранять JSON-контракт `summary`, `product_fit`, `questions`; нельзя разрешать модели добавлять отсутствующие продукты и новости.

```bash
# Рабочая директория: task3/
GIGACHAT_PROMPT_FILE= python -m evaluation.cli run \
  --version prompt_A --mode full

GIGACHAT_PROMPT_FILE=config/prompts/strict_risk_first.txt \
  python -m evaluation.cli run --version prompt_B --mode full

python -m evaluation.cli compare \
  --baseline evaluation/runs/prompt_A \
  --candidate evaluation/runs/prompt_B \
  --out results/prompt_comparison
```

**Анализ:** автоматические `narrative_contract_rate`, `source_error_count`, `critical_error_count`, метрики продуктов и итоговый score; **обязательно** вручную оцени фактическую точность, специфичность клиенту, полезность вопросов и объяснений продуктов. Изменение промпта не всегда отражается в автоматических метриках.

## Эксперимент 2 — retrieval-логика OpenSearch

**Гипотеза:** поиск только по заголовку повышает precision, но уменьшает recall, если компания указана в тексте.

В `task2/src/retrieval.py`, функция `OpenSearchRetriever.get_context()`, поддержаны `balanced` и `title_only`:

```bash
NEWS_QUERY_MODE=balanced python -m evaluation.cli run \
  --version retrieval_A --mode full

NEWS_QUERY_MODE=title_only python -m evaluation.cli run \
  --version retrieval_B --mode full

python -m evaluation.cli compare \
  --baseline evaluation/runs/retrieval_A \
  --candidate evaluation/runs/retrieval_B \
  --out results/retrieval_comparison
```

**Анализ:** `retrieval_news_precision_judged`, `retrieval_news_known_recall`, `selected_news_precision_judged`, `selected_news_known_recall`, число нерелевантных новостей и цитируемых источников.

При изменении самого Python-запроса в `src/retrieval.py` вместо параметра среды фиксируй Git-коммиты или два worktree с разными версиями и указывай `--agent-root` для каждой. При одинаковом индексе повторная индексация не нужна, если не поменялся набор полей/документов.

## Эксперимент 3 — параметры поиска: boost, top-k, выбранные новости

**Гипотеза:** увеличение веса заголовка улучшит точность верхних результатов, но способно понизить полноту.

```bash
NEWS_TITLE_BOOST=4 NEWS_CONTENT_BOOST=1 python -m evaluation.cli run \
  --version boost_A --mode full

NEWS_TITLE_BOOST=8 NEWS_CONTENT_BOOST=1 python -m evaluation.cli run \
  --version boost_B --mode full

python -m evaluation.cli compare \
  --baseline evaluation/runs/boost_A \
  --candidate evaluation/runs/boost_B \
  --out evaluation/comparison
```

Глубину получения новостей и число выбранных новостей можно менять без кода:

```bash
python -m evaluation.cli run --version top18 --mode full --retrieval-news-limit 18
python -m evaluation.cli run --version top5  --mode full --retrieval-news-limit 5
python -m evaluation.cli compare \
  --baseline evaluation/runs/top18 \
  --candidate evaluation/runs/top5 \
  --out evaluation/comparison
```

**Внимание:** максимальное количество показываемых в текущем макете новостей — 4. Если меняешь `--selected-news-limit`, проверяй, что слайд действительно отображает запрошенное число; для большего количества сначала меняй `task2/src/presentation.py`.

При изменении только `boost`, top-k или режима запроса **переиндексация не нужна**.

## Эксперимент 4 — чанкинг документов (обязательно два индекса)

`task2/src/retrieval.py` реализует `split_into_chunks()`: разбиение новостного текста на пересекающиеся фрагменты по числу символов с сохранением информации об исходной статье. Профили клиентов, продукты и заметки не чанкуются.

`NEWS_CHUNK_SIZE=0` значит «новость целиком», `NEWS_CHUNK_OVERLAP=100` — перекрытие 100 символов. Переиндексация **обязательна** при смене чанкинга. Имена индексов должны быть различными, чтобы B не перезатёр A.

```bash
# Сначала создаём оба индекса, находясь в task2/
cd ../task2
OPENSEARCH_INDEX_NAME=ab_news_full NEWS_CHUNK_SIZE=0 NEWS_CHUNK_OVERLAP=100 \
  python -m src.cli index

OPENSEARCH_INDEX_NAME=ab_news_chunk600 NEWS_CHUNK_SIZE=600 NEWS_CHUNK_OVERLAP=100 \
  python -m src.cli index

# Оцениваем через Task 3, каждый со своим индексом
cd ../task3
OPENSEARCH_INDEX_NAME=ab_news_full NEWS_CHUNK_SIZE=0 NEWS_CHUNK_OVERLAP=100 \
  python -m evaluation.cli run --version chunk_A --mode full

OPENSEARCH_INDEX_NAME=ab_news_chunk600 NEWS_CHUNK_SIZE=600 NEWS_CHUNK_OVERLAP=100 \
  python -m evaluation.cli run --version chunk_B --mode full

python -m evaluation.cli compare \
  --baseline evaluation/runs/chunk_A \
  --candidate evaluation/runs/chunk_B \
  --out evaluation/comparison
```

**Анализ:** полнота и точность retrieval, число уникальных новостей после слияния чанков, потерянные публикации, скорость и ресурсы. Если экспериментируешь с другой реализацией разбиения (по предложениям и т. п.), меняй `split_into_chunks()` в `task2/src/retrieval.py` и сохраняй commit/manifest.

## Эксперимент 5 — генерация `.pptx`

`task2/src/presentation.py` содержит тему `PPTX_THEME=teal` и `PPTX_THEME=blue`. Для проверки только оформления можно использовать `demo`, чтобы исключить нестабильность GigaChat:

```bash
PPTX_THEME=teal python -m evaluation.cli run --version pptx_A --mode demo
PPTX_THEME=blue python -m evaluation.cli run --version pptx_B --mode demo

python -m evaluation.cli compare \
  --baseline evaluation/runs/pptx_A \
  --candidate evaluation/runs/pptx_B \
  --out evaluation/comparison
```

**Автоматически:** проверка `.pptx` (открытие, количество слайдов, обязательные элементы, выход текста за границы), `pptx_valid_rate`. **Вручную:** читаемость, плотность текста, контраст, иерархия, полезность источников и перегруз слайдов. Чистая смена палитры может не изменить автоматические метрики — это ожидаемо. Для нового макета поменяй `task2/src/presentation.py`, при необходимости скорректируй PPTX-проверки, и сравни оба варианта на одних и тех же данных.