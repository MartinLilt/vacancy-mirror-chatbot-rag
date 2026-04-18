# TODO — Assistant

## In Progress

- [ ] **Statistics branch: connect real report API**
  - Replace stub `_fetch_weekly_report()` in `statistics_branch.py`
  - HTTP call to report server → returns weekly market data per category
  - Define response schema

## Next Up

- [ ] **Statistics branch: describe remaining layers**
  - After weekly report: are there more layers before BranchResult?

- [ ] **Tests — branch handlers**
  - `test_knowledge_branch.py` — retrieval decision + grounded answer
  - `test_statistics_branch.py` — category detection, stub response
  - `test_simple_branch.py` — quick reply format

- [ ] **Tests — orchestrator end-to-end**
  - Route → execute → synthesize full flow
  - Multi-branch parallel execution

## Done

- [x] `InitOrchestrator` — routing logic (route + execute)
- [x] `ResultOrchestrator` — synthesis (single branch + multi-branch)
- [x] `KnowledgeBranchHandler` — Layer 1 retrieval decision + grounded answer
- [x] `StatisticsBranchHandler` — Layer 1 weekly report routing (stub API)
- [x] `SimpleBranchHandler` — Layer 1 quick conversational reply
- [x] All 3 handlers registered in `infer_server.py`
- [x] Routing prompt updated with `simple` fallback rules