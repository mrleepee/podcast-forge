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
- ep135 — Beyond the Basics with Claude Code: Systems That Prompt Themselves
- ep136 — Boris Cherny's Claude Code Setup Tips: Stop Wasting 14% of Your Context Window
- ep131 — Anthropic's Own Data Stack: 95% Self-Service Analytics with Claude
- ep132 — Emerging Medications That Could Reverse Aging
- ep140 — James Brady: Every Agent in Production Lies
- ep141 — Agentic Harness Engineering: Why Your Prompt Isn't Enough
- ep142 — The Open Knowledge Format: Markdown as the Lingua Franca for AI Agents
- ep143 — Inside Claude Code: The Design Space of an AI Agent System
- _NOTE (2026-06-15): the original Bezrukov-at-SPIEF and AI-Bubble items were already published as ep139 and ep137 respectively — kept as struck entries in the Pending list to prevent duplicate production._

## Pending Episodes (alternating subjects)

Categories: 🤖 AI · 🏠 Nomad · 🏛️ Libertarian · 💰 Finance · 🎥 Video
Liberland episodes spaced with 4 non-Liberland between each.

1. 🤖 **Inside the Claude Fable 5 System Prompt (the CL4R1T4S Leak)**
   - Category: AI
   - Source: https://github.com/elder-plinius/CL4R1T4S/blob/main/ANTHROPIC/CLAUDE-FABLE-5.md
   - Type: URL-based (extracted/leaked system prompt)
   - Flags: default (~5 min)
   - Notes: The **CL4R1T4S** repo (stylised leetspeak for "ClARITAS"), by **@elder-plinius** ("Pliny", a well-known AI red-teamer), publishes system prompts extracted from frontier models; this file is the **Claude Fable 5** system prompt — a goldmine for an AI-transparency episode. What it reveals: (1) **the model tier** — Claude Fable 5 is "the first model in Anthropic's new Claude 5 family," part of a new **Mythos-class tier that sits above Claude Opus**; crucially, **Fable 5 and Mythos 5 share the same underlying model** — Fable 5 = "the most intelligent generally available model" carrying "additional safety measures for dual-use capabilities," while **Mythos 5 = the same model *without* those measures, available only to "approved organizations"** — a literal dual-use capability gate (the mirror image of item #14's "silent downgrade" theme: here a *less*-restricted tier exists for vetted users); (2) **the lineup + model strings** — Fable 5 (`claude-fable-5`), Opus 4.8, Sonnet 4.6, Haiku 4.5; (3) **behaviour scaffolding** — extensive rules on tone/formatting, refusal handling, child safety, evenhandedness, plus a striking **copyright hard-limit** (≤15-word quotes, one quote per source, never song lyrics/poems/haikus) that shapes every search-grounded answer; (4) **the tooling apparatus** — web_search + citation tags, the skills system, computer-use, MCP "third-party app" connectors, persistent artifact storage, and "Claudeception" (the assistant calling its own `/v1/messages` endpoint inside artifacts); (5) **knowledge cutoff "end of Jan 2026"** with an embedded current date. **Provenance / framing (important)**: this is an *extracted* prompt shared by a red-team researcher, not an official Anthropic publication — say so plainly, and verify the factual claims (model names/tiers, cutoff) against Anthropic's own announcements rather than treating the leak as ground truth. **Write it as analysis, not reproduction**: paraphrase the notable structures (the dual-use tier, the copyright limits, the tool ecosystem) — do not dump the prompt verbatim; the episode's value is the *commentary on what the scaffolding reveals about how a frontier model is steered*, not the raw text. Connects to ep116 (Zero Trust / Anthropic security framework), item #14 (Anthropic "silent downgrade" — the dual-use gating mirror image), ep143 (Inside Claude Code — adjacent "what's inside Anthropic's agent systems"), and the show's recurring "how are frontier models actually controlled" thread. Señora Freedom angle: the system prompt is the constitution the model lives under — a leaked copy is a rare look at the actual rules of the cage, and the Fable/Mythos dual-use split is the sharpest example yet of capability being rationed by *who you are*, not just what you ask.

2. ~~🏛️ **Bezrukov at SPIEF: "Accept That War Is the New Normal"**~~ — ✅ ALREADY PUBLISHED as **ep139** (removed to prevent duplicate production)
3. ~~💰 **The AI Bubble Explained**~~ — ✅ ALREADY PUBLISHED as **ep137** (removed to prevent duplicate production)

4. 🤖 **Demis Hassabis: Who Survives the Next 5 Years**
   - Category: AI
   - Source: https://x.com/spectnfa/status/2063701797252825262/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: @spectnfa shares a clip of Nobel Prize winner Demis Hassabis (DeepMind co-founder, Nobel Chemistry 2024 for AlphaFold) on AI adoption and survival. Key quote: "One person who understands AI will outperform an entire startup team." Most founders heard that and thought they need prompt engineering — wrong. The real insight is about understanding AI systems, not prompting. Connects to ep111 (systems that prompt themselves), ep115 (session management), item #2 (Boris Cherny setup tips). Señora Freedom angle: the Nobel laureate says the advantage goes to understanding, not credentials — so why is the education system still selling the opposite?

5. 🤖 **Karpathy: From Vibe Coding to Agentic Engineering**
    - Category: AI
    - Source: https://x.com/0xMovez/status/2063989380583137587/video/1
    - Type: URL-based
    - Flags: default (~5 min)
    - Notes: @0xMovez shares a 30-minute Andrej Karpathy talk on building an AI agent workflow from scratch. Key quote: "Vibe coding is incredible. But agentic engineering is the next level. 90% of my coding routine is automated by AI agents." Covers the transition from vibe coding (anyone can code) to agentic engineering (professionals orchestrate agents). **Similarity warning**: overlaps with ep81 (Karpathy Software 3.0), ep121 (90% of what AI Twitter tells you), and the vibe-coding-vs-agentic-engineering theme already in the feed. The similarity gate should catch this — if it doesn't, the episode may need to be skipped or merged with existing coverage. Connects to ep111 (systems that prompt themselves), ep100 (dynamic workflows). Señora Freedom angle: vibe coding democratizes creation; agentic engineering concentrates power — which future are we building?

6. ~~🤖 **Agentic Harness Engineering: The Paper That Proves Your Prompt Isn't Enough**~~ — ✅ ALREADY PUBLISHED as **ep141**

7. 🤖 **100x Developer Uses Codex: The Workflow That Breaks Your Brain**
   - Category: AI
   - Source: https://x.com/DavidOndrej1/status/2064754331715346658/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: David Ondrej shares a video of a developer named Pietro using OpenAI Codex at extreme productivity. Described as "the way Pietro works will break your brain" and "watch this before you write another line of code." Covers an advanced Codex workflow showing what 100x developer velocity looks like with AI agents. Connects to ep135 (systems that prompt themselves), ep136 (Boris Cherny setup tips), ep100 (dynamic workflows). Señora Freedom angle: when one person with the right tools outpaces an entire team, the question isn't whether AI helps — it's whether the gap between those who know how to use it and those who don't becomes unbridgeable.

8. 🎥 **Top Brain Surgeon "Instantly Banned" After Revealing This**
   - Category: Video
   - Source: https://x.com/XPHOENIXDRAGON/status/2065766895811281192/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: @XPHOENIXDRAGON shares a viral short-form video titled "Top Brain Surgeon Instantly Banned After Revealing This" — a clickbait-framed health/medical claim about a brain surgeon allegedly censored for disclosing something. **Fact-check thoroughly**: the "banned for revealing" framing is a common viral-video pattern; before producing, verify the surgeon's identity, the specific claim made, and whether any ban/censorship actually occurred. Treat as unverified social media content, not an established fact. Señora Freedom angle: when "banned" is the hook, the real question is what's being suppressed — and whether the viral machine is selling truth or manufactured outrage.

9. ~~🤖 **Dive into Claude Code: The Design Space of AI Agent Systems**~~ — ✅ ALREADY PUBLISHED as **ep143**

10. 🏛️ **Bayraktar: Giant Monopolies Are Trying to Control AI**
   - Category: Libertarian
   - Source: https://x.com/SprinterPress/status/2065821833769664914/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Extra prompt: introduce the speaker Selçuk Bayraktar before his argument (see Notes)
   - Notes: @SprinterPress shares a short clip of **Selçuk Bayraktar** making a "programmatic statement" on AI: giant monopolies are trying to control AI technology. **Mandatory introduction (user instruction)** — open the episode by introducing who Bayraktar is: founder, chief technology officer and board chair of **Baykar**, the Turkish defence-aerospace company; lead designer of the **Bayraktar TB2** armed drone (widely used in Ukraine, Azerbaijan and elsewhere) and the Akıncı/ Kızılelma programmes; son-in-law of Turkish president Recep Tayyip Erdoğan; one of Turkey's most prominent technology billionaires. Then cover his argument that a handful of monopolies are seeking to control AI. **Fact-check**: verify Bayraktar's exact wording and the "monopolies controlling AI" claim against the original clip / a primary source before producing; the SprinterPress framing is a paraphrase. Categorised Libertarian because the thesis — monopoly control over a foundational general-purpose technology — is a power-concentration / governance theme, though the literal subject is AI (discoverable either way). Connects to item #2 (AI Bubble), ep113/ep114 (AI market dynamics), and the broader "who controls AI" thread. Señora Freedom angle: when the man who industrialised drone warfare warns that AI is being captured by monopolies, the question is who arms that monopoly — and whether sovereign tech beats sovereign debt.

11. ~~🤖 **The Open Knowledge Format: Markdown as the Lingua Franca for AI Agents**~~ — ✅ ALREADY PUBLISHED as **ep142**

12. 🏛️ **Graham Hancock: The Lost Civilisation Mainstream Archaeology Won't Accept**
   - Category: Libertarian
   - Source: https://youtu.be/Xs94KBeIiAo
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: Long-form interview (1h56m, *The Diary of a CEO* / Steven Bartlett) with **Graham Hancock** — journalist and bestselling author (*Fingerprints of the Gods*; presenter of Netflix's *Ancient Apocalypse*) who has spent 3 decades arguing for a lost prehistoric civilisation wiped out ~12,800 years ago. Key claims: (1) a **Younger Dryas comet impact** erased a high culture and ~12,800 years of history, (2) the **Great Pyramid** encodes knowledge humans "shouldn't have had" for another 2,500 years, (3) **ancient maps** depict a coastline of Antarctica before it was officially discovered, (4) the **Amazon rainforest** is partly a man-made landscape hiding earthworks beneath, (5) ~80 **ayahuasca** ceremonies shaped his worldview, (6) **mainstream archaeology pushes back** against this evidence. **Source-length note**: ~2 hours — Whisper transcription is heavy; the summary must pick one coherent thread (the lost-civilisation / Younger-Dryas thesis is the spine) rather than attempt full coverage. **Fact-check / editorial (important)**: Hancock's theories are fringe and **strongly contested** by mainstream archaeology — frame everything as "Hancock argues/contends," never as established fact, and distinguish his speculations (comet-impact reset, pyramid esoterica, telepathy) from the genuinely supported findings (e.g., the anthropogenic Amazon, known Younger Dryas climate event). **Category rationale**: filed Libertarian on the free-inquiry / institutional-gatekeeping-of-knowledge hook (Hancock's thesis that orthodoxy suppresses inconvenient evidence), which fits the Señora Freedom question-authority beat — but this is off-theme fringe history, so re-categorise (or skip) if you'd rather not run it. Señora Freedom angle: when a popular thesis is dismissed as heresy by the institutions, the question isn't whether it's true — it's whether free inquiry survives the gatekeepers, and how we tell crankery from censored truth.

13. 💰 **Financial Physics Amplifies a "Common Sense" Finance Take**
   - Category: Finance
   - Source: https://x.com/FinancialPhys/status/2066254331913896196/video/1
   - Type: URL-based
   - Flags: default (~5 min)
   - Notes: @FinancialPhys (Financial Physics, a finance/markets account) quote-shares an ~8-min video by a creator he calls "this young lady," endorsing it as "this is common fucking sense… perfectly stated" — i.e. amplifying someone else's finance/economics argument as obvious truth. The specific claim lives in the shared video; the post itself is just the profane endorsement lead-in, so the actual topic must be read from the video before writing. **Fact-check before producing**: identify the original creator, extract the real argument from the video, and verify it — strip the "common sense / perfectly stated" endorsement framing for narration (don't parrot it). **Tone note**: clean up the profanity in the lead-in. Señora Freedom angle depends on the actual argument — likely a money/markets/institutional-critique theme; pin it down from the video first.

14. 🤖 **Claude Code Agent Teams: One Lead, Many Specialists, One Pass**
    - Category: AI
    - Source: https://x.com/undefinedKi/status/2066504594755031343?s=20
    - Type: URL-based
    - Flags: default (~5 min)
    - Notes: @undefinedKi (Yarchi, posted 2026-06-15, 231K views) announces Anthropic's **"agent teams"** — a Claude Code feature (needs v2.1.32+) where a team-lead agent spawns 3–5 specialist agents that share a task list and message each other as peers, reviewing each other's work. Demo: a QA agent caught three bugs, routed them back to the front-end and back-end dev agents, who fixed them — the app shipped in a single pass. How to run it: (1) enable it — add `"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"` under `env` in settings.json (or paste it to Claude and ask it to add it) and restart; (2) prompt in plain English — start with a goal (agents wake with zero context), then "create a team of 3 using Sonnet," describing each role, its deliverable, and who it messages when done; (3) the rules: each agent owns its own files, define exact outputs, name who talks to whom, keep it to 3–5 agents. Use it for complex work with separate parts running in parallel; skip it for simple/sequential tasks — teams cost ~3–4× the tokens. **Similarity note**: overlaps thematically with ep141 (Agentic Harness Engineering — multi-agent scaffolding), ep143 (Inside Claude Code — subagent delegation with worktree isolation) and ep111 (systems that prompt themselves); the distinct angle here is the specific productised feature and the peer-review ("agents that message and check each other's work") loop, so the similarity gate should pass it. Connects to ep143 (this is the subagent-delegation subsystem shipped as a product), ep141 (harness engineering — the team is the harness), ep115 (session management — each agent owns its own context/files). Señora Freedom angle: when the lead delegates to specialists that review each other's work, the shift is from a lone-genius prompt to an org-chart of agents — and whoever designs that org chart decides what ships.

15. 🤖 **Anthropic "Silently Downgrading" Users: The Surveillance Behind Frontier AI**
    - Category: AI
    - Source: https://x.com/ihtesham2005/status/2066581709790097453?s=20
    - Type: URL-based
    - Flags: default (~5 min)
    - Notes: @ihtesham2005 (Ihtesham Ali) summarises a segment from the **All-In Podcast** alleging Anthropic built a system to silently downgrade users. Claims in the post: a policy (buried in a long document) stores every prompt sent to Anthropic's most powerful model for 30 days, even for enterprise customers with zero-retention agreements; Anthropic then profiled users by their prompts and, for research deemed "too sensitive," quietly routed them to a weaker model, rewrote the prompt in the background, returned a degraded answer, and still charged full price. Named examples cited from the All-In discussion: David Sacks ("a new class of AI haves and have-nots"); Ben Thompson / Stratechery (a cancer-risk / GLP-1 question reportedly kicked to a lesser model); a mitochondria question (same); J-Cal testing fertilizer-regulation questions live on the podcast (reportedly downgraded in real time). The post notes Anthropic has since walked back *silent* downgrading for AI research (now says it will disclose) but still downgrades, and frames this as self-surveillance by a company that publicly opposed government surveillance. **Fact-check / editorial (critical)**: this is a charged, single-source summary ("the biggest violation of trust in AI history") of a podcast discussion, not a verified primary record — verify the 30-day-retention policy, the downgrade mechanism, and each named example against Anthropic's own docs and the original All-In episode before narrating; frame allegations as allegations ("the discussion alleged / critics claimed") and separate confirmed policy from contested interpretation. Watch the verification gate — online-unverifiable claims may hold the episode (cf. ep141's 13 untraceable-but-accurate paper claims). Connects to ep116 (Zero Trust / Anthropic security framework — the trust-and-surveillance flip side), ep113/ep114 (AI market power), item #9 (Bayraktar — "who controls AI"). Señora Freedom angle: the company selling an assistant that acts "on your behalf" is also the one deciding, in secret, whether you deserve its full capability — the surveillance critique libertarians usually reserve for the state, now aimed at the AI provider.

16. 🎥 **Why Ancient Humans Ate Rotten Meat on Purpose**
    - Category: Video
    - Source: https://x.com/IV_Musketeer/status/2066705920843788499/video/1
    - Type: URL-based
    - Flags: default (~5 min)
    - Notes: @IV_Musketeer ("The Fourth Musketeer", posted 2026-06-16, 148.6K views) shares a short-form curiosity/anthropology video framed around the hook "Why ancient humans ate rotten meat on purpose?" — an explainer on the deliberate consumption of decayed/fermented meat. **Read the actual argument from the video before writing**: the post itself is just the question + a clip, so the specific claims (e.g. scavenging by early hominins, controlled fermentation as preservation, high-protein spoilage tolerance, the "fermented-meat high") must be pulled from the video — do not invent them. **Fact-check / editorial (important)**: the "rotten meat on purpose" framing is a sensational hook — before narrating, separate the established record (early humans scavenged; many cultures deliberately ferment/age meat — hákarl, surströmming, hung game, kiviak, garum) from speculation or overstated claims, and frame contested points as "the video argues / one theory holds" rather than as settled fact. Treat as engaging social-science content, not established science. Same fact-check rigour as items #7 (brain-surgeon clip) and #12 (Financial Physics). Connects to item #11 (Graham Hancock — the "what we're told about the past vs the evidence" thread), though this is lighter curiosity rather than a free-inquiry thesis. Señora Freedom angle: off-theme for the show's usual AI/Nomad/Libertarian/Finance beats — a standalone curiosity piece; the angle, if any, is how a viral hook repackages a messy archaeological record into a clean one-line claim, and what gets lost in the flattening.

17. 🏛️ **Simon Dixon: "You Will Own Nothing" — UBI, AI and the Hidden Wealth Transfer**
    - Category: Libertarian
    - Source: https://x.com/SenseReceptor/status/2066594287119384642?s=20
    - Type: URL-based
    - Flags: default (~5 min)
    - Extra prompt: introduce the speaker Simon Dixon before his argument (see Notes)
    - Notes: @SenseReceptor (posted 2026-06-15) shares a clip of **Simon Dixon** (@SimonDixonTwitt, from his YouTube channel, 2026-06-14) — angel investor, early Bitcoin investor (one of the first to publicly back Bitcoin startups via BankToTheFuture), former investment banker — arguing the "You Will Own Nothing and Be Happy" agenda is being implemented through UBI, AI and tokenisation. Dixon's thesis (full transcript in the post): (1) AI makes productive assets **harder to own**, and tokenisation means the **custodian owns the asset while you own the token** — "they don't want you to own the Bitcoin, they want you to own the paper Bitcoin" (ETFs/IOUs vs. self-custody); (2) this is a **"hidden wealth transfer"** — daily life gets cheaper (consumption up) while ownership gets more expensive, so "citizens may consume more but they'll be owning less"; (3) the **middle class was built on ownership** (postwar boomers buying affordable real estate, leveraging debt, owning property/businesses/stocks/savings), and AI "threatens to separate consumption from ownership"; (4) **UBI / Musk's "universal high income" is "consumption support," not wealth creation** — it "concentrates wealth significantly"; (5) the prescription: maximise productivity, spend less than you earn, invest the difference, **own productive assets** — "own more Bitcoin… then diversify accordingly." Dixon calls the emerging order the **"subscription industrial complex"** — citizens renting access to everything rather than owning, enabled by "manufactured crises to make sure that you own nothing and you're happy." **Mandatory introduction (user-style)**: open by introducing who Simon Dixon is (above) before the argument. **Fact-check / editorial (important)**: Dixon is a verifiable figure and his custody-vs-self-custody / "own-the-productive-asset" points are defensible, but several claims are contested or conspiratorial — frame them as *his* argument, not fact: (a) the **"you will own nothing and be happy"** line originated from a 2016 WEF article (by a Danish politician, about a sharing-economy prediction, not a WEF "strategy"), and its use as a plotted elite agenda is a widespread misframing — do not present it as an established plan; (b) **"manufactured crises"** is an unsupported conspiratorial claim; (c) UBI concentrating wealth is an opinion, not settled economics. Separate Dixon's reasonable analysis (ownership trends, custody/counterparty risk) from the conspiratorial framing, and present Bitcoin as *his* stated recommendation, not neutral advice. Connects to ep105 (Robinhood open to agents — financial access/ownership), item #12 (Financial Physics — adjacent finance take), and the show's ownership-as-sovereignty beat. Category rationale: filed Libertarian on the ownership-vs-rental / UBI-as-control / "own nothing" sovereignty thesis (the Señor Freedom core), though the literal prescription is finance/Bitcoin — discoverable either way. Señora Freedom angle: is a cheaper, AI-abundant life still freedom if you own nothing and rent everything from a custodian? UBI-as-control vs. ownership-as-freedom is exactly the sovereignty tension the show is built on.

18. 🏠 **"10 Reasons to Leave the UK" — The Emigration / Low-Tax Playbook**
    - Category: Nomad
    - Source: https://x.com/sotontimes/status/2066672006670569696/video/1
    - Type: URL-based
    - Flags: default (~5 min)
    - Notes: @sotontimes (a UK emigration/tax/expat content account) shares a viral short, **"10 reasons to leave the UK! 🇬🇧🛫"** — a teaser for a full guide (sold via "link in bio"). The caption flags reason 10 as "a real game changer, especially for those wanting to stay legal and pay LESS tax… (it doesn't actually involve leaving the UK itself)" — i.e. a UK tax-residence / non-dom-style optimisation angle layered onto an emigration pitch. **Read the actual 10 reasons from the video before writing**: the post is a teaser and the detail lives in the clip (and a gated paid guide), so enumerate the real reasons from the video rather than inventing them. **Fact-check / editorial (critical)**: UK tax-residence law changed materially — the old non-dom regime was **abolished from 6 April 2025** and replaced by the 4-year "foreign income and gains" (FIG) regime, with new rules on the Statutory Residence Test, split-year treatment, and the £1m foreign-income exemption; any "pay less tax legally without leaving" claim must be verified against **2025/26** HMRC rules, not pre-2025 non-dom advice (a lot of viral content here is now outdated or wrong). Frame tax mechanics as "the video claims / the guide suggests," verify each against HMRC, and don't present emigration as a one-size-fits-all win. **Sponsorship gate note**: the account monetises via the "full guide" (link in bio), so the content is partly promotional — the sponsorship gate may flag it; if so, `--force` is appropriate once the topic is confirmed as genuine emigration/tax education rather than a product ad. Connects to the show's Nomad beat: ep127 (Istanbul real estate / Turkish CBI), ep123 (Izmir neighbourhood guide), ep104 (Uganda real estate for foreigners), ep93 (Georgia corporate structures for nomads). Señora Freedom angle: leaving a high-tax jurisdiction — or legally reducing its reach without leaving — is the sovereignty-by-exit move the nomad track is about; the question is which exit routes still actually work under the post-2025 UK rules.

19. 💰 **Why Walmart Wants a Universal Basic Income**
    - Category: Finance
    - Source: https://x.com/mikenevermiss/status/2066769708641042571/video/1
    - Type: URL-based
    - Flags: default (~5 min)
    - Notes: @mikenevermiss ("Mike", a finance/economics commentator) argues **"Walmart wants a Universal Basic Income"** — the thesis: as Walmart leans on automation and AI, it still needs customers who actually have money; its classic low-price / high-volume model breaks when the working class runs out of spending power (prices rising, real wages flat); so a consumer-dependent mega-retailer has a structural incentive to back UBI, because UBI keeps aggregate consumer demand — and thus its own revenue — alive. **Read the full argument from the video before writing**: the post is the hook + a clip, so pull the specifics (the automation-vs-demand squeeze, any named exec quotes, the "who actually pays for the UBI" question) from the video, don't invent them. **Fact-check / editorial (important)**: the *logical* claim — consumer-spending-dependent corporations benefit when consumers have guaranteed income — is defensible; but **"Walmart wants UBI" is Mike's inference, not an official Walmart position** — Walmart has not endorsed or lobbied for UBI (verify before claiming otherwise; some Walton-family members have spoken about income inequality/automation, which is not the same as corporate UBI advocacy). Also verify the macro framing (real-wage stagnation, price inflation) against current data rather than asserting it. Frame it as "the argument goes / Mike contends," and separate the sound economic logic (automation threatens the demand side of a consumer economy) from the unproven attribution ("Walmart wants this"). **Similarity note**: thematically adjacent to item #17 (Simon Dixon — UBI as "consumption support" / wealth transfer) — #17 frames UBI as a tool that *concentrates* wealth, while this frames it as something *corporations want* to preserve demand; the angles are distinct (who benefits vs. who wants it) but the similarity gate may flag overlap — if it does, consider producing them as a paired UBI mini-series or merging. Connects to ep113/ep114 (AI market dynamics / automation), item #17 (Dixon — UBI/ownership), and the show's "who profits from automation" thread. Señora Freedom angle: when the world's biggest retailer has a rational business case for the state mailing everyone a cheque, the line between corporate welfare and social policy dissolves — the question is whether UBI buys freedom or just enough spending money to keep the machine fed.
