# Baltic Marketplace

Minimal Python project scaffold for building a job-market analysis and profile-optimization system.

## Requirements

- Python 3.13+

## Setup

Create and activate a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade packaging tools if needed:

```sh
python -m pip install --upgrade pip setuptools
```

## Status

This repository currently contains only the base scaffold:

- `pyproject.toml`
- `.python-version`
- `README.md`
- `.gitignore`

## Current structure

- `src/baltic_marketplace/services/apify.py`

Default Apify actor:

- `upwork-vibe/upwork-job-scraper`

Environment:

```sh
export APIFY_TOKEN="..."
export OPENAI_API_KEY="..."
export UPWORK_ACCESS_TOKEN="..."
```

## CLI

Broad market collection for the `Web Development` category:

```sh
PYTHONPATH=src python3 -m baltic_marketplace.cli collect-web-development-jobs --limit 6000
```

Example with explicit output path:

```sh
PYTHONPATH=src python3 -m baltic_marketplace.cli collect-web-development-jobs \
  --limit 6000 \
  --output data/web_development.json
```

Marketplace collection through the official Upwork GraphQL API:

```sh
PYTHONPATH=src python3 -m baltic_marketplace.cli collect-upwork-jobs \
  --query "web development" \
  --limit 200 \
  --output data/web_development.json
```

Frequency analysis with separate CSV files for `skills`, `title`, and `description`
saved into `data/pattern_layer/`:

```sh
PYTHONPATH=src python3 -m baltic_marketplace.cli show-market-top-frequencies
```

Normalize `title` and `description` pattern CSV files and save copies into
`data/normalizer_layer/`:

```sh
PYTHONPATH=src python3 -m baltic_marketplace.cli normalize-market-patterns
```

LLM classification of market patterns:

```sh
PYTHONPATH=src python3 -m baltic_marketplace.cli classify-market-patterns
```
