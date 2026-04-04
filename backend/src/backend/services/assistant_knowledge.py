"""Assistant knowledge sections and deterministic section retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeSection:
    section_id: str
    title: str
    content: str


DEFAULT_KNOWLEDGE_SECTIONS: tuple[KnowledgeSection, ...] = (
    KnowledgeSection(
        section_id="benefits",
        title="Benefits",
        content=(
            "Weekly Freelance Trends Report, "
            "AI Market Assistant, Weekly Trend Charts, Profile Optimisation Expert, "
            "Weekly Profile and Projects Agent, Extended Projects Agent, and Weekly Skills "
            "and Tags Report. Free features include trend report, assistant chat, and charts. "
            "Plus adds profile optimization and up to 5 portfolio project recommendations. "
            "Pro Plus extends portfolio coverage to up to 12 projects and adds skills and tags reporting."
        ),
    ),
    KnowledgeSection(
        section_id="assistant_rules",
        title="Assistant Rules",
        content=(
            "Assistant provides guidance and recommendations only. It does not access user accounts, "
            "does not submit proposals, does not contact clients, does not log in on user behalf, "
            "does not automate account activity, and does not take actions in Upwork or other platforms. "
            "AI insights can be incomplete or delayed, so important decisions should be verified."
        ),
    ),
    KnowledgeSection(
        section_id="plans_subs",
        title="Plans and Subscriptions",
        content=(
            "Plans are Free, Plus ($9.99 per month), and Pro Plus ($19.99 per month). "
            "Free includes 35 AI messages per day and basic weekly reports. Plus includes 60 AI messages "
            "per day and profile and portfolio guidance up to 5 projects. Pro Plus includes 120 AI messages "
            "per day and extended portfolio guidance up to 12 projects. Paid plans are billed monthly and can be cancelled anytime."
        ),
    ),
    KnowledgeSection(
        section_id="assistant_info",
        title="Assistant Information",
        content=(
            "Vacancy Mirror is an AI-powered freelance market intelligence assistant for Upwork-focused freelancers. "
            "It helps with market trend understanding, role and skill demand, niche comparison, career direction, "
            "proposal positioning, and profile improvement using public market signals."
        ),
    ),
    KnowledgeSection(
        section_id="policy",
        title="Policy",
        content=(
            "Vacancy Mirror is independent and not affiliated with Upwork, "
            "Telegram, Google, or other third-party platforms. Data sources are publicly available internet information "
            "such as public job listings and metadata. Service is read-only analytical software. It does not request "
            "passwords, cookies, or private account credentials. It may store Telegram ID, user messages, search history, "
            "preferences, reports, and technical logs to provide the service."
        ),
    ),
    KnowledgeSection(
        section_id="features_coming_soon",
        title="Features (Coming Soon)",
        content=(
            "Frontend pages currently present seven available tools and active pricing tiers. "
            "Do not promise unpublished roadmap items as available features. If a user asks about coming soon, "
            "state that roadmap may expand with additional data sources and richer reports, but no fixed delivery date is published."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_terms_rules",
        title="Upwork Terms and Rules Overview",
        content=(
            "Upwork Legal Center publishes key legal documents such as Terms of Service, User Agreement, "
            "Terms of Use, escrow instructions, fee and ACH authorization terms, and freelancer membership policy. "
            "For rules questions, assistant should summarize at a high level and advise checking the latest official "
            "legal text before acting."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_news_updates",
        title="Upwork News and Updates Signals",
        content=(
            "Public Upwork surfaces for updates include official resources pages, help center updates, and product-related "
            "announcements. Assistant should present updates as recent signals, avoid absolute claims when publication date "
            "is unclear, and suggest confirming the latest post on official Upwork pages."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_profile_growth",
        title="Upwork Profile and Proposal Growth Guidance",
        content=(
            "Upwork Help topics for freelancers emphasize creating a complete profile, writing strong title and overview, "
            "understanding Connects, sending stronger proposals, and improving job success outcomes. Assistant should focus "
            "on practical actions: clear niche positioning, evidence of outcomes, relevant portfolio, and tailored proposals."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_connects_and_bidding",
        title="Upwork Connects and Bidding Basics",
        content=(
            "Upwork uses Connects for proposal activity, including standard proposals and optional boosted visibility in "
            "competitive situations. Freelancers should manage Connects budget carefully, prioritize high-fit jobs, and "
            "avoid low-probability bidding patterns."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_proposals_best_practices",
        title="Upwork Proposals Best Practices",
        content=(
            "Strong proposals are specific to the client brief, show relevant proof of results, and clearly outline scope, "
            "approach, timeline, and next step. Generic copy-paste proposals reduce conversion and usually perform worse over time."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_job_search_and_fit",
        title="Upwork Job Search and Opportunity Fit",
        content=(
            "Freelancers should filter for relevant category, experience level, budget realism, client history, and required skills. "
            "A better fit strategy is fewer high-quality applications to suitable projects instead of many low-fit submissions."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_contracts_and_milestones",
        title="Upwork Contracts and Milestones",
        content=(
            "Work can be hourly or fixed-price with milestones. Scope clarity, milestone definitions, acceptance criteria, and "
            "documented communication are critical for healthy contracts and fewer disputes."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_payments_fees_and_withdrawal",
        title="Upwork Payments, Fees, and Withdrawal",
        content=(
            "Freelancers should understand billing cycles, platform fees, available withdrawal methods, and payout timing. "
            "Before accepting work, confirm net earnings expectations after fees and transfer costs."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_job_success_and_badges",
        title="Upwork Job Success and Badges",
        content=(
            "Long-term profile strength depends on outcomes, client satisfaction, communication quality, and reliable delivery. "
            "Signals such as Job Success Score and badges improve credibility when consistently supported by completed results."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_trust_safety_and_scams",
        title="Upwork Trust, Safety, and Scam Prevention",
        content=(
            "Freelancers should avoid off-platform payment requests, suspicious urgency, and requests that violate platform rules. "
            "Keep work and payment workflow inside approved platform processes and report suspicious behavior through official channels."
        ),
    ),
)


class AssistantSectionRetriever:
    """Simple lexical section retriever for policy/product Q&A grounding."""

    def __init__(self, sections: tuple[KnowledgeSection, ...] | None = None) -> None:
        self.sections = sections or DEFAULT_KNOWLEDGE_SECTIONS

    def retrieve(self, *, query: str, top_k: int = 4) -> list[KnowledgeSection]:
        tokens = self._tokens(query)
        scored: list[tuple[int, KnowledgeSection]] = []
        for section in self.sections:
            haystack_tokens = self._tokens(
                f"{section.section_id} {section.title} {section.content}"
            )
            score = len(tokens.intersection(haystack_tokens))
            if score > 0:
                scored.append((score, section))

        if not scored:
            # Default to core policy/product sections when query is too vague.
            fallback_ids = {
                "assistant_info",
                "policy",
                "plans_subs",
                "upwork_terms_rules",
                "upwork_profile_growth",
                "upwork_trust_safety_and_scams",
                "upwork_payments_fees_and_withdrawal",
            }
            return [s for s in self.sections if s.section_id in fallback_ids][:top_k]

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [section for _, section in scored[:top_k]]

    @staticmethod
    def render_sections(sections: list[KnowledgeSection]) -> str:
        if not sections:
            return "(no sections found)"
        blocks = []
        for section in sections:
            blocks.append(
                f"[{section.section_id}] {section.title}\n{section.content}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9_]+", text.lower())
            if len(token) > 2
        }

