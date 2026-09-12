"""Editor Agent — port 5009
Scores raw feed items → top 15 picks with why_matters, angle, novelty.
"""
import os, sys, json, traceback
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.model_client import call_model

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "http://localhost:8080", "http://127.0.0.1:8080",
    "http://localhost:5008", "http://127.0.0.1:5008",
]}})

VOICE_PATH     = Path(__file__).parent.parent / 'VOICE.md'
DEFAULT_MODEL  = 'gemini-2.5-flash'
ALLOWED_MODELS = {'gemini-3.1-pro-preview', 'gemini-2.5-pro', 'gemini-2.5-flash'}


def load_voice():
    try:
        return VOICE_PATH.read_text()
    except Exception:
        return "Direct, practical LinkedIn content for a Singapore People Manager in tech."


def _rank_once(prompt, request_model):
    """One call+parse attempt. Raises on API failure (model_client.ModelClientError
    or the provider's own exception) or on malformed JSON — either way the
    caller retries once with a different model."""
    resp = call_model('editor', prompt, request_model=request_model)
    text = resp.text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.rsplit('```', 1)[0].strip()
    return json.loads(text), resp


@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/rank', methods=['POST'])
def rank():
    data          = request.json or {}
    items         = data.get('items', [])
    role          = data.get('role',  'People Manager')
    recent_posted = data.get('recent_posted', [])
    model         = data.get('model', DEFAULT_MODEL)
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL

    if not items:
        return jsonify(picks=[])

    print(f"[Editor Agent] Ranking {len(items)} items for '{role}'…")

    voice       = load_voice()
    count       = min(15, len(items))
    items_text  = '\n'.join(
        f"[{i}] (Tier {it.get('tier', 3)} · {it['source']}) "
        f"{it['title'][:120]} — {it.get('summary', '')[:180]}"
        for i, it in enumerate(items)
    )
    posted_text = '\n'.join(f"- {t}" for t in recent_posted[:20]) or 'None yet.'

    prompt = f"""You are the editor for a {role} based in Singapore who posts on LinkedIn about AI and technology.

---VOICE PROFILE---
{voice}
---END VOICE---

Topics this person has recently posted about:
{posted_text}

Below are {len(items)} AI/tech stories from the last 36 hours.
Pick the {count} BEST candidates for a LinkedIn post. Return exactly {count} if there are enough stories, fewer only if the total is under {count}.

Selection criteria (in priority order):
1. Sparks real conversation — controversy, surprising data, practical impact
2. Fits the voice and role — AI adoption, people management, leadership angle
3. NOT similar to recently posted topics — avoid repetition
4. Has a clear "so what?" for a Singapore / SEA tech leader audience
5. Mix: at least one repost-friendly news item, one opinion-worthy trend
6. When quality is equal, prefer lower Tier numbers (Tier 1 = most authoritative)

For each of your {count} picks, return:
- rank: integer 1-{count} (1 = strongest pick)
- index: the [N] from the story list
- why_matters: 2 sentences. Be concrete about why THIS reader's Singapore/SEA audience cares. Not generic.
- angle: one sentence. The specific hook or take to use. Written as if speaking in first person.
- novelty: integer 1-5 (5 = very different from recent posts, 1 = too similar)
- format: "repost" (short reaction + source link works fine) or "opinion" (full post, own take)
- excerpt: one sentence paraphrased from the story (under 20 words, no quotes)

---STORIES---
{items_text}
---END---

Return ONLY a valid JSON array of up to {count} objects, sorted by rank ascending. No markdown fences, no preamble."""

    # Try the requested model, then the default once more if that also
    # fails (API error or malformed JSON) — skip the redundant second
    # attempt if the requested model already was the default.
    model_attempts = [model] if model == DEFAULT_MODEL else [model, DEFAULT_MODEL]

    picks_raw, resp = None, None
    for attempt_model in model_attempts:
        try:
            picks_raw, resp = _rank_once(prompt, attempt_model)
            break
        except Exception as e:
            print(f"[Editor Agent] [{attempt_model}] {type(e).__name__}: {e}")

    if picks_raw is None:
        print(traceback.format_exc())
        return jsonify(picks=[])

    # hydrate with full item data — allowlist AI fields to prevent injection
    ALLOWED_AI_FIELDS = {'rank', 'index', 'why_matters', 'angle', 'novelty', 'format', 'excerpt'}
    picks = []
    for p in picks_raw:
        idx = p.get('index', -1)
        if isinstance(idx, int) and 0 <= idx < len(items):
            safe_p = {k: p[k] for k in ALLOWED_AI_FIELDS if k in p}
            picks.append({**items[idx], **safe_p})

    print(f"[Editor Agent] ✓ Selected {len(picks)} picks via {resp.provider}/{resp.model}")
    return jsonify(picks=picks)


if __name__ == '__main__':
    print("[Editor Agent] Starting on port 5009…")
    app.run(port=5009, debug=False)
