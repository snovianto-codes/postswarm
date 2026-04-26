# PostSwarm 🐝

> **⚠️ Prototype — built for learning, not production. Rough edges expected.**

A multi-agent system that generates LinkedIn posts by coordinating 7 specialised AI agents. Each agent handles one job: research, fact-checking, counter-arguments, SEA perspective, hook writing, and final assembly. They run in parallel where possible and stream live progress to the browser.

---

## What it does

Give it a topic (plain text or paste a URL to an article). Seven agents coordinate:

```
Orchestrator (port 8080)
├── Research Agent (5001)
│   ├── Web Agent (5002)          — fetches the URL or generates research points
│   ├── Fact Checker (5003)       — verifies and cleans the research
│   └── Devil's Advocate (5004)   — generates honest counter-arguments
├── Perspective Agent (5005)      — adds SEA / role-specific angle  [parallel]
├── Hook Agent (5006)             — writes 5 opening line variants  [parallel]
└── Writer Agent (5007)           — assembles the final post
```

The browser streams live agent activity via SSE. Each card shows what the agent is doing in real time. After completion, expand any card to see exactly what it found or produced.

---

## Quick start

**1. Clone**
```bash
git clone https://github.com/yourusername/postswarm.git
cd postswarm
```

**2. Add your Gemini API key**
```bash
cp .env.example .env
# Edit .env:
# GEMINI_API_KEY=your_key_here
```
Get a free key at [Google AI Studio](https://aistudio.google.com/).

**3. Start**
```bash
bash start.sh
```
Open **http://localhost:8080**

**4. Stop**
```bash
bash stop.sh
```

Logs are written to `logs/*.log` (one file per agent). If the output is blank or agents complete suspiciously fast, restart with `bash stop.sh && bash start.sh` — this usually means a stale process hit a rate limit.

---

## How to use

| Field | What it does |
|-------|-------------|
| **Topic** | Plain text or paste a URL — Web Agent will fetch and read the article |
| **My Take** | Your angle or opinion |
| **Tone** | Skeptical / Curious / Excited / Provocative / Balanced |
| **Role** | Your professional perspective (People Manager, Engineer, CTO…) — shapes the angle |
| **Model** | Gemini model to use — higher quality = slower/more expensive |

Click **"View details"** on any completed agent card to see what it produced.

---

## Customise your voice

Edit `VOICE.md` to define the writing persona. The Writer Agent reads this on every run. Write it in first person, describe your communication style, what topics you care about, and phrases to avoid.

---

## Project structure

```
postswarm/
├── agents/
│   ├── orchestrator.py           # Port 8080 — serves HTML + pipeline coordinator
│   ├── research_agent.py         # Port 5001
│   ├── web_agent.py              # Port 5002
│   ├── factchecker_agent.py      # Port 5003
│   ├── devils_advocate_agent.py  # Port 5004
│   ├── perspective_agent.py      # Port 5005
│   ├── hook_agent.py             # Port 5006
│   └── writer_agent.py           # Port 5007
├── PostSwarm.html                # Single-file React frontend (no build step)
├── VOICE.md                      # Writing persona — edit this
├── start.sh                      # Start all 8 processes
├── stop.sh                       # Stop all agents
├── requirements.txt
├── .env.example                  # Copy to .env and add your API key
└── logs/                         # Per-agent logs (auto-created)
```

---

## Stack

- **Backend**: Python 3.11+, Flask
- **AI**: Google Gemini (`google-genai` SDK) — model selectable per run
- **Frontend**: React 18 (CDN), Tailwind CSS, vanilla SSE — no build step needed
- **Concurrency**: `ThreadPoolExecutor` for parallel agent calls

---

## Security (prototype limitations)

Designed for **local use only**. Mitigations applied:

| Risk | Status |
|------|--------|
| SSRF | ✅ URL validation blocks private IPs, `file://`, cloud metadata endpoints |
| Input limits | ✅ Topic ≤ 2000 chars, take ≤ 500, role ≤ 100 |
| Model whitelist | ✅ Only the 4 listed Gemini models accepted |
| CORS | ✅ Worker agents restricted to localhost origins |
| Prompt injection | ⚠️ Inputs are delimited in prompts — LLMs remain inherently susceptible |
| Authentication | ❌ None — localhost only |
| Rate limiting | ❌ None — add before any shared deployment |
| HTTPS | ❌ None — HTTP only, fine for localhost |

**Do not expose port 8080 to the internet without adding auth and rate limiting.**

---

## What's next (v2 ideas)

This prototype uses Gemini only. Ideas for the next iteration:

- **Multi-model routing** — different agents use different models by task (Gemini for research, Claude for writing, etc.)
- **Pluggable model layer** — support OpenAI, Claude, Mistral alongside Gemini
- **Live web search** — replace URL-only research with Tavily or Serper
- **Judge agent** — scores drafts before accepting them
- **Memory** — build a personal style profile from posts you actually publish
- **Post scheduler** — queue and publish directly to LinkedIn

---

## Requirements

```
flask
flask-cors
google-genai
requests
python-dotenv
```

Python 3.11+ recommended. Ports 5001–5007 and 8080 must be free.

---

*Built by [Novianto](https://www.linkedin.com/in/snovianto/) — prototype, expect rough edges and the occasional hallucinated Gartner statistic.*
