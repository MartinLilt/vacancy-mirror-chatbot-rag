net, """Assistant knowledge sections and deterministic section retrieval."""

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
            "Upwork Legal Center publishes core documents such as Terms of Service, User Agreement, Terms of Use, and payment-related terms. "
            "Freelancers should review rules on platform communication, payments, and acceptable use before starting client work. "
            "Some policy wording changes over time, so users should verify the current legal text on official Upwork pages before decisions. "
            "Assistant should provide high-level guidance only and avoid presenting legal interpretation as binding advice."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_news_updates",
        title="Upwork News and Updates Signals",
        content=(
            "Upwork updates are commonly published through official resources pages, product announcements, and Help Center updates. "
            "When summarizing news, assistant should mark items as signals and mention uncertainty if publish date or rollout scope is unclear. "
            "Freelancers should confirm whether an update affects their account type, region, or contract model before acting. "
            "Assistant should recommend checking the latest official post link for final confirmation."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_profile_growth",
        title="Upwork Profile and Proposal Growth Guidance",
        content=(
            "Profile growth starts with clear niche positioning, a specific title, and an overview focused on client outcomes. "
            "Strong profiles use proof-based portfolio items with context, result, and relevance to the target project type. "
            "Proposal quality improves when the first lines address the client brief directly and show matching experience. "
            "Assistant should guide users toward repeatable weekly improvements instead of one-time profile edits."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_connects_and_bidding",
        title="Upwork Connects and Bidding Basics",
        content=(
            "Upwork uses Connects for proposal actions, so bidding strategy should be treated as a limited budget problem. "
            "Freelancers should prioritize high-fit jobs with realistic budgets, clear scope, and relevant required skills. "
            "Boosting visibility can help in competitive niches, but it should be used selectively where conversion odds are strong. "
            "Assistant should recommend tracking connects spent per interview and per hire to improve bidding efficiency."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_proposals_best_practices",
        title="Upwork Proposals Best Practices",
        content=(
            "Effective proposals start with a short diagnosis of the client problem and a concrete plan for first steps. "
            "High-converting proposals include relevant proof of results, not generic skill lists or broad claims. "
            "A clear structure with scope, timeline, deliverables, and next action improves trust and reply rates. "
            "Copy-paste templates can be used as internal drafts, but final text should always be tailored to the specific brief."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_job_search_and_fit",
        title="Upwork Job Search and Opportunity Fit",
        content=(
            "Job search quality improves when freelancers filter by niche relevance, budget realism, and complexity they can deliver well. "
            "Client signals such as payment verification, hiring history, and clarity of brief help estimate project quality. "
            "Applying to fewer but better-fit jobs usually outperforms mass application strategies over time. "
            "Assistant should encourage a fit checklist before sending proposals to reduce wasted Connects."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_contracts_and_milestones",
        title="Upwork Contracts and Milestones",
        content=(
            "Upwork work structures usually include hourly contracts or fixed-price milestones with defined outputs. "
            "Before starting, freelancers should align on scope boundaries, acceptance criteria, and change-request process. "
            "Milestones should be specific enough to avoid ambiguity about what is delivered and when payment is expected. "
            "Assistant should recommend documenting key decisions in writing to reduce dispute risk later."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_payments_fees_and_withdrawal",
        title="Upwork Payments, Fees, and Withdrawal",
        content=(
            "Freelancers should understand billing cycles, processing timelines, and withdrawal options available in their country. "
            "Net income planning should include platform fees, transfer fees, and currency conversion impact where relevant. "
            "Before accepting a project, users should estimate take-home pay after all costs, not only gross contract amount. "
            "Assistant should guide users to validate final payout details in official account billing and payment settings."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_job_success_and_badges",
        title="Upwork Job Success and Badges",
        content=(
            "Job Success and credibility signals improve when freelancers deliver reliably and manage expectations early. "
            "Consistent communication, on-time delivery, and quality outcomes are stronger long-term drivers than one-off wins. "
            "Badges and profile trust signals are usually outcomes of sustained performance, not isolated tactics. "
            "Assistant should emphasize controllable habits and repeatable client success processes."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_trust_safety_and_scams",
        title="Upwork Trust, Safety, and Scam Prevention",
        content=(
            "Freelancers should avoid off-platform payment requests, suspicious urgency, and identity-sensitive requests outside normal workflow. "
            "Work terms, communication, and payment handling should remain inside approved Upwork processes whenever possible. "
            "Red flags include unrealistic promises, pressure to move fast without scope clarity, and requests to bypass platform safeguards. "
            "Assistant should advise documenting evidence and using official reporting channels for suspicious behavior."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_academy_learning_path",
        title="Upwork Academy and Learning Path",
        content=(
            "Upwork public learning materials often focus on profile setup, proposal quality, client communication, and delivery process. "
            "A practical growth path is niche definition, profile optimization, portfolio proof, and proposal conversion tracking. "
            "Freelancers should apply one improvement per week and measure effects on replies, interviews, and hires. "
            "Assistant should convert learning topics into clear weekly action plans instead of generic theory."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_account_setup_verification_tax",
        title="Upwork Account Setup, Verification, and Tax Basics",
        content=(
            "Onboarding usually includes account configuration, profile completion, payout setup, and identity verification steps. "
            "Tax form requirements vary by jurisdiction and account type, so users should follow current in-account instructions. "
            "Verification checks may require updated documents, and processing timelines can differ by region. "
            "Assistant should provide preparation guidance while directing final compliance decisions to official Upwork flows."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_interviews_and_discovery_calls",
        title="Upwork Interviews and Discovery Calls",
        content=(
            "Interview quality improves when freelancers clarify scope, timeline, budget limits, and decision criteria early. "
            "Discovery calls should focus on business outcome, current blockers, and clear definition of done. "
            "After calls, a short written recap reduces misalignment and increases close probability. "
            "Assistant should coach users to ask decisive questions instead of generic qualification scripts."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_pricing_rate_cards_and_estimation",
        title="Upwork Pricing, Rate Cards, and Estimation",
        content=(
            "Pricing should account for complexity, uncertainty, communication overhead, and revision risk. "
            "Fixed-price estimates are stronger when each milestone has explicit deliverables and acceptance criteria. "
            "Hourly offers should define expected weekly capacity, response windows, and what tasks are in scope. "
            "Assistant should help users build simple rate cards to keep pricing consistent across similar project types."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_client_communication_and_expectations",
        title="Upwork Client Communication and Expectation Management",
        content=(
            "Client trust grows with predictable communication cadence and clear status updates. "
            "Kickoff alignment should confirm priorities, constraints, and escalation path before implementation starts. "
            "When scope changes, written summaries and tradeoff options prevent confusion and hidden expectation drift. "
            "Assistant should promote concise, decision-ready communication rather than long status text."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_hourly_protection_and_time_tracking",
        title="Upwork Hourly Protection and Time Tracking",
        content=(
            "Hourly contracts require disciplined tracking with accurate notes and activity aligned to agreed tasks. "
            "Work logs should be clear enough for a client to understand value delivered during each interval. "
            "Freelancers should review tracker habits regularly to avoid gaps that reduce payment confidence. "
            "Assistant should point users to official Upwork tracker and payment-protection guidance for final rules."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_disputes_refunds_and_resolution",
        title="Upwork Disputes, Refunds, and Resolution",
        content=(
            "When conflicts appear, freelancers should first document scope history, delivered artifacts, approvals, and timeline changes. "
            "Most cases benefit from calm de-escalation and a written proposal for resolution before formal escalation. "
            "If needed, users should follow official Upwork dispute and refund channels with complete evidence. "
            "Assistant should avoid legal claims and focus on structured, evidence-based resolution steps."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_availability_response_time_and_invites",
        title="Upwork Availability, Response Time, and Invites",
        content=(
            "Availability settings should reflect real capacity so clients receive accurate expectations from the start. "
            "Fast, clear replies often improve invite conversion when matched with relevant expertise. "
            "Response quality matters as much as speed: users should answer scope and outcome questions directly. "
            "Assistant should help users design a repeatable reply framework for invites and inbound messages."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_agency_vs_independent_freelancer",
        title="Upwork Agency vs Independent Freelancer",
        content=(
            "Independent freelancers usually optimize for personal positioning, direct client trust, and focused niche specialization. "
            "Agency models can scale delivery through team roles, but add coordination overhead and quality-control complexity. "
            "The right model depends on lead volume, project size, collaboration needs, and operational maturity. "
            "Assistant should compare tradeoffs clearly instead of assuming one model fits all users."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_search_ranking_profile_visibility",
        title="Upwork Search Ranking and Profile Visibility Signals",
        content=(
            "Profile visibility tends to improve when niche relevance, skill alignment, and proof quality are consistently strong. "
            "Freelancers should optimize for client fit and outcomes, not keyword stuffing or speculative ranking hacks. "
            "Stable delivery quality and strong client feedback usually support long-term discoverability better than short-term tricks. "
            "Assistant should avoid secret-formula claims and focus on controllable profile and proposal fundamentals."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_no_replies_to_proposals",
        title="Upwork No Replies to Proposals",
        content=(
            "When proposals get no replies, the fastest fix is improving the first two lines to mirror client goals and constraints. "
            "Freelancers should cut generic introductions and replace them with proof tied to similar project outcomes. "
            "Low-reply streaks often indicate weak fit targeting, so narrowing job filters and sending fewer high-fit proposals helps. "
            "Assistant should suggest testing proposal variants weekly and tracking reply rate by niche and budget range."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_low_interview_rate",
        title="Upwork Low Interview Rate",
        content=(
            "Low interview rate usually means the proposal does not create enough confidence for a next-step conversation. "
            "Freelancers should add a short discovery plan, specific questions, and a concrete first deliverable to reduce buyer risk. "
            "Interview conversion improves when portfolio proof is directly mapped to the posted requirements, not shown broadly. "
            "Assistant should coach users to measure interview rate separately from reply rate to identify the true bottleneck."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_jss_drop_recovery",
        title="Upwork JSS Drop Recovery",
        content=(
            "If Job Success Score drops, recovery starts with delivery consistency, clear expectation setting, and proactive communication. "
            "Freelancers should prioritize projects with clean scope and strong fit to reduce additional negative outcomes. "
            "Short-term recovery plans should focus on quality completions and reliable client experience rather than volume. "
            "Assistant should avoid score manipulation advice and focus on sustainable performance habits."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_scope_creep_handling",
        title="Upwork Scope Creep Handling",
        content=(
            "Scope creep is easier to prevent when milestones include explicit deliverables, exclusions, and revision limits. "
            "When new requests appear, freelancers should acknowledge value, estimate impact, and propose change options in writing. "
            "A neutral change-request format helps keep relationships healthy while protecting delivery capacity and timelines. "
            "Assistant should guide users to document all accepted scope updates before execution."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_rate_negotiation_playbook",
        title="Upwork Rate Negotiation Playbook",
        content=(
            "Rate negotiation works better when freelancers negotiate around outcomes, risk reduction, and speed-to-value instead of hourly arguments alone. "
            "Users should prepare floor rate, target rate, and concession boundaries before negotiation starts. "
            "When budget is constrained, reducing scope or deliverables is often safer than cutting price without boundaries. "
            "Assistant should recommend respectful negotiating scripts that protect margin and long-term positioning."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_low_quality_clients_filtering",
        title="Upwork Low-Quality Clients Filtering",
        content=(
            "Client quality filtering should consider brief clarity, responsiveness, budget realism, and previous hiring behavior. "
            "Freelancers can reduce risk by asking clarifying questions before committing and by checking mismatch signals early. "
            "Consistent low-quality leads often indicate filters are too broad or niche positioning is too generic. "
            "Assistant should promote a qualification checklist to avoid costly engagements with poor-fit clients."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_repeat_clients_strategy",
        title="Upwork Repeat Clients Strategy",
        content=(
            "Repeat clients usually come from predictable delivery, proactive communication, and clear business impact reporting. "
            "Freelancers should close each project with next-step recommendations and optional follow-up packages. "
            "Retention improves when users document wins with simple metrics and provide a roadmap for future improvements. "
            "Assistant should help design low-friction follow-up systems that feel helpful instead of sales-heavy."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_connects_burn_rate_control",
        title="Upwork Connects Burn Rate Control",
        content=(
            "Connects burn rate should be managed like paid acquisition spend with explicit weekly caps and stop-loss rules. "
            "Freelancers should pause low-performing proposal patterns quickly and reallocate to high-conversion niches. "
            "Tracking connects per reply, per interview, and per hire helps identify where budget is leaking. "
            "Assistant should recommend periodic review cycles to keep bidding efficiency stable over time."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_large_contract_delivery_governance",
        title="Upwork Large Contract Delivery Governance",
        content=(
            "Large contracts need explicit governance with milestones, owners, decision points, and escalation rules. "
            "Freelancers should run short weekly review rituals focused on risks, blockers, and acceptance readiness. "
            "Scope control is stronger when every major change is tied to timeline and budget impact before approval. "
            "Assistant should recommend lightweight governance artifacts that keep delivery predictable without heavy overhead."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_stakeholder_alignment_reporting",
        title="Upwork Stakeholder Alignment and Reporting",
        content=(
            "Projects with multiple stakeholders require clear communication roles and one source of truth for status. "
            "Weekly reporting should highlight outcomes delivered, next commitments, and risks needing decisions. "
            "Freelancers should separate operational updates from strategic recommendations to avoid confusion. "
            "Assistant should help users produce concise decision-ready reports rather than long narrative updates."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_procurement_and_vendor_readiness",
        title="Upwork Procurement and Vendor Readiness",
        content=(
            "Some clients apply procurement checks before engagement, especially for larger or recurring contracts. "
            "Freelancers should prepare clear service description, security posture summary, and delivery workflow outline. "
            "A reusable readiness pack reduces delays when clients ask for process or compliance clarification. "
            "Assistant should guide users to answer procurement questions transparently without over-claiming certifications."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_risk_register_and_change_control",
        title="Upwork Risk Register and Change Control",
        content=(
            "A simple risk register helps teams track probability, impact, owner, and mitigation for delivery threats. "
            "Freelancers should review risks on a fixed cadence and trigger action before issues become deadlines misses. "
            "Change control works best with written impact notes covering scope, timeline, and cost deltas. "
            "Assistant should encourage practical risk discipline that is easy to maintain in real client work."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_team_collaboration_and_qc",
        title="Upwork Team Collaboration and Quality Control",
        content=(
            "When multiple contributors are involved, quality drops unless ownership and review gates are explicit. "
            "Freelancers should define handoff standards, testing checklist, and final acceptance preparation workflow. "
            "Internal QA before client review reduces revision loops and protects confidence in team delivery. "
            "Assistant should suggest lightweight collaboration rules that preserve speed and consistency."
        ),
    ),
    KnowledgeSection(
        section_id="upwork_project_handoff_and_offboarding",
        title="Upwork Project Handoff and Offboarding",
        content=(
            "Project closure should include deliverables audit, documentation transfer, and clear support boundaries. "
            "Freelancers should provide a handoff summary with known limitations, open items, and recommended next steps. "
            "A structured offboarding process increases client trust and improves chances of repeat work. "
            "Assistant should coach users to treat handoff as a strategic stage, not just an administrative ending."
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
            score = self._score_section(tokens=tokens, section=section)
            if score > 0:
                scored.append((score, section))

        if not scored:
            # Default to core policy/product sections when query is too vague.
            fallback_ids = {
                "assistant_info",
                "policy",
                "plans_subs",
                "upwork_terms_rules",
                "upwork_academy_learning_path",
                "upwork_profile_growth",
                "upwork_trust_safety_and_scams",
                "upwork_payments_fees_and_withdrawal",
                "upwork_account_setup_verification_tax",
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

    @staticmethod
    def _score_section(
        *,
        tokens: set[str],
        section: KnowledgeSection,
    ) -> int:
        """Weighted lexical score favoring explicit section id/title intent matches."""
        id_title_tokens = AssistantSectionRetriever._tokens(
            f"{section.section_id} {section.title}"
        )
        content_tokens = AssistantSectionRetriever._tokens(section.content)
        id_title_hits = len(tokens.intersection(id_title_tokens))
        content_hits = len(tokens.intersection(content_tokens))
        fuzzy_id_title_hits = AssistantSectionRetriever._fuzzy_hits(
            query_tokens=tokens,
            section_tokens=id_title_tokens,
        )
        fuzzy_content_hits = AssistantSectionRetriever._fuzzy_hits(
            query_tokens=tokens,
            section_tokens=content_tokens,
        )
        return (
            (id_title_hits * 9)
            + content_hits
            + (fuzzy_id_title_hits * 6)
            + fuzzy_content_hits
        )

    @staticmethod
    def _fuzzy_hits(*, query_tokens: set[str], section_tokens: set[str]) -> int:
        """Count near-matches using shared 5-char prefixes for long tokens."""
        hits = 0
        for token in query_tokens:
            if len(token) < 5:
                continue
            prefix = token[:5]
            if any(
                st.startswith(prefix) or token.startswith(st[:5])
                for st in section_tokens
                if len(st) >= 5
            ):
                hits += 1
        return hits

