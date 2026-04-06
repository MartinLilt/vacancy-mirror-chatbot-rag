"""Three-layer reasoning orchestrator for assistant responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from backend.services.assistant_knowledge import (
    AssistantSectionRetriever,
    KnowledgeSection,
)


class StructuredLLM(Protocol):
    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, object]:
        """Return a JSON object from an LLM call."""


class SectionRetriever(Protocol):
    def retrieve(self, *, query: str, top_k: int = 4) -> list[KnowledgeSection]:
        """Return relevant knowledge sections for a query."""

    def render_sections(self, sections: list[KnowledgeSection]) -> str:
        """Render retrieved sections into a prompt-friendly text block."""


@dataclass(slots=True)
class OrchestratorResult:
    final_answer: str
    checklist: list[str]
    step_summaries: list[str]
    route: str = "long_path"


class ReasoningOrchestrator:
    """Runs a 3-layer reasoning pipeline over a user message and history."""

    def __init__(
        self,
        *,
        llm: StructuredLLM,
        retriever: SectionRetriever | None = None,
        max_history_messages: int = 8,
    ) -> None:
        self.llm = llm
        self.retriever = retriever or AssistantSectionRetriever()
        self.max_history_messages = max_history_messages
        self.fast_path_intent_confidence_min = 0.82
        self.fast_path_grounding_confidence_min = 0.65

    def run(
        self,
        *,
        question: str,
        history: list[dict[str, str]] | None = None,
        stage_callback: Callable[[str], None] | None = None,
    ) -> OrchestratorResult:
        def _emit(stage: str) -> None:
            if stage_callback is None:
                return
            try:
                stage_callback(stage)
            except Exception:  # noqa: BLE001
                pass

        _emit("layer1_start")
        history_block = self._format_history(history or [])
        layer1_sections = self.retriever.retrieve(query=question, top_k=6)
        layer1 = self._run_layer1(
            question=question,
            history_block=history_block,
            sections_block=self.retriever.render_sections(layer1_sections),
        )

        route = str(layer1.get("route", "long_path")).strip().lower()
        if route not in {"fast_path", "long_path"}:
            route = "long_path"

        # Backward-compatible fallback: if route is omitted but model provides
        # a direct fast answer, we can still short-circuit.
        if route == "long_path":
            needs_reasoning = layer1.get("needs_reasoning")
            if isinstance(needs_reasoning, bool) and not needs_reasoning:
                route = "fast_path"

        if route == "fast_path":
            quick_answer = str(
                layer1.get("fast_answer")
                or layer1.get("answer")
                or ""
            ).strip()
            if quick_answer and self._should_use_fast_path(layer1):
                _emit("fast_path_start")
                return OrchestratorResult(
                    final_answer=quick_answer,
                    checklist=[],
                    step_summaries=[],
                    route="fast_path",
                )

        checklist = layer1.get("checklist")
        checklist_items: list[str] = []
        if isinstance(checklist, list):
            checklist_items = [
                str(item).strip()
                for item in checklist
                if str(item).strip()
            ]
        if not checklist_items:
            # Keep pipeline moving even when Layer 1 returns partial JSON.
            checklist_items = [
                "Provide one concise, grounded answer to the user question."
            ]

        context_summary = str(layer1.get("context_summary", "")).strip()
        steps: list[dict[str, str]] = []
        step_summaries: list[str] = []
        _emit("layer2_start")
        for item in checklist_items:
            item_sections = self.retriever.retrieve(
                query=f"{question}\n{item}",
                top_k=4,
            )
            layer2_item = self._run_layer2_item(
                question=question,
                context_summary=context_summary,
                checklist_item=item,
                sections_block=self.retriever.render_sections(item_sections),
            )
            action_plan = str(layer2_item.get("action_plan", "")).strip()
            answer_summary = str(layer2_item.get("answer_summary", "")).strip()
            if not answer_summary:
                continue
            steps.append({
                "item": item,
                "action_plan": action_plan,
                "answer_summary": answer_summary,
            })
            step_summaries.append(answer_summary)

        if not steps:
            raise RuntimeError("Layer 2 returned no valid step summaries.")

        _emit("layer3_start")
        layer3 = self._run_layer3(
            question=question,
            context_summary=context_summary,
            steps=steps,
        )
        final_answer = str(layer3.get("final_answer", "")).strip()
        if not final_answer:
            raise RuntimeError("Layer 3 did not return final_answer.")

        return OrchestratorResult(
            final_answer=final_answer,
            checklist=checklist_items,
            step_summaries=step_summaries,
            route="long_path",
        )

    def _format_history(self, history: list[dict[str, str]]) -> str:
        cleaned: list[str] = []
        for item in history[-self.max_history_messages :]:
            role = str(item.get("role", "user")).strip().lower()
            if role not in {"user", "assistant"}:
                role = "user"
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            cleaned.append(f"{role}: {content}")
        return "\n".join(cleaned) if cleaned else "(no prior history)"

    def _run_layer1(
        self,
        *,
        question: str,
        history_block: str,
        sections_block: str,
    ) -> dict[str, object]:
        system_prompt = (
            "You are Layer 1 of a reasoning orchestrator. "
            "Read chat history + user message, detect intent, and decide routing. "
            "Output JSON only. "
            "Use English only. "
            "When the request is simple and can be answered safely from retrieved sections, "
            "set route=fast_path and provide fast_answer. "
            "When reasoning is needed, set route=long_path and provide checklist. "
            "Also return routing signals: risk_level (low|medium|high), "
            "needs_multi_step (true|false), intent_confidence (0..1), grounding_confidence (0..1). "
            "Use fast_path only when: risk_level=low, needs_multi_step=false, "
            "intent_confidence>=0.82, grounding_confidence>=0.65. "
            "Return one of these shapes: "
            '{"route":"fast_path","context_summary":"...","fast_answer":"...",'
            '"risk_level":"low","needs_multi_step":false,'
            '"intent_confidence":0.93,"grounding_confidence":0.88} '
            "or "
            '{"route":"long_path","context_summary":"...","checklist":["task 1","task 2"],'
            '"risk_level":"medium","needs_multi_step":true,'
            '"intent_confidence":0.61,"grounding_confidence":0.54}. '
            "Checklist items must be concrete and action-oriented."
        )
        user_prompt = (
            "Conversation history:\n"
            f"{history_block}\n\n"
            "Latest user message:\n"
            f"{question.strip()}\n\n"
            "Retrieved sections:\n"
            f"{sections_block}"
        )
        return self.llm.generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _bool_or_none(value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "1", "yes"}:
                return True
            if v in {"false", "0", "no"}:
                return False
        return None

    def _should_use_fast_path(self, layer1: dict[str, object]) -> bool:
        """Validate Layer-1 routing signals before allowing fast-path."""
        risk_level = str(layer1.get("risk_level", "low")).strip().lower()
        if risk_level in {"medium", "high"}:
            return False

        needs_multi_step = self._bool_or_none(layer1.get("needs_multi_step"))
        if needs_multi_step is True:
            return False

        intent_confidence = self._float_or_none(layer1.get("intent_confidence"))
        if (
            intent_confidence is not None
            and intent_confidence < self.fast_path_intent_confidence_min
        ):
            return False

        grounding_confidence = self._float_or_none(
            layer1.get("grounding_confidence")
        )
        if (
            grounding_confidence is not None
            and grounding_confidence < self.fast_path_grounding_confidence_min
        ):
            return False

        return True

    def _run_layer2_item(
        self,
        *,
        question: str,
        context_summary: str,
        checklist_item: str,
        sections_block: str,
    ) -> dict[str, object]:
        system_prompt = (
            "You are Layer 2 (planner/executor) of a reasoning orchestrator. "
            "Process one checklist item at a time. Use retrieved sections as source of truth. "
            "Do not invent unavailable product features or policy claims. "
            "Use English only. "
            "Keep answer_summary concise and specific (max 2 short sentences). "
            "Return JSON only with shape: "
            '{"action_plan":"...","answer_summary":"..."}'
        )
        payload = {
            "question": question.strip(),
            "context_summary": context_summary,
            "checklist_item": checklist_item,
            "retrieved_sections": sections_block,
        }
        return self.llm.generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            temperature=0.2,
        )

    def _run_layer3(
        self,
        *,
        question: str,
        context_summary: str,
        steps: list[dict[str, str]],
    ) -> dict[str, object]:
        system_prompt = (
            "You are Layer 3 (aggregator). "
            "Merge step summaries into one coherent final response with practical conclusions. "
            "Keep response aligned with product and policy statements from prior steps. "
            "Use English only. "
            "Avoid large text blocks and generic filler. "
            "Keep the answer short (target 3 to 6 short lines, max ~700 chars). "
            "Use concise Telegram-friendly structure. "
            "Use 1 to 4 emojis maximum, only where naturally helpful. "
            "Use plain Telegram Markdown for light emphasis where useful. "
            "No separate Conclusion section. Integrate conclusion into the main answer. "
            "No HTML tags. "
            "Return JSON only with shape: "
            '{"final_answer":"..."}. '
            "Keep it concise and user-facing."
        )
        payload = {
            "question": question.strip(),
            "context_summary": context_summary,
            "steps": steps,
        }
        return self.llm.generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            temperature=0.3,
        )
