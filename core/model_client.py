"""Model client — provider-agnostic LLM calls for all PostSwarm agents.

Every agent that used to build its own google-genai client and hand-roll a
fallback loop should call `call_model(role, prompt, ...)` instead. Model
assignment per role comes from config/models.yaml; if that file is missing,
or a role isn't listed in it, every role defaults to gemini-2.5-flash so
behavior is unchanged from before this module existed.
"""
import os
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests as http
import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
_ENV_PATH = _ROOT / '.env'
_MODELS_CONFIG_PATH = _ROOT / 'config' / 'models.yaml'
_PRICES_CONFIG_PATH = _ROOT / 'config' / 'prices.yaml'

DEFAULT_PROVIDER = 'gemini'
DEFAULT_MODEL = 'gemini-2.5-flash'
HTTP_TIMEOUT_DEFAULT = 30

load_dotenv(_ENV_PATH)


class ModelClientError(Exception):
    """Raised when both the primary model and its configured fallback fail."""


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_ms: int
    cost_usd: Optional[float]


# ── Config loading (cheap mtime check so edits apply without restarting
#    every agent process, matching the existing GEMINI_API_KEY reload
#    pattern used across the agents) ──────────────────────────────────

_config_cache = {'mtime': None, 'data': {}}
_prices_cache = {'mtime': None, 'data': {}}


def _load_yaml_cached(path: Path, cache: dict) -> dict:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        cache['mtime'] = None
        cache['data'] = {}
        return {}
    if cache['mtime'] != mtime:
        with open(path) as f:
            cache['data'] = yaml.safe_load(f) or {}
        cache['mtime'] = mtime
    return cache['data']


def _load_models_config() -> dict:
    return _load_yaml_cached(_MODELS_CONFIG_PATH, _config_cache)


def _load_prices_config() -> dict:
    return _load_yaml_cached(_PRICES_CONFIG_PATH, _prices_cache)


def _resolve(role: str, request_model: Optional[str]) -> dict:
    """Return {'provider', 'model', 'fallback': {...} or None} for this call."""
    if request_model:
        # Every caller today only ever passes a Gemini model name here
        # (orchestrator's ALLOWED_MODELS is Gemini-only), so an explicit
        # request_model always means "use Gemini with this model" — this
        # preserves the existing user-facing model-picker behavior exactly.
        return {'provider': 'gemini', 'model': request_model, 'fallback': None}

    config = _load_models_config()
    entry = config.get(role)
    if not entry:
        default_fallback = (config.get('defaults') or {}).get('fallback')
        return {'provider': DEFAULT_PROVIDER, 'model': DEFAULT_MODEL,
                'fallback': default_fallback}

    fallback = entry.get('fallback') or (config.get('defaults') or {}).get('fallback')
    return {'provider': entry.get('provider', DEFAULT_PROVIDER),
            'model': entry.get('model', DEFAULT_MODEL),
            'fallback': fallback}


def _price_for(provider: str, model: str) -> Optional[dict]:
    prices = _load_prices_config()
    return (prices.get(provider) or {}).get(model)


def _estimate_cost(provider: str, model: str, input_tokens, output_tokens) -> Optional[float]:
    if input_tokens is None or output_tokens is None:
        return None
    price = _price_for(provider, model)
    if not price:
        return None
    return round(
        (input_tokens / 1000) * price.get('input_per_1k', 0)
        + (output_tokens / 1000) * price.get('output_per_1k', 0),
        6,
    )


# ── Provider calls ───────────────────────────────────────────────────

def _call_gemini(model: str, prompt: str, timeout: int):
    from google import genai
    load_dotenv(_ENV_PATH, override=True)
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    response = client.models.generate_content(model=model, contents=prompt)
    usage = getattr(response, 'usage_metadata', None)
    input_tokens = getattr(usage, 'prompt_token_count', None) if usage else None
    output_tokens = getattr(usage, 'candidates_token_count', None) if usage else None
    return response.text.strip(), input_tokens, output_tokens


def _call_openrouter(model: str, prompt: str, timeout: int):
    api_key = os.environ['OPENROUTER_API_KEY']
    r = http.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}'},
        json={'model': model, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    text = body['choices'][0]['message']['content'].strip()
    usage = body.get('usage') or {}
    return text, usage.get('prompt_tokens'), usage.get('completion_tokens')


def _call_anthropic(model: str, prompt: str, timeout: int):
    api_key = os.environ['ANTHROPIC_API_KEY']
    r = http.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': model,
            'max_tokens': 4096,
            'messages': [{'role': 'user', 'content': prompt}],
        },
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    text = body['content'][0]['text'].strip()
    usage = body.get('usage') or {}
    return text, usage.get('input_tokens'), usage.get('output_tokens')


def _call_ollama(model: str, prompt: str, timeout: int):
    base_url = os.environ['OLLAMA_BASE_URL'].rstrip('/')
    r = http.post(
        f'{base_url}/api/generate',
        json={'model': model, 'prompt': prompt, 'stream': False},
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    text = (body.get('response') or '').strip()
    return text, body.get('prompt_eval_count'), body.get('eval_count')


_PROVIDER_FUNCS = {
    'gemini': _call_gemini,
    'openrouter': _call_openrouter,
    'anthropic': _call_anthropic,
    'ollama': _call_ollama,
}


def _dispatch(provider: str, model: str, prompt: str, timeout: int):
    func = _PROVIDER_FUNCS.get(provider)
    if func is None:
        raise ModelClientError(f"Unknown provider: {provider}")
    return func(model, prompt, timeout)


# ── Public entry point ───────────────────────────────────────────────

def call_model(role: str, prompt: str, request_model: Optional[str] = None,
                timeout: int = HTTP_TIMEOUT_DEFAULT) -> ModelResponse:
    """Resolve the model for `role` (or honor an explicit request_model),
    call it, and fall back once on error if a fallback is configured.
    Raises ModelClientError only if the primary AND the fallback both fail
    (or no fallback is configured and the primary fails) — callers should
    catch this and degrade the same way they did before this module existed
    (e.g. return an empty result, mark the agent FAILED)."""
    resolved = _resolve(role, request_model)
    provider, model, fallback = resolved['provider'], resolved['model'], resolved['fallback']

    t0 = time.time()
    try:
        text, in_tok, out_tok = _dispatch(provider, model, prompt, timeout)
        latency_ms = int((time.time() - t0) * 1000)
        return ModelResponse(
            text=text, provider=provider, model=model,
            input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms,
            cost_usd=_estimate_cost(provider, model, in_tok, out_tok),
        )
    except Exception as primary_err:
        print(f"[model_client] [{role}] {provider}/{model} FAILED: "
              f"{type(primary_err).__name__}: {primary_err}")
        print(traceback.format_exc())

        if not fallback:
            raise ModelClientError(
                f"{role}: {provider}/{model} failed and no fallback configured: {primary_err}"
            ) from primary_err

        fb_provider = fallback.get('provider', DEFAULT_PROVIDER)
        fb_model = fallback.get('model', DEFAULT_MODEL)
        t1 = time.time()
        try:
            text, in_tok, out_tok = _dispatch(fb_provider, fb_model, prompt, timeout)
            latency_ms = int((time.time() - t1) * 1000)
            print(f"[model_client] [{role}] recovered via fallback {fb_provider}/{fb_model}")
            return ModelResponse(
                text=text, provider=fb_provider, model=fb_model,
                input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms,
                cost_usd=_estimate_cost(fb_provider, fb_model, in_tok, out_tok),
            )
        except Exception as fallback_err:
            print(f"[model_client] [{role}] fallback {fb_provider}/{fb_model} ALSO FAILED: "
                  f"{type(fallback_err).__name__}: {fallback_err}")
            raise ModelClientError(
                f"{role}: primary {provider}/{model} and fallback {fb_provider}/{fb_model} "
                f"both failed. primary={primary_err!r} fallback={fallback_err!r}"
            ) from fallback_err
