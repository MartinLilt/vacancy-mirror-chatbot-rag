"""Knowledge branch pipeline — Layer 1: retrieval decision + grounded answer."""

from __future__ import annotations

import logging

from backend.services.assistant.knowledge import AssistantSectionRetriever
from backend.services.assistant.orchestrator import Branch, BranchResult, LLM

log = logging.getLogger(__name__)

_LAYER1_SYSTEM_PROMPT = """\
You are a retrieval-decision agent for a freelance market assistant.

Analyze the conversation and decide whether answering the user's question
requires grounding in the product/platform knowledge base (Upwork Academy,
product plans, assistant rules, Upwork policies, freelancing guidance).

Return JSON only:
{"needs_retrieval": true, "retrieval_query": "concise search query for the knowledge base"}
{"needs_retrieval": false, "retrieval_query": ""}

Rules:
- needs_retrieval=true when the user asks about: Upwork platform rules, product plans
  or pricing, assistant capabilities, account setup, proposals, contracts, JSS, payments,
  scam prevention, profile growth, freelancing best practices, or any topic covered by
  the Upwork Academy or product documentation.
- needs_retrieval=false when the question is fully general and no documented knowledge
  section would improve the answer.
- retrieval_query must be a short, focused English search string (5–10 words max).
"""

_LAYER1_ANSWER_SYSTEM_PROMPT = """\
You are a freelance market assistant. Answer the user's question using the
knowledge sections provided below as your primary source of truth.

Rules:
- Be concise and practical (target 3–8 short lines, max ~900 chars).
- Use plain Telegram Markdown for light emphasis (*bold*).
- Use 1–3 emojis maximum, only where naturally helpful.
- Do not mention section IDs or say "according to section X".
- If the sections do not fully cover the question, say so briefly and give
  your best practical guidance based on general knowledge.
"""


class KnowledgeBranchHandler:
    """Two-step knowledge branch: retrieval decision → grounded answer."""

    def __init__(self, llm: LLM, *, top_k: int = 4) -> None:
        self.llm = llm
        self.retriever = AssistantSectionRetriever()
        self.top_k = top_k

    def __call__(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> BranchResult:
        # Layer 1: decide whether retrieval is needed
        needs_retrieval, retrieval_query = self._decide_retrieval(
            question=question, history=history
        )

        if needs_retrieval:
            answer = self._answer_with_retrieval(
                question=question,
                history=history,
                retrieval_query=retrieval_query,
            )
        else:
            answer = self.llm.answer_with_history(question=question, history=history)

        return BranchResult(branch=Branch.KNOWLEDGE, content=answer, success=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decide_retrieval(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> tuple[bool, str]:
        user_prompt = _format_messages(question, history)
        try:
            raw = self.llm.generate_structured_json(
                system_prompt=_LAYER1_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            needs = bool(raw.get("needs_retrieval", True))
            query = str(raw.get("retrieval_query", "")).strip() or question
            log.info(
                "Knowledge Layer 1 → needs_retrieval=%s query=%r", needs, query
            )
            return needs, query
        except Exception as exc:  # noqa: BLE001
            log.warning("Knowledge Layer 1 LLM failed (%s), defaulting to retrieval", exc)
            return True, question

    def _answer_with_retrieval(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
        retrieval_query: str,
    ) -> str:
        sections = self.retriever.retrieve(query=retrieval_query, top_k=self.top_k)
        rendered = self.retriever.render_sections(sections)
        log.info(
            "Knowledge retrieval → %d sections for query=%r",
            len(sections),
            retrieval_query,
        )

        conversation = _format_messages(question, history)
        user_prompt = (
            f"## Knowledge sections\n\n{rendered}\n\n"
            f"## Conversation\n\n{conversation}"
        )
        return self.llm.generate_text(
            system_prompt=_LAYER1_ANSWER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
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