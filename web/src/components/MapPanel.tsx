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

        // 원래 스펙대로 직선(점선)만 그려서 UI 시각화 (선 색상: 파란색)
        L.polyline(
          [
            [lat, lon],
            [target.lat, target.lon],
          ],
          { weight: 4, dashArray: '8 6', opacity: 0.8, color: '#0066ff' },
        ).addTo(map);
      }
    } catch {
      setTiles('failed');
    }

    return () => {
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
