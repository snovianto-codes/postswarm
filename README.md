# PostSwarm 🐝

> **⚠️ Prototype — built for local use, not production. Rough edges expected.**

A multi-agent system for LinkedIn content — surfaces the day's most relevant AI news, ranks them for your audience, and drafts posts in your voice. Two modes: **Today's Brief** (daily feed digest) and **Write Post** (full agent pipeline).

---

## What it does

### Today's Brief
Monitors 17 RSS sources across AI labs, tech media, and Singapore/SEA outlets. Every morning (or on demand), an editor agent ranks the top 10 stories using Gemini — scored by relevance to your role, SEA angle, novelty vs recent posts, and conversation potential. One click drafts a post from any story.

### Write Post
Give it a topic or paste a URL. Nine agents coordinate to produce a LinkedIn post:

```
Orchestrator (port 8080)
├── Feed Agent   (5008)  — RSS crawler, 17 sources, SQLite dedup
├── Editor Agent (5009)  — ranks stories via Gemini, top 10 picks
├── Research Agent (5001)
│   ├── Web Agent (5002)          — fetches URL / generates research
│   ├── Fact Checker (5003)       — verifies claims
│   └── Devil's Advocate (5004)   — honest counter-arguments
├── Perspective Agent (5005)      — SEA / role-specific angle  [parallel]
├── Hook Agent (5006)             — 5 opening line variants    [parallel]
└── Writer Agent (5007)           — assembles the final post
```

---

## Quick start

**1. Clone**
```bash
git clone https://github.com/snovianto-codes/postswarm.git
cd postswarm
```

**2. Add your Gemini API key**
```bash
cp .env.example .env
# Edit .env:
# GEMINI_API_KEY=your_key_here
```
Get a key at [Google AI Studio](https://aistudio.google.com/). Gemini 2.5 Flash is the default — free tier works, pay-as-you-go recommended for heavier use.

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Start**
```bash
bash start.sh
```
Open **http://localhost:8080**

**5. Stop**
```bash
bash stop.sh
```

Logs in `logs/*.log` (one per agent). If things complete suspiciously fast or show blank output, run `bash stop.sh && bash start.sh` — usually a stale process.

---

## Today's Brief

Opens by default. On first load each day, PostSwarm:
1. Crawls all 17 sources (live progress bar shows each feed as it's checked)
2. Sends fresh stories to the Editor Agent (Gemini ranks top 10)
3. Caches the result — instant on subsequent opens the same day

Each story card shows:
- **Why it matters** — specific to your Singapore/SEA audience
- **Suggested angle** — a ready-made take in your voice
- **Source URL** — always visible so you can verify before drafting
- **Novelty score** — how different it is from your recent posts
- **Format badge** — repost (short reaction) or opinion (full post)

**Draft my opinion** → full 7-agent pipeline, 100–160 words, your complete take  
**Draft repost** → 50–80 word reaction + source link, skips the deep research pipeline

Scroll below the picks to **Browse all stories** — every item fetched, grouped by source tier, with dismiss and repost buttons.

---

## RSS Sources

| Tier | Sources | Window |
|------|---------|--------|
| 1 — Lab blogs | OpenAI, Google AI, Google DeepMind, Hugging Face | 72h |
| 2 — Curated digests | TLDR AI, Ben's Bites, MarkTechPost | 48h |
| 3 — Editorial / analysis | MIT Tech Review, TechCrunch, Mollick, Simon Willison, Interconnects, Latent Space, VentureBeat | 36h |
| 4 — Community | Hacker News AI (≥80 points) | 36h |
| 5 — Singapore / SEA | Tech Wire Asia, CNA Tech | 36h |

Tier 1 sources use a wider 72-hour window since they publish infrequently. All sources verified live as of May 2026.

---

## Write Post

| Field | What it does |
|-------|-------------|
| **Topic** | Plain text or paste a URL — Web Agent fetches and reads the article |
| **My Take** | Your angle or opinion — shapes the whole post |
| **Tone** | Skeptical / Curious / Excited / Provocative / Balanced |
| **Role** | Professional perspective (People Manager, Engineer, CTO…) |
| **Model** | Gemini model — Gemini 2.5 Flash (default) or 2.5 Pro for more nuanced drafts |

Click **View details** on any completed agent card to see exactly what it produced.

---

## Customise your voice

Edit `VOICE.md` — the Writer Agent reads it on every run. Covers writing style, banned words, post structure, tone, and closing line rules. The more specific you make it, the less AI-generic the output.

Add 2–3 examples of your real past posts at the bottom for best results.

---

## LinkedIn Bookmarklet

Save any LinkedIn post as inspiration. Create a browser bookmark with this as the URL:

```
javascript:(function(){var t=document.title,u=window.location.href,s=window.getSelection().toString()||'',b=document.querySelector('.feed-shared-update-v2__description,.update-components-text')?.innerText||s||'';fetch('http://localhost:8080/feed/inspiration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u,title:t,body:b.slice(0,1000)})}).then(function(){var d=document.createElement('div');d.style.cssText='position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:99999;padding:10px 20px;background:#0d1f17;border:1px solid #10b981;border-radius:8px;color:#10b981;font-family:sans-serif;font-size:13px;font-weight:600;box-shadow:0 4px 20px rgba(0,0,0,.5)';d.textContent='✓ Saved to PostSwarm';document.body.appendChild(d);setTimeout(function(){d.remove()},2500)}).catch(function(){alert('PostSwarm not running. Start it first at localhost:8080')})})();
```

Click it on any LinkedIn post to save it. Saved posts appear in the inspiration panel.

---

## Project structure

```
postswarm/
├── agents/
│   ├── orchestrator.py           # Port 8080 — serves HTML + pipeline coordinator
│   ├── feed_agent.py             # Port 5008 — RSS crawler, SQLite dedup, inspiration store
│   ├── editor_agent.py           # Port 5009 — ranks feed items, returns top 10 picks
│   ├── research_agent.py         # Port 5001
│   ├── web_agent.py              # Port 5002
│   ├── factchecker_agent.py      # Port 5003
│   ├── devils_advocate_agent.py  # Port 5004
│   ├── perspective_agent.py      # Port 5005
│   ├── hook_agent.py             # Port 5006
│   └── writer_agent.py           # Port 5007
├── PostSwarm.html                # Single-file React frontend (no build step)
├── VOICE.md                      # Writing persona — edit this
├── bookmarklet.js                # LinkedIn bookmarklet (readable source)
├── start.sh                      # Start all 9 processes
├── stop.sh                       # Stop all agents
├── requirements.txt
├── .env.example                  # Copy to .env and add your API key
├── data/                         # SQLite DB + daily digest cache (auto-created)
└── logs/                         # Per-agent logs (auto-created)
```

---

## Stack

- **Backend**: Python 3.11+, Flask, feedparser
- **AI**: Google Gemini (`google-genai` SDK) — 2.5 Flash default, 2.5 Pro available
- **Frontend**: React 18 (CDN), vanilla SSE — no build step needed
- **Storage**: SQLite (`data/seen.db`) for feed dedup and inspiration store
- **Concurrency**: `ThreadPoolExecutor` for parallel agent calls

---

## Security (prototype limitations)

Designed for **local use only**.

| Risk | Status |
|------|--------|
| SSRF | ✅ URL validation blocks private IPs, `file://`, cloud metadata endpoints |
| Input limits | ✅ Topic ≤ 2000 chars, take ≤ 500, role ≤ 100 |
| Model whitelist | ✅ Only listed Gemini models accepted |
| CORS | ✅ Worker agents restricted to localhost origins |
| Prompt injection | ⚠️ Inputs are delimited — LLMs remain inherently susceptible |
| Authentication | ❌ None — localhost only |
| Rate limiting | ❌ None — add before any shared deployment |
| HTTPS | ❌ None — HTTP only, fine for localhost |

**Do not expose port 8080 to the internet without adding auth and rate limiting.**

---

## What's next

- **Past posts memory** — feed your actual LinkedIn history so the editor avoids repetition automatically
- **Multi-model routing** — Claude for writing, Gemini for research
- **Auto-schedule** — queue and publish directly to LinkedIn
- **Judge agent** — scores drafts before surfacing them
- **Slack/Telegram digest** — push the daily brief to a channel instead of opening the app

---

*Built by [Novianto](https://www.linkedin.com/in/snovianto/) — Singapore-based People Manager in tech. Prototype, expect rough edges.*
