from typing import Any, Optional

from services.route.interface import (
    RouteProvider, RouteRequest, RoutePoint, DestinationPoint,
    target_for, not_required
)
from services.decision.enums import Action, RouteStatus, Profile
from services.route.distance import haversine_m

class DesignatedPointRouteProvider(RouteProvider):
    def __init__(self, safe_points: list[dict[str, Any]], sensors: list[dict[str, Any]]):
        self.safe_points = safe_points
        self.sensors = sensors

    def solve(self, request: RouteRequest) -> dict[str, Any]:
        target_enum = target_for(request.primary_action)
        route_target = target_enum.value if target_enum else None

        # 1. NOT_REQUIRED 처리
        if request.primary_action in (Action.WAIT, Action.EMERGENCY, Action.UNAVAILABLE):
            return not_required("경로 탐색이 필요하지 않은 행동입니다.")

        # 2. 공식 통제로부터 차단된 목적지/거점 ID 목록 수집
        blocked_ids = set()
        official = request.official
        for key in ("closures", "confirmed_flooding"):
            for item in official.get(key, []):
                for b_id in item.get("blocks_destination_ids", []):
                    blocked_ids.add(b_id)

        # 3. 유효 센서 필터링
        valid_sensors = []
        for s in self.sensors:
            try:
                lat = float(s["location"]["lat"])
                lon = float(s["location"]["lon"])
                p = float(s["horizons"]["30"]["high_level_p"])
                valid_sensors.append({"lat": lat, "lon": lon, "risk": p})
            except (KeyError, TypeError, ValueError):
                continue

        # 유효 센서가 하나도 없으면 DATA_UNAVAILABLE 반환
        if not valid_sensors and request.primary_action == Action.EVACUATE:
            return {
                "status": RouteStatus.DATA_UNAVAILABLE.value,
                "route_target": route_target,
                "target": None,
                "route_attempted": False,
                "no_safe_route": None,
                "route_verified": False,
                "limit": "유효한 좌표와 30분 위험 확률을 함께 가진 센서가 없어 후보 간 상대 위험을 판단할 수 없습니다."
            }

        if request.primary_action == Action.MOVE:
            dest_id = request.destination.id
            if dest_id in blocked_ids:
                return {
                    "status": RouteStatus.DESTINATION_BLOCKED.value,
                    "route_target": route_target,
                    "target": None,
                    "route_attempted": False,
                    "no_safe_route": None,
                    "route_verified": False,
                    "limit": "공식 정보에 의해 명시적으로 차단된 목적지입니다."
                }
            else:
                return {
                    "status": RouteStatus.FALLBACK_CANDIDATE.value,
                    "route_verified": False,
                    "route_target": route_target,
                    "target": {
                        "kind": "DESTINATION_POINT",
                        "id": dest_id,
                        "label": request.destination.label,
                        "lat": request.destination.lat,
                        "lon": request.destination.lon
                    },
                    "route_attempted": True,
                    "no_safe_route": False,
                    "distance_m": haversine_m(request.origin.lat, request.origin.lon, request.destination.lat, request.destination.lon),
                    "eta_sec": None,
                    "profile_applied": [p.value for p in request.profiles],
                    "limit": "지정 지점에 대한 점대점 비교 결과이며 실제 통행 가능성이나 안전을 보장하지 않습니다." + (" (경사 데이터가 없어 1.5 적용 불가)" if request.profiles else "")
                }

        elif request.primary_action == Action.EVACUATE:
            candidates = []
            for sp in self.safe_points:
                if sp["id"] in blocked_ids:
                    continue
                
                nearest_risk = None
                min_dist = float('inf')
                for s in valid_sensors:
                    dist = haversine_m(sp["lat"], sp["lon"], s["lat"], s["lon"])
                    if dist < min_dist:
                        min_dist = dist
                        nearest_risk = s["risk"]
                        
                origin_dist = haversine_m(request.origin.lat, request.origin.lon, sp["lat"], sp["lon"])
                
                candidates.append({
                    "sp": sp,
                    "risk": nearest_risk if nearest_risk is not None else 0.0,
                    "dist": origin_dist
                })

            if not candidates:
                return {
                    "status": RouteStatus.NO_SAFE_POINT.value,
                    "route_target": route_target,
                    "target": None,
                    "route_attempted": False,
                    "no_safe_route": None,
                    "route_verified": False,
                    "limit": "모든 안전거점이 공식 정보에 의해 차단되었습니다."
                }

            if request.profiles:
                min_dist = min(c["dist"] for c in candidates)
                detour_limit = min_dist * 1.15
                candidates.sort(key=lambda x: (x["dist"] > detour_limit, x["risk"], x["dist"], x["sp"]["id"]))
                
                profile_applied = [p.value for p in request.profiles]
                limit_text = "공식 대피시설 후보의 상대 비교 결과이며 실제 통행 가능성이나 안전을 보장하지 않습니다. 우회 상한 1.15 이내에서 위험도 순으로 조정했습니다. (경사 가중치 1.5는 경사 데이터가 없어 적용 불가)"
            else:
                candidates.sort(key=lambda x: (x["risk"], x["dist"], x["sp"]["id"]))
                profile_applied = []
                limit_text = "공식 대피시설 후보의 상대 비교 결과이며 실제 통행 가능성이나 안전을 보장하지 않습니다."
            
            best = candidates[0]
            return {
                "status": RouteStatus.FALLBACK_CANDIDATE.value,
                "route_verified": False,
                "route_target": route_target,
                "target": {
                    "kind": "SHELTER",
                    "id": best["sp"]["id"],
                    "label": best["sp"]["label"],
                    "lat": best["sp"]["lat"],
                    "lon": best["sp"]["lon"]
                },
                "route_attempted": True,
                "no_safe_route": False,
                "distance_m": best["dist"],
                "eta_sec": None,
                "profile_applied": profile_applied,
                "limit": limit_text
            }
        
        return not_required("알 수 없는 행동입니다.")

def provider_for(
    payload: dict, safe_points: list[dict[str, Any]]
) -> DesignatedPointRouteProvider:
    """`payload` 한 건에 대한 실제 경로 엔진.

    `sensors` 는 시나리오마다 다르므로 **요청마다** 만든다. 반대로 `safe_points` 는
    7곳으로 닫혀 있어(C-32) 호출자가 한 번 읽어 넘긴다 - 여기서 파일을 열면 요청마다
    디스크를 친다.

    어느 시나리오가 LIVE 인지는 **데모 판단이라 여기서 정하지 않는다.** 그 분기는
    `api/main.py` 가 들고 있다.
    """
    return DesignatedPointRouteProvider(
        safe_points=safe_points,
        sensors=payload.get("risk", {}).get("sensors", []),
    )


def route_request_from(
    payload: dict, primary_action: Action, profiles: tuple[Profile, ...] = ()
) -> RouteRequest:
    """`AssessResponse` payload 에서 경로 엔진 입력을 만든다.

    입력 7개는 전부 payload 안에 이미 있다 - 새로 계산하는 값이 없다.

    **`api/main.py` 와 테스트가 같은 함수를 통과한다.** 한쪽만 payload 를 다르게
    읽으면 "픽스처를 그대로 받는다"가 아니라 "정제하면 통과한다"를 증명하게 된다(C-21).
    같은 이유로 `services/decision/adapters.py` 의 `signals_from()` 도 앱 코드 쪽에 있다.

    `destination` 은 `RouteRequest` 의 필수 필드(F-19)인데 `EVACUATE` 시나리오처럼
    `user_state.destination` 이 비어 있는 응답도 있다. `EVACUATE` 는 이 값을 쓰지
    않으므로(`solve()` 의 `EVACUATE` 분기가 `request.destination` 을 참조하지 않는다)
    `origin` 과 같은 좌표의 빈 자리표시자로 채운다 - `MOVE` 에서 목적지가 비는 경우는
    없다(픽스처가 항상 기본 목적지를 채워 둔다).

    **목적지는 `decision.user_state.destination` 에 있다.** payload 최상위에는 없다 -
    최상위를 읽으면 조용히 `(0.0, 0.0)` 이 되어 `distance_m` 이 4,900km 로 나온다.
    """
    location = payload["location"]
    origin = RoutePoint(lat=location["lat"], lon=location["lon"])

    dest = payload["decision"]["user_state"].get("destination")
    if dest is not None:
        destination = DestinationPoint(
            id=dest["id"], label=dest["label"], lat=dest["lat"], lon=dest["lon"]
        )
    else:
        destination = DestinationPoint(id="", label="", lat=origin.lat, lon=origin.lon)

    return RouteRequest(
        primary_action=primary_action,
        origin=origin,
        destination=destination,
        asof=payload["risk"]["asof"],
        profiles=tuple(Profile(pf) for pf in profiles),
        official=payload.get("official", {}),
        in_service_area=location["in_service_area"],
    )
