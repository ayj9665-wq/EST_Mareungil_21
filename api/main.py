"""통합 API — UI 에 AssessResponse 하나를 제공한다.

    .\\make.ps1 api        # http://127.0.0.1:8000  (문서: /docs)

지금 상태
---------
`decision` 블록은 이제 `classify()`/`decide()`/`apply()`를 실제로 호출해 채운다
(P0-5). `route` 블록은 여전히 경로 엔진이 붙기 전이라 픽스처의 STUB 값을 그대로
쓴다 - `apply()`는 그 STUB 상태를 입력으로 받아 후처리 규칙만 실제로 적용한다.

`source_kind`는 이번 배선에서 건드리지 않았다. FIXTURE/STUB/LIVE_PIPELINE 중
지금 상태에 어떤 값이 맞는지(decision은 실제 계산, route는 여전히 STUB인
혼합 상태)는 문서에서 확인이 안 돼 임의로 정하지 않았다 - `docs/DECISIONS.md`
확인 또는 PM 확인 필요.

이 파일이 하는 일은 넷이다.
1. 픽스처를 읽고
2. 사용자가 고른 목적지·프로필을 반영하고
3. RiskSignals 로 변환해 `classify()`/`decide()`/`apply()`로 decision 블록을 채우고
4. **돌려주기 전에 계약을 검증한다.**

4번이 핵심이다. 계약 위반을 UI 가 아니라 여기서 잡아야 다섯 명이 병렬로 만들 때
통합이 덜 깨진다.
"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.fixtures import (
    apply_destination,
    apply_profiles,
    contract_errors,
    load_destinations,
    load_scenarios,
    load_validators,
)
from services.decision.adapters import signals_from
from services.decision.decide import decide
from services.decision.enums import Profile, RouteStatus
from services.decision.postprocess import apply
from services.decision.service_risk import classify
from services.route.provider import provider_for, route_request_from

CONTRACT_VERSION = os.environ.get("MAREUNGIL_CONTRACT_VERSION", "v1")
DEFAULT_SCENARIO = os.environ.get("MAREUNGIL_DEFAULT_SCENARIO", "DS-S1")

app = FastAPI(
    title="마른길 통합 API",
    version="0.1.0",
    description=(
        "2022-08-08 강남 집중호우 재생. **교육·시연용이며 공식 재난안전 판단 도구가 아니다.** "
        "현재 응답은 전부 픽스처 기반이며 source_kind 필드로 표시된다."
    ),
)

# 프론트 개발 서버(Vite)에서 직접 호출할 수 있게 열어둔다. 데모는 로컬 전용이다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_validators = load_validators()
_scenarios = load_scenarios()
_destinations = load_destinations()
_points = {p["id"]: p for p in _destinations["points"]}


@app.get("/api/health")
def health() -> dict:
    """개발 서버가 살아 있는지, 픽스처를 몇 개 읽었는지."""
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "scenarios": sorted(_scenarios),
        "destinations": len(_points),
        "source_kind": "FIXTURE",
    }


#: 계획된 DS 시나리오 전체. 여기서 실제 로드된 것을 빼면 `pending` 이다.
#: 목록을 손으로 두 번 적으면 픽스처를 추가해도 "아직 없음"이 남는다.
PLANNED_SCENARIOS = ["DS-S1", "DS-S2", "DS-S3", "DS-S4", "DS-S5", "DS-S6", "DS-S7", "DS-S8"]


@app.get("/api/scenarios")
def scenarios() -> dict:
    """M-18. 수동 재판단이 고를 수 있는 재생 시각.

    자동 감지·자동 재탐색은 MVP 범위 밖이므로 여기서 시각을 바꾸는 것이
    재판단의 유일한 방법이다. 아직 만들지 않은 시나리오는 `pending` 으로
    구분해 돌려준다 — 없는 것을 있는 척하지 않는다.
    """
    return {
        "scenarios": [
            {
                "id": sid,
                "label": body.get("_scenario", sid),
                "why": body.get("_why_this_moment"),
                "clock_label": body["clock"]["label"],
                "action": body["decision"]["action"],
            }
            for sid, body in sorted(_scenarios.items())
        ],
        "pending": [sid for sid in PLANNED_SCENARIOS if sid not in _scenarios],
    }


@app.get("/api/destinations")
def destinations() -> dict:
    """RT-14. 목적지로 고를 수 있는 지정 지점 목록.

    자유 좌표·자유 텍스트 입력은 제공하지 않는다. 목록 등재가 안전 보장은
    아니며 차단 여부는 재생 시각마다 다시 판정한다(RT-17).
    """
    return {
        "status": _destinations["_status"],
        "scope": _destinations["scope"],
        "points": _destinations["points"],
        "note": "목록에 있다는 사실이 안전을 보장하지 않습니다.",
    }


def _apply_decision_engine(body: dict) -> dict:
    """RF 위험 -> classify() -> decide() -> 경로 상태 -> apply() 로 decision 블록을 채운다.

    `risk` 블록은 이미 실제 모델 출력이다. `route` 는 아직 STUB 이므로 그 status 를
    그대로 `apply()`에 넘긴다 - 후처리 규칙(CONFIRMED_TRANSITIONS·CONFIRMED_HOLDS)
    자체는 실제로 동작한다.

    `needs_route`는 계약(`assess_response.schema.json`의 allOf)이 **1차 행동
    (`primary_action`) 기준**으로 강제한다 - 경로 후처리로 최종 행동이 바뀌어도
    그대로다. 그래서 `post.action`이 아니라 `primary.needs_route`
    (= `primary_action`에서 파생된 값)를 쓴다.
    """
    signals = signals_from(body)
    risk_result = classify(signals)
    primary = decide(signals)
    
    req = route_request_from(body, primary.action)
    route_res = provider_for(body).solve(req)

    post = apply(primary.action, RouteStatus(route_res["status"]))

    reason_code = post.reason[0] if post.reason is not None else primary.reasons[0].code

    out = json.loads(json.dumps(body))  # 원본 픽스처를 건드리지 않는다
    out["decision"].pop("_stub", None)
    out["decision"].update(
        primary_action=primary.action.value,
        action=post.action.value,
        route_postprocess_applied=post.applied,
        service_risk_level=risk_result.level.value,
        needs_route=primary.needs_route,
        reason_code=reason_code,
        reasons=[r.as_dict() for r in primary.reasons],
    )
    
    out["route"].pop("_stub", None)
    out["route"].update(route_res)
    
    return out


@app.get("/api/assess")
def assess(
    scenario: str = Query(default=DEFAULT_SCENARIO, description="재생 시나리오 id"),
    destination: str | None = Query(default=None, description="지정 지점 id (RT-14)"),
    profile: list[str] = Query(
        default=[],
        description=(
            "M-37. 고령자·아이동반 프로필. 순서 조정용이며 안전 기준을 완화하지 않는다. "
            "경로 비교 엔진이 STUB 이라 아직 route.profile_applied 에 반영되지 않는다."
        ),
    ),
) -> dict:
    """UI 가 받는 단일 응답.

    돌려주기 전에 `AssessResponse` + `RiskAssessment` + `SafeRoute` 를 모두 검증한다.
    위반이 있으면 500 으로 떨어뜨린다 — 계약을 어긴 응답을 화면까지 보내지 않는다.
    """
    body = _scenarios.get(scenario)
    if body is None:
        raise HTTPException(
            404,
            f"시나리오 {scenario} 가 없다. 사용 가능: {sorted(_scenarios)}",
        )

    if destination is not None:
        point = _points.get(destination)
        if point is None:
            # RT-14/RT-15. 목록 밖 지점은 애초에 받지 않는다.
            raise HTTPException(
                400,
                f"지정 지점 목록에 없는 목적지 {destination}. 사용 가능: {sorted(_points)}",
            )
        body = apply_destination(body, point)

    if profile:
        # X1 / C-14. WHEELCHAIR·WITH_PET 은 계약 enum 밖이다. 여기서 막지 않으면
        # 계약 검증에서 500 이 되는데, 그건 사용자 입력 오류를 서버 오류로 보고하는 것이다.
        unknown = [p for p in profile if p not in {m.value for m in Profile}]
        if unknown:
            raise HTTPException(
                400,
                f"MVP 가 지원하지 않는 프로필 {unknown}. "
                f"사용 가능: {sorted(m.value for m in Profile)}",
            )
        body = apply_profiles(body, profile)

    body = _apply_decision_engine(body)

    violations = contract_errors(_validators, body)
    if violations:
        raise HTTPException(500, {"contract_violations": violations[:10]})

    return body
