from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
import pytest

from alexrag.agents.audit_log import AuditLog
from alexrag.agents.risk import RiskAgent
from alexrag.broker.alpaca_paper import (
    ALPACA_KEY_ID_ENV,
    ALPACA_SECRET_KEY_ENV,
    AlpacaPaperBroker,
    alpaca_paper_credentials_present,
)
from alexrag.config import ROOT, Settings, load_settings
from alexrag.llm.inferhub import (
    INFERHUB_API_KEY_ENV,
    INFERHUB_MODEL,
    INFERHUB_PROVIDER,
    INFERHUB_PROVIDER_ENV,
    InferhubClient,
)
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.proposal import Citation, Proposal
from alexrag.schemas.reasons import AbstainReason


def _go_proposal() -> Proposal:
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    return Proposal.model_validate(
        {
            "proposal_id": "p-op",
            "decision_clock": clock,
            "tickers": ["NVDA"],
            "regime": "trend_day",
            "size_ner_pct": 0.25,
            "confidence": 0.7,
            "abstain": False,
            "abstain_reason": None,
            "citations": [
                Citation(
                    source_id="tl",
                    source_type="trade_log",
                    chunk_id="c1",
                    excerpt="Trade log: filled $NVDA long. Size NER 0.25%.",
                    timestamp=datetime(2026, 9, 15, 18, 10, tzinfo=timezone.utc),
                )
            ],
        }
    )


def test_operator_pcts_derive_dollars_from_equity() -> None:
    settings = load_settings(overrides={"paper": {"nav": 100000.0}})
    assert settings.hard_limits.max_positions == 15
    assert settings.hard_limits.max_daily_loss_pct == 0.10
    assert settings.hard_limits.max_portfolio_dd == 0.25
    assert settings.hard_limits.max_notional_pct == 1.5
    assert settings.max_notional_dollars() == 150000.0
    assert settings.max_daily_loss_dollars() == 10000.0
    snap = settings.hard_limits_snapshot()
    assert snap["max_notional"] == 150000.0
    assert snap["notional_breach_policy"] == "pro_rata_trim_for_new_entry"
    assert snap["max_daily_loss"] == 10000.0
    assert snap["paper_equity"] == 100000.0


def test_nav_zero_cannot_derive_dollars(tmp_path: Path) -> None:
    settings = load_settings()
    assert settings.hard_limits.max_positions == 15
    assert settings.paper.nav == 0.0
    assert settings.hard_limits_ready() is False
    out = RiskAgent().run(_go_proposal(), settings, AuditLog(tmp_path / "nav.jsonl"))
    assert out.abstain is True
    assert out.abstain_reason == AbstainReason.HARD_LIMITS_UNCONFIGURED


def test_llm_locked_to_inferhub_cbcn() -> None:
    settings = load_settings()
    assert settings.llm.provider == "inferhub"
    assert settings.llm.model == "cbcn/glm-5.3-flash"
    assert settings.llm.base_url == "https://api.inferhub.dev/v1"
    assert settings.llm.inferhub_provider == "cbcn"
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"provider": "openai"}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"inferhub_provider": "inferhub.dev"}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"model": "GLM-5.3-flash"}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"model": "other/GLM-5.3-flash"}})


def test_inferhub_stub_presence_only_never_returns_key(monkeypatch) -> None:
    monkeypatch.delenv(INFERHUB_API_KEY_ENV, raising=False)
    monkeypatch.delenv(INFERHUB_PROVIDER_ENV, raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INFERHUB_BASE_URL", raising=False)
    cold = InferhubClient()
    assert cold.configured is False
    assert cold.provider == INFERHUB_PROVIDER
    payload = cold.complete([{"role": "user", "content": "hello"}])
    assert payload["status"] == "stubbed"
    assert payload["provider"] == "cbcn"
    assert payload["request"]["provider"] == "cbcn"
    assert payload["request"]["model"] == INFERHUB_MODEL
    assert payload["model"] == INFERHUB_MODEL
    assert payload["llm_provider"] == "inferhub"
    assert payload["base_url"] == "https://api.inferhub.dev/v1"
    assert payload["text"] is None
    blob = str(payload)
    assert "sk-" not in blob
    assert INFERHUB_API_KEY_ENV in blob  # env *name* is documented
    assert INFERHUB_PROVIDER_ENV in blob

    monkeypatch.setenv(INFERHUB_API_KEY_ENV, "secret-must-not-leak")
    hot = InferhubClient()
    assert hot.configured is True

    class _Resp:
        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"ok"}}]}'

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "alexrag.llm.inferhub.urllib.request.urlopen", lambda *a, **k: _Resp()
    )
    hot_payload = hot.complete()
    assert hot_payload["configured"] is True
    assert hot_payload["status"] == "ok"
    assert hot_payload["text"] == "ok"
    assert hot_payload["request"]["provider"] == "cbcn"
    assert hot_payload["request"]["model"] == INFERHUB_MODEL
    assert "secret-must-not-leak" not in str(hot_payload)
    assert "secret-must-not-leak" not in repr(hot)

    with pytest.raises(ValueError, match="cbcn"):
        InferhubClient(provider="other-upstream")
    with pytest.raises(ValueError, match="cbcn"):
        cold.complete(provider="openai")
    with pytest.raises(ValueError, match="cbcn"):
        InferhubClient(model="GLM-5.3-flash")
    with pytest.raises(ValueError, match="cbcn"):
        cold.complete(model="other/GLM-5.3-flash")

    monkeypatch.setenv(INFERHUB_PROVIDER_ENV, "not-cbcn")
    with pytest.raises(ValueError, match="cbcn"):
        InferhubClient()


def test_alpaca_paper_env_names_presence_only(monkeypatch) -> None:
    monkeypatch.delenv(ALPACA_KEY_ID_ENV, raising=False)
    monkeypatch.delenv(ALPACA_SECRET_KEY_ENV, raising=False)
    assert alpaca_paper_credentials_present() is False
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    intent = FillIntent(
        intent_id="i",
        proposal_id="p",
        mode="paper",
        ticker="NVDA",
        side="buy",
        order_type="market",
        notional=250.0,
        qty=2.0,
        size_ner_pct=0.25,
        decision_clock=clock,
        abstain=False,
    )
    missing = AlpacaPaperBroker().submit_paper(intent)
    assert missing.status == "stubbed"
    assert missing.filled is False
    assert missing.skip_reason == "alpaca_paper_no_keys"

    monkeypatch.setenv(ALPACA_KEY_ID_ENV, "id-must-not-leak")
    monkeypatch.setenv(ALPACA_SECRET_KEY_ENV, "secret-must-not-leak")
    assert alpaca_paper_credentials_present() is True
    present = AlpacaPaperBroker().submit_paper(intent)
    assert present.status == "stubbed"
    assert present.filled is False
    assert present.qty_filled == 0
    assert present.skip_reason == "alpaca_paper_stub_no_network"
    dumped = present.model_dump()
    assert "id-must-not-leak" not in str(dumped)
    assert "secret-must-not-leak" not in str(dumped)


def test_inferhub_provider_env_must_be_cbcn(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "inferhub")
    monkeypatch.setenv("LLM_MODEL", "cbcn/GLM-5.3-flash")
    monkeypatch.setenv("INFERHUB_BASE_URL", "https://api.inferhub.dev/v1")
    monkeypatch.setenv("INFERHUB_PROVIDER", "cbcn")
    settings = load_settings(load_env_file=False)
    assert settings.llm.provider == "inferhub"
    assert settings.llm.model == "cbcn/glm-5.3-flash"
    assert settings.llm.inferhub_provider == "cbcn"
    monkeypatch.setenv("INFERHUB_PROVIDER", "other")
    with pytest.raises(ValidationError):
        load_settings(load_env_file=False)
    monkeypatch.setenv("INFERHUB_PROVIDER", "cbcn")
    monkeypatch.setenv("LLM_MODEL", "other/GLM-5.3-flash")
    with pytest.raises(ValidationError):
        load_settings(load_env_file=False)


def test_paper_nav_env_derives_dollars(monkeypatch) -> None:
    monkeypatch.setenv("ALEXRAG_PAPER_NAV", "50000")
    settings = load_settings(load_env_file=False)
    assert settings.paper.nav == 50000.0
    assert settings.max_notional_dollars() == 75000.0
    assert settings.max_daily_loss_dollars() == 5000.0



def test_inferhub_model_case_insensitive_normalize(monkeypatch) -> None:
    """Accept capital-GLM lock spelling; HTTP model is always lowercase canonical."""

    monkeypatch.delenv(INFERHUB_API_KEY_ENV, raising=False)
    for spelling in ("cbcn/GLM-5.3-flash", "cbcn/glm-5.3-flash", "cbcn/Glm-5.3-Flash"):
        client = InferhubClient(model=spelling)
        assert client.model == INFERHUB_MODEL == "cbcn/glm-5.3-flash"
        body = client.request_body([{"role": "user", "content": "x"}])
        assert body["model"] == "cbcn/glm-5.3-flash"
    settings = Settings.model_validate({"llm": {"model": "cbcn/GLM-5.3-flash"}})
    assert settings.llm.model == "cbcn/glm-5.3-flash"
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"model": "cbcn/other-model"}})
    with pytest.raises(ValueError, match="cbcn"):
        InferhubClient(model="other/glm-5.3-flash")


def test_secrets_stay_out_of_git() -> None:
    root = ROOT
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "INFERHUB_API_KEY=" in example
    assert "INFERHUB_PROVIDER=cbcn" in example
    assert "LLM_PROVIDER=inferhub" in example
    assert "LLM_MODEL=cbcn/glm-5.3-flash" in example
    assert "INFERHUB_BASE_URL=https://api.inferhub.dev/v1" in example
    assert "ALPACA_API_KEY_ID=" in example
    assert "ALPACA_API_SECRET_KEY=" in example
    # Placeholders only — no assigned secret values in the example.
    for line in example.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            if key in {INFERHUB_API_KEY_ENV, ALPACA_KEY_ID_ENV, ALPACA_SECRET_KEY_ENV}:
                assert value == ""

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert any(line.strip() == ".env" for line in gitignore.splitlines())

    src = "\n".join(p.read_text(encoding="utf-8") for p in (root / "src").rglob("*.py"))
    assert "ALPACA_API_KEY_ID" in src
    assert "ALPACA_API_SECRET_KEY" in src
    assert INFERHUB_API_KEY_ENV in src
    assert "ALPACA_API_KEY=" not in src
    assert "ALPACA_API_SECRET=" not in src
