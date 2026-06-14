'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { geoApi } from '@/lib/api';
import { Btn, Tag, Icon, PulseDot } from '@/components/sentinel';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LocationKind = 'port' | 'anomaly';

interface GeoLocation {
  id: string;
  name: string;
  lat: number;
  lng: number;
  entity_type?: string;
  entity_id?: string;
  country?: string;
  events?: number;
  kind?: LocationKind;
}

type FilterKind = 'all' | 'port' | 'anomaly';

// ---------------------------------------------------------------------------
// Projection — gentle polar-ish: lat [40,85] → y, lon [-15,50] → x
// ---------------------------------------------------------------------------

const LAT_MIN = 40;
const LAT_MAX = 85;
const LON_MIN = -15;
const LON_MAX = 50;
const MAP_W = 1000;
const MAP_H = 600;
const PAD_X = 60;
const PAD_Y = 40;

function project(lat: number, lon: number): { x: number; y: number } {
  const lonClamped = Math.max(LON_MIN, Math.min(LON_MAX, lon));
  const latClamped = Math.max(LAT_MIN, Math.min(LAT_MAX, lat));

  const lonNorm = (lonClamped - LON_MIN) / (LON_MAX - LON_MIN);
  const latNorm = (latClamped - LAT_MIN) / (LAT_MAX - LAT_MIN);

  // Gentle compression at top — squeezes high-latitude x toward center
  const compress = 1 - latNorm * 0.32;
  const xFromCenter = (lonNorm - 0.5) * compress;
  const x = PAD_X + (xFromCenter + 0.5) * (MAP_W - PAD_X * 2);

  // Invert lat (higher lat → lower y)
  const y = PAD_Y + (1 - latNorm) * (MAP_H - PAD_Y * 2);

  return { x, y };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function inferKind(loc: GeoLocation): LocationKind {
  if (loc.kind) return loc.kind;
  const name = (loc.name || '').toLowerCase();
  if (name.includes('loiter') || name.includes('anomaly') || name.includes('dark')) return 'anomaly';
  if (loc.entity_type === 'INDICATOR') return 'anomaly';
  return 'port';
}

function colorForKind(kind: LocationKind): string {
  return kind === 'anomaly' ? 'var(--warn)' : 'var(--cite)';
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export function GeoView() {
  const router = useRouter();
  const { activeProject } = useProject();

  const [locations, setLocations] = useState<GeoLocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKind>('all');
  const [showTracks, setShowTracks] = useState(true);
  const [tSlider, setTSlider] = useState(1);

  useEffect(() => {
    if (!activeProject) {
      setLocations([]);
      return;
    }
    setLoading(true);
    geoApi
      .locations(activeProject.id)
      .then((res) => {
        const raw = res.data as
          | GeoLocation[]
          | { locations?: GeoLocation[]; data?: GeoLocation[] }
          | undefined;
        const items: GeoLocation[] = Array.isArray(raw)
          ? raw
          : Array.isArray(raw?.locations)
            ? raw.locations
            : Array.isArray(raw?.data)
              ? raw.data
              : [];
        setLocations(items);
        if (items.length && !selectedId) setSelectedId(items[0].id);
      })
      .catch(() => setLocations([]))
      .finally(() => setLoading(false));
  }, [activeProject]); // eslint-disable-line react-hooks/exhaustive-deps

  const enriched = useMemo(
    () =>
      locations.map((l) => ({
        ...l,
        _kind: inferKind(l),
        _proj: project(l.lat, l.lng),
      })),
    [locations],
  );

  const filtered = useMemo(
    () => (filter === 'all' ? enriched : enriched.filter((l) => l._kind === filter)),
    [enriched, filter],
  );

  const selected = enriched.find((l) => l.id === selectedId) || null;

  if (!activeProject) {
    return (
      <EmptyState
        title="No active project"
        body="Select a project to view geospatial intelligence."
        action={<Btn variant="solid" icon="arrow-right" onClick={() => router.push('/')}>Open hub</Btn>}
      />
    );
  }

  return (
    <div
      style={{
        height: '100%',
        display: 'grid',
        gridTemplateColumns: '1fr 320px',
        gridTemplateRows: 'auto 1fr auto',
        background: 'var(--paper)',
        overflow: 'hidden',
      }}
    >
      {/* Toolbar — spans both columns */}
      <Toolbar
        filter={filter}
        setFilter={setFilter}
        showTracks={showTracks}
        setShowTracks={setShowTracks}
        count={filtered.length}
      />

      {/* Map */}
      <div
        style={{
          gridRow: 2,
          gridColumn: 1,
          position: 'relative',
          background: 'var(--paper-2)',
          borderRight: '1px solid var(--line)',
          overflow: 'hidden',
        }}
      >
        {loading ? (
          <LoadingOverlay text="Resolving locations…" />
        ) : enriched.length === 0 ? (
          <LoadingOverlay text="No geospatial data for this project." />
        ) : (
          <MapSvg
            items={filtered}
            selectedId={selectedId}
            onSelect={setSelectedId}
            showTracks={showTracks}
          />
        )}
      </div>

      {/* Inspector */}
      <aside
        style={{
          gridRow: 2,
          gridColumn: 2,
          background: 'var(--paper)',
          overflowY: 'auto',
        }}
      >
        <GeoInspector
          selected={selected}
          onOpenEntity={(eid) => router.push(`/network?entity=${eid}`)}
        />
      </aside>

      {/* Temporal slider — spans both columns */}
      <TemporalSlider value={tSlider} onChange={setTSlider} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

function Toolbar({
  filter,
  setFilter,
  showTracks,
  setShowTracks,
  count,
}: {
  filter: FilterKind;
  setFilter: (f: FilterKind) => void;
  showTracks: boolean;
  setShowTracks: (v: boolean) => void;
  count: number;
}) {
  const chips: { id: FilterKind; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'port', label: 'Ports' },
    { id: 'anomaly', label: 'Anomalies' },
  ];

  return (
    <div
      style={{
        gridRow: 1,
        gridColumn: '1 / span 2',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '14px 22px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--paper)',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 9.5,
            letterSpacing: '0.2em',
            color: 'var(--fg-3)',
            fontWeight: 600,
            textTransform: 'uppercase',
          }}
        >
          GEO LENS
        </span>
        <h1
          style={{
            margin: '2px 0 0',
            fontFamily: 'var(--serif)',
            fontWeight: 500,
            fontSize: 22,
            color: 'var(--ink)',
            letterSpacing: '-0.01em',
          }}
        >
          Geo · vessel movement
        </h1>
      </div>

      <span style={{ flex: 1 }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {chips.map((c) => (
          <FilterChip
            key={c.id}
            active={filter === c.id}
            onClick={() => setFilter(c.id)}
          >
            {c.label}
          </FilterChip>
        ))}
      </div>

      <div style={{ width: 1, height: 22, background: 'var(--line)' }} />

      <button
        onClick={() => setShowTracks(!showTracks)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 10px',
          fontFamily: 'var(--sans)',
          fontSize: 11.5,
          color: showTracks ? 'var(--ink)' : 'var(--fg-3)',
          background: showTracks ? 'var(--paper-2)' : 'transparent',
          border: '1px solid var(--line)',
          borderRadius: 3,
          cursor: 'pointer',
        }}
      >
        <Icon name={showTracks ? 'eye' : 'eye'} size={12} />
        Tracks
      </button>

      <Tag tone="neutral">{count} VISIBLE</Tag>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 10px',
        fontFamily: 'var(--mono)',
        fontSize: 10.5,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        background: active ? 'var(--ink)' : 'transparent',
        color: active ? 'var(--paper)' : 'var(--fg-2)',
        border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
        borderRadius: 3,
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Map SVG
// ---------------------------------------------------------------------------

interface ProjectedItem extends GeoLocation {
  _kind: LocationKind;
  _proj: { x: number; y: number };
}

function MapSvg({
  items,
  selectedId,
  onSelect,
  showTracks,
}: {
  items: ProjectedItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  showTracks: boolean;
}) {
  // Build simple per-vessel-ish track from anomalies sorted by id (visual only)
  const trackPath = useMemo(() => {
    if (!showTracks) return '';
    const sorted = [...items].sort((a, b) => a.id.localeCompare(b.id));
    if (sorted.length < 2) return '';
    return sorted
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p._proj.x.toFixed(1)} ${p._proj.y.toFixed(1)}`)
      .join(' ');
  }, [items, showTracks]);

  return (
    <svg
      viewBox={`0 0 ${MAP_W} ${MAP_H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', display: 'block' }}
    >
      {/* Background grid — meridians */}
      <g stroke="var(--line-soft)" strokeWidth={0.7} fill="none">
        {Array.from({ length: 7 }).map((_, i) => {
          const lon = LON_MIN + ((LON_MAX - LON_MIN) / 6) * i;
          const top = project(LAT_MAX, lon);
          const bot = project(LAT_MIN, lon);
          return (
            <line
              key={`m${i}`}
              x1={top.x}
              y1={top.y}
              x2={bot.x}
              y2={bot.y}
            />
          );
        })}
        {Array.from({ length: 6 }).map((_, i) => {
          const lat = LAT_MIN + ((LAT_MAX - LAT_MIN) / 5) * i;
          // Build a subtle parallel as polyline through projected points
          const pts: string[] = [];
          for (let k = 0; k <= 12; k++) {
            const lon = LON_MIN + ((LON_MAX - LON_MIN) / 12) * k;
            const p = project(lat, lon);
            pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
          }
          return <polyline key={`p${i}`} points={pts.join(' ')} />;
        })}
      </g>

      {/* Lat labels */}
      <g
        fill="var(--fg-4)"
        fontFamily="var(--mono)"
        fontSize={9}
        style={{ letterSpacing: '0.08em' }}
      >
        {Array.from({ length: 6 }).map((_, i) => {
          const lat = LAT_MIN + ((LAT_MAX - LAT_MIN) / 5) * i;
          const p = project(lat, LON_MIN);
          return (
            <text key={i} x={p.x - 6} y={p.y + 3} textAnchor="end">
              {Math.round(lat)}°
            </text>
          );
        })}
      </g>

      {/* Track */}
      {showTracks && trackPath && (
        <path
          d={trackPath}
          fill="none"
          stroke="var(--violet)"
          strokeWidth={1.2}
          strokeDasharray="4 3"
          opacity={0.55}
        />
      )}

      {/* Points */}
      {items.map((it) => {
        const isSel = it.id === selectedId;
        const color = colorForKind(it._kind);
        const r = isSel ? 7 : 5;
        return (
          <g
            key={it.id}
            onClick={() => onSelect(it.id)}
            style={{ cursor: 'pointer' }}
          >
            {isSel && (
              <circle
                cx={it._proj.x}
                cy={it._proj.y}
                r={r + 5}
                fill="none"
                stroke={color}
                strokeWidth={1}
                opacity={0.5}
              />
            )}
            <circle
              cx={it._proj.x}
              cy={it._proj.y}
              r={r}
              fill={color}
              stroke="var(--paper)"
              strokeWidth={1.2}
            />
            <text
              x={it._proj.x}
              y={it._proj.y + r + 12}
              textAnchor="middle"
              fontFamily="var(--mono)"
              fontSize={9.5}
              fill={isSel ? 'var(--ink)' : 'var(--fg-2)'}
              style={{ letterSpacing: '0.04em', userSelect: 'none' }}
            >
              {truncate(it.name, 22)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

// ---------------------------------------------------------------------------
// Inspector
// ---------------------------------------------------------------------------

function GeoInspector({
  selected,
  onOpenEntity,
}: {
  selected: ProjectedItem | null;
  onOpenEntity: (entityId: string) => void;
}) {
  if (!selected) {
    return (
      <div style={{ padding: '24px 22px' }}>
        <SectionLabel>INSPECTOR</SectionLabel>
        <p style={{ marginTop: 14, fontSize: 12.5, color: 'var(--fg-3)', lineHeight: 1.5 }}>
          Select a point on the map to inspect.
        </p>
      </div>
    );
  }

  const color = colorForKind(selected._kind);

  return (
    <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <SectionLabel>INSPECTOR</SectionLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: color,
              flexShrink: 0,
            }}
          />
          <Tag tone={selected._kind === 'anomaly' ? 'warn' : 'cite'}>
            {selected._kind.toUpperCase()}
          </Tag>
        </div>
        <h2
          style={{
            margin: '8px 0 0',
            fontFamily: 'var(--serif)',
            fontWeight: 500,
            fontSize: 20,
            lineHeight: 1.2,
            color: 'var(--ink)',
            letterSpacing: '-0.01em',
          }}
        >
          {selected.name}
        </h2>
      </div>

      <DataRow label="COUNTRY" value={selected.country || '—'} />
      <DataRow
        label="EVENTS"
        value={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 14, color: 'var(--ink)' }}>
              {selected.events ?? 0}
            </span>
            {(selected.events ?? 0) > 0 && <PulseDot color={color} size={5} />}
          </span>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <DataRow label="LAT" value={selected.lat.toFixed(3)} mono />
        <DataRow label="LON" value={selected.lng.toFixed(3)} mono />
      </div>

      {selected.entity_id && (
        <Btn
          variant="solid"
          icon="arrow-right"
          onClick={() => onOpenEntity(selected.entity_id as string)}
        >
          Open entity
        </Btn>
      )}

      <div style={{ borderTop: '1px solid var(--line-soft)', paddingTop: 14 }}>
        <SectionLabel>NOTE</SectionLabel>
        <p
          style={{
            marginTop: 8,
            fontSize: 12.5,
            color: 'var(--fg-2)',
            lineHeight: 1.5,
          }}
        >
          {selected._kind === 'anomaly'
            ? 'Loitering or off-pattern dwell flagged by the AIS scan. Cross-check vessel manifest for this window.'
            : 'Recurring port of call in current dataset. Open entity to inspect related shipments.'}
        </p>
      </div>
    </div>
  );
}

function DataRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div
        style={{
          marginTop: 4,
          fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
          fontSize: mono ? 13 : 13,
          color: 'var(--ink)',
        }}
      >
        {value}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontFamily: 'var(--mono)',
        fontSize: 9.5,
        letterSpacing: '0.2em',
        color: 'var(--fg-3)',
        fontWeight: 600,
        textTransform: 'uppercase',
      }}
    >
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Temporal slider (visual)
// ---------------------------------------------------------------------------

function TemporalSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div
      style={{
        gridRow: 3,
        gridColumn: '1 / span 2',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '12px 22px',
        borderTop: '1px solid var(--line)',
        background: 'var(--paper)',
      }}
    >
      <SectionLabel>TIME</SectionLabel>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
        2026-03-04
      </span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{
          flex: 1,
          accentColor: 'var(--ink)',
        }}
      />
      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
        2026-04-12
      </span>
      <Tag tone="signal">{Math.round(value * 100)}%</Tag>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty / loading
// ---------------------------------------------------------------------------

function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        background: 'var(--paper)',
      }}
    >
      <h2
        style={{
          margin: 0,
          fontFamily: 'var(--serif)',
          fontWeight: 500,
          fontSize: 22,
          color: 'var(--ink)',
        }}
      >
        {title}
      </h2>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-3)' }}>{body}</p>
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}

function LoadingOverlay({ text }: { text: string }) {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--mono)',
        fontSize: 11,
        letterSpacing: '0.16em',
        color: 'var(--fg-3)',
        textTransform: 'uppercase',
      }}
    >
      {text}
    </div>
  );
}
