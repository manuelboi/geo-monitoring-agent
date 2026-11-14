# Synthetic GEO data catalog

This catalog describes the locally generated demonstration dataset in `csv/`. The data is not derived from real
client work and does not identify a company, person, website, or source.

## Tables

| CSV | Rows | Grain |
|---|---:|---|
| `00_README.csv` | 2 | Dataset note |
| `01_context.csv` | 12 | Scenario setting |
| `02_kpi_definitions.csv` | 12 | Metric or concept |
| `03_data_dictionary.csv` | 8 | Field description |
| `04_prompts.csv` | 8 | Synthetic prompt |
| `05_answers.csv` | 32 | Prompt and assistant |
| `06_mentions.csv` | 64 | Brand mention |
| `07_citations.csv` | 64 | Citation and mention |

The evidence chain is `prompts.prompt_id` → `answers.answer_id` → `mentions.answer_id` → `citations.mention_id`.
The same citation can support multiple mentions. `answer_id` combines a prompt ID with one of four monitored AI
assistants.

## Metrics

Metrics are calculated from the synthetic rows at query time:

| Metric | Formula |
|---|---|
| Visibility | Answers mentioning a brand / answers in scope |
| Share of voice | Brand mentions / all brand mentions in scope |
| Sentiment | Positive mentions / brand mentions |
| Average position | Mean position of the brand's mentions |
| Top-3 rate | Mentions at positions 1–3 / brand mentions |
| Prominence | Sum of `max(0, (11 - position) / 10)` / answers in scope |
| Source mix | Citations of an ownership type / all citations in scope |

All names and text are synthetic. URLs use the reserved `.example` domain; assistant and metric names are generic
product/category labels.
