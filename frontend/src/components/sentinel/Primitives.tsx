'use client';

import React, { useState } from 'react';
import { Icon } from './Icon';

// ---------------------------------------------------------------------------
// ENTITY_META
// ---------------------------------------------------------------------------

export const ENTITY_META: Record<string, { icon: string; tint: string }> = {
  VESSEL:    { icon: 'vessel',    tint: 'oklch(0.58 0.11 230)' },
  ORG:       { icon: 'org',       tint: 'oklch(0.55 0.13 295)' },
  PERSON:    { icon: 'person',    tint: 'oklch(0.55 0.12 15)'  },
  LOCATION:  { icon: 'location',  tint: 'oklch(0.56 0.12 155)' },
  INDICATOR: { icon: 'indicator', tint: 'oklch(0.55 0.14 60)'  },
};

// ---------------------------------------------------------------------------
// ClassificationStrip
// ---------------------------------------------------------------------------

interface ClassificationStripProps {
  text?: string;
}

export function ClassificationStrip({
  text = 'UNCLASSIFIED//FOR OFFICIAL USE ONLY',
}: ClassificationStripProps) {
  const dot: React.CSSProperties = {
    display: 'inline-block',
    width: 4,
    height: 4,
    borderRadius: '50%',
    background: 'var(--signal-ink)',
    opacity: 0.5,
    flexShrink: 0,
  };

  const wrap: React.CSSProperties = {
    height: 20,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    background: 'var(--signal-soft)',
    color: 'var(--signal-ink)',
    fontFamily: 'var(--mono)',
    fontSize: 10,
    letterSpacing: '0.18em',
    userSelect: 'none',
  };

  return (
    <div style={wrap}>
      <span style={dot} />
      <span style={dot} />
      <span>{text}</span>
      <span style={dot} />
      <span style={dot} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tag
// ---------------------------------------------------------------------------

type TagTone = 'neutral' | 'ink' | 'signal' | 'live' | 'warn' | 'cite';

interface TagProps {
  children: React.ReactNode;
  tone?: TagTone;
  style?: React.CSSProperties;
}

const TAG_TONE_STYLES: Record<TagTone, React.CSSProperties> = {
  neutral: {
    background: 'transparent',
    color: 'var(--fg-3)',
    border: '1px solid var(--line)',
  },
  ink: {
    background: 'var(--ink)',
    color: 'var(--paper)',
    border: '1px solid var(--ink)',
  },
  signal: {
    background: 'var(--signal-soft)',
    color: 'var(--signal-ink)',
    border: '1px solid transparent',
  },
  live: {
    background: 'transparent',
    color: 'var(--live)',
    border: '1px solid var(--live)',
  },
  warn: {
    background: 'transparent',
    color: 'var(--warn)',
    border: '1px solid var(--warn)',
  },
  cite: {
    background: 'transparent',
    color: 'var(--cite)',
    border: '1px solid var(--cite)',
  },
};

export function Tag({ children, tone = 'neutral', style }: TagProps) {
  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    fontFamily: 'var(--mono)',
    fontSize: 9.5,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    borderRadius: 2,
    padding: '2px 6px',
    lineHeight: 1.4,
    whiteSpace: 'nowrap',
    ...TAG_TONE_STYLES[tone],
    ...style,
  };

  return <span style={base}>{children}</span>;
}

// ---------------------------------------------------------------------------
// PulseDot
// ---------------------------------------------------------------------------

interface PulseDotProps {
  color?: string;
  size?: number;
}

export function PulseDot({ color = 'var(--live)', size = 6 }: PulseDotProps) {
  const wrap: React.CSSProperties = {
    position: 'relative',
    width: size,
    height: size,
    flexShrink: 0,
  };

  const base: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    borderRadius: '50%',
    background: color,
  };

  const pulse: React.CSSProperties = {
    ...base,
    animation: 'pulse-dot 1.6s ease-in-out infinite',
    opacity: 0.4,
    transform: 'scale(1.7)',
    background: color,
  };

  return (
    <span style={wrap}>
      <span style={pulse} />
      <span style={base} />
    </span>
  );
}

// ---------------------------------------------------------------------------
// Corners
// ---------------------------------------------------------------------------

interface CornersProps {
  color?: string;
  size?: number;
  inset?: number;
}

export function Corners({
  color = 'var(--line)',
  size = 8,
  inset = 0,
}: CornersProps) {
  const shared: React.CSSProperties = {
    position: 'absolute',
    width: size,
    height: size,
    pointerEvents: 'none',
  };

  const corners: Array<{ style: React.CSSProperties; borders: React.CSSProperties }> = [
    {
      style: { top: inset, left: inset },
      borders: { borderTop: `1px solid ${color}`, borderLeft: `1px solid ${color}` },
    },
    {
      style: { top: inset, right: inset },
      borders: { borderTop: `1px solid ${color}`, borderRight: `1px solid ${color}` },
    },
    {
      style: { bottom: inset, left: inset },
      borders: { borderBottom: `1px solid ${color}`, borderLeft: `1px solid ${color}` },
    },
    {
      style: { bottom: inset, right: inset },
      borders: { borderBottom: `1px solid ${color}`, borderRight: `1px solid ${color}` },
    },
  ];

  return (
    <>
      {corners.map((c, i) => (
        <span key={i} style={{ ...shared, ...c.style, ...c.borders }} />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Btn
// ---------------------------------------------------------------------------

type BtnVariant = 'ghost' | 'outline' | 'solid' | 'signal';
type BtnSize = 'sm' | 'md';

interface BtnProps {
  children?: React.ReactNode;
  variant?: BtnVariant;
  icon?: string;
  tone?: string;
  onClick?: () => void;
  style?: React.CSSProperties;
  title?: string;
  size?: BtnSize;
}

const BTN_VARIANT_STYLES: Record<BtnVariant, React.CSSProperties> = {
  ghost: {
    background: 'transparent',
    color: 'var(--fg-2)',
    border: '1px solid transparent',
  },
  outline: {
    background: 'transparent',
    color: 'var(--fg)',
    border: '1px solid var(--line)',
  },
  solid: {
    background: 'var(--ink)',
    color: 'var(--paper)',
    border: '1px solid var(--ink)',
  },
  signal: {
    background: 'var(--signal)',
    color: 'var(--ink)',
    border: '1px solid var(--signal)',
  },
};

const BTN_SIZE_STYLES: Record<BtnSize, React.CSSProperties> = {
  sm: { padding: '5px 8px',  fontSize: 11.5 },
  md: { padding: '8px 12px', fontSize: 12.5 },
};

export function Btn({
  children,
  variant = 'outline',
  icon,
  tone,
  onClick,
  style,
  title,
  size = 'md',
}: BtnProps) {
  const [hovered, setHovered] = useState(false);

  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    borderRadius: 3,
    fontFamily: 'var(--sans)',
    fontWeight: 500,
    lineHeight: 1,
    cursor: 'pointer',
    transition: 'opacity 0.1s, background 0.1s',
    opacity: hovered ? 0.8 : 1,
    ...BTN_VARIANT_STYLES[variant],
    ...BTN_SIZE_STYLES[size],
    ...(tone ? { color: tone } : {}),
    ...style,
  };

  return (
    <button
      style={base}
      onClick={onClick}
      title={title}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {icon && <Icon name={icon} size={13} />}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Meter
// ---------------------------------------------------------------------------

interface MeterProps {
  value?: number;
  label?: string;
  tone?: string;
  width?: number;
}

export function Meter({
  value = 0,
  label,
  tone = 'var(--signal)',
  width = 80,
}: MeterProps) {
  const clamp = Math.max(0, Math.min(1, value));

  const track: React.CSSProperties = {
    width,
    height: 3,
    background: 'var(--line)',
    borderRadius: 2,
    overflow: 'hidden',
    flexShrink: 0,
  };

  const fill: React.CSSProperties = {
    height: '100%',
    width: `${clamp * 100}%`,
    background: tone,
    borderRadius: 2,
    transition: 'width 0.3s ease',
  };

  const wrap: React.CSSProperties = {
    display: 'inline-flex',
    flexDirection: 'column',
    gap: 3,
  };

  const labelStyle: React.CSSProperties = {
    fontFamily: 'var(--mono)',
    fontSize: 9,
    color: 'var(--fg-3)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  };

  return (
    <div style={wrap}>
      {label && <span style={labelStyle}>{label}</span>}
      <div style={track}>
        <div style={fill} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CiteChip
// ---------------------------------------------------------------------------

interface CiteChipProps {
  children: React.ReactNode;
  kind?: 'entity' | 'doc';
  onClick?: () => void;
  entityType?: string;
}

export function CiteChip({
  children,
  kind = 'doc',
  onClick,
  entityType,
}: CiteChipProps) {
  const [hovered, setHovered] = useState(false);

  const tint =
    entityType && ENTITY_META[entityType]
      ? ENTITY_META[entityType].tint
      : kind === 'entity'
      ? 'var(--cite)'
      : 'var(--fg-3)';

  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 3,
    fontFamily: 'var(--mono)',
    fontSize: 9.5,
    letterSpacing: '0.08em',
    padding: '1px 5px 2px',
    borderRadius: '2px 2px 0 0',
    borderBottom: `2px solid ${tint}`,
    background: hovered ? 'var(--paper-2)' : 'var(--paper)',
    color: hovered ? 'var(--fg)' : 'var(--fg-2)',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'background 0.1s, color 0.1s',
    whiteSpace: 'nowrap',
  };

  return (
    <button
      style={base}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// EntityChip
// ---------------------------------------------------------------------------

interface EntityChipEntity {
  type: string;
  name: string;
  watched?: boolean;
}

interface EntityChipProps {
  entity: EntityChipEntity;
  onClick?: () => void;
  size?: 'sm' | 'md';
}

export function EntityChip({ entity, onClick, size = 'sm' }: EntityChipProps) {
  const [hovered, setHovered] = useState(false);
  const meta = ENTITY_META[entity.type];
  const tint = meta ? meta.tint : 'var(--fg-3)';

  const isSm = size === 'sm';

  const wrap: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: isSm ? 4 : 5,
    padding: isSm ? '2px 6px' : '3px 8px',
    borderRadius: 3,
    border: '1px solid var(--line)',
    background: hovered ? 'var(--paper-2)' : 'var(--paper)',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'background 0.1s',
    fontSize: isSm ? 11 : 12.5,
    fontFamily: 'var(--sans)',
    color: 'var(--fg)',
    whiteSpace: 'nowrap',
  };

  const dot: React.CSSProperties = {
    width: isSm ? 5 : 6,
    height: isSm ? 5 : 6,
    borderRadius: '50%',
    background: tint,
    flexShrink: 0,
  };

  const nameStyle: React.CSSProperties = {
    fontWeight: 500,
    lineHeight: 1.2,
  };

  const starStyle: React.CSSProperties = {
    color: 'var(--signal)',
    fontSize: isSm ? 9 : 10,
    lineHeight: 1,
    marginLeft: 1,
  };

  return (
    <span
      style={wrap}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <span style={dot} />
      <span style={nameStyle}>{entity.name}</span>
      {entity.watched && <span style={starStyle}>★</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Kbd
// ---------------------------------------------------------------------------

interface KbdProps {
  children: React.ReactNode;
}

export function Kbd({ children }: KbdProps) {
  const style: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 16,
    padding: '0 4px',
    fontFamily: 'var(--mono)',
    fontSize: 9,
    letterSpacing: '0.04em',
    background: 'var(--paper-2)',
    border: '1px solid var(--line)',
    borderRadius: 3,
    color: 'var(--fg-3)',
    whiteSpace: 'nowrap',
    lineHeight: 1,
  };

  return <kbd style={style}>{children}</kbd>;
}

// ---------------------------------------------------------------------------
// ConfidenceRing
// ---------------------------------------------------------------------------

interface ConfidenceRingProps {
  value?: number;
  size?: number;
  label?: React.ReactNode;
}

export function ConfidenceRing({
  value = 0,
  size = 40,
  label,
}: ConfidenceRingProps) {
  const clamp = Math.max(0, Math.min(1, value));
  const strokeWidth = 3;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamp);

  const color =
    clamp > 0.75
      ? 'var(--live)'
      : clamp > 0.5
      ? 'var(--signal)'
      : 'var(--warn)';

  const wrap: React.CSSProperties = {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: size,
    height: size,
    flexShrink: 0,
  };

  const labelWrap: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'var(--mono)',
    fontSize: size * 0.22,
    color: 'var(--fg)',
    lineHeight: 1,
  };

  return (
    <div style={wrap}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--line)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.4s ease' }}
        />
      </svg>
      {label !== undefined && <div style={labelWrap}>{label}</div>}
    </div>
  );
}
