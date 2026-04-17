"""Branching orchestrator pipeline.

Flow:
  user message
      → InitOrchestrator.route()       — fast LLM, decides which branches to run
      → branches execute in parallel   — each returns BranchResult
      → ResultOrchestrator.synthesize() — waits for all, forms final answer
      → answer to user
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class Branch(str, Enum):
    KNOWLEDGE = "knowledge"
    STATISTICS = "statistics"
    SIMPLE = "simple"


@dataclass
class RoutingDecision:
    branches: list[Branch]
    reasoning: str = ""


@dataclass
class BranchResult:
    """Fixed structure returned by every branch pipeline."""
    branch: Branch
    content: str       # main text answer produced by the branch
    success: bool      # False when the branch raised an exception
    error: str = ""    # populated only when success=False


BranchHandler = Callable[..., BranchResult]


# ---------------------------------------------------------------------------
# LLM protocol (both orchestrators share the same interface)
# ---------------------------------------------------------------------------

class LLM(Protocol):
    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> dict: ...

    def answer_with_history(
        self,
        *,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> str: ...


# ---------------------------------------------------------------------------
# InitOrchestrator — routing only
# ---------------------------------------------------------------------------

_ROUTING_SYSTEM_PROMPT = """\
You are a fast routing agent for a freelance market assistant.

Analyze the conversation (up to 10 messages) and decide which branch(es) to activate.

## Branch definitions

"knowledge"
  Activate when the user asks about: product policies, assistant rules and capabilities,
  Vacancy Mirror plans and pricing, what the product offers, Upwork platform rules,
  Upwork Academy, public freelancing knowledge, Reddit discussions, general Upwork tips,
  or any publicly available information about the platform or the assistant itself.

"statistics"
  Activate when the user wants analytical or statistical data derived from job postings:
  weekly market reports, top professions or roles in any category, fastest-growing stacks
  or technologies, skill demand breakdowns, overcrowded vs niche skill opportunities,
  market trend signals.

"simple"
  Activate ONLY as a fallback when no business action is needed: greetings, farewells,
  small talk, simple acknowledgements, thank-you messages, off-topic chat, or any
  message that requires no knowledge lookup or statistics.
  NEVER combine "simple" with "knowledge" or "statistics".

## Rules
- Activate "knowledge" and/or "statistics" when the message has a business intent.
- If intent clearly maps to one business branch, activate only that one.
- If the conversation touches both business topics, activate both.
- Activate "simple" alone only when there is no business intent whatsoever.
- When in doubt between business and simple, prefer the business branch.

Return JSON only:
{"branches": ["knowledge"], "reasoning": "short reason"}
{"branches": ["statistics"], "reasoning": "short reason"}
{"branches": ["knowledge", "statistics"], "reasoning": "short reason"}
{"branches": ["simple"], "reasoning": "short reason"}
"""


class InitOrchestrator:
    """Decides which branch pipelines to run for a given conversation."""

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def route(
        self,
        *,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> RoutingDecision:
        """Call the fast LLM and return the routing decision."""
        user_prompt = _format_messages(question, history or [])
        try:
            raw = self.llm.generate_structured_json(
                system_prompt=_ROUTING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            branches = _parse_branches(raw)
            reasoning = str(raw.get("reasoning", "")).strip()
            if not branches:
                log.warning("Router returned no valid branches, defaulting to knowledge")
                branches = [Branch.KNOWLEDGE]
            log.info(
                "Routing → branches=%s reasoning=%r",
                [b.value for b in branches],
                reasoning,
            )
            return RoutingDecision(branches=branches, reasoning=reasoning)
        except Exception as exc:  # noqa: BLE001
            log.warning("Routing LLM call failed (%s), defaulting to knowledge", exc)
            return RoutingDecision(branches=[Branch.KNOWLEDGE])

    def execute(
        self,
        routing: RoutingDecision,
        *,
        question: str,
        history: list[dict[str, str]],
        branch_handlers: dict[Branch, BranchHandler] | None = None,
    ) -> list[BranchResult]:
        """Run all activated branches (in parallel when >1) and collect BranchResult."""
        handlers = branch_handlers or {}

        if len(routing.branches) == 1:
            branch = routing.branches[0]
            return [self._run_branch(handlers, branch, question=question, history=history)]

        results: list[BranchResult] = []
        with ThreadPoolExecutor(max_workers=len(routing.branches)) as pool:
            futures = {
                pool.submit(
                    self._run_branch, handlers, b,
                    question=question, history=history,
                ): b
                for b in routing.branches
            }
            for future in as_completed(futures):
                results.append(future.result())

        # Preserve routing order in results
        order = {b: i for i, b in enumerate(routing.branches)}
        results.sort(key=lambda r: order.get(r.branch, 99))
        return results

    def _run_branch(
        self,
        handlers: dict[Branch, BranchHandler],
        branch: Branch,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> BranchResult:
        handler = handlers.get(branch, self._stub_handler)
        try:
            result = handler(question=question, history=history)
            # Handler may return BranchResult directly or a plain string (stub case)
            if isinstance(result, BranchResult):
                return result
            return BranchResult(branch=branch, content=str(result), success=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("Branch %r raised: %s", branch.value, exc)
            return BranchResult(branch=branch, content="", success=False, error=str(exc))

    def _stub_handler(self, *, question: str, history: list[dict[str, str]]) -> BranchResult:
        """Placeholder until the branch pipeline is implemented."""
        content = self.llm.answer_with_history(question=question, history=history)
        return BranchResult(branch=Branch.KNOWLEDGE, content=content, success=True)


# ---------------------------------------------------------------------------
# ResultOrchestrator — synthesis of all branch results
# ---------------------------------------------------------------------------

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a result synthesizer for a freelance market assistant.

You receive answers from one or more specialized branch pipelines and must produce
a single, coherent, user-facing response.

Rules:
- If only one branch responded, present its content directly — do not add meta-commentary.
- If multiple branches responded, merge them naturally into one flowing answer.
  Do not say "according to branch X" or "the knowledge branch says" — just integrate.
- Keep the answer concise and Telegram-friendly (target 3–8 short lines, max ~900 chars).
- Use plain Telegram Markdown for light emphasis where useful (bold with *text*).
- Use 1–4 emojis maximum, only where naturally helpful.
- No HTML tags. No large text blocks. No generic filler.

Return JSON only:
{"final_answer": "..."}
"""


class ResultOrchestrator:
    """Waits for all branch results and synthesizes the final answer."""

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def synthesize(
        self,
        *,
        question: str,
        results: list[BranchResult],
    ) -> str:
        """Form the final user-facing answer from all branch results."""
        successful = [r for r in results if r.success and r.content.strip()]

        if not successful:
            log.warning("All branches failed or returned empty content")
            return (
                "⚠️ Could not process your request right now. "
                "Please retry in a moment."
            )

        # Single branch — return content directly, no extra LLM call
        if len(successful) == 1:
            return successful[0].content.strip()

        # Multiple branches — synthesize with LLM
        payload = {
            "question": question.strip(),
            "branch_results": [
                {"branch": r.branch.value, "content": r.content.strip()}
                for r in successful
            ],
        }
        try:
            raw = self.llm.generate_structured_json(
                system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
                temperature=0.3,
            )
            final = str(raw.get("final_answer", "")).strip()
            if not final:
                raise ValueError("Synthesizer returned empty final_answer")
            return final
        except Exception as exc:  # noqa: BLE001
            log.warning("Result synthesis LLM call failed (%s), falling back to merge", exc)
            return "\n\n".join(r.content.strip() for r in successful)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_branches(raw: dict) -> list[Branch]:
    branches: list[Branch] = []
    for item in raw.get("branches", []):
        try:
            branches.append(Branch(str(item).lower().strip()))
        except ValueError:
            log.warning("Unknown branch value in routing response: %r", item)
    return branches


def _format_messages(question: str, history: list[dict[str, str]]) -> str:
    lines: list[str] = ["Conversation history:"]
    for msg in history[-9:]:
        role = str(msg.get("role", "user")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    lines.append(f"\nLatest user message:\n{question.strip()}")
    return "\n".join(lines)