'use client';

import React, { useState } from 'react';

export interface TimelinePoint {
  t: number;
  c: number;
  n?: number;
  label: string;
  docId?: string;
  tone?: 'neutral' | 'up' | 'down' | 'now';
}

interface ConfidenceTimelineProps {
  points: TimelinePoint[];
  start?: string;
  end?: string;
  size?: 'full' | 'compact';
  title?: string;
  tone?: 'signal' | 'cite';
}

export function ConfidenceTimeline({
  points,
  start = '',
  end = '',
  size = 'full',
  title = 'Confidence trajectory',
  tone = 'signal',
}: ConfidenceTimelineProps) {
  const [hover, setHover] = useState<number | null>(null);
  const H = size === 'full' ? 92 : 56;
  const pad = { top: 14, bottom: 22 };

  const VB_W = 1000;
  const VB_H = H;
  const lineY = (c: number) => pad.top + (1 - c) * (VB_H - pad.top - pad.bottom);
  const lineX = (t: number) => 8 + t * (VB_W - 16);

  const pathD = points
    .map((p, i) => {
      const x = lineX(p.t),
        y = lineY(p.c);
      if (i === 0) return `M ${x.toFixed(1)} ${y.toFixed(1)}`;
      const prev = points[i - 1];
      const px = lineX(prev.t),
        py = lineY(prev.c);
      const cx1 = px + (x - px) * 0.5,
        cy1 = py;
      const cx2 = px + (x - px) * 0.5,
        cy2 = y;
      return `C ${cx1.toFixed(1)} ${cy1.toFixed(1)}, ${cx2.toFixed(1)} ${cy2.toFixed(1)}, ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');

  const areaD =
    pathD +
    ` L ${lineX(1).toFixed(1)} ${VB_H - pad.bottom} L ${lineX(0).toFixed(1)} ${VB_H - pad.bottom} Z`;

  const accent = tone === 'signal' ? 'var(--signal)' : 'var(--cite)';
  const last = points[points.length - 1];

  return (
    <div
      style={{
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        padding: size === 'full' ? '14px 18px' : '10px 12px',
      }}
    >
      {size === 'full' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            marginBottom: 6,
          }}
        >
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 9.5,
              letterSpacing: '0.2em',
              color: 'var(--fg-3)',
              fontWeight: 600,
            }}
          >
            {title.toUpperCase()}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>
              {start} → {end}
            </span>
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 18,
                fontWeight: 600,
                color: 'var(--ink)',
              }}
            >
              {Math.round(last.c * 100)}
              <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>%</span>
            </span>
          </div>
        </div>
      )}

      <div style={{ position: 'relative' }}>
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          preserveAspectRatio="none"
          style={{ width: '100%', height: H, display: 'block' }}
        >
          {[0.25, 0.5, 0.75].map((g) => (
            <line
              key={g}
              x1={0}
              x2={VB_W}
              y1={lineY(g)}
              y2={lineY(g)}
              stroke="var(--line-soft)"
              strokeWidth="0.5"
              strokeDasharray="2 4"
            />
          ))}
          <path d={areaD} fill={accent} fillOpacity="0.08" />
          <path
            d={pathD}
            fill="none"
            stroke={accent}
            strokeWidth={size === 'full' ? 2 : 1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {points.map((p, i) => {
            const x = lineX(p.t),
              y = lineY(p.c);
            const isLast = i === points.length - 1;
            const r = isLast ? 5 : 3.5;
            const color =
              p.tone === 'down'
                ? 'var(--warn)'
                : p.tone === 'now'
                ? accent
                : 'var(--ink)';
            return (
              <g
                key={i}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                style={{ cursor: 'pointer' }}
              >
                {hover === i && <circle cx={x} cy={y} r="10" fill={accent} fillOpacity="0.18" />}
                <circle
                  cx={x}
                  cy={y}
                  r={r}
                  fill="var(--paper)"
                  stroke={color}
                  strokeWidth="1.6"
                />
                {isLast && <circle cx={x} cy={y} r="2" fill={accent} />}
              </g>
            );
          })}
        </svg>

        {size === 'full' && (
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 4px 0' }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)' }}>
              {start}
            </span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)' }}>
              {end} · now
            </span>
          </div>
        )}

        {hover !== null && (
          <div
            style={{
              position: 'absolute',
              left: `${points[hover].t * 100}%`,
              top: lineY(points[hover].c) * (H / VB_H) - 12,
              transform: 'translate(-50%, -100%)',
              background: 'var(--ink)',
              color: 'var(--paper)',
              padding: '6px 10px',
              borderRadius: 2,
              fontSize: 11,
              lineHeight: 1.4,
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
              zIndex: 5,
              boxShadow: '0 4px 12px rgba(15,18,22,0.18)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: 'var(--mono)', fontWeight: 600 }}>
                {Math.round(points[hover].c * 100)}%
              </span>
              <span style={{ opacity: 0.6 }}>·</span>
              <span>{points[hover].label}</span>
              {points[hover].tone === 'down' && (
                <span style={{ color: 'var(--warn)' }}>↓</span>
              )}
              {points[hover].tone === 'up' && (
                <span style={{ color: 'var(--live)' }}>↑</span>
              )}
            </div>
          </div>
        )}
      </div>

      {size === 'full' && (
        <div
          style={{
            display: 'flex',
            gap: 16,
            marginTop: 8,
            fontSize: 11,
            color: 'var(--fg-3)',
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span
              style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ink)' }}
            />{' '}
            evidence event
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span
              style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--warn)' }}
            />{' '}
            confidence dropped
          </span>
          <span style={{ flex: 1 }} />
          <span>{points.length} events · hover any node for detail</span>
        </div>
      )}
    </div>
  );
}
