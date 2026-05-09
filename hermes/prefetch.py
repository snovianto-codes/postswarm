"""Standalone prefetch script for Hermes.
Fetches RSS articles + runs editor ranking → writes digest cache.
PostSwarm reads the same cache file, so it's pre-populated on open.

Usage:
    python /path/to/postswarm/hermes/prefetch.py
"""
import os, sys, json, sqlite3, time
from pathlib import Path
from datetime import date

# ── Paths ─────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
DATA_DIR  = ROOT / 'data'
VOICE_PATH = ROOT / 'VOICE.md'

# Allow importing feed_agent without Flask starting
sys.path.insert(0, str(ROOT / 'agents'))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from google import genai

_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
DEFAULT_MODEL  = 'gemini-2.5-flash'
FALLBACK_MODELS = [DEFAULT_MODEL, 'gemini-1.5-flash']


# ── Helpers ───────────────────────────────────────────────────────────

def load_voice():
    try:
        return VOICE_PATH.read_text()
    except Exception:
        return "Direct, practical LinkedIn content for a Singapore People Manager in tech."


def recent_posted_titles():
    db_path = DATA_DIR / 'seen.db'
    if not db_path.exists():
        return []
    try:
        c = sqlite3.connect(str(db_path))
        try:
            rows = c.execute(
                "SELECT title FROM seen WHERE posted=1 ORDER BY ts DESC LIMIT 20"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            c.close()
    except Exception as e:
        print(f"[prefetch] WARN: could not read recent posted titles: {e}")
        return []


def fetch_articles():
    from feed_agent import fetch_all
    print("[prefetch] Fetching articles from RSS sources…")
    items = fetch_all()
    print(f"[prefetch] Got {len(items)} fresh articles")
    return items


def rank_articles(items, role='People Manager'):
    if not items:
        return []

    voice        = load_voice()
    recent       = recent_posted_titles()
    count        = min(10, len(items))
    items_text   = '\n'.join(
        f"[{i}] (Tier {it.get('tier', 3)} · {it['source']}) "
        f"{it['title'][:120]} — {it.get('summary', '')[:180]}"
        for i, it in enumerate(items)
    )
    posted_text  = '\n'.join(f"- {t}" for t in recent) or 'None yet.'

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

    for model_name in FALLBACK_MODELS:
        try:
            print(f"[prefetch] Ranking with {model_name}…")
            response = _client.models.generate_content(model=model_name, contents=prompt)
            text = response.text.strip()
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
                text = text.rsplit('```', 1)[0].strip()

            picks_raw = json.loads(text)
            ALLOWED_AI_FIELDS = {'rank', 'index', 'why_matters', 'angle', 'novelty', 'format', 'excerpt'}
            picks = []
            for p in picks_raw:
                idx = p.get('index', -1)
                if isinstance(idx, int) and 0 <= idx < len(items):
                    safe_p = {k: p[k] for k in ALLOWED_AI_FIELDS if k in p}
                    picks.append({**items[idx], **safe_p})

            print(f"[prefetch] ✓ {len(picks)} picks selected via {model_name}")
            return picks
        except Exception as e:
            print(f"[prefetch] [{model_name}] failed: {e}")

    return []


def save_digest(items, picks):
    DATA_DIR.mkdir(exist_ok=True)
    sorted_items = sorted(items, key=lambda x: (x.get('tier', 5), -x.get('ts', 0)))
    result = {
        'picks':         picks,
        'all_items':     sorted_items,
        'refreshed_at':  int(time.time()),
        'items_scanned': len(items),
    }
    cache_file = DATA_DIR / f'digest_{date.today()}.json'
    cache_file.write_text(json.dumps(result))
    print(f"[prefetch] ✓ Saved → {cache_file}")
    return cache_file


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    t0 = time.time()
    print("[prefetch] Starting PostSwarm prefetch…")

    items = fetch_articles()
    if not items:
        print("[prefetch] No new articles found. Exiting.")
        sys.exit(0)

    picks = rank_articles(items)
    cache_file = save_digest(items, picks)

    elapsed = round(time.time() - t0, 1)
    print(f"\n[prefetch] Done in {elapsed}s — {len(picks)} picks ready.")
    print(f"[prefetch] Open PostSwarm and the digest will be pre-loaded.")
