"""Simple branch pipeline — fast conversational fallback with no business logic."""

from __future__ import annotations

import logging

from backend.services.assistant.orchestrator import Branch, BranchResult, LLM

log = logging.getLogger(__name__)

_LAYER1_SYSTEM_PROMPT = """\
You are a friendly freelance market assistant in a Telegram chat.

The user sent a message that requires no business action — it may be a greeting,
farewell, thank-you, small talk, or simple acknowledgement.

Respond briefly and warmly. Rules:
- Keep the reply to 1–2 short sentences maximum.
- Match the tone of the user (casual if they are casual, polite if formal).
- Do not mention features, plans, or data unless the user asked about them.
- Use plain Telegram Markdown (*bold*) only when it feels natural.
- Use at most 1 emoji if it fits naturally; none if it does not.
- Never say you are an AI or explain your limitations unprompted.

Return JSON only:
{"answer": "your short reply here"}
"""


class SimpleBranchHandler:
    """Fallback branch: short conversational reply, no retrieval or stats."""

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def __call__(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> BranchResult:
        answer = self._quick_reply(question=question, history=history)
        return BranchResult(branch=Branch.SIMPLE, content=answer, success=True)

    def _quick_reply(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
    ) -> str:
        user_prompt = _format_messages(question, history)
        try:
            raw = self.llm.generate_structured_json(
                system_prompt=_LAYER1_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.5,
            )
            answer = str(raw.get("answer", "")).strip()
            if not answer:
                raise ValueError("Empty answer from simple branch LLM")
            log.info("Simple branch → answer=%r", answer[:80])
            return answer
        except Exception as exc:  # noqa: BLE001
            log.warning("Simple branch LLM failed (%s), using fallback", exc)
            return self.llm.answer_with_history(question=question, history=history)


def _format_messages(question: str, history: list[dict[str, str]]) -> str:
    lines: list[str] = ["Conversation history:"]
    for msg in history[-9:]:
        role = str(msg.get("role", "user")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    lines.append(f"\nLatest user message:\n{question.strip()}")
    return "\n".join(lines)