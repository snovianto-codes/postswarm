"""Writer Agent — port 5007
Called by Orchestrator. Assembles the final LinkedIn post using VOICE.md.
"""
import os, sys
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.model_client import call_model, ModelClientError
from core.moa import draft_moa, MoAError, is_enabled as moa_enabled

app = Flask(__name__)
CORS(app, resources={r"/run": {"origins": ["http://localhost:5001","http://127.0.0.1:5001","http://localhost:8080","http://127.0.0.1:8080"]}, r"/health": {"origins": "*"}})

VOICE_PATH = Path(__file__).parent.parent / 'VOICE.md'
FALLBACK_MODEL  = 'gemini-2.5-flash'


def load_voice():
    try:
        return VOICE_PATH.read_text()
    except Exception:
        return "Direct, no fluff, short sentences. Max 200 words. End with a sharp question."


@app.route('/health')
def health():
    return jsonify(status='ok')


def build_prompt(topic='', take='', tone='Skeptical', research=None, hooks=None,
                  insights=None, role='People Manager', post_type='opinion'):
    """Builds the writer prompt from assignment inputs. Factored out of
    run() so scripts/compare_moa.py can build the same prompt a real
    request would, without duplicating these templates (see the
    hermes/prefetch.py prompt-duplication issue from the July audit —
    not repeating that pattern here)."""
    research = research or {}
    hooks = hooks or []
    insights = insights or []

    voice = load_voice()
    verified   = research.get('verified', [])
    counters   = research.get('counter_points', [])
    source_url = research.get('source_url')

    verified_text  = '\n'.join(f"- {p}" for p in verified[:3])   if verified  else "No verified data."
    counters_text  = '\n'.join(f"- {p}" for p in counters[:2])   if counters  else "None."
    insights_text  = '\n'.join(f"- {p}" for p in insights[:2])   if insights  else "None."
    hooks_text     = '\n'.join(f"{i+1}. {h}" for i, h in enumerate(hooks[:5])) if hooks else "No hooks provided."
    source_note    = f"\nSource article: {source_url}\nUse findings from this article as the basis for the post — make it clear the post is a reaction to this specific article." if source_url else ""

    if post_type == 'repost':
        prompt = f"""You are ghostwriting a short LinkedIn repost for the author described in this voice profile:

---VOICE PROFILE---
{voice}
---END VOICE---

## Assignment
Topic/article: {topic[:2000]}
Author's take: {(take or "React honestly to this")[:500]}
{source_note}

Write a SHORT repost-style reaction — the kind where someone shares a link and adds a quick sharp comment.

## Format
- 2-4 sentences MAX. 50-80 words total.
- First sentence: your honest reaction (agree, push back, or add a nuance). No "I just read..." opener.
- Second sentence: the concrete implication for your team or Singapore/SEA context.
- Optional third sentence: a question or flat observation — only if it adds something.
- End with the source URL on its own line if one is in the topic.
- 0-2 hashtags. Often none.

## Hard rules
- Plain English. Short sentences.
- BANNED words: leverage, robust, seamless, empower, unlock, paradigm, game-changing, revolutionary, groundbreaking
- No "Here's the thing:" — no triadic lists — no AI performance
- Sound like a person, not a newsletter

Return ONLY the post text. No preamble."""
    else:
        prompt = f"""You are ghostwriting a LinkedIn post for the author described in this voice profile:

---VOICE PROFILE---
{voice}
---END VOICE---

## Assignment
---USER INPUT START---
Topic: {topic[:2000]}
Author's role / perspective: {role[:100]}
Author's take: {(take or "Be direct and honest")[:500]}
Tone: {tone[:50]}
---USER INPUT END---
{source_note}

Write the post FROM the perspective of a {role[:100]} — use language, concerns, and angles that are natural for someone in that role.

## Research to use
Verified facts:
{verified_text}

Counter-arguments (use 1 for balance):
{counters_text}

SEA/team insights (weave in naturally):
{insights_text}

## Hook options (pick the best one):
{hooks_text}

## Output structure
1. Best hook from the list above (pick the most arresting one for the tone)
2. 1-2 sentences of context
3. The author's real take, supported by 1-2 specific data points
4. 1 honest counter-point or friction (balanced view)
5. 1 Southeast Asia / team management angle
6. Closing line — pick what fits, do NOT default to a question every time:
   - Flat statement (works most of the time)
   - One-line observation
   - Question (only if the post genuinely invites debate)
   - Trailing thought that lingers
   Vary it across posts. Ending with a question every single time is an AI tell.
7. Hashtags: 0 to 4, your judgment. Sometimes none is cleaner.

## Hard rules
- Max 200 words. Aim for 100-160.
- Vary sentence length. Some short. Some with a dependent clause or two. Never the same rhythm twice.
- Plain English. Always choose the simpler word.
  → "Use" not "leverage". "Help" not "empower". "Real" not "authentic". "Big" not "significant".
- BANNED words: leverage, robust, seamless, comprehensive, elegant, profound, unprecedented,
  paradigm, ecosystem, holistic, journey, unlock, empower, harness, navigate, landscape,
  game-changing, revolutionary, dive into, delve, groundbreaking, in today's fast-paced world,
  it's worth noting, needless to say, at the end of the day
- BANNED structures:
  → "It's not just X, it's Y" openers
  → "Here's the thing:" / "Here's what I found:"
  → Every paragraph starting the same way
  → Triadic punch lists on every post
- Arrow lists (→): only when listing 3+ things. Not in every post.
- No excessive exclamation marks
- One blank line between paragraphs
- Sound like a tired but sharp person who has seen things — not a marketer performing for engagement

Return ONLY the post text. No preamble, no explanation."""

    return prompt


@app.route('/run', methods=['POST'])
def run():
    data = request.json or {}
    topic     = data.get('topic', '')
    take      = data.get('take', '')
    tone      = data.get('tone', 'Skeptical')
    research  = data.get('research', {})
    hooks     = data.get('hooks', [])
    insights  = data.get('insights', [])
    ALLOWED_MODELS = {'gemini-3.1-pro-preview', 'gemini-2.5-pro', 'gemini-2.5-flash'}
    DEFAULT_MODEL = FALLBACK_MODEL
    model     = data.get('model', DEFAULT_MODEL)
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL
    role      = data.get('role', 'People Manager')
    post_type = data.get('post_type', 'opinion')  # 'opinion' or 'repost'
    primary_model = model
    print(f"[Writer Agent] ← Received | model: {model} | Writing {post_type} for: {topic[:50]}...")

    prompt = build_prompt(topic=topic, take=take, tone=tone, research=research,
                           hooks=hooks, insights=insights, role=role, post_type=post_type)

    if moa_enabled():
        try:
            result = draft_moa(prompt)
        except MoAError as e:
            print(f"[Writer Agent] [ERROR] MoA drafting failed: {e}")
            return jsonify(post='', model_used='fallback')
        post = result.post
        model_used = f"moa({result.aggregator.model})"
        proposer_drafts = [
            {'provider': d.provider, 'model': d.model, 'text': d.text}
            for d in result.proposer_drafts
        ]
        print(f"[Writer Agent] ✓ Post written ({len(post.split())} words) via MoA "
              f"({len(result.proposer_drafts)} proposers → {result.aggregator.model})")
        return jsonify(post=post, model_used=model_used, proposer_drafts=proposer_drafts)

    try:
        resp = call_model('writer', prompt, request_model=primary_model)
    except ModelClientError as e:
        print(f"[Writer Agent] [ERROR] {e}")
        return jsonify(post='', model_used='fallback')

    post = resp.text
    print(f"[Writer Agent] ✓ Post written ({len(post.split())} words) using {resp.provider}/{resp.model}")
    return jsonify(post=post, model_used=resp.model)


if __name__ == '__main__':
    print("[Writer Agent] Starting on port 5007...")
    app.run(port=5007, debug=False)
