# Podcast Production Backlog

## Published from this backlog
- ep127 — Istanbul Real Estate: Renovation Costs and ROI for Turkish CBI
- ep126 — Closing Claude Code's Feedback Loop — Self-Checking Before Handoff
- ep125 — A Day in the Life of Alex in AnCapville
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

1. 🤖 **Beyond the Basics with Claude Code: Systems That Prompt Themselves**
   - Source: https://x.com/i/status/2061821319034143172
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Khairallah AL-Awady (Anthropic engineer) breaks down the advanced Claude Code workflow: "You're not supposed to prompt Claude. You're supposed to build a system that prompts itself." Covers the mistake most users make (direct prompting vs building agentic workflows) and the performance cost of getting it wrong. Connects to ep111 (build a system that prompts itself), ep115 (session management), and the new verification pipeline — the system checks itself before you see it. Señora Freedom angle: when the agent grades its own homework, who controls the rubric?

2. 🤖 **Boris Cherny: Why Most People Aren't Getting Real Results from Claude Code**
   - Category: AI
   - Source: https://x.com/i/status/2062184732075741349
   - Type: URL-based
   - Flags: `--long` (~10 min)
   - Notes: Boris Cherny is the creator of Claude Code at Anthropic. In this interview he explains exactly how most people never actually set up Claude properly. Must hit his key points as a near-bullet list: (1) the 14% of context window you lose to CLAUDE.md before typing a word — understand the cost and design for it, (2) the memory system that eliminates repeating yourself every conversation, (3) the custom instructions most users leave completely blank, (4) the project settings that give Claude permanent context about your work. Cherny argues that anyone using Claude for more than a month without leaving the chat window has at least 30 untouched features. This is Boris Cherny — recognise his role as the creator/architect of Claude Code. Connects to ep115 (session management), ep111 (systems that prompt themselves), ep100 (dynamic workflows). Señora Freedom angle: the tool is free — the setup tax is attention, and most people won't pay it.

3. 🤖 **Anthropic's Own Data Stack: 95% Self-Service Analytics with Claude**
   - Category: AI
   - Source: https://claude.com/blog/how-anthropic-enables-self-service-data-analytics-with-claude
   - Type: URL-based
   - Flags: `--long` (~10 min)
   - Notes: Anthropic's Data Science team published (Jun 3, 2026) how they achieve 95% accuracy automating business analytics via Claude. Key insight: analytics accuracy is a context and verification problem, not a code generation issue. Three failure modes: (1) concept↔entity ambiguity — agent can't pick the right field from millions of candidates, (2) data staleness — schemas change constantly, (3) retrieval failure — the answer exists but the agent can't find it. Their stack: canonical datasets (one governed answer per concept), semantic layer as mandatory first path, skills (markdown the agent reads on demand — without skills accuracy was 21%, with skills 95%+), adversarial review sub-agents (+6% accuracy at 32% more tokens), offline evals pinned to snapshot dates. Best quote: "the information was there, the agent saw it, and it still didn't use it" — their bottleneck wasn't access, it was structure. Connects to ep116 (zero trust), ep111 (systems that prompt themselves). Señora Freedom angle: when the company dogfooding the AI says the hard part is documentation, not intelligence — what does that mean for everyone else?

4. 🎥 **From Longevity to Curing Autoimmune Disease — The Future Is Bright**
   - Category: Video
   - Source: https://www.instagram.com/reels/DZGTYHPJhgZ/
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Instagram reel from @themaxdose covering the frontier of longevity/aging research and autoimmune disease cures. Cited research in the comments. Health and longevity science angle for the podcast.

5. 🤖 **James Brady: Every Agent in Production Lies**
   - Category: AI
   - Source: https://x.com/0x_rody/status/2063318596202242171/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Anthropic engineer James Brady's 29-minute talk on agent verification. Key quote: "Every agent in production lies. We measured it. The good ones lie less, the great ones catch the lie before the user does." Walks through the verification stack he built and the patterns the Claude Code team adopted. Connects to ep126 (closing the feedback loop), ep111 (systems that prompt themselves), ep115 (session management). Señora Freedom angle: if every agent lies, the question isn't trust — it's how fast you catch it.

6. 🤖 **Boris Cherny: Loops, Routines, and Dynamic Workflows**
   - Category: AI
   - Source: https://x.com/0xMovez/status/2062970118033023115/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Boris Cherny (creator of Claude Code) reveals his real daily setup in a 24-minute clip. Key quote: "I don't prompt Claude anymore. What I mostly use now is loops. I create loops — they do the rest of my job." Covers Claude + loops + routines + dynamic workflows. Overlaps with item #2 (Boris Cherny setup tips) — produce whichever has more novel content. Connects to ep115 (session management), ep111 (systems that prompt themselves), ep100 (dynamic workflows). Señora Freedom angle: the tool is free — the setup tax is attention, and most people won't pay it.

7. 🏛️ **Bezrukov at SPIEF: "Accept That War Is the New Normal"**
   - Category: Libertarian
   - Source: https://x.com/STANISKRAPIVNIK/status/2062549390909170079
   - Type: URL-based
   - Flags: `--long` (~10 min)
   - Notes: Stanislav Krapivnik shares key theses from Andrey Bezrukov (former SVR intelligence officer, exposed as Russian illegal "Donald Heathfield" in 2010) speaking at St. Petersburg International Economic Forum (Jun 2026, 77K views). Bezrukov argues: (1) Russia is in a "new type of war" — attrition and subversion targeting leaders, infrastructure, scientists, not territory, (2) West pursuing "boiling frog" strategy to avoid nuclear clash while gradually escalating, (3) "We're on the first hill of world war" — next major clash likely in Asia, (4) enemy aims to neutralise Russian nuclear forces via space-based systems or agent-planted strikes like "Operation Spider Web", (5) biowar threat from labs around Russia's borders, (6) economy must serve both development and defence for "a couple of decades", (7) "Stop being good — too many red lines remain on paper." **Fact-check thoroughly**: verify Bezrukov's identity and background (SVR colonel, arrested in US 2010 as part of Illegals Program, deported in spy swap), verify SPIEF 2026 context, cross-reference claims about "Operation Spider Web" and biolab allegations against known sources. Connects to ep90 (Liberland meritocracy), ep97 (Liberland para-state). Señora Freedom angle: when both sides claim existential threat, who pays the price?

8. 💰 **The AI Bubble Explained**
   - Category: Finance
   - Source: https://x.com/FinanceLancelot/status/2063408394111783353/video/1
   - Type: URL-based
   - Flags: `--long` (~10 min)
   - Extra prompt: mirror all points in fine detail
   - Notes: FinanceLancelot shares what he calls "the best explanation of the AI bubble I've ever heard" — a video from @atmoio covering the insanity of AI hype and bubble dynamics. **Extra prompt**: mirror all points in fine detail — ensure the narration reproduces every argument and data point from the source. Connects to the broader AI investment narrative, Silicon Valley spending, and the question of whether AI delivers on its promises. Señora Freedom angle: when trillions flow into a narrative, who profits and who pays?
