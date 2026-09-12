"""MoA (Mixture-of-Agents) drafting for the writer role — Phase 2.

Fires each configured proposer model on the same prompt in parallel, then
sends every proposer draft to a configured aggregator model, which picks or
merges them into one final post. Off by default via config/models.yaml's
`moa.enabled` — see agents/writer_agent.py, which falls back to a single
call_model('writer', ...) when this is disabled.
"""
import concurrent.futures
from dataclasses import dataclass
from typing import List, Optional

from core.model_client import call_model, ModelClientError, ModelResponse, get_config


class MoAError(Exception):
    """Raised when every proposer fails, or the aggregator call fails."""


@dataclass
class MoAResult:
    post: str
    proposer_drafts: List[ModelResponse]
    aggregator: ModelResponse


def is_enabled() -> bool:
    return bool((get_config().get('moa') or {}).get('enabled'))


def _moa_config() -> dict:
    moa = get_config().get('moa') or {}
    proposers = moa.get('proposers') or []
    aggregator = moa.get('aggregator')
    if not proposers or not aggregator:
        raise MoAError("config/models.yaml 'moa' section needs at least one "
                        "proposer and an aggregator")
    return {'proposers': proposers, 'aggregator': aggregator}


def _try_proposer(entry: dict, prompt: str, timeout: int) -> Optional[ModelResponse]:
    try:
        # request_model carries the proposer's model name straight through
        # call_model; role='writer' is only used for its log-line label.
        return call_model('writer', prompt, request_model=entry['model'], timeout=timeout)
    except ModelClientError as e:
        print(f"[moa] proposer {entry.get('model')} failed: {e}")
        return None


def _build_aggregation_prompt(original_prompt: str, drafts: List[ModelResponse]) -> str:
    numbered = "\n\n".join(
        f"--- DRAFT {i + 1} ({d.provider}/{d.model}) ---\n{d.text}"
        for i, d in enumerate(drafts)
    )
    return f"""You were given this writing assignment:

{original_prompt}

{len(drafts)} independent drafts were written for this assignment:

{numbered}

Pick the single best draft, or merge the strongest parts of each into one
better post. Follow every rule from the original assignment above (voice,
word count, banned words/structures) exactly as if you had written it
yourself from scratch.

Return ONLY the final post text. No preamble, no explanation, no mention
that this came from multiple drafts."""


def draft_moa(prompt: str, timeout: int = 30) -> MoAResult:
    """Run every configured proposer on `prompt` in parallel, then have the
    aggregator combine whichever drafts succeeded into one final post.
    Raises MoAError if every proposer fails, or if the aggregator call
    itself fails."""
    cfg = _moa_config()
    proposers = cfg['proposers']

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(proposers)) as pool:
        results = list(pool.map(lambda entry: _try_proposer(entry, prompt, timeout), proposers))

    drafts = [r for r in results if r is not None]
    if not drafts:
        raise MoAError("all MoA proposers failed")

    aggregation_prompt = _build_aggregation_prompt(prompt, drafts)
    try:
        aggregator_resp = call_model('writer', aggregation_prompt,
                                      request_model=cfg['aggregator']['model'], timeout=timeout)
    except ModelClientError as e:
        raise MoAError(f"aggregator failed: {e}") from e

    return MoAResult(post=aggregator_resp.text, proposer_drafts=drafts, aggregator=aggregator_resp)
