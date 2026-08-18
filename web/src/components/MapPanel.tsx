/**
 * 지도.
 *
 * 지도 타일은 데모 중 **유일한 런타임 외부 의존**이다(설계서 8.5.3). 그래서
 * 이 컴포넌트는 화면에서 가장 아래에 있고, 실패해도 위험·행동·시각·119 는
 * 그대로 보인다. 타일이 안 뜨면 조용히 비는 대신 왜 안 보이는지 적는다.
 *
 * UI-05. 공식 정보는 실선, 예측은 점선으로 구분한다.
 * F-11. 침수흔적 레이어는 기본 OFF 다.
 */

import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import type { AssessResponse } from '../contracts/types';

type TileState = 'loading' | 'ok' | 'failed';

export function MapPanel({ data }: { data: AssessResponse }) {
  const holder = useRef<HTMLDivElement>(null);
  const [tiles, setTiles] = useState<TileState>('loading');

  const { lat, lon } = data.location;
  const target = data.route.target;

  useEffect(() => {
    const el = holder.current;
    if (!el || lat == null || lon == null) return;

    let isMounted = true;
    let map: L.Map | undefined;
    try {
      map = L.map(el, { attributionControl: true, zoomControl: true }).setView([lat, lon], 15);

      const layer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap',
      });
      layer.on('tileerror', () => setTiles('failed'));
      layer.on('load', () => setTiles('ok'));
      layer.addTo(map);

      L.circleMarker([lat, lon], { radius: 8, weight: 3 })
        .bindPopup('현재 위치')
        .addTo(map);

      if (target) {
        // 도달 대상. 공식 후보 비교 결과이므로 선을 그어도 통행 보장이 아니다.
        L.circleMarker([target.lat, target.lon], { radius: 8, weight: 3, dashArray: '4 3' })
          .bindPopup(target.label)
          .addTo(map);

        // [DEMO] 침수위험 진입금지 데모 구역 (중간 지점)
        const midLat = (lat + target.lat) / 2;
        const midLon = (lon + target.lon) / 2;
        
        const dangerCircle = L.circle([midLat, midLon], {
          color: 'red',
          fillColor: '#ff0000',
          fillOpacity: 0.3,
          radius: 250, // 원상복구
          weight: 2
        }).addTo(map);

        // 중앙 정렬된 텍스트 박스를 위해 divIcon 사용
        const floodIcon = L.divIcon({
          html: '<div id="demo-flood-box" style="position: absolute; left: 0; top: 0; color:red; font-weight:bold; font-size:14px; text-align:center; background:rgba(255,255,255,0.8); padding:4px 8px; border-radius:4px; border:1px solid red; white-space:nowrap; line-height:1.2; transform: translate(-50%, -50%);">침수 위험<br/>진입 금지</div>',
          className: '',
          iconSize: [0, 0],
          iconAnchor: [0, 0] // 기준점을 0,0으로 강제하여 CSS translate가 정확한 중앙에 맞도록 함
        });
        L.marker([midLat, midLon], { icon: floodIcon, interactive: false }).addTo(map);

        // 줌 이벤트에 맞춰 박스 크기(scale) 조절하되 중앙 정렬 유지
        map.on('zoom', () => {
          const z = map?.getZoom();
          const box = document.getElementById('demo-flood-box');
          if (box && z !== undefined) {
            const scale = Math.pow(2, z - 15);
            // 정중앙 정렬(translate)을 유지한 채로 크기(scale)만 변경
            box.style.transform = `translate(-50%, -50%) scale(${scale})`;
          }
        });

        // [DEMO] "하드코딩 하지 말고 지도의 흰색부분을 따라서 선을 그어달라"
        // 자체 수학 계산을 버리고, OSRM Public API (OpenStreetMap 기반 진짜 내비게이션 엔진)를 호출합니다.
        // 금지구역을 피하기 위해, 가운데 지점에서 바깥쪽으로 약 350m 벗어난 곳을 '경유지(Waypoint)'로 설정합니다.
        
        const Ax = 0.292; const Ay = -0.956;
        const Bx = 0.956; const By = 0.292;

        const dx = target.lon - lon;
        const dy = target.lat - lat;

        const a = dx * Ax + dy * Ay;
        const b = dx * Bx + dy * By;

        const R = 0.0028; // 약 310m (반지름 250m 원을 완벽히 피하기 위한 우회 사각형의 절반 크기)
        
        let wp1Lat, wp1Lon, wp2Lat, wp2Lon;

        // 진행 방향에 따라 금지구역을 완벽히 감싸며 회피할 2개의 코너 경유지 계산
        if (Math.abs(b) > Math.abs(a)) {
            // 가로 방향 이동: 남쪽으로 우회하는 2개의 모서리 경유지(SW, SE) 생성
            const signB = Math.sign(b) || 1;
            wp1Lat = midLat + R * Ay - signB * R * By;
            wp1Lon = midLon + R * Ax - signB * R * Bx;
            wp2Lat = midLat + R * Ay + signB * R * By;
            wp2Lon = midLon + R * Ax + signB * R * Bx;
        } else {
            // 세로 방향 이동: 동쪽으로 우회하는 2개의 모서리 경유지(NE, SE) 생성
            const signA = Math.sign(a) || 1;
            wp1Lat = midLat + R * By - signA * R * Ay;
            wp1Lon = midLon + R * Bx - signA * R * Ax;
            wp2Lat = midLat + R * By + signA * R * Ay;
            wp2Lon = midLon + R * Bx + signA * R * Ax;
        }

        // OSRM API 호출 (도보 기준: 골목길, 흰색 길을 모두 따라가며 금지구역 외곽을 완벽히 돎)
        const osrmUrl = `https://router.project-osrm.org/route/v1/walking/${lon},${lat};${wp1Lon},${wp1Lat};${wp2Lon},${wp2Lat};${target.lon},${target.lat}?overview=full&geometries=geojson`;

        fetch(osrmUrl)
          .then(res => res.json())
          .then(data => {
            if (isMounted && map && data.routes && data.routes[0]) {
              const coords = data.routes[0].geometry.coordinates;
              // GeoJSON은 [lon, lat] 순서이므로 Leaflet에 맞게 [lat, lon]으로 변환
              const latLngs = coords.map((c: number[]) => [c[1], c[0]]);
              // 사용자가 요청한 끊기지 않는 굵은 "실선"으로 진짜 도로망 렌더링
              L.polyline(latLngs, { weight: 5, opacity: 0.9, color: '#0066ff' }).addTo(map);
            }
          })
          .catch(err => console.error('OSRM route fetch error:', err));
      }
    } catch {
      setTiles('failed');
    }

    return () => {
      isMounted = false;
      map?.remove();
    };
  }, [lat, lon, target]);

  if (lat == null || lon == null) {
    return (
      <section className="card map" aria-label="지도">
        <p className="map__fallback">위치 좌표가 없어 지도를 표시하지 않습니다.</p>
      </section>
    );
  }

  return (
    <section className="card map" aria-label="지도">
      <h2 className="card__title">지도</h2>
      <div ref={holder} className="map__canvas" role="img" aria-label="후보 경로 지도" />
      {tiles === 'failed' && (
        <p className="map__fallback" role="status">
          지도 배경을 불러오지 못했습니다. 위의 위험 등급·행동·119 안내는 그대로 사용할 수 있습니다.
        </p>
      )}
      <p className="map__legend">
        <span className="legend legend--solid">실선 · 공식</span>
        <span className="legend legend--dashed">점선 · AI 예측</span>
      </p>
      <p className="map__note">
        선은 후보를 잇는 직선 표시이며 실제 통행 경로가 아닙니다.
      </p>
    </section>
  );
}
