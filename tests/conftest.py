"""테스트 공통 설정.

픽스처를 판정 코드의 입력으로 옮기는 **어댑터를 여기 한 곳에 둔다.**

등급 축(`test_demo_fixture_consistency.py`)과 행동 축(`test_fixture_engine_agreement.py`)
이 각자 어댑터를 들고 있으면, 한쪽이 픽스처를 조금 정제하는 순간 그 파일은
"픽스처를 그대로 받는다"가 아니라 "정제하면 통과한다"를 증명하게 된다. 저장소가
이미 밟은 사고다(C-21). 그래서 **두 축이 같은 함수를 통과한다.**
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from services.decision.enums import AiRiskLevel, HazardSign, UserContext
from services.decision.service_risk import RiskSignals

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def ds_s1() -> dict:
    """DS-S1 통합 데모 응답. 수직 슬라이스가 실제로 쓰는 픽스처다."""
    path = ROOT / "contracts" / "fixtures" / "demo" / "DS-S1.assess_response.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def decide():
    """행동 판정 본체 `decide()` (설계서 9장 우선순위 1~10).

    **아직 없다.** P0-3 에서 `services/decision/decide.py` 로 들어온다. 그때까지는
    이 픽스처를 받는 검사만 skip 되고, 파일이 생기는 순간 전부 자동으로 켜진다 —
    기대값을 먼저 주는 것이 P0-2 의 목적이므로 검사를 미리 심어 둔다.

    `test_safe_points.py` 의 `pytestmark = skipif` 와 같은 관용구이며, 픽스처로 둔
    이유는 **파일 전체가 조용해지지 않게** 하기 위해서다. 후처리·어댑터·계약 조합
    검사는 `decide()` 없이도 돌아야 한다.
    """
    module = pytest.importorskip(
        "services.decision.decide",
        reason=(
            "P0-3 미구현 — services/decision/decide.py 가 없다. "
            "그 파일이 생기면 이 픽스처를 받는 기대값 검사가 전부 켜진다."
        ),
    )
    return module.decide


def load(root: Path, name: str) -> dict:
    """`DS-*` 통합 응답 픽스처를 읽는다.

    원본 데이터(7.5GB)를 필요로 하지 않는다 — 그래야 팀원 전원이 돌릴 수 있다.
    """
    path = root / "contracts" / "fixtures" / "demo" / f"{name}.assess_response.json"
    return json.loads(path.read_text(encoding="utf-8"))


#: `RiskSignals` 가 실제로 받는 필드 이름.
#:
#: 규칙 9 의 TH-01(10분 >= 5mm)이 쓸 `rain_past_10m_mm` 은 **픽스처에 실려 있지만
#: `RiskSignals` 에는 아직 없다**(REPOSITORY_AUDIT 6절). P0-3 이 그 필드를 더하면
#: 이 집합에 자동으로 들어오고 아래 필터는 아무것도 걸러내지 않는다. 그때까지
#: 없는 필드를 넘겨 12건이 통째로 깨지는 것을 막는 다리다.
_RISK_SIGNAL_FIELDS = {f.name for f in fields(RiskSignals)}


def signals_from(payload: dict) -> RiskSignals:
    """`AssessResponse` 를 판정 함수의 입력으로 옮긴다.

    출처는 `service_risk.RiskSignals` 문서화 표와 같다. **여기서 값을 정제하지
    않는다** — 정제하면 "픽스처를 그대로 받는다"가 아니라 "정제하면 통과한다"를
    증명하게 된다(C-21).
    """
    decision = payload["decision"]
    user_state = decision["user_state"]
    official = payload.get("official") or {}
    risk = payload["risk"]
    drivers = {d["feature"]: d["value"] for d in risk.get("drivers", [])}
    ai_level = risk["area_risk"].get("ai_risk_level")

    values = {
        "context": UserContext(user_state["context"]),
        "trapped": user_state.get("trapped", False),
        "hazard_signs": tuple(HazardSign(h) for h in user_state.get("hazard_signs") or ()),
        "official_present": bool(official),
        # 계약 필드를 그대로 읽는다. `official_info@v1` 이 required 로 두는 값이며
        # `alerts[]` 에는 이 뜻을 가진 항목이 없다 - 항목의 키는 `type` 이고
        # `EVACUATION_ORDER` 라는 값도 계약에 없다. 예전에는 여기서 `alerts[]` 를
        # 뒤졌고, 네 픽스처가 전부 false 라 **아무것도 빨개지지 않은 채 틀려 있었다.**
        "evacuation_order": bool(official.get("evacuation_order")),
        "closure_count": len(official.get("closures", [])),
        "ai_risk_level": AiRiskLevel(ai_level) if ai_level is not None else None,
        "data_age_sec": payload["clock"].get("data_age_sec") or 0,
        "observed_rate": risk["data_quality"]["observed_rate"],
        "rain_available": risk["data_quality"]["rain_available"],
        "rain_past_60m_mm": drivers.get("rain_past_60m_mm"),
        "rain_past_10m_mm": drivers.get("rain_past_10m_mm"),
        "in_service_area": payload["location"].get("in_service_area", True),
    }
    return RiskSignals(**{k: v for k, v in values.items() if k in _RISK_SIGNAL_FIELDS})
