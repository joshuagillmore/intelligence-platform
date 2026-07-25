'use client';
import { useEffect, useState, useRef } from 'react';
import { TYPE_COLOR_HEX } from '@/lib/entityStyles';

// DO NOT import leaflet CSS at top level - it crashes SSR
// import 'leaflet/dist/leaflet.css';

interface GeoLocation {
  id: string;
  name: string;
  latitude?: number | null;
  longitude?: number | null;
  lat?: number | null;
  lng?: number | null;
  geocoded?: boolean;
  connections?: number;
  connection_count?: number;
  entity_type?: string;
  geo_source?: string;
  geo_confidence?: string;
  mgrs?: string;
  location_type?: string;
  properties?: Record<string, unknown>;
  relationships?: Array<{target_name: string; rel_type: string}>;
}

interface ConnectionLine {
  from: [number, number];
  to: [number, number];
  names: string;
  weight?: number;
  shared_entities?: string[];
}

interface GeoMapProps {
  locations: GeoLocation[];
  connectionLines?: ConnectionLine[];
  onLocationClick?: (location: GeoLocation) => void;
  selectedLocationId?: string | null;
  showRelationships?: boolean;
  heatMap?: boolean;
  onBoundsChange?: (b: { minLat: number; minLng: number; maxLat: number; maxLng: number }) => void;
}

function getLat(loc: GeoLocation): number | null {
  // `== null`, not `|| null` — a real 0 (equator) must not be dropped.
  const v = loc.latitude ?? loc.lat ?? (loc.properties?.latitude as number | undefined);
  return v == null ? null : v;
}

function getLng(loc: GeoLocation): number | null {
  const v = loc.longitude ?? loc.lng ?? (loc.properties?.longitude as number | undefined);
  return v == null ? null : v;
}

// Escape strings interpolated into leaflet popup HTML — entity names come from
// scraped documents (attacker-influenceable), and this repo is going public.
function esc(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string),
  );
}

export default function GeoMap({ locations, connectionLines = [], onLocationClick, selectedLocationId, showRelationships = true, heatMap = false, onBoundsChange }: GeoMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [mapReady, setMapReady] = useState(false);
  const [error, setError] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const leafletMapRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const leafletRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const linesRef = useRef<any[]>([]);

  useEffect(() => {
    if (!mapRef.current || leafletMapRef.current) return;

    // Dynamically import Leaflet and its CSS to avoid SSR crashes
    // @ts-expect-error - CSS import has no type declaration
    const cssImport = import('leaflet/dist/leaflet.css');
    Promise.all([
      import('leaflet'),
      cssImport,
    ]).then(([L]) => {
      try {
        if (!mapRef.current) return;

        // Fix default marker icons
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delete (L.default.Icon.Default.prototype as any)._getIconUrl;
        L.default.Icon.Default.mergeOptions({
          iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
          iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
          shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
        });

        // Leaflet's own controls default to the top corners, where they sat on
        // top of the geo page's floating panels (zoom over "Layer Control" at
        // top-left, the basemap switcher over the stats pills at top-right —
        // Leaflet controls are z-index 1000, so they always won). Both move to
        // the bottom corners, which the page leaves free, so each corner has a
        // single owner.
        const map = L.default.map(mapRef.current, { zoomControl: false }).setView([20, 40], 3);
        L.default.control.zoom({ position: 'bottomleft' }).addTo(map);

        // Basemap / imagery switcher — dark default, plus streets, topo, and
        // keyless satellite (EOX Sentinel-2 cloudless 2016, CC BY 4.0 —
        // commercial-safe, unlike the NC-licensed recent mosaics). All
        // attributions carried per each source's terms.
        const baseLayers = {
          Dark: L.default.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
          }),
          Streets: L.default.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19,
          }),
          Topographic: L.default.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
            attribution: 'Map data: &copy; OpenStreetMap, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
            maxZoom: 17,
          }),
          Satellite: L.default.tileLayer('https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2016_3857/default/g/{z}/{y}/{x}.jpg', {
            attribution: 'Sentinel-2 cloudless 2016 &copy; <a href="https://s2maps.eu">EOX</a> (CC BY 4.0, Copernicus Sentinel data)',
            maxZoom: 16,
          }),
        };
        baseLayers.Dark.addTo(map);
        L.default.control.layers(baseLayers, {}, { position: 'bottomright', collapsed: true }).addTo(map);

        // Report view bounds so the page can run AOI ("what's in this area") queries.
        const emitBounds = () => {
          const b = map.getBounds();
          onBoundsChange?.({ minLat: b.getSouth(), minLng: b.getWest(), maxLat: b.getNorth(), maxLng: b.getEast() });
        };
        map.on('moveend', emitBounds);
        emitBounds();

        leafletMapRef.current = map;
        leafletRef.current = L.default;
        setMapReady(true);
      } catch {
        setError(true);
      }
    }).catch(() => {
      setError(true);
    });

    return () => {
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
      }
    };
    // Once-only map init; onBoundsChange is a stable useState setter from the
    // parent, so capturing it here is intentional (no stale-closure bug).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update markers when locations change
  useEffect(() => {
    if (!leafletMapRef.current || !mapReady || !leafletRef.current) return;

    const map = leafletMapRef.current;
    const L = leafletRef.current;

    // Clear existing markers
    markersRef.current.forEach(m => map.removeLayer(m));
    markersRef.current = [];

    // Clear existing lines
    linesRef.current.forEach(l => map.removeLayer(l));
    linesRef.current = [];

    // Add connection lines between locations (edges based on shared entities)
    const maxWeight = Math.max(1, ...connectionLines.map(l => l.weight || 1));
    if (showRelationships) connectionLines.forEach(line => {
      const w = line.weight || 1;
      const lineWidth = Math.max(1, Math.min(6, (w / maxWeight) * 6));
      const opacity = Math.max(0.3, Math.min(0.8, 0.3 + (w / maxWeight) * 0.5));
      const polyline = L.polyline([line.from, line.to], {
        color: '#3b82f6',
        weight: lineWidth,
        opacity,
      }).addTo(map);
      // Tooltip showing shared entities
      const sharedText = line.shared_entities?.length
        ? `<br><br>Shared entities:<br>${line.shared_entities.map((e: string) => `• ${esc(e)}`).join('<br>')}`
        : '';
      polyline.bindPopup(
        `<div style="font-size:12px"><b>${esc(line.names)}</b><br>Shared entities: ${w}${sharedText}</div>`
      );
      linesRef.current.push(polyline);
    });

    // Add markers for geocoded locations
    const geocoded = locations.filter(loc => getLat(loc) != null && getLng(loc) != null);

    const maxConn = Math.max(1, ...geocoded.map(l => l.connections || l.connection_count || 0));
    geocoded.forEach(loc => {
      const lat = getLat(loc)!;
      const lng = getLng(loc)!;
      const connCount = loc.connections || loc.connection_count || 0;
      const t = maxConn > 0 ? connCount / maxConn : 0;
      // Density layer: warm gradient + larger radius for higher-connection hubs (raw connection count, not activity/change)
      const heatFill = t > 0.66 ? '#ef4444' : t > 0.33 ? '#f59e0b' : '#3b82f6';
      const radius = heatMap
        ? Math.max(8, Math.min(28, 8 + t * 20))
        : Math.max(6, Math.min(16, (connCount || 1) * 2));
      const isSelected = selectedLocationId === loc.id;
      // Colour by entity type (IPs, facilities, actors distinct from places);
      // report-derived coordinate points get their own amber; heatMap mode keeps
      // the connection-tier gradient.
      const isCoord = (loc.location_type ?? (loc.properties?.location_type as string | undefined)) === 'coordinate';
      const typeColor = isCoord
        ? '#eab308'
        : ((loc.entity_type && TYPE_COLOR_HEX[loc.entity_type]) || '#3b82f6');

      const marker = L.circleMarker([lat, lng], {
        radius,
        fillColor: isSelected ? '#f97316' : (heatMap ? heatFill : typeColor),
        fillOpacity: heatMap ? 0.55 : 0.8,
        color: isSelected ? '#f97316' : (heatMap ? heatFill : typeColor),
        weight: 2,
      }).addTo(map);

      const srcLabel = loc.geo_source === 'geoip'
        ? 'IP geolocation (approximate)'
        : (loc.geo_source || '');
      marker.bindPopup(
        `<div style="font-size:12px"><b>${esc(loc.name)}</b>` +
        `${loc.entity_type ? `<br><span style="opacity:.7">${esc(loc.entity_type)}${loc.location_type ? ` · ${esc(loc.location_type)}` : ''}</span>` : ''}` +
        `<br>Connections: ${connCount}<br>Lat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}` +
        `${loc.mgrs ? `<br>MGRS: ${esc(loc.mgrs)}` : ''}` +
        `${loc.geo_confidence && loc.geo_confidence !== 'high' ? `<br><i style="opacity:.6">confidence: ${esc(loc.geo_confidence)}</i>` : ''}` +
        `${srcLabel ? `<br><i style="opacity:.7">${esc(srcLabel)}</i>` : ''}</div>`
      );

      if (onLocationClick) {
        marker.on('click', () => onLocationClick(loc));
      }

      markersRef.current.push(marker);
    });
  }, [locations, connectionLines, mapReady, selectedLocationId, onLocationClick, showRelationships, heatMap]);

  if (error) {
    // Fallback: show location table
    const geocoded = locations.filter(loc => getLat(loc) != null && getLng(loc) != null);
    return (
      <div className="w-full h-full bg-navy-800 p-4 overflow-y-auto">
        <p className="text-sm text-gray-400 mb-3">Map unavailable. Showing location data:</p>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-navy-600">
              <th className="text-left py-1">Location</th>
              <th className="text-right py-1">Lat</th>
              <th className="text-right py-1">Lng</th>
              <th className="text-right py-1">Connections</th>
            </tr>
          </thead>
          <tbody>
            {geocoded.map(loc => (
              <tr key={loc.id} className="border-b border-navy-700 cursor-pointer hover:bg-navy-700"
                  onClick={() => onLocationClick?.(loc)}>
                <td className="py-1 text-gray-200">{loc.name}</td>
                <td className="text-right text-gray-400">{getLat(loc)?.toFixed(2)}</td>
                <td className="text-right text-gray-400">{getLng(loc)?.toFixed(2)}</td>
                <td className="text-right text-gray-400">{loc.connections || loc.connection_count || 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div ref={mapRef} className="w-full h-full" style={{ minHeight: '400px', zIndex: 0, borderRadius: '0.5rem' }} />
  );
}
