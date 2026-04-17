from __future__ import annotations

import unittest

from backend.services.assistant.knowledge import (
    AssistantSectionRetriever,
    DEFAULT_KNOWLEDGE_SECTIONS,
)


class AssistantKnowledgeRetrieverTest(unittest.TestCase):
    def test_has_extended_upwork_sections(self) -> None:
        upwork_sections = [
            section for section in DEFAULT_KNOWLEDGE_SECTIONS
            if section.section_id.startswith("upwork_")
        ]
        self.assertGreaterEqual(len(upwork_sections), 34)

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

    def test_upwork_verification_query_hits_onboarding_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How do identity verification and tax forms work on Upwork?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_account_setup_verification_tax", ids)

    def test_upwork_no_replies_query_hits_no_replies_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="I send many proposals on Upwork but get no replies, how to fix it?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_no_replies_to_proposals", ids)

    def test_upwork_jss_drop_query_hits_jss_recovery_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="My JSS dropped and I need a recovery plan on Upwork",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_jss_drop_recovery", ids)

    def test_upwork_scope_creep_query_hits_scope_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="Client keeps adding tasks, how do I handle scope creep in contract?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_scope_creep_handling", ids)

    def test_upwork_negotiation_query_hits_rate_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How should I negotiate my rates with Upwork clients?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_rate_negotiation_playbook", ids)

    def test_upwork_repeat_clients_query_hits_retention_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How can I get repeat clients and retain them after project delivery?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_repeat_clients_strategy", ids)

    def test_upwork_governance_query_hits_large_contract_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How do I set delivery governance for a large Upwork contract?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_large_contract_delivery_governance", ids)

    def test_upwork_procurement_query_hits_vendor_readiness_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="Client asked vendor procurement questions before contract, what should I prepare?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_procurement_and_vendor_readiness", ids)

    def test_upwork_handoff_query_hits_offboarding_section(self) -> None:
        retriever = AssistantSectionRetriever()
        sections = retriever.retrieve(
            query="How should I do project handoff and offboarding after delivery?",
            top_k=4,
        )
        ids = [section.section_id for section in sections]
        self.assertIn("upwork_project_handoff_and_offboarding", ids)


if __name__ == "__main__":
    unittest.main()

