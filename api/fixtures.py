"""픽스처 로딩과 계약 검증.

런타임에 외부 API 를 호출하지 않는다. 재생 모드는 사전 가공된 픽스처만 쓰므로
네트워크가 끊겨도 데모가 성립한다(설계서 8.5.3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from contracts.validate import COMPOSED_BLOCKS, SCHEMA_DIR

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "contracts" / "fixtures"
DEMO_DIR = FIXTURE_DIR / "demo"
DESTINATIONS = ROOT / "contracts" / "destinations.json"
SAFE_POINTS = ROOT / "contracts" / "safe_points.json"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_validators() -> dict[str, Draft202012Validator]:
    out: dict[str, Draft202012Validator] = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        out[path.name.removesuffix(".schema.json")] = Draft202012Validator(_read(path))
    return out


def contract_errors(
    validators: dict[str, Draft202012Validator], response: dict[str, Any]
) -> list[str]:
    """`AssessResponse` 합성 검증. 위반 목록을 돌려준다(빈 리스트면 통과)."""
    def fmt(prefix: str, err: Any) -> str:
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        return f"{prefix}{where}: {err.message}"

    found = [fmt("", e) for e in validators["assess_response"].iter_errors(response)]
    for block, schema_name in COMPOSED_BLOCKS.items():
        body = response.get(block)
        if isinstance(body, dict):
            found += [fmt(f"{block}/", e) for e in validators[schema_name].iter_errors(body)]
    return found


def load_scenarios() -> dict[str, dict[str, Any]]:
    """`contracts/fixtures/demo/` 의 DS-* 응답을 전부 읽는다."""
    scenarios: dict[str, dict[str, Any]] = {}
    for path in sorted(DEMO_DIR.glob("*.assess_response.json")):
        scenarios[path.name.removesuffix(".assess_response.json")] = _read(path)
    return scenarios


def load_destinations() -> dict[str, Any]:
    """RT-14. 목적지로 고를 수 있는 지정 지점 목록."""
    return _read(DESTINATIONS)


def load_safe_points() -> list[dict[str, Any]]:
    """C-32. `EVACUATE` 후보 비교에 쓰는 안전거점 7곳(고정 집합)."""
    return _read(SAFE_POINTS)["points"]


def apply_destination(response: dict[str, Any], point: dict[str, Any]) -> dict[str, Any]:
    """사용자가 고른 목적지를 응답에 반영한다.

    목적지는 **경로를 그리기 위한 입력**이지 위험 판정의 입력이 아니다. 따라서
    위험 등급과 행동은 건드리지 않고 `user_state.destination` 과 경로 도달
    대상만 바꾼다(설계서 5.3).

    픽스처가 상정한 목적지와 다른 지점을 고르면 거리·소요시간은 계산된 값이
    아니므로 `null` 로 비운다. **없는 숫자를 지어내지 않는다.**
    """
    out = json.loads(json.dumps(response))  # 원본 픽스처를 건드리지 않는다
    dest = {k: point[k] for k in ("id", "label", "lat", "lon")}

    previous = out["decision"]["user_state"]["destination"]
    out["decision"]["user_state"]["destination"] = dest

    route = out["route"]
    if route.get("route_target") == "USER_DESTINATION" and route.get("target"):
        route["target"] = {
            **route["target"],
            "id": dest["id"],
            "label": dest["label"],
            "lat": dest["lat"],
            "lon": dest["lon"],
        }

    if not previous or previous.get("id") != dest["id"]:
        route["distance_m"] = None
        route["eta_sec"] = None
        route["detour_ratio"] = None
        route["_stub"] = (
            "목적지를 바꿨다. 경로 엔진이 없어 거리·소요시간을 다시 계산할 수 없으므로 "
            "비워 두었다. 지어낸 값을 표시하지 않는다."
        )
    return out


def apply_profiles(response: dict[str, Any], profiles: list[str]) -> dict[str, Any]:
    """M-37. 사용자가 고른 프로필을 응답에 반영한다.

    회의는 고령자·아이동반을 MVP 에 **유지**하고 우회 상한 1.15 · 경사 가중 1.5 를
    정책값으로 쓰기로 확정했다. 다만 두 값이 하는 일은 **이미 안전이 허용된 후보
    안에서 순서를 조정하는 것**뿐이고, 안전 기준이나 위험구간 제외 기준을 완화하지
    않는다.

    경로 비교 엔진(`DesignatedPointRouteProvider`)이 `request.profiles`를 받아
    우회 상한 1.15 이내에서 위험도 우선으로 정렬하고, 그 결과를 `route.profile_applied`에
    반환한다. (단, 경사 데이터가 없어 1.5 가중치는 적용 불가 사유로 남긴다)
    """
    out = json.loads(json.dumps(response))
    out["decision"]["user_state"]["profiles"] = list(profiles)
    return out
