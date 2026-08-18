"""데모 픽스처의 `decision` 블록을 판정 엔진이 그대로 재현하는가 (P0-2).

`test_demo_fixture_consistency.py` 가 **등급 축**에 대해 하는 일을, 이 파일이
**행동 축 전체**에 대해 한다. 그 파일의 docstring 이 예고한 자리다.

왜 단위 테스트만으로는 부족한가
-------------------------------
`test_decide.py` 는 손으로 만든 입력으로 규칙 1~10 을 시험한다. 그것만 있으면
`decide()` 가 전건 통과하면서도 **실제 데모 픽스처와 어긋날 수 있다** — 저장소가
이미 그렇게 당했다. `classify()` 에 테스트가 27건 붙어 있는데도 `DS-S1`·`DS-S6` 의
등급이 코드와 달랐고, 원인은 아무도 픽스처를 그 함수에 통과시켜 보지 않은 것이었다
(C-28 / `REPOSITORY_AUDIT.md` 10.1).

그래서 여기서는 **손으로 만든 입력을 쓰지 않는다.** 픽스처를 `conftest.signals_from()`
으로 그대로 옮겨 넣고 `decision` 블록과 대조한다.

무엇을 대조하나
---------------
==============================  ===============================================
픽스처                           엔진
==============================  ===============================================
`decision.primary_action`       `decide(signals).action`
`decision.action`               `apply(primary, route.status).action`
`decision.route_postprocess_applied`  `apply(...).applied`
`decision.reason_code`          후처리 사유가 있으면 그 코드, 없으면 `decide()` 의 대표 사유
`decision.needs_route`          `action in NEEDS_ROUTE`
==============================  ===============================================

등급(`service_risk_level`)은 `test_demo_fixture_consistency.py` 가 이미 덮으므로
여기서 다시 세지 않는다.

`decide()` 이전에도 절반은 돈다
-------------------------------
후처리 대조와 어댑터 검사는 `decide` 픽스처를 받지 않으므로 **P0-3 전에도 실행된다.**
파일 전체가 skip 으로 조용해지면 "검사를 넣었다"는 말만 남고 지키는 것이 없어진다.
"""

from __future__ import annotations

import pytest
from conftest import load, signals_from

from services.decision.enums import NEEDS_ROUTE, Action, RouteStatus
from services.decision.postprocess import apply

#: 대조할 통합 응답 픽스처. 새 DS-* 를 만들면 여기 더한다.
DEMO_FIXTURES = ["DS-S1", "DS-S6", "DS-S7", "DS-S8"]


def postprocess_of(payload: dict, primary_action: Action):
    """`apply()` 를 픽스처의 경로 상태로 부른다.

    계약상 불가능한 조합이면 `ContractViolation` 이 올라온다 — 픽스처가 RT-13 을
    어기고 있다는 뜻이고, 그것도 잡아야 할 결함이다.
    """
    return apply(primary_action, RouteStatus(payload["route"]["status"]))


def reason_code_of(primary_reasons, post) -> str:
    """화면의 `reason_code` 를 만드는 규칙.

    경로 실패가 있으면 그것이 대표 사유다 — 사용자가 지금 마주친 것이 그것이기
    때문이다. 실패가 없으면 행동을 만든 규칙의 사유가 대표다.
    """
    if post.reason is not None:
        return post.reason[0]
    return primary_reasons[0].code


# --- decide() 없이도 도는 검사 ------------------------------------------------


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_픽스처의_최종_행동이_후처리_출력과_같다(root, name):
    """1차 행동 + 경로 상태 -> 최종 행동. `decide()` 없이 픽스처만으로 검사할 수 있다.

    깨뜨리는 법: `postprocess.CONFIRMED_TRANSITIONS` 에 전이를 하나 더하거나
    픽스처의 `action` 을 손으로 바꾸면 빨개진다. C-01 이 걸려 있는 자리다.
    """
    payload = load(root, name)
    decision = payload["decision"]
    primary = Action(decision["primary_action"])
    post = postprocess_of(payload, primary)

    assert post.action is Action(decision["action"]), (
        f"{name}: 픽스처는 {primary.value} + {payload['route']['status']} 에서 "
        f"{decision['action']} 인데 apply() 는 {post.action.value} 를 낸다."
    )


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_픽스처의_후처리_수행여부가_같다(root, name):
    """RT-10. **확정 규칙을 적용한 것과 행동이 바뀐 것은 다르다.**

    유지 조합(M-15·M-16)에서 `route_postprocess_applied` 는 `false` 다. `true` 로
    적혀 있으면 화면이 "경로 때문에 행동을 바꿨다"고 잘못 말하게 된다.
    """
    payload = load(root, name)
    decision = payload["decision"]
    post = postprocess_of(payload, Action(decision["primary_action"]))

    assert post.applied is decision["route_postprocess_applied"], (
        f"{name}: 픽스처는 {decision['route_postprocess_applied']} 인데 "
        f"apply() 는 applied={post.applied} 다."
    )


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_경로가_실패한_픽스처는_그_사유를_대표로_싣는다(root, name):
    """실패 조합에서만 도는 검사다. `DS-S6`·`DS-S8` 이 여기 걸린다.

    두 픽스처의 `reason_code` 는 이미 `postprocess.CONFIRMED_HOLDS` 의 코드와 같다 —
    이 검사는 **그 일치가 우연이 아니라 유지되도록** 못 박는다.
    """
    payload = load(root, name)
    decision = payload["decision"]
    post = postprocess_of(payload, Action(decision["primary_action"]))

    if post.reason is None:
        pytest.skip(f"{name} 은 경로 실패 조합이 아니다 — 대표 사유는 decide() 가 만든다")

    assert decision["reason_code"] == post.reason[0], (
        f"{name}: 픽스처의 reason_code 는 {decision['reason_code']} 인데 "
        f"후처리 사유는 {post.reason[0]} 이다."
    )


def test_어댑터는_계약_필드에서_대피지시를_읽는다(root):
    """규칙 4 를 대조하려면 어댑터가 이 값을 제대로 읽어야 한다.

    예전 `signals_from()` 은 `alerts[]` 에서 `kind == "EVACUATION_ORDER"` 를 찾았다.
    항목의 키는 `type` 이고 그런 값도 계약에 없다. **네 픽스처가 전부 `false` 라
    아무것도 빨개지지 않은 채 틀려 있었다** — 대피 지시가 있는 픽스처를 만드는
    순간(`DS-S4` 등) 엔진이 `MOVE` 를 내고 원인이 어댑터에 숨는다.

    깨뜨리는 법: `conftest.signals_from()` 을 옛 방식으로 되돌리면 빨개진다.
    """
    payload = load(root, "DS-S1")
    assert signals_from(payload).evacuation_order is False

    payload["official"]["evacuation_order"] = True
    assert signals_from(payload).evacuation_order is True


# --- decide() 가 들어오면 켜지는 검사 -----------------------------------------


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_픽스처의_1차_행동이_decide_출력과_같다(decide, root, name):
    """**이 파일의 핵심.** 픽스처를 정제하지 않고 그대로 `decide()` 에 넣는다.

    `DS-S1`·`DS-S6` 은 규칙 10 -> `MOVE`, `DS-S7`·`DS-S8` 은 규칙 6 -> `EVACUATE` 다.
    깨뜨리는 법: 규칙 순서를 바꾸거나 임계를 건드리면 여기가 먼저 빨개진다.
    """
    payload = load(root, name)
    expected = payload["decision"]["primary_action"]
    result = decide(signals_from(payload))

    assert result.action is Action(expected), (
        f"{name}: 픽스처는 {expected} 인데 decide() 는 규칙 {result.rule} 로 "
        f"{result.action.value} 를 낸다. "
        f"ai_risk_level={payload['risk']['area_risk'].get('ai_risk_level')} · "
        f"observed_rate={payload['risk']['data_quality']['observed_rate']}"
    )


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_픽스처의_대표_사유가_엔진_출력과_같다(decide, root, name):
    """`reason_code` 는 전환 배너에 그대로 찍힌다.

    `DS-S1` 의 `NO_TRIGGER` 와 `DS-S7` 의 `AI_AREA_HIGH` 는 **픽스처가 규칙 10 과
    규칙 6 의 사유 코드를 이미 고정해 둔 것이다.** 구현이 다른 코드를 쓰면 여기서 걸린다.
    """
    payload = load(root, name)
    decision = payload["decision"]
    primary = decide(signals_from(payload))
    post = postprocess_of(payload, primary.action)

    assert decision["reason_code"] == reason_code_of(primary.reasons, post), (
        f"{name}: 픽스처는 {decision['reason_code']} 인데 엔진은 "
        f"{reason_code_of(primary.reasons, post)} 를 낸다."
    )


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_픽스처의_needs_route_가_엔진_출력과_같다(decide, root, name):
    """`MOVE`·`EVACUATE` 는 항상 true. 손으로 정하는 값이 아니다."""
    payload = load(root, name)
    primary = decide(signals_from(payload))
    post = postprocess_of(payload, primary.action)

    assert payload["decision"]["needs_route"] is (post.action in NEEDS_ROUTE), name


@pytest.mark.parametrize("name", DEMO_FIXTURES)
def test_픽스처의_decision_블록_전체가_엔진으로_재현된다(decide, root, name):
    """위 검사들을 한 번에 — **한 픽스처가 통째로 맞는지**가 데모의 단위다.

    개별 필드가 다 맞아도 조합이 틀릴 수 있다. 그리고 실패했을 때 어느 필드가
    틀렸는지 한 화면에서 보는 편이 새벽 4시에 빠르다.
    """
    payload = load(root, name)
    decision = payload["decision"]
    primary = decide(signals_from(payload))
    post = postprocess_of(payload, primary.action)

    actual = {
        "primary_action": primary.action.value,
        "action": post.action.value,
        "route_postprocess_applied": post.applied,
        "reason_code": reason_code_of(primary.reasons, post),
        "needs_route": post.action in NEEDS_ROUTE,
    }
    expected = {key: decision[key] for key in actual}

    assert actual == expected, f"{name}: 규칙 {primary.rule} 로 판정했다"
