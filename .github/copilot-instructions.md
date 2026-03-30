# Copilot Instructions — vacancy-mirror-chatbot-rag

## Language

- All code comments must be written in **English only**
- Docstrings must be in **English only**
- Variable names, function names, class names — **English only**
- Print/log messages — **English only**

## Code Style

- Follow **PEP 8** strictly (max line length: 79 characters)
- Use `from __future__ import annotations` in every file
- Use type hints everywhere (function arguments, return types, variables)
- Prefer `pathlib.Path` over raw string paths
- Prefer `f-strings` over `.format()` or `%`
- No unused imports

## Project Structure

- Source code lives in `src/vacancy_mirror_chatbot_rag/`
- Services go into `src/vacancy_mirror_chatbot_rag/services/`
- Scripts and experiments go into `scripts/`
- Data files go into `data/`

## Architecture

- This is a **RAG pipeline** for Upwork job vacancies
- Browser automation uses **nodriver** (real Chrome, anti-bot)
- Embeddings use **sentence-transformers** (`BAAI/bge-small-en-v1.5`)
- LLM naming uses **OpenAI API** (model from `OPENAI_MODEL` env var)
- All services must be implemented as **classes** with clear responsibilities

## Async

- Browser automation code is **async** (use `asyncio`)
- Use `nodriver` patterns: `await page.send(cdp.*)` for CDP commands

## Error Handling

- Always handle file-not-found and network errors gracefully
- Raise specific exceptions with clear messages, never silent `except: pass`

## Terminal Commands

- **Never run blocking terminal processes** that prevent the user from continuing the chat
- Always use `isBackground: true` for long-running processes (servers, watchers, docker-compose up, bot processes, etc.)
- If a command must run in the foreground, warn the user first and confirm before running it

## Do Not

- Do not use `requests` library — use `urllib` or `httpx`
- Do not hardcode API keys — use environment variables
- Do not write comments or docstrings in any language other than English
- Do not use `print` in library code — use `logging`
