import json
from pathlib import Path
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
                    "profile_applied": [],
                    "limit": "지정 지점에 대한 점대점 비교 결과이며 실제 통행 가능성이나 안전을 보장하지 않습니다."
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

            candidates.sort(key=lambda x: (x["risk"], x["dist"], x["sp"]["id"]))
            
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
                "profile_applied": [],
                "limit": "공식 대피시설 후보의 상대 비교 결과이며 실제 통행 가능성이나 안전을 보장하지 않습니다."
            }
        
        return not_required("알 수 없는 행동입니다.")

def provider_for(payload: dict) -> DesignatedPointRouteProvider:
    safe_points_path = Path(__file__).parent.parent.parent / "contracts" / "safe_points.json"
    with open(safe_points_path, "r", encoding="utf-8") as f:
        sp_data = json.load(f)
    
    sensors = []
    if "risk" in payload and "sensors" in payload["risk"]:
        sensors = payload["risk"]["sensors"]
        
    return DesignatedPointRouteProvider(
        safe_points=sp_data.get("points", []),
        sensors=sensors
    )

def route_request_from(payload: dict, primary_action: Action, profiles: tuple[Profile, ...] = ()) -> RouteRequest:
    loc = payload.get("location") or {}
    origin = RoutePoint(lat=loc.get("lat", 0.0), lon=loc.get("lon", 0.0))
    
    dest_data = payload.get("destination") or {}
    dest = DestinationPoint(
        id=dest_data.get("id", ""),
        label=dest_data.get("label", ""),
        lat=dest_data.get("lat", 0.0),
        lon=dest_data.get("lon", 0.0)
    )
    
    risk_data = payload.get("risk") or {}
    asof = risk_data.get("asof", "2022-08-08T21:40:00+09:00")
    
    official = payload.get("official") or {}
    
    return RouteRequest(
        primary_action=primary_action,
        origin=origin,
        destination=dest,
        asof=asof,
        profiles=profiles,
        official=official,
        in_service_area=True
    )
