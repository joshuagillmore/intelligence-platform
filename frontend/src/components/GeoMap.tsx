'use client';
import { useEffect, useState } from 'react';

import 'leaflet/dist/leaflet.css';

interface GeoLocation {
  id: string;
  name: string;
  latitude?: number | null;
  longitude?: number | null;
  lat?: number | null;
  lng?: number | null;
  geocoded?: boolean;
  connections?: number;
  properties?: Record<string, unknown>;
}

interface ConnectionLine {
  from: [number, number];
  to: [number, number];
  names: string;
}

interface GeoMapProps {
  locations: GeoLocation[];
  connectionLines?: ConnectionLine[];
  onLocationClick?: (location: GeoLocation) => void;
  selectedLocationId?: string | null;
}

function getLat(loc: GeoLocation): number | null {
  return (loc.latitude ?? loc.lat ?? (loc.properties?.latitude as number | undefined)) || null;
}

function getLng(loc: GeoLocation): number | null {
  return (loc.longitude ?? loc.lng ?? (loc.properties?.longitude as number | undefined)) || null;
}

function GeoMapInner({ locations, connectionLines = [], onLocationClick, selectedLocationId }: GeoMapProps) {
  const [L, setL] = useState<typeof import('leaflet') | null>(null);
  const [MapComponents, setMapComponents] = useState<typeof import('react-leaflet') | null>(null);

  useEffect(() => {
    Promise.all([
      import('leaflet'),
      import('react-leaflet'),
    ]).then(([leaflet, reactLeaflet]) => {
      // Fix default marker icons
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (leaflet.default.Icon.Default.prototype as any)._getIconUrl;
      leaflet.default.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
      });
      setL(leaflet);
      setMapComponents(reactLeaflet);
    });
  }, []);

  if (!L || !MapComponents) {
    return <div className="w-full h-full bg-navy-800 flex items-center justify-center text-gray-500">Loading map...</div>;
  }

  const { MapContainer, TileLayer, CircleMarker, Popup, Polyline } = MapComponents;

  const geocodedLocations = locations.filter(loc => {
    const lat = getLat(loc);
    const lng = getLng(loc);
    return lat != null && lng != null;
  });

  return (
    <MapContainer
      center={[20, 60] as [number, number]}
      zoom={3}
      style={{ width: '100%', height: '100%', borderRadius: '0.5rem' }}
      className="z-0"
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      {connectionLines.map((line, i) => (
        <Polyline
          key={`line-${i}`}
          positions={[line.from, line.to]}
          color="#3b82f6"
          weight={1}
          opacity={0.4}
          dashArray="5,5"
        />
      ))}
      {geocodedLocations.map((loc) => {
        const lat = getLat(loc)!;
        const lng = getLng(loc)!;
        const connCount = loc.connections || 0;
        return (
          <CircleMarker
            key={loc.id}
            center={[lat, lng] as [number, number]}
            radius={Math.max(6, Math.min(16, (connCount || 1) * 2))}
            fillColor={selectedLocationId === loc.id ? '#f97316' : '#3b82f6'}
            fillOpacity={0.8}
            color={selectedLocationId === loc.id ? '#f97316' : '#60a5fa'}
            weight={2}
            eventHandlers={{
              click: () => onLocationClick?.(loc),
            }}
          >
            <Popup>
              <div className="text-sm">
                <strong>{loc.name}</strong>
                <br />
                Connections: {connCount}
                <br />
                Lat: {lat.toFixed(4)}, Lng: {lng.toFixed(4)}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}

export default function GeoMap(props: GeoMapProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="w-full h-full bg-navy-800 flex items-center justify-center text-gray-500">Loading map...</div>;
  return <GeoMapInner {...props} />;
}
