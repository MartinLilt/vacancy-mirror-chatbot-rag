# Vacancy Mirror Chatbot RAG

Pipeline for turning raw Upwork job data into clustered role profiles and semantic cores.

## Setup

Activate the local environment:

```sh
source .venv/bin/activate
```

Check Python version:

```sh
.venv/bin/python --version
```

## One-Command Run

Run the full pipeline from raw JSON to final semantic core JSON:

```sh
PYTHONPATH=src .venv/bin/python -m vacancy_mirror_chatbot_rag.cli run-full-pipeline
```

Default input:
- `data/web_development_jobs.json`

Final output:
- `data/top_demanded_profiles_semantic_core.json`

## Required Environment

For the naming step, set `OPENAI_API_KEY`. You can also override the naming model with `OPENAI_MODEL`, or pass `--naming-model` to the CLI.

Resume behavior:
- by default, existing output artifacts are reused and skipped
- use `--force` to rebuild everything from scratch
- use `--embedding-batch-size 16` or similar if embedding generation feels too heavy
