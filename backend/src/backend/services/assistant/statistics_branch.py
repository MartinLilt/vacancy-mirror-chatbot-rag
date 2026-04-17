"""Statistics branch pipeline — Layer 1: weekly report routing."""

from __future__ import annotations

import logging

from backend.services.assistant.orchestrator import Branch, BranchResult, LLM

log = logging.getLogger(__name__)

# Canonical category names (must stay in sync with scraper/src/scraper/categories.py)
UPWORK_CATEGORIES: tuple[str, ...] = (
    "Accounting & Consulting",
    "Admin Support",
    "Customer Service",
    "Data Science & Analytics",
    "Design & Creative",
    "Engineering & Architecture",
    "IT & Networking",
    "Legal",
    "Sales & Marketing",
    "Translation",
    "Web, Mobile & Software Dev",
    "Writing",
)

_LAYER1_SYSTEM_PROMPT = f"""\
You are a routing agent for a freelance market statistics assistant.

Analyze the conversation and decide whether the user is asking for a
*weekly market report* for a specific Upwork category.

The 12 valid Upwork categories are:
{chr(10).join(f'  - {c}' for c in UPWORK_CATEGORIES)}

Return JSON only:
{{"wants_weekly_report": true, "category": "Design & Creative"}}
{{"wants_weekly_report": false, "category": null}}

Rules:
- wants_weekly_report=true only when the user explicitly wants a market
  report, trend summary, weekly stats, or top-skills breakdown for a
  specific category (or their own category if clearly stated in history).
- category must be one of the 12 names above — pick the closest match.
- If the category cannot be determined from the conversation, set
  wants_weekly_report=false.
- wants_weekly_report=false for general open-ended questions that are not
  asking for a report.
"""


class StatisticsBranchHandler:
    """
    Statistics branch: Layer 1 decides if weekly report is needed,
    then routes to the market report API (stub until the API is live).
    """

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def __call__(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> BranchResult:
        wants_report, category = self._decide_report(
            question=question, history=history
        )

        if wants_report and category:
            content = self._fetch_weekly_report(category=category)
        else:
            content = self.llm.answer_with_history(question=question, history=history)

        return BranchResult(branch=Branch.STATISTICS, content=content, success=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decide_report(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> tuple[bool, str | None]:
        user_prompt = _format_messages(question, history)
        try:
            raw = self.llm.generate_structured_json(
                system_prompt=_LAYER1_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            wants = bool(raw.get("wants_weekly_report", False))
            category = raw.get("category") or None
            if category and category not in UPWORK_CATEGORIES:
                log.warning(
                    "Statistics Layer 1 returned unknown category %r, ignoring", category
                )
                category = None
            log.info(
                "Statistics Layer 1 → wants_weekly_report=%s category=%r",
                wants,
                category,
            )
            return wants, category
        except Exception as exc:  # noqa: BLE001
            log.warning("Statistics Layer 1 LLM failed (%s), skipping report", exc)
            return False, None

    def _fetch_weekly_report(self, *, category: str) -> str:
        """
        Route to the market-report assistant API.
        TODO: replace stub with real HTTP call to the report server.
        """
        log.info("Statistics branch → weekly report requested for %r (stub)", category)
        return (
            f"📊 Weekly market report for *{category}* is being prepared.\n"
            "This feature is currently being connected to the report server."
        )


def _format_messages(question: str, history: list[dict[str, str]]) -> str:
    lines: list[str] = ["Conversation history:"]
    for msg in history[-9:]:
        role = str(msg.get("role", "user")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    lines.append(f"\nLatest user message:\n{question.strip()}")
    return "\n".join(lines)