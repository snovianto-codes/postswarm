import pytest

import core.model_client as mc


def test_call_model_success_does_not_touch_fallback(monkeypatch):
    monkeypatch.setattr(mc, '_resolve', lambda role, request_model: {
        'provider': 'gemini', 'model': 'primary-model',
        'fallback': {'provider': 'gemini', 'model': 'fallback-model'},
    })
    calls = []

    def fake_dispatch(provider, model, prompt, timeout):
        calls.append((provider, model))
        return ("primary text", 5, 7)

    monkeypatch.setattr(mc, '_dispatch', fake_dispatch)

    resp = mc.call_model('writer', 'a prompt')

    assert resp.text == "primary text"
    assert resp.provider == 'gemini'
    assert resp.model == 'primary-model'
    assert calls == [('gemini', 'primary-model')]


def test_call_model_falls_back_on_primary_failure(monkeypatch):
    monkeypatch.setattr(mc, '_resolve', lambda role, request_model: {
        'provider': 'gemini', 'model': 'primary-model',
        'fallback': {'provider': 'gemini', 'model': 'fallback-model'},
    })
    calls = []

    def fake_dispatch(provider, model, prompt, timeout):
        calls.append((provider, model))
        if model == 'primary-model':
            raise RuntimeError("boom")
        return ("fallback text", 10, 20)

    monkeypatch.setattr(mc, '_dispatch', fake_dispatch)

    resp = mc.call_model('writer', 'a prompt')

    assert resp.text == "fallback text"
    assert resp.model == 'fallback-model'
    assert calls == [('gemini', 'primary-model'), ('gemini', 'fallback-model')]


def test_call_model_raises_when_no_fallback_configured(monkeypatch):
    monkeypatch.setattr(mc, '_resolve', lambda role, request_model: {
        'provider': 'gemini', 'model': 'primary-model', 'fallback': None,
    })
    monkeypatch.setattr(mc, '_dispatch', lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(mc.ModelClientError):
        mc.call_model('writer', 'a prompt')


def test_call_model_skips_retry_when_fallback_is_identical_to_primary(monkeypatch):
    monkeypatch.setattr(mc, '_resolve', lambda role, request_model: {
        'provider': 'gemini', 'model': 'same-model',
        'fallback': {'provider': 'gemini', 'model': 'same-model'},
    })
    calls = []

    def fake_dispatch(provider, model, prompt, timeout):
        calls.append((provider, model))
        raise RuntimeError("boom")

    monkeypatch.setattr(mc, '_dispatch', fake_dispatch)

    with pytest.raises(mc.ModelClientError):
        mc.call_model('writer', 'a prompt')

    # identical fallback is skipped — only one attempt, not two
    assert calls == [('gemini', 'same-model')]


def test_call_model_raises_when_both_primary_and_fallback_fail(monkeypatch):
    monkeypatch.setattr(mc, '_resolve', lambda role, request_model: {
        'provider': 'gemini', 'model': 'primary-model',
        'fallback': {'provider': 'gemini', 'model': 'fallback-model'},
    })
    monkeypatch.setattr(mc, '_dispatch', lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(mc.ModelClientError):
        mc.call_model('writer', 'a prompt')


def test_resolve_defaults_when_role_missing_from_config(monkeypatch):
    monkeypatch.setattr(mc, '_load_models_config', lambda: {})

    resolved = mc._resolve('some_role', None)

    assert resolved == {'provider': mc.DEFAULT_PROVIDER, 'model': mc.DEFAULT_MODEL, 'fallback': None}


def test_resolve_honors_explicit_request_model(monkeypatch):
    monkeypatch.setattr(mc, '_load_models_config', lambda: {
        'writer': {'provider': 'gemini', 'model': 'configured-model'},
    })

    resolved = mc._resolve('writer', 'requested-model')

    assert resolved == {'provider': 'gemini', 'model': 'requested-model', 'fallback': None}
