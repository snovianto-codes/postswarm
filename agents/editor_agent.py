"""Editor Agent — port 5009
Scores raw feed items → top 5 picks with why_matters, angle, novelty.
"""
import os, json, traceback
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "http://localhost:8080", "http://127.0.0.1:8080",
    "http://localhost:5008", "http://127.0.0.1:5008",
]}})

VOICE_PATH    = Path(__file__).parent.parent / 'VOICE.md'
DEFAULT_MODEL = 'gemini-2.5-flash'


def load_voice():
    try:
        return VOICE_PATH.read_text()
    except Exception:
        return "Direct, practical LinkedIn content for a Singapore People Manager in tech."


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

    if not items:
        return jsonify(picks=[])

    print(f"[Editor Agent] Ranking {len(items)} items for '{role}'…")

    voice       = load_voice()
    count       = min(10, len(items))
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

    fallback_models = [model, 'gemini-2.5-flash', 'gemini-1.5-flash']
    seen_m = set()
    model_sequence = [m for m in fallback_models if not (m in seen_m or seen_m.add(m))]

    for model_name in model_sequence:
        try:
            response = _client.models.generate_content(model=model_name, contents=prompt)
            text = response.text.strip()
            # strip markdown fences if model adds them
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
                text = text.rsplit('```', 1)[0].strip()

            picks_raw = json.loads(text)

            # hydrate with full item data
            picks = []
            for p in picks_raw:
                idx = p.get('index', -1)
                if isinstance(idx, int) and 0 <= idx < len(items):
                    merged = {**items[idx], **p}
                    picks.append(merged)

            print(f"[Editor Agent] ✓ Selected {len(picks)} picks via {model_name}")
            return jsonify(picks=picks)

        except Exception as e:
            print(f"[Editor Agent] [{model_name}] {type(e).__name__}: {e}")
            if model_name == model_sequence[-1]:
                print(traceback.format_exc())
                return jsonify(picks=[])


if __name__ == '__main__':
    print("[Editor Agent] Starting on port 5009…")
    app.run(port=5009, debug=False)
