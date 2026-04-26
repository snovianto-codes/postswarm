# PostSwarm

> 7 agents. One LinkedIn post. Your voice.

PostSwarm is a multi-agent system that generates LinkedIn posts by running a full research-and-writing pipeline — fact-checking, devil's advocate analysis, SEA perspective, hook generation, and final writing — all coordinated by an orchestrator and streamed live to the browser UI.

---

## Agent Architecture

```
Browser (PostSwarm.html)
        │
        │  SSE stream (GET /run)
        ▼
┌───────────────────┐
│   Orchestrator    │  :5000  ← entry point
└───────┬───────────┘
        │
        │  POST /run
        ▼
┌───────────────────┐
│  Research Agent   │  :5001
└──┬────────────────┘
   │
   ├──── POST /run ──► Web Agent         :5002  (5 research points)
   │                        │
   │                        ▼ (data_points)
   ├──── POST /run ──► Fact Checker      :5003  (verified points)
   │
   └──── POST /run ──► Devil's Advocate  :5004  (counter-arguments)

        │  (parallel)
        ├──── POST /run ──► Hook Agent        :5006  (5 hooks)
        └──── POST /run ──► Perspective Agent :5005  (SEA insights)

        │
        ▼
┌───────────────────┐
│   Writer Agent    │  :5007  (final LinkedIn post)
└───────────────────┘
```

**Pipeline stages:**

```
1. Research Agent  →  calls Web + Fact Checker + Devil's Advocate
2. Hook + Perspective  →  run in parallel
3. Writer Agent    →  assembles everything into the final post
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/postswarm.git
cd postswarm
cp .env.example .env          # add your GEMINI_API_KEY
```

Or create `.env` manually:

```
GEMINI_API_KEY=your_key_here
```

### 2. Start the backend

```bash
bash start.sh
```

This will:
- Install all Python dependencies
- Start all 7 agents on ports 5001–5007
- Start the orchestrator on port 5000

### 3. Open the frontend

Open `PostSwarm.html` directly in your browser (no server needed):

```
open PostSwarm.html
```

Or drag it into Chrome/Safari.

### 4. Stop everything

```bash
bash stop.sh
```

---

## Example Input

| Field | Value |
|-------|-------|
| Topic | Kimi K2.6 just launched with 300 AI sub-agents |
| My Take | impressive tech but most teams aren't ready |
| Tone | Skeptical |

## Example Output

```
300 AI sub-agents. Most teams can't handle 3.

Kimi K2.6 launched this week. The benchmarks are real. The demos are slick.

But here's what actually matters: 65% of enterprises use AI in at least one function —
yet fewer than 30% have it integrated into core workflows. The gap isn't the model.
It's the infrastructure, the governance, and the people.

Most teams don't have observability into single LLM calls, let alone 300 coordinated agents.

In Singapore and across SEA, I watch teams buy the tool, skip the change management,
and wonder why adoption stalls at the pilot stage.

What's your team actually doing to prepare for agentic AI?

#AI #AgentAI #SEA #FutureOfWork
```

---

## Project Structure

```
postswarm/
├── agents/
│   ├── orchestrator.py         # :5000 — SSE hub, pipeline coordinator
│   ├── research_agent.py       # :5001 — calls web + fact + devil
│   ├── web_agent.py            # :5002 — Gemini: 5 research points
│   ├── factchecker_agent.py    # :5003 — Gemini: verify/label points
│   ├── devils_advocate_agent.py # :5004 — Gemini: counter-arguments
│   ├── perspective_agent.py    # :5005 — Gemini: SEA team insights
│   ├── hook_agent.py           # :5006 — Gemini: 5 LinkedIn hooks
│   └── writer_agent.py         # :5007 — Gemini 1.5 Pro: final post
├── VOICE.md                    # author voice profile
├── PostSwarm.html              # frontend UI (no build step)
├── start.sh                    # start all agents
├── stop.sh                     # kill all agents
├── requirements.txt
└── .env                        # GEMINI_API_KEY (not committed)
```

---

## Tech Stack

- **Backend**: Python, Flask, flask-cors
- **AI**: Google Gemini 2.0 Flash (research agents) + Gemini 1.5 Pro (writer)
- **Frontend**: React 18 (CDN), Tailwind CSS, vanilla SSE
- **Concurrency**: Python `ThreadPoolExecutor` for parallel agent calls

---

## Requirements

- Python 3.9+
- A valid `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/)
- Ports 5000–5007 available

---

## Notes

- The UI runs in **Demo mode** if the backend is unreachable — useful for testing the UI without credentials.
- The Writer Agent tries `gemini-1.5-pro` first, falls back to `gemini-2.0-flash` automatically.
- All agents include fallback responses — the pipeline always completes even if individual agents fail.
