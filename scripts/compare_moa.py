#!/usr/bin/env python3
"""Phase 2 comparison tool — run this before flipping config/models.yaml's
`moa.enabled` to true.

Runs the same sample topics through the existing single-model writer path
and the new MoA ensemble path, and prints every draft — the single-model
baseline, each individual proposer's draft, and the final merged post —
with latency and estimated cost, so you can judge by eye whether the
ensemble (and each proposer within it) is actually worth the extra calls.
This is deliberately NOT a pass/fail test — there's no automated quality
score for "is this a good LinkedIn post," so a human has to read them and
decide.

Usage: python scripts/compare_moa.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.writer_agent import build_prompt
from core.model_client import call_model, ModelClientError
from core.moa import draft_moa, MoAError

SAMPLE_TOPICS = [
    {
        'topic': 'A new study finds AI coding assistants slow down experienced '
                 'developers by 19% on real tasks, even though the developers '
                 'themselves felt they were working faster.',
        'take': 'This matches what I see on my own team — the perceived '
                'speedup and the real speedup are not the same thing.',
        'tone': 'Skeptical',
        'role': 'Engineering Manager',
    },
    {
        'topic': 'A major bank announces layoffs tied to AI-driven automation '
                 'of back-office roles.',
        'take': 'The headline number always looks bigger than the actual '
                'retraining and redeployment story underneath.',
        'tone': 'Analytical',
        'role': 'People Manager',
    },
]


def _run_single(prompt):
    t0 = time.time()
    resp = call_model('writer', prompt)
    ms = int((time.time() - t0) * 1000)
    return resp.text, f"{resp.provider}/{resp.model}", resp.cost_usd, ms


def _run_moa(prompt):
    t0 = time.time()
    result = draft_moa(prompt)
    ms = int((time.time() - t0) * 1000)
    cost = sum(d.cost_usd or 0 for d in result.proposer_drafts) + (result.aggregator.cost_usd or 0)
    return result, cost, ms


def main():
    for sample in SAMPLE_TOPICS:
        prompt = build_prompt(**sample)
        print("=" * 80)
        print(f"TOPIC: {sample['topic'][:70]}...")
        print("=" * 80)

        try:
            text, label, cost, ms = _run_single(prompt)
            cost_note = f", ${cost:.5f}" if cost else ""
            print(f"\n--- SINGLE MODEL ({label}, {ms}ms{cost_note}) ---")
            print(text)
        except ModelClientError as e:
            print(f"\n--- SINGLE MODEL FAILED: {e} ---")

        try:
            result, cost, ms = _run_moa(prompt)
            cost_note = f", ${cost:.5f}" if cost else ""

            for i, draft in enumerate(result.proposer_drafts):
                print(f"\n--- MoA PROPOSER {i + 1} ({draft.provider}/{draft.model}, "
                      f"{draft.latency_ms}ms) ---")
                print(draft.text)

            label = f"{len(result.proposer_drafts)} proposers -> {result.aggregator.model}"
            print(f"\n--- MoA MERGED ({label}, {ms}ms{cost_note}) ---")
            print(result.post)
        except MoAError as e:
            print(f"\n--- MoA FAILED: {e} ---")

        print()


if __name__ == '__main__':
    main()
