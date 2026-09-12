import pytest

import core.moa as moa


def _config(enabled=True, n_proposers=2):
    proposers = [{'provider': 'gemini', 'model': f'model-{i}'} for i in range(n_proposers)]
    return {'moa': {'enabled': enabled, 'proposers': proposers,
                     'aggregator': {'provider': 'gemini', 'model': 'agg-model'}}}


class FakeResponse:
    def __init__(self, text, model):
        self.text = text
        self.provider = 'gemini'
        self.model = model
        self.cost_usd = 0.001


def test_moa_matches_the_real_config_file():
    # Real config/models.yaml, no mocking. Enabled after comparing MoA vs
    # single-model output via scripts/compare_moa.py and choosing MoA.
    assert moa.is_enabled() is True


def test_is_enabled_reads_config(monkeypatch):
    monkeypatch.setattr(moa, 'get_config', lambda: _config(enabled=True))
    assert moa.is_enabled() is True

    monkeypatch.setattr(moa, 'get_config', lambda: _config(enabled=False))
    assert moa.is_enabled() is False


def test_draft_moa_combines_proposers_via_aggregator(monkeypatch):
    monkeypatch.setattr(moa, 'get_config', lambda: _config(n_proposers=2))

    def fake_call_model(role, prompt, request_model=None, timeout=30):
        if request_model == 'agg-model':
            return FakeResponse("merged final post", 'agg-model')
        return FakeResponse(f"draft from {request_model}", request_model)

    monkeypatch.setattr(moa, 'call_model', fake_call_model)

    result = moa.draft_moa("write something")

    assert result.post == "merged final post"
    assert len(result.proposer_drafts) == 2
    assert result.aggregator.model == 'agg-model'


def test_draft_moa_tolerates_one_proposer_failure(monkeypatch):
    monkeypatch.setattr(moa, 'get_config', lambda: _config(n_proposers=2))

    def fake_call_model(role, prompt, request_model=None, timeout=30):
        if request_model == 'model-0':
            raise moa.ModelClientError("boom")
        if request_model == 'agg-model':
            return FakeResponse("merged final post", 'agg-model')
        return FakeResponse(f"draft from {request_model}", request_model)

    monkeypatch.setattr(moa, 'call_model', fake_call_model)

    result = moa.draft_moa("write something")

    assert len(result.proposer_drafts) == 1
    assert result.post == "merged final post"


def test_draft_moa_raises_when_all_proposers_fail(monkeypatch):
    monkeypatch.setattr(moa, 'get_config', lambda: _config(n_proposers=2))
    monkeypatch.setattr(moa, 'call_model',
                         lambda *a, **k: (_ for _ in ()).throw(moa.ModelClientError("boom")))

    with pytest.raises(moa.MoAError):
        moa.draft_moa("write something")


def test_draft_moa_raises_when_aggregator_fails(monkeypatch):
    monkeypatch.setattr(moa, 'get_config', lambda: _config(n_proposers=2))

    def fake_call_model(role, prompt, request_model=None, timeout=30):
        if request_model == 'agg-model':
            raise moa.ModelClientError("aggregator boom")
        return FakeResponse(f"draft from {request_model}", request_model)

    monkeypatch.setattr(moa, 'call_model', fake_call_model)

    with pytest.raises(moa.MoAError):
        moa.draft_moa("write something")


def test_moa_config_requires_proposers_and_aggregator(monkeypatch):
    monkeypatch.setattr(moa, 'get_config', lambda: {'moa': {'enabled': True, 'proposers': [], 'aggregator': None}})

    with pytest.raises(moa.MoAError):
        moa.draft_moa("write something")
