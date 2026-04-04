from __future__ import annotations

import unittest

from backend.services.assistant_knowledge import (
    AssistantSectionRetriever,
    DEFAULT_KNOWLEDGE_SECTIONS,
)


class AssistantKnowledgeRetrieverTest(unittest.TestCase):
    def test_has_ten_upwork_sections(self) -> None:
        upwork_sections = [
            section for section in DEFAULT_KNOWLEDGE_SECTIONS
            if section.section_id.startswith("upwork_")
        ]
        self.assertEqual(len(upwork_sections), 10)

    def test_upwork_terms_query_hits_terms_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="What Upwork terms and rules should I check before working?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_terms_rules", ids)

    def test_upwork_profile_query_hits_growth_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How can I improve my Upwork profile and proposals?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_profile_growth", ids)

    def test_upwork_connects_query_hits_connects_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How should I spend Connects and when to boost proposals on Upwork?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_connects_and_bidding", ids)

    def test_upwork_payment_query_hits_payment_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="What should I know about Upwork fees, billing cycles, and withdrawal timing?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_payments_fees_and_withdrawal", ids)


if __name__ == "__main__":
    unittest.main()

