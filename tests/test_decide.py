"""행동 판정 `decide()` 의 기대값 — 설계서 9장 우선순위 1~10 (P0-2).

이 파일은 **검사가 아니라 계약이다.** 구현보다 먼저 쓰였고, `services/decision/decide.py`
가 생기는 순간 전건이 자동으로 켜진다(`conftest.py` 의 `decide` 픽스처). 구현자는 이
파일을 명세로 읽으면 된다.

규칙 1~10 이 어디 있나
----------------------
정본은 `docs/마른길_MVP_설계서.md` 9장이고 순서의 근거가 같은 절 아래 문단에 있다.
DQ-01~05 의 세부는 `docs/마른길_요구사항_정의서.md` 3.4 표다. 그리고 **이미 도는
전사본이 하나 더 있다** — `scripts/render_service_risk_matrix.py` 의 `action_of()` 다.
문서용 조합표 PNG 의 `action` 열을 그 함수가 채운다.

그래서 이 파일은 두 가지를 동시에 한다.

1. `action_of()` 가 **이미 정해 둔 동작을 고정한다.** 규칙 5가 `AND` 인 것과
   규칙 6~8이 지연 자료에도 발화하는 것이 그것이다. 지금은 그 결정을 지키는 검사가
   하나도 없어서, `decide()` 가 다르게 구현돼도 그림과 엔진이 조용히 갈라진다.
2. `action_of()` 가 **빠뜨린 것을 채운다.** TH-01(`rain_past_10m_mm`)과 DQ-03(관측률)을
   읽는 코드가 저장소 어디에도 없다(`REPOSITORY_AUDIT.md` 6절). 여기가 `decide()` 가
   실제로 새로 만드는 부분이다.

테스트가 `action_of()` 를 직접 import 하지 못하는 이유
-----------------------------------------------------
그 파일은 상단이 `from PIL import ...` 이고 Pillow 는 앱 venv 에 없다. CLAUDE.md 10절이
*"앱과 테스트는 렌더 스크립트를 import하지 않는다"* 로 막고 있다. 그래서 기대값을 여기
옮겨 적었다 — **사본이 하나 더 느는 것이 아니라, 사본을 지키는 검사가 처음 생기는 것이다.**
`decide()` 가 들어오면 렌더 스크립트가 `classify()` 처럼 `decide()` 를 호출하도록 바꾸고
`action_of()` 를 지운다(P0-3 이후 후속).

두 축은 1:1 이 아니다
---------------------
`classify()` 는 "지금 얼마나 위험한가", `decide()` 는 "지금 무엇을 해야 하는가"다.
같은 입력에서 등급 `SAFE` 와 행동 `WAIT` 이 함께 나올 수 있고 그것은 모순이 아니다 —
아래 `test_두_축이_TH01_을_다르게_쓴다` 가 그 자리를 고정한다.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from services.decision.enums import (
    NEEDS_ROUTE,
    Action,
    AiRiskLevel,
    HazardSign,
    ServiceRiskLevel,
    UserContext,
)
from services.decision.service_risk import (
    EXPIRED_SEC,
    OBSERVED_RATE_MIN,
    RAIN_60M_MM,
    STALE_SEC,
    RiskSignals,
    classify,
)

#: TH-01. 10분 강우 기준값(mm). 설계서 9.2 확정값이며 **여기서 고른 수가 아니다.**
#: 구현이 들어오면 `services/decision/decide.py` 의 상수가 정본이 되고
#: `test_TH01_기준값이_설계서와_같다` 가 두 값을 묶는다.
RAIN_10M_MM = 5.0

#: 전부 정상인 기준 입력. 각 검사는 여기서 **한 축만** 바꾼다.
#: `test_service_risk.py:29` 의 `CLEAN` 과 같은 방식이며 값도 같다.
CLEAN = RiskSignals(
    context=UserContext.OUTDOOR,
    ai_risk_level=AiRiskLevel.LOW,
    official_present=True,
    observed_rate=1.0,
    rain_available=True,
    rain_past_60m_mm=0.0,
    data_age_sec=0,
)

#: 규칙 2 를 만드는 최소 입력. 여러 검사가 같이 쓴다.
UNDERGROUND_SIGN = {
    "context": UserContext.UNDERGROUND,
    "hazard_signs": (HazardSign.WATER_INFLOW,),
}


def signals(**changes) -> RiskSignals:
    """`CLEAN` 에서 한 축만 바꾼 입력.

    `rain_past_10m_mm` 을 넘기면 P0-3 이 그 필드를 더하기 전까지 `TypeError` 가 난다.
    그것이 맞는 신호다 — 규칙 9 의 TH-01 은 그 값 없이 계산할 수 없다.
    `test_RiskSignals_가_TH01_입력을_갖는다` 가 먼저 읽을 수 있는 문장으로 알려준다.
    """
    return replace(CLEAN, **changes)


# --- 규칙별 단독 발화 --------------------------------------------------------
#
# (설명, 바꿀 축, 기대 행동, 기대 규칙 번호, 기대 대표 사유 코드)
#
# 사유 코드는 **하나(`RAIN_10M_OVER_TH01`)를 빼고 전부 `classify()` 가 이미 내보내는
# 코드다.** 새 코드를 만들면 화면 라벨 표도 같이 채워야 하므로(CLAUDE.md 4절) 재사용이
# 기본값이다.

RULES = [
    ("1 고립 신고", {"trapped": True}, Action.EMERGENCY, 1, "TRAPPED_REPORTED"),
    ("2 지하 + 현장 징후", UNDERGROUND_SIGN, Action.EVACUATE, 2, "UNDERGROUND_HAZARD_SIGN"),
    ("3 범위 밖", {"in_service_area": False}, Action.UNAVAILABLE, 3, "OUT_OF_SERVICE_AREA"),
    ("4 공식 대피 지시", {"evacuation_order": True}, Action.EVACUATE, 4, "OFFICIAL_EVACUATION_ORDER"),
    (
        "5 AI·강우 동시 결측",
        {"ai_risk_level": None, "rain_available": False},
        Action.UNAVAILABLE,
        5,
        "AI_UNAVAILABLE",
    ),
    ("6 AI HIGH + 실외", {"ai_risk_level": AiRiskLevel.HIGH}, Action.EVACUATE, 6, "AI_AREA_HIGH"),
    (
        "7 AI HIGH + 실내",
        {"ai_risk_level": AiRiskLevel.HIGH, "context": UserContext.INDOOR},
        Action.WAIT,
        7,
        "AI_AREA_HIGH",
    ),
    (
        "8 AI HIGH + 지하 + 징후 없음",
        {"ai_risk_level": AiRiskLevel.HIGH, "context": UserContext.UNDERGROUND},
        Action.WAIT,
        8,
        "AI_AREA_HIGH",
    ),
    (
        "9 TH-02 60분 누적 강우",
        {"rain_past_60m_mm": RAIN_60M_MM},
        Action.WAIT,
        9,
        "RAIN_60M_OVER_TH02",
    ),
    ("10 걸리는 조건 없음", {}, Action.MOVE, 10, "NO_TRIGGER"),
]

RULE_IDS = [row[0] for row in RULES]


@pytest.mark.parametrize("label, change, action, rule, code", RULES, ids=RULE_IDS)
def test_규칙별로_자기_조건에서_자기_번호로_이긴다(decide, label, change, action, rule, code):
    """각 규칙이 단독으로 발화하는지. 여기가 1~10 의 바닥이다."""
    result = decide(signals(**change))

    assert result.action is action, f"{label}: {action.value} 를 기대했는데 {result.action.value}"
    assert result.rule == rule, f"{label}: 규칙 {rule} 을 기대했는데 {result.rule}"
    assert result.reasons[0].code == code, (
        f"{label}: 대표 사유가 {code} 여야 한다 — 지금은 {result.reasons[0].code}. "
        "화면의 reason_code 가 이 값이다."
    )


def test_규칙_1_10_이_전부_표에_있다():
    """규칙 하나가 표에서 빠지면 그 규칙은 조용히 사라진다.

    `decide()` 없이도 도는 검사다 — P0-3 이전에도 이 파일이 완전히 침묵하지 않게 한다.
    """
    assert {row[3] for row in RULES} == set(range(1, 11))


def test_RiskSignals_가_TH01_입력을_갖는다(decide):
    """규칙 9 의 TH-01 을 계산하려면 이 필드가 있어야 한다.

    `rain_past_10m_mm` 은 **픽스처에 이미 실려 있는데 읽는 코드가 없다**
    (`REPOSITORY_AUDIT.md` 6절). `RiskSignals` 에 한 줄 더하는 것이 P0-3 의 일부다.
    """
    names = {f.name for f in fields(RiskSignals)}
    assert "rain_past_10m_mm" in names, (
        "RiskSignals 에 rain_past_10m_mm 이 없다. TH-01(10분 >= 5mm)을 이 값 없이 "
        "계산할 수 없다 — services/decision/service_risk.py 의 RiskSignals 에 "
        "`rain_past_10m_mm: float | None = None` 을 더한다."
    )


# --- 순서 — 첫 일치가 이긴다 --------------------------------------------------
#
# **답만 봐서는 순서를 검사할 수 없다.** 규칙 2 와 6 이 둘 다 EVACUATE 라 순서가
# 뒤집혀도 action 만으로는 통과한다. 그래서 `rule` 번호까지 본다.

ORDERING = [
    ("1 이 2 를 이긴다", {"trapped": True, **UNDERGROUND_SIGN}, Action.EMERGENCY, 1),
    ("2 가 3 을 이긴다", {**UNDERGROUND_SIGN, "in_service_area": False}, Action.EVACUATE, 2),
    ("3 이 4 를 이긴다", {"in_service_area": False, "evacuation_order": True}, Action.UNAVAILABLE, 3),
    (
        "4 가 5 를 이긴다",
        {"evacuation_order": True, "ai_risk_level": None, "rain_available": False},
        Action.EVACUATE,
        4,
    ),
    ("1 이 9 를 이긴다", {"trapped": True, "observed_rate": 0.5}, Action.EMERGENCY, 1),
    (
        "2 가 9 를 이긴다",
        {**UNDERGROUND_SIGN, "rain_past_60m_mm": RAIN_60M_MM},
        Action.EVACUATE,
        2,
    ),
    (
        "6 이 9 를 이긴다",
        {"ai_risk_level": AiRiskLevel.HIGH, "rain_past_60m_mm": RAIN_60M_MM},
        Action.EVACUATE,
        6,
    ),
    (
        "5 가 10 을 이긴다",
        {"ai_risk_level": None, "rain_available": False},
        Action.UNAVAILABLE,
        5,
    ),
]


@pytest.mark.parametrize("label, change, action, rule", ORDERING, ids=[r[0] for r in ORDERING])
def test_첫_일치가_이긴다(decide, label, change, action, rule):
    """순서 자체가 합의 사항이다 — 바꾸려면 설계서 9장부터 고쳐야 한다.

    `3 이 4 를 이긴다` 와 `4 가 5 를 이긴다` 는 설계서가 문단으로 근거를 적어 둔 자리다.
    범위 밖 사용자에게 이 지역의 대피 지시를 적용하지 않고(3 > 4), 대피 지시는 내부
    데이터와 독립이라 데이터 단절이 덮지 못한다(4 > 5).
    """
    result = decide(signals(**change))
    assert result.action is action, label
    assert result.rule == rule, f"{label}: 규칙 {rule} 이 이겨야 하는데 {result.rule} 이 이겼다"


# --- action_of() 가 이미 정해 둔 것 -------------------------------------------


def test_규칙_5_는_AND_다(decide):
    """AI 만 없고 강우 자료가 살아 있으면 `UNAVAILABLE` 이 **아니다.**

    `action_of():114` 가 `ai_risk_level is None and not rain_available` 로 정해 뒀고
    `WHY[101]` 이 이유를 적어 뒀다 — *"AI 값이 없지만 강우 자료는 살아 있다.
    우선순위 5 에 걸리지 않아 기본값으로 떨어진다."*

    깨뜨리는 법: 규칙 5 를 `or` 로 바꾸면 여기가 빨개진다. 그리고 조합표 PNG 의
    D그룹 첫 줄이 조용히 틀려진다.
    """
    result = decide(signals(ai_risk_level=None))
    assert result.action is Action.MOVE
    assert result.rule == 10


def test_AI_결측에서_등급과_행동이_갈린다(decide):
    """같은 입력인데 등급은 `CAUTION`, 행동은 `MOVE` 다. **의도된 갈림이다.**

    `WHY[101]` 의 문장 그대로다 — *"등급이 CAUTION 인 것과 행동이 MOVE 인 것이
    여기서 갈린다."* 등급 축은 "판단할 근거가 없다"를 `SAFE` 라고 말하지 않으려고
    하한을 올리고, 행동 축은 강우 자료가 살아 있으므로 이동을 막을 이유가 없다.
    """
    s = signals(ai_risk_level=None)
    assert classify(s).level is ServiceRiskLevel.CAUTION
    assert decide(s).action is Action.MOVE


def test_지연_30분_초과여도_AI_HIGH_는_규칙_6_을_낸다(decide):
    """행동 축은 등급 축과 **다르게** 간다.

    `classify()` 는 `service_risk.py:424` 에서 expired 자료를 AI 축에서 빼지만,
    `action_of()` 는 DQ-02 를 규칙 9 **뒤의** 별도 분기에 두어 규칙 6~8 이 먼저
    이기게 했다(`build_rows()` B그룹이 그 줄들이다).

    등급이 `CAUTION` 으로 내려가는 동안 행동은 `EVACUATE` 를 유지한다 — 30분 된
    자료라도 "위험이 높았다"를 근거로 대피를 늦추지 않는다는 뜻이다.
    """
    s = signals(ai_risk_level=AiRiskLevel.HIGH, data_age_sec=EXPIRED_SEC + 1)
    result = decide(s)

    assert result.rule == 6
    assert result.action is Action.EVACUATE
    assert classify(s).level is ServiceRiskLevel.CAUTION


# --- action_of() 가 빠뜨린 것 — decide() 가 새로 만드는 부분 ------------------


def test_TH01_단독으로_WAIT_이_된다(decide):
    """10분 5mm 만 걸리고 60분 누적은 기준 아래인 경우.

    `action_of()` 에 이 분기가 없다. 설계서 9.2 는 8/8 19:30 에 TH-01 이 60분 신호보다
    **30분 앞서** 걸린다고 적었다 — 빠뜨리면 그 30분을 잃는다.
    """
    result = decide(signals(rain_past_10m_mm=RAIN_10M_MM, rain_past_60m_mm=5.0))

    assert result.action is Action.WAIT
    assert result.rule == 9
    assert result.reasons[0].code == "RAIN_10M_OVER_TH01"


def test_TH01_기준값이_설계서와_같다(decide):
    """5mm 는 설계서 9.2 확정값이며 강우 관측행의 상위 8.6% 다."""
    from services.decision.decide import RAIN_10M_MM as implemented

    assert implemented == RAIN_10M_MM


@pytest.mark.parametrize(
    "label, change",
    [
        ("TH-01 만", {"rain_past_10m_mm": RAIN_10M_MM, "rain_past_60m_mm": 5.0}),
        ("TH-02 만", {"rain_past_10m_mm": 0.0, "rain_past_60m_mm": RAIN_60M_MM}),
        ("둘 다", {"rain_past_10m_mm": RAIN_10M_MM, "rain_past_60m_mm": RAIN_60M_MM}),
    ],
    ids=["TH-01 만", "TH-02 만", "둘 다"],
)
def test_TH01_과_TH02_는_OR_로_묶인다(decide, label, change):
    """요구사항 정의서 167 · 설계서 9.2 · 회귀 케이스 R14 에서 확정된 묶음이다.

    **등급 축은 이 묶음을 쓰지 않는다**(O-15 → C-27). 같은 두 기준값이 두 축에서
    다른 무게를 갖는 것이 C-23 의 요점이다.
    """
    result = decide(signals(**change))
    assert result.action is Action.WAIT, label
    assert result.rule == 9, label


def test_관측률이_기준_아래면_WAIT_이다(decide):
    """DQ-03. `action_of()` 는 `observed_rate` 를 아예 보지 않는다.

    C-28 이 계산식을 고친 바로 그 값이며, 임계 `0.70` 은 그대로 두기로 했다.
    """
    result = decide(signals(observed_rate=OBSERVED_RATE_MIN - 0.01))

    assert result.action is Action.WAIT
    assert result.rule == 9
    assert result.reasons[0].code == "DATA_QUALITY_LOW"


def test_DQ01_10분_초과만이면_행동을_바꾸지_않는다(decide):
    """설계서 9장 규칙 9 의 단서 — *"10분 초과만이면 현 행동 유지 + 지연 표시"*.

    **단계는 10분과 30분 둘뿐이다**(M-08). 20분 단계를 만들지 않는다.
    """
    result = decide(signals(data_age_sec=STALE_SEC + 1))

    assert result.action is Action.MOVE
    assert result.rule == 10


def test_DQ02_는_MOVE_일_때만_WAIT_로_내린다(decide):
    """30분을 넘겼다고 **모든 행동을 `WAIT` 으로 바꾸지 않는다**(M-08).

    자기신고와 공식 지시는 내부 관측 자료가 아니라 낡음과 함께 사라지지 않는다.
    """
    stale = {"data_age_sec": EXPIRED_SEC + 1}

    downgraded = decide(signals(**stale))
    assert downgraded.action is Action.WAIT
    assert downgraded.rule == 9
    assert downgraded.reasons[0].code == "DATA_EXPIRED"

    assert decide(signals(trapped=True, **stale)).action is Action.EMERGENCY
    assert decide(signals(**UNDERGROUND_SIGN, **stale)).action is Action.EVACUATE
    assert decide(signals(evacuation_order=True, **stale)).action is Action.EVACUATE


def test_DQ04_강우_결측이_1_2_4_확정행동을_덮지_않는다(decide):
    """요구사항 정의서 133 — *"단 우선순위 1·2·4로 확정된 행동은 유지"*."""
    blackout = {"ai_risk_level": None, "rain_available": False}

    assert decide(signals(**blackout)).action is Action.UNAVAILABLE
    assert decide(signals(trapped=True, **blackout)).action is Action.EMERGENCY
    assert decide(signals(**UNDERGROUND_SIGN, **blackout)).action is Action.EVACUATE
    assert decide(signals(evacuation_order=True, **blackout)).action is Action.EVACUATE


def test_DQ05_품질_사유로_하향하지_않는다(decide):
    """요구사항 정의서 134. 순서가 이미 보장하지만 **명시적으로 건다** —

    규칙 9 를 위로 올리고 싶은 유혹이 생기는 자리이고, 올리는 순간 고립 신고가
    품질 문제로 대기가 된다.
    """
    low = {"observed_rate": OBSERVED_RATE_MIN - 0.01}

    assert decide(signals(trapped=True, **low)).action is Action.EMERGENCY
    assert decide(signals(**UNDERGROUND_SIGN, **low)).action is Action.EVACUATE
    assert decide(signals(evacuation_order=True, **low)).action is Action.EVACUATE


# --- 두 축이 같은 신호를 다르게 쓴다 ------------------------------------------


def test_두_축이_TH01_을_다르게_쓴다(decide):
    """**O-15 → C-27 의 전부가 이 한 건이다.**

    등급 축의 추가 위험신호는 TH-02 하나뿐이고(`test_service_risk.py` 의
    `test_등급_축의_추가_신호는_TH02_하나뿐이다`), 행동 축은 `TH-01 OR TH-02` 다.
    TH-01 은 강우 사건 22개 중 14개에서 걸려 TH-02(6개)보다 2.3배 흔하다 — 등급에
    넣으면 `DANGER` 가 사실상 `AI HIGH` 와 같아진다.

    그래서 같은 입력에서 **등급은 `SAFE`, 행동은 `WAIT`** 이 나온다. 화면 두 줄이
    서로를 부정하는 것이 아니라 다른 질문에 답하는 것이다 — "지금 얼마나 위험한가"와
    "지금 무엇을 해야 하는가". 발표에서 이 조합이 보이면 그대로 설명한다.
    """
    s = signals(rain_past_10m_mm=RAIN_10M_MM, rain_past_60m_mm=5.0)

    assert classify(s).level is ServiceRiskLevel.SAFE
    assert decide(s).action is Action.WAIT


# --- 파생값과 성질 ------------------------------------------------------------


@pytest.mark.parametrize("label, change, action, rule, code", RULES, ids=RULE_IDS)
def test_needs_route_는_NEEDS_ROUTE_에서_파생된다(decide, label, change, action, rule, code):
    """`MOVE`·`EVACUATE` 는 항상 true, 그 외는 항상 false (계약 설명 그대로).

    따로 정하는 값이 아니다 — 손으로 정하면 `enums.NEEDS_ROUTE` 와 갈라진다.
    """
    result = decide(signals(**change))
    assert result.needs_route is (action in NEEDS_ROUTE), label


def test_decide_는_순수함수다(decide):
    """N-04 재현성. 같은 입력이면 항상 같은 출력.

    `datetime.now()` 를 쓰고 싶어지면 설계가 틀린 신호다 — 시각은 입력이다.
    """
    s = signals(ai_risk_level=AiRiskLevel.HIGH, rain_past_60m_mm=RAIN_60M_MM)
    assert decide(s) == decide(s)


def test_사유가_비어있는_판정은_없다(decide):
    """화면이 "왜 그런지"를 말하지 못하는 상태를 만들지 않는다.

    상한은 `MAX_REASONS`(3)이며 계약도 같은 상한을 건다(F-03).
    """
    for label, change, _action, _rule, _code in RULES:
        result = decide(signals(**change))
        assert result.reasons, label
        assert len(result.reasons) <= 3, label
