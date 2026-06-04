# Podcast Production Backlog

## Published from this backlog
- ep90 — Liberland's Direct Meritocracy: How Vit Jedlicka Designed a New Nation
- ep93 — Setting Up Shop in the Caucasus: Georgia Corporate Structures for Nomads
- ep97 — Liberland: From Micronation to Para-State
- ep99 — Your AI Agent Dies the Second You Close the Terminal
- ep100 — Claude Code Dynamic Workflows: Opus 4.8 Changes Everything
- ep101 — GBrain: Garry Tan's AI Knowledge System
- ep102 — Liberland, AI and Global Government
- ep103 — The Unreasonable Effectiveness of HTML for AI Agents
- ep104 — Uganda Real Estate Investment for Foreigners
- ep105 — Robinhood Is Now Open to Agents
- ep107 — The History of Taxation: From Ancient Tribute to Modern Certainty
- ep108 — Karpathy's LLM Wiki: Build Your Own Knowledge Base
- ep110 — Robinhood Is Now Open to Agents (evidence-first pipeline)
- ep111 — Build a System That Prompts Itself
- ep112 — Boris Cyrulnik on Civilization, Resilience, and Child Development
- ep113 — The AI Layoff Trap: When Rational Automation Destroys Its Own Market
- ep114 — AI Made Us Faster. That Was the Problem
- ep115 — Claude Code Session Management: A Clean Context Beats a Long Context
- ep116 — Zero Trust for AI Agents — Anthropic Security Framework
- ep117 — OpenHands — Open Source AI Software Engineer
- ep118 — Liberland 2026 Master Plan
- ep121 — Karpathy: 90% of What AI Twitter Tells You to Learn Will Be Dead in 6 Months
- ep123 — Izmir Neighborhood Guide: Where to Actually Buy

## Pending Episodes (alternating subjects)

Categories: 🤖 AI · 🏠 Nomad · 🏛️ Libertarian · 💰 Finance · 🎥 Video
Liberland episodes spaced with 4 non-Liberland between each.

1. 🤖 **Closing Claude Code's Feedback Loop — Self-Checking Before Handoff**
   - Category: AI
   - Source: https://x.com/i/status/2061900434722496604
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: ClaudeDevs (Anthropic's Claude Code account) demo on getting Claude Code to check its own work before handing it back — encoding your manual review checks so Claude closes its own feedback loop (self-verification, automated QA gates). Connects to ep111 (build a system that prompts itself), ep115 (session management), and the evidence-first pipeline's own QA loop. Señora Freedom angle: if the agent grades its own homework, who sets the rubric?

2. 🏠 **Istanbul Real Estate: Renovation Costs and ROI for Turkish CBI**
   - Source: https://www.youtube.com/watch?v=N-qCy1CCcpY
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Investment analysis for Istanbul real estate targeting Turkish citizenship-by-investment (CBI). Covers renovation costs, ROI calculations, and practical considerations. **Format note: should be generalized advice (first-person or dialogue), not a case study of one specific property.**

3. 🤖 **Beyond the Basics with Claude Code: Systems That Prompt Themselves**
   - Source: https://x.com/i/status/2061821319034143172
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Khairallah AL-Awady (Anthropic engineer) breaks down the advanced Claude Code workflow: "You're not supposed to prompt Claude. You're supposed to build a system that prompts itself." Covers the mistake most users make (direct prompting vs building agentic workflows) and the performance cost of getting it wrong. Connects to ep111 (build a system that prompts itself), ep115 (session management), and the new verification pipeline — the system checks itself before you see it. Señora Freedom angle: when the agent grades its own homework, who controls the rubric?

4. 🤖 **Boris Cherny: Why Most People Aren't Getting Real Results from Claude Code**
   - Category: AI
   - Source: https://x.com/i/status/2062184732075741349
   - Type: URL-based
   - Flags: `--long` (~10 min)
   - Notes: Boris Cherny is the creator of Claude Code at Anthropic. In this interview he explains exactly how most people never actually set up Claude properly. Must hit his key points as a near-bullet list: (1) the 14% of context window you lose to CLAUDE.md before typing a word — understand the cost and design for it, (2) the memory system that eliminates repeating yourself every conversation, (3) the custom instructions most users leave completely blank, (4) the project settings that give Claude permanent context about your work. Cherny argues that anyone using Claude for more than a month without leaving the chat window has at least 30 untouched features. This is Boris Cherny — recognise his role as the creator/architect of Claude Code. Connects to ep115 (session management), ep111 (systems that prompt themselves), ep100 (dynamic workflows). Señora Freedom angle: the tool is free — the setup tax is attention, and most people won't pay it.

5. 🤖 **Anthropic's Own Data Stack: 95% Self-Service Analytics with Claude**
   - Category: AI
   - Source: https://claude.com/blog/how-anthropic-enables-self-service-data-analytics-with-claude
   - Type: URL-based
   - Flags: `--long` (~10 min)
   - Notes: Anthropic's Data Science team published (Jun 3, 2026) how they achieve 95% accuracy automating business analytics via Claude. Key insight: analytics accuracy is a context and verification problem, not a code generation issue. Three failure modes: (1) concept↔entity ambiguity — agent can't pick the right field from millions of candidates, (2) data staleness — schemas change constantly, (3) retrieval failure — the answer exists but the agent can't find it. Their stack: canonical datasets (one governed answer per concept), semantic layer as mandatory first path, skills (markdown the agent reads on demand — without skills accuracy was 21%, with skills 95%+), adversarial review sub-agents (+6% accuracy at 32% more tokens), offline evals pinned to snapshot dates. Best quote: "the information was there, the agent saw it, and it still didn't use it" — their bottleneck wasn't access, it was structure. Connects to ep116 (zero trust), ep111 (systems that prompt themselves). Señora Freedom angle: when the company dogfooding the AI says the hard part is documentation, not intelligence — what does that mean for everyone else?
