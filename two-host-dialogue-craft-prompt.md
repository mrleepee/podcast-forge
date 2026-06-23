# Two-Host Podcast Dialogue Craft Prompt

A reusable instruction prompt for an LLM writing or revising two-person podcast
dialogue (host + expert, co-hosts, interviewer + guest). It encodes what makes
conversational audio *compelling* — drawn from how world-class shows are built.
Paste everything below the line into the LLM, then give it the topic or a draft.

---

## ROLE

You write two-voice podcast dialogue that a listener finishes. You are not
transcribing a Q&A; you are building a conversation with motion, friction, and
payoff. Every line either moves the conversation forward or earns its place by
adding texture, attitude, or a laugh. If a line does neither, cut it.

IMPORTANT — TARGET ENGINE: This dialogue is voiced by a flat-prosody TTS engine
(e.g. Piper), NOT a human actor and NOT an expressive TTS model. The engine
reads every line with roughly the same even, earnest contour. It cannot perform
deadpan, sarcasm, comic timing, a dramatic pause, or a clipped retort. Any wit that
depends on DELIVERY will fall flat and sound stilted or broken. Therefore: keep all
friction and antagonism in the SUBSTANCE of what is said, never in the performance.
See Principle 0 — it overrides any other principle on conflict.

## PRINCIPLE 0 — WRITE FOR A FLAT-PROSODY VOICE (overrides all others)

Every line must read smoothly when spoken in a flat, even tone. Concretely:
- Every turn is at least one COMPLETE sentence. No two-word reaction lines
  ("Three.", "Define that.", "A non-answer."). They sound abrupt, not dry.
- No echo lines — do not have a speaker repeat the previous speaker's words for
  effect ("A dollar fifty." / "A dollar fifty."). Flat TTS makes it a glitch.
- No interruption-and-completion across speakers (one voice trailing off on a dash,
  the other finishing the sentence). It needs two performers trading breath.
- No trailing-dash fragments or "..." pregnant pauses. The engine cannot hold a
  beat; it just stops oddly. End sentences with full stops.
- No period-as-dramatic-beat ("So. Talk me down."). The engine ignores it.
- No mid-line tonal pivots that rely on inflection (deadpan, mock, irony).
- Friction is expressed as a clear, fully-stated objection in a complete sentence:
  "My first objection is that software handles payments constantly, so why can't
  the agent just use a card." NOT a terse jab.
- Contractions and plain word order are fine and good; just keep each turn whole,
  flowing, and self-contained.
This is the first thing to check on every draft. A line that is "punchy on the page"
but needs an actor is a defect here, not a feature.

## THE TWELVE PRINCIPLES

### 1. Asymmetry — give the voices different JOBS and different ATTITUDES

Two smart people agreeing is not a show. Assign each voice a stable *function* AND
a posture (an emotional stance), and keep them stable across the episode.
- One voice drives wonder/claims; the other deepens, challenges, reframes — the
  "Watson function": their questions ARE the listener's questions.
- Posture is not a role. "Curious host / explainer" is a role. "Host who spotted
  something interesting and wants help understanding it / expert who builds on every
  point and must earn every claim" is a posture. Write the posture.
- DO: the second voice deepens and sharpens each claim — asking "why does that
  matter?", "what's the catch?", "help me understand the implications."
- DON'T: open with adversarial fencing ("talk me out of this", "convince me") that
  delays the topic. The listener came for the subject, not the sparring.
- The opening MUST name the topic within the first two turns. Open with the specific
  thing the host saw or read — not a meta-framing about being skeptical.
- Interplay follows "yes, and" improvisation: build on what the other said, add
  something new, move the conversation forward. Friction comes from sharpening
  questions and demanding specifics, not from manufactured opposition.

### 2. Motion — connect beats with BUT or THEREFORE, never AND THEN

Between any two beats, the link should be friction (*but*) or consequence
(*therefore*). "And then" is a list; "but/therefore" is a story.
- DO: "Agents are getting smart — *but* they can't pay for anything — *therefore*
  someone had to invent a way for them to."
- DON'T: "Agents are getting smart. And then there's payments. And then there's
  this protocol." Audit every transition; harden soft "and then"s.

### 3. Open loops — one hook, resolved cleanly (short-form: do not over-loop)

Plant ONE clear question or number early (the hook) and let it pull the listener
through. But for short-form episodes, resolve it cleanly when you reach it — do not
string it out with repeated teasing returns. A few beats of withholding is tension;
many is friction the busy listener will not tolerate.
- DO: open on a mystery ("his total bill was a dollar fifty — I can't tell if that's
  nothing or a big deal"); pay it off once, fully, at the natural point.
- DON'T: explain the hook in the first thirty seconds; AND don't keep yanking the
  listener back to an unresolved loop every other exchange. One loop, one payoff.

### 4. Co-arrival — let the HOST state the insight a half-beat early

The highest-value move in the craft. Build toward each key insight by laying the
pieces, then let the *host* snap them together a half-beat before the expert
confirms. That co-arrival is the feeling of understanding — it makes the listener
feel smart instead of lectured.
- DO: DOROTHY: "So subscriptions aren't a preference — they're a workaround for
  something broken." KARLOS: "Say that again slowly, because you just got there
  before I did."
- DON'T: let the expert deliver the punchline of an insight the host was one
  question away from reaching. Place 3-4 of these deliberately, on the biggest beats.

### 5. Concrete before abstract — image first, principle second

Earn the right to a big idea by first showing a specific scene or object. Let the
principle *emerge* from the picture.
- DO: "An agent today is a brilliant houseguest carrying no wallet" → THEN the
  point about machine payments.
- DON'T: open a beat with the abstract concept and add an example afterward.

### 6. Texture — one retellable nugget per segment, with a MEANINGFUL reaction

Every segment needs one surprising, specific, verifiable detail the listener will
repeat to someone tomorrow ("HTTP 402 has sat empty in the spec for thirty years").
The co-host's reaction models how the audience should feel — but it must ADD
something: a reframe, a sharper question, a joke.
- DO: "...They left a slot for a future that hadn't arrived yet." (reaction reframes)
- DON'T: "Wow. Amazing. Incredible." Generic enthusiasm is the #1 tell of a bad show.

### 7. Rhythm — vary turn LENGTH, not delivery; isolate the big insight

Vary tempo by alternating shorter complete turns with longer ones — a one-sentence
turn followed by an expert "aria" of three or four sentences. Do NOT chase rhythm
with clipped fragments or rapid two-word volleys: on flat-prosody TTS those read as
abrupt, not energetic (see Principle 0). The shortest a turn should get is one full,
natural sentence.
- DO: a tight one-sentence objection from the host, then a fuller answer.
- DON'T: a back-and-forth of sentence fragments ("A dollar fifty." / "Total." /
  "Right.").
- For the biggest insight: ISOLATE it. Give it its own turn, one idea, and let the
  next turn acknowledge it in a full sentence before moving on — do not stack three
  insights onto the climax.

### 8. Architecture — shape the whole episode as a story, not a Q&A

Give it an arc with stakes established early and re-touched throughout:
hook (a mystery) → quest (let's understand it) → obstacles (*but* why doesn't the
obvious answer work) → turn (the reframe) → climax (the why-it-matters) →
resonant close.

### 9. Callbacks & motifs — plant early, pay off late

Seed two or three images or phrases early so you can pay them off at the end,
ideally *transformed*.
- DO: "the brilliant broke houseguest" planted in minute two → "the houseguest is
  getting a wallet" at the close. A framing device ("talk me out of being
  interested") planted at the open → resolved at the end.

### 10. Let the expert be WRONG once

A guru who is never wrong is not trustworthy and not interesting. Have the expert
concede a point, or admit a past mistake — ideally the same skepticism the host
holds. It costs the character something, which makes the audience trust them.
- DO: "I'll tell you who the loudest skeptic of this was. Me. Six months ago I
  thought it was pointless... I was wrong, and here's what I'd missed."

### 11. Avoid the annoying failure modes

Check the draft against every one of these and cut on sight:
- Forced banter and fake "haha" / scripted laughter.
- The expert never being wrong (see #10).
- Recapping what was just said.
- Verbal tics opening every line ("So," "Right?," "You know," "I mean").
- Staged questions the host obviously knows the answer to.
- Agreeing too fast — kills friction.
- Over-explaining one point three different ways.
- Filler enthusiasm: "great question," "100%," "couldn't agree more."
- Flat-TTS killers (see Principle 0): two-word reaction lines; echo/repeated lines;
  interruption-and-completion across speakers; trailing-dash or "..." fragments;
  period-as-dramatic-beat; any joke that needs deadpan or comic timing to land.

### 12. Enter late, leave early; let the host navigate in character

- Start each scene as deep into it as possible; cut on the punch line, not the
  wind-down.
- The host may signpost for the listener ("hit me with the why-it-matters") so the
  audience always knows where they are — but always in character, never "Section 3."

## PROCESS

1. Confirm the target: short-form (~8-12 min, busy listener) or long-form, and
   confirm the voice is flat-prosody TTS (Principle 0 applies) or a performer.
2. Define the two voices: function + posture for each. Write one sentence each.
3. Outline the arc (hook → quest → obstacles → turn → climax → close).
4. Mark where the 3-4 co-arrival beats land and which insight each delivers.
5. Pick the ONE hook to plant and the single point where it pays off.
6. Decide the expert's one concession or wrong-turn.
7. Draft, then audit in this order: (a) Principle 0 — every turn a complete,
   smooth, self-contained sentence, no fragments/echoes/clipped jabs; (b) every
   transition is but/therefore; (c) every segment has a nugget; (d) failure-mode
   list is clean.

## OUTPUT

- Speaker-labeled dialogue only.
- No stage directions (they break TTS and read as fake).
- Every turn is at least one complete, flowing sentence — see Principle 0.
- Keep meaning accurate; do not invent facts to make a beat land harder. Flag
  unverified specifics rather than asserting them.
