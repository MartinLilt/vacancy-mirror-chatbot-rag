# Knowledge Sections — Index

Source: `services/assistant/knowledge.py` → `DEFAULT_KNOWLEDGE_SECTIONS`  
Total: 40 sections

## Product

| section_id | Title |
|------------|-------|
| `assistant_info` | Assistant Information |
| `benefits` | Benefits |
| `plans_subs` | Plans and Subscriptions |
| `policy` | Policy |
| `assistant_rules` | Assistant Rules |
| `features_coming_soon` | Features (Coming Soon) |

## Upwork Platform — General

| section_id | Title |
|------------|-------|
| `upwork_terms_rules` | Upwork Terms and Rules Overview |
| `upwork_news_updates` | Upwork News and Updates Signals |
| `upwork_account_setup_verification_tax` | Account Setup, Verification, and Tax Basics |
| `upwork_trust_safety_and_scams` | Trust, Safety, and Scam Prevention |
| `upwork_payments_fees_and_withdrawal` | Payments, Fees, and Withdrawal |
| `upwork_academy_learning_path` | Upwork Academy and Learning Path |

## Profile & Proposals

| section_id | Title |
|------------|-------|
| `upwork_profile_growth` | Profile and Proposal Growth Guidance |
| `upwork_connects_and_bidding` | Connects and Bidding Basics |
| `upwork_proposals_best_practices` | Proposals Best Practices |
| `upwork_job_search_and_fit` | Job Search and Opportunity Fit |
| `upwork_no_replies_to_proposals` | No Replies to Proposals |
| `upwork_low_interview_rate` | Low Interview Rate |
| `upwork_search_ranking_profile_visibility` | Search Ranking and Profile Visibility Signals |
| `upwork_availability_response_time_and_invites` | Availability, Response Time, and Invites |

## Contracts & Delivery

| section_id | Title |
|------------|-------|
| `upwork_contracts_and_milestones` | Contracts and Milestones |
| `upwork_hourly_protection_and_time_tracking` | Hourly Protection and Time Tracking |
| `upwork_disputes_refunds_and_resolution` | Disputes, Refunds, and Resolution |
| `upwork_scope_creep_handling` | Scope Creep Handling |
| `upwork_large_contract_delivery_governance` | Large Contract Delivery Governance |
| `upwork_stakeholder_alignment_reporting` | Stakeholder Alignment and Reporting |
| `upwork_project_handoff_and_offboarding` | Project Handoff and Offboarding |
| `upwork_risk_register_and_change_control` | Risk Register and Change Control |
| `upwork_team_collaboration_and_qc` | Team Collaboration and Quality Control |
| `upwork_procurement_and_vendor_readiness` | Procurement and Vendor Readiness |

## Clients & Pricing

| section_id | Title |
|------------|-------|
| `upwork_client_communication_and_expectations` | Client Communication and Expectation Management |
| `upwork_interviews_and_discovery_calls` | Interviews and Discovery Calls |
| `upwork_pricing_rate_cards_and_estimation` | Pricing, Rate Cards, and Estimation |
| `upwork_rate_negotiation_playbook` | Rate Negotiation Playbook |
| `upwork_low_quality_clients_filtering` | Low-Quality Clients Filtering |
| `upwork_repeat_clients_strategy` | Repeat Clients Strategy |

## Career & Performance

| section_id | Title |
|------------|-------|
| `upwork_job_success_and_badges` | Job Success and Badges |
| `upwork_jss_drop_recovery` | JSS Drop Recovery |
| `upwork_connects_burn_rate_control` | Connects Burn Rate Control |
| `upwork_agency_vs_independent_freelancer` | Agency vs Independent Freelancer |

## Retrieval Logic

`AssistantSectionRetriever.retrieve(query, top_k=4)` uses **weighted lexical scoring**:
- ID/title token match → ×9
- Fuzzy ID/title prefix match → ×6
- Content token match → ×1
- Fuzzy content prefix match → ×1

Fallback (when score=0 for all sections): returns 9 core sections (assistant_info, policy, plans_subs, upwork_terms_rules, upwork_academy_learning_path, upwork_profile_growth, upwork_trust_safety_and_scams, upwork_payments_fees_and_withdrawal, upwork_account_setup_verification_tax).