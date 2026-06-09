# How Anthropic Enables Self-Service Data Analytics with Claude

**Source:** https://claude.com/blog/how-anthropic-enables-self-service-data-analytics-with-claude
**Published:** June 3, 2026
**Authors:** Chen Chang, Clement Peng, Justin Leder, Johanne Jiao, Josh Cherry (Anthropic Data Science & Data Engineering)

---

## Core Thesis

Analytics accuracy is a context and verification problem, not a code generation issue. The central challenge is mapping a user's natural-language question to the correct entity in a data model — if you solve that, the SQL becomes trivial. At Anthropic, 95% of business analytics queries are automated via Claude with approximately 95% accuracy in aggregate, freeing the data science team for strategic work like causal modeling, forecasting, and machine learning.

## Why Data Is Not Software

Coding agents thrive in an open-ended solution space where creativity is rewarded and tests provide natural guardrails. Analytics is the opposite: there is usually one correct answer from one correct source, and no deterministic way to prove correctness. The end user of the data model is no longer a data expert but an agent acting on behalf of someone who cannot validate the underlying correctness. This fundamental shift changes where the engineering effort must go — not into better SQL generation, but into better context and structure.

## Three Failure Modes

Anthropic identified three attributes that account for an overwhelming majority of inaccurate responses:

1. **Concept-entity ambiguity:** With hundreds of viable options in a data model (out of potentially millions of fields), the agent cannot choose the correct fields. Example: measuring "active users" — what actions constitute activity? Include fraudulent users? What lookback window?

2. **Data staleness:** Data sources, business definitions, and schemas change constantly. Assets and agent knowledge go stale and start returning subtly wrong answers.

3. **Retrieval failure:** The right information exists in the data model and is properly annotated, but given the vastness of the search space, the agent simply does not find it.

## The Agentic Analytics Stack

Each layer of the stack addresses one or more of these failure modes:

### Data Foundations

The most important layer. If "revenue" resolves to one governed dataset instead of forty plausible candidates, the ambiguity problem largely disappears before the agent ever has to search. Key practices:

- **Create canonical datasets:** Fewer, more heavily governed logical models. Curate a small set of canonical, single source-of-truth datasets that are clearly owned, consumption-ready, and discoverable. Aggressively deprecate near-duplicates.
- **Enforce standards:** Governance must be enforced by tooling (the agent is structurally routed to canonical models first), by CI (changes that bypass them fail review), and by mandate.
- **Colocate artifacts:** Nearly all data code lives in a single repo with CI checks that protect cross-layer integrity. If a modeling change would break a downstream dashboard or invalidate a documented metric, CI flags it.
- **Treat metadata as a first-class product:** Column and table descriptions, canonical metric definitions, grain documentation, valid value ranges, lineage, ownership, and model tiering must be maintained with the same rigor as transformations.

### Sources of Truth

Reference surfaces the agent consults to navigate the data warehouse, in descending order of trust:

1. **Semantic layer:** Compiled metric and dimension definitions. If a question maps cleanly to a defined metric, the agent calls a function and gets one number — the same number every other surface produces. Agents are structurally required to leverage the semantic layer first. Auto-generating metric definitions with LLMs was tried and was net-negative — it encoded the very ambiguities they were trying to eliminate. Recommendation: generate documentation with Claude, but have humans own the definitions.

2. **Lineage and transformation graph:** When the semantic layer does not cover a question, lineage and table ranking let the agent reason about which upstream models feed a concept, which are deprecated, and which share grain.

3. **Query corpus:** Historical SQL from dashboards, notebooks, and prior analyses. In practice, giving the agent raw retrieval access to thousands of prior queries moved accuracy by less than a point. The information was there, the agent saw it, and it still did not use it. What works is distilling that corpus into structured per-domain reference docs and reusable analysis patterns.

4. **Business context:** The layer most teams skip. An agent that does not understand the business will answer what the user asked, but not what they meant. Anthropic pipes in a company knowledge graph of indexed docs, roadmaps, decision logs, and organizational structure.

### Skills

Without skills, Claude's ability to answer analytics questions accurately did not exceed 21% on evals. Adding skills gets numbers consistently above 95% in aggregate and regularly around 99% in certain domains.

In Claude Code, a skill is a folder of markdown the agent reads on demand. Key patterns:

- **Pairwise skills:** A knowledge skill acts as a thin top-level router (try semantic layer first, then load domain-specific reference files). An analyst skill encodes the process a senior analyst would follow: clarify the question, find sources, run the query, loop through adversarial review sub-agents.
- **Proper reference docs:** Written for retrieval by an LLM. Describe tables (grain, scope, exclusions), gotchas, and explicit routing triggers without prescriptive recipes that go stale.
- **Skill maintenance as first-class citizen:** Skill docs describe a data model that changes daily. Without active maintenance they are wrong within weeks. Offline accuracy drifted from ~95% at launch to ~65% over a month before they treated this as an engineering problem. Solution: colocate skill markdown in the same repo as transformation models; a code-review hook flags any reporting-model change that does not touch a skill file. Roughly 90% of data-model PRs now include a skill change.
- **Consistent experience across surfaces:** The same skill provides the same answer in Slack, IDE, dashboard tool, and standalone agent sessions.

### Validation

**Offline evaluations:** Question/answer pairs, auto-generated by Claude then human-validated. Dashboard-based evals cover common stakeholder questions; long-tail evals are generated by feeding Claude business context. Every correction from a stakeholder becomes a candidate eval. Best practices: pin evals to snapshot dates, store results in warehouse tables with full metadata, gate launches per domain (domain owner cannot announce agent until eval slice clears ~90%).

**Ablation techniques:** Every structural decision is tested by holding the offline eval set fixed and varying exactly one component. The most useful ablation was a negative result: giving the agent direct grep access to thousands of prior SQL files. The agent read them, the answers were in there 80% of the time, but accuracy did not improve. "The information was there, the agent saw it, and it still didn't use it." This revealed the bottleneck was not access but structure — mapping a question to the right entity.

**Online validation:**
- **Adversarial review:** A Claude skill that aggressively challenges all underlying assumptions on a potential final answer. Increased accuracy by 6% but at 32% more tokens and 72% higher latency.
- **Provenance footer:** Every response carries source tier, data freshness, and model owner. Does not make the answer more correct but helps the consumer judge trustworthiness.
- **Data quality checks:** Ensure referenced fields are up-to-date, complete, and have no anomalies.
- **Passive monitoring:** Track share of queries resolving through semantic layer and share of responses with correction language.
- **Active correction harvesting:** A scheduled agent scans stakeholder channels for corrections, drafts fixes to reference docs, and opens PRs tagged to domain owners.

The failure mode none of this fully catches is the silent one: the answer is wrong but looks plausible and is used without objection. Mitigations are provenance footers, explicit human sign-off on leadership-bound answers, and standing evals for top KPIs.

## Getting Started

If starting from zero: a handful of canonical datasets, a few dozen offline evals, and a thin knowledge skill will capture most of the upside. Everything else in the post is what they added once those basics were built.

Key decision factors: how important is correctness today vs. future (models improve rapidly), how complex will the business become, how technical is the audience, how much spend for improved accuracy, and comfort around access controls and data privacy.

## Standout Quotes

- "The information was there, the agent saw it, and it still didn't use it."
- "Analytics accuracy is a context and verification problem, not a code generation issue."
- "Without skills, Claude's ability to answer analytics questions accurately didn't exceed 21% on our evals. Adding skills gets these numbers consistently above 95%."
- "We watched our offline accuracy drift from ~95% at launch to ~65% over a month before we treated this as an engineering problem."
