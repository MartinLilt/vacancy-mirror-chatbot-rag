# Architecture — Assistant Pipeline

## Overview

```
Telegram Bot
    │
    ▼
AssistantInferClient  (round-robin, failover across replicas)
    │  POST /v1/answer
    ▼
AssistantInferServer  (ThreadingHTTPServer, BoundedSemaphore max 24)
    │
    ├─ 1. ROUTING — InitOrchestrator.route()
    │      LLM analyzes 9+1 messages → RoutingDecision{branches, reasoning}
    │
    ├─ 2. EXECUTE — InitOrchestrator.execute()
    │      Parallel via ThreadPoolExecutor when >1 branch
    │      Each branch → BranchResult{branch, content, success, error}
    │
    └─ 3. SYNTHESIS — ResultOrchestrator.synthesize()
           1 branch  → return content directly (no extra LLM call)
           2 branches → LLM merges into one Telegram-friendly answer
```

---

## Branches

### `knowledge`
Triggers on: product plans, assistant rules, Upwork platform guidance, Upwork Academy, freelancing best practices.

**Layer 1** — retrieval decision  
LLM → `{"needs_retrieval": bool, "retrieval_query": str}`

- `needs_retrieval=true` → `AssistantSectionRetriever.retrieve(query, top_k=4)` → top sections from `DEFAULT_KNOWLEDGE_SECTIONS` → LLM answers grounded in sections
- `needs_retrieval=false` → `answer_with_history()` direct

**File:** `services/assistant/knowledge_branch.py`

---

### `statistics`
Triggers on: weekly market reports, skill demand, top roles, trend signals per Upwork category.

**Layer 1** — report decision  
LLM → `{"wants_weekly_report": bool, "category": str | null}`

- `wants_report=true` + valid category → `_fetch_weekly_report(category)` ← **stub, TODO: HTTP → report server**
- otherwise → `answer_with_history()` direct

Valid categories (12):
- Accounting & Consulting, Admin Support, Customer Service
- Data Science & Analytics, Design & Creative, Engineering & Architecture
- IT & Networking, Legal, Sales & Marketing
- Translation, Web Mobile & Software Dev, Writing

**File:** `services/assistant/statistics_branch.py`

---

### `simple`
Fallback only. **Never runs alongside other branches.**  
Triggers on: greetings, farewells, small talk, thank-you, off-topic chat.

**Layer 1** — quick reply  
LLM → `{"answer": "1–2 sentence reply"}`

**File:** `services/assistant/simple_branch.py`

---

## LLM Call Budget per Request

| Scenario | Calls |
|----------|-------|
| simple | 2 (router + layer1) |
| knowledge, no retrieval | 2 (router + answer) |
| knowledge + retrieval | 3 (router + layer1 + answer) |
| statistics, no report | 2 (router + answer) |
| statistics + report | 2 (router + layer1) ← stub |
| knowledge + statistics | 4–5 (router + both layers + answers + synthesis) |

---

## Key Files

| File | Purpose |
|------|---------|
| `orchestrator.py` | Branch enum, RoutingDecision, BranchResult, InitOrchestrator, ResultOrchestrator |
| `knowledge_branch.py` | Knowledge branch handler |
| `statistics_branch.py` | Statistics branch handler |
| `simple_branch.py` | Simple fallback handler |
| `knowledge.py` | DEFAULT_KNOWLEDGE_SECTIONS (40+ sections), AssistantSectionRetriever |
| `openai.py` | OpenAIMarketAssistantService (implements LLM protocol) |
| `infer_server.py` | HTTP server, wires all handlers |
| `infer_client.py` | HTTP client with round-robin failover |