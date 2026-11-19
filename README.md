# Tasks 1–3 · News analytics & client presentation agent

| Раздел | Что выполнено | Главные файлы | Результаты |
|---|---|---|---|
| **[Task 1](task1/README.md)** | NLP: компании, отрасль, события и цитируемость | [`task1/task1_pipeline.ipynb`](task1/task1_pipeline.ipynb) | `task1/results/news_predictions.csv` |
| **[Task 2](task2/README.md)** | Агент RAG + OpenSearch + GigaChat → `.pptx` | [`task2/src/`](task2/src/) | `task2/examples/*.pptx` |
| **[Task 3](task3/README.md)** | Валидация и A/B сравнения агента | [`task3/evaluation/`](task3/evaluation/) | `task3/results/comparison_prompt/comparison.html`; `task3/results/comparison_retriever/comparison.html` |

## Организация проекта

```text
.
├── task1/
│   ├── README.md
│   ├── task1_final_pipeline.ipynb
│   ├── data/news.csv                 # исходные новости
│   └── results/                     # news_predictions.csv
├── task2/
│   ├── README.md
│   ├── src/                         # Python-код агента
│   ├── data/                        # входные JSON + news.csv
│   ├── config/prompts/              # альтернативный системный промпт
│   ├── outputs/                     # директория, создаваемая агентом для результатов
│   ├── examples/                     # презентации .pptx
│   ├── tests/
│   ├── .env.example                 # шаблон без ключей
│   └── docker-compose.yml
├── task3/
│   ├── README.md
│   ├── EXPERIMENTS.md               # инструкции для 5 типов A/B тестов
│   ├── evaluation/                  # код, gold, сравнение
│   ├── tests/
│   └── results/
│       ├── comparison_prompt/
│       └── comparison_retriever/
├── .gitignore
└── README.md
```

## Быстрый запуск

Task 1 умеет работать независимо; Task 2 и Task 3 используют одно окружение и один настроенный агент.

```bash
# Task 1
cd task1
pip install -r requirements.txt
jupyter notebook task1_pipeline.ipynb

# Task 2 (в другом терминале/после возврата в корень)
cd ../task2
pip install -r requirements.txt
cp .env.example .env        # API-ключи только локально
# docker compose up -d; python -m src.cli index
python -m src.cli generate "Подготовь презентацию о РЖД"

# Task 3 — использует Task 2, в том числе его task2/.env
cd ../task3
python -m evaluation.cli run --version baseline_demo --mode demo
```

Инструкция по A/B: [task3/EXPERIMENTS.md](task3/EXPERIMENTS.md). [Схема архитектуры](docs/architecture.md) и [ход решений](docs/decisions.md). Инструкция по публикации: [GITHUB_SETUP.md](GITHUB_SETUP.md).

