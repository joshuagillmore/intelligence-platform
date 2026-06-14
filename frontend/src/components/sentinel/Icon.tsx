'use client';

import React from 'react';

interface IconProps {
  name: string;
  size?: number;
  stroke?: number;
  className?: string;
}

export function Icon({ name, size = 16, stroke = 1.5, className }: IconProps) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: stroke,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className,
  };

  const solid = {
    ...common,
    fill: 'currentColor',
    stroke: 'none',
    strokeWidth: undefined,
  };

  switch (name) {
    case 'search':
      return (
        <svg {...common}>
          <circle cx={11} cy={11} r={7} />
          <path d="m20 20-3.5-3.5" />
        </svg>
      );
    case 'command':
      return (
        <svg {...common}>
          <path d="M6 6h12v12H6z" />
          <path d="M6 9H3a3 3 0 0 1 0-6h3zM18 9h3a3 3 0 0 0 0-6h-3zM6 15H3a3 3 0 0 0 0 6h3zM18 15h3a3 3 0 0 1 0 6h-3z" />
        </svg>
      );
    case 'graph':
      return (
        <svg {...common}>
          <circle cx={6} cy={6} r={2.5} />
          <circle cx={18} cy={6} r={2.5} />
          <circle cx={12} cy={18} r={2.5} />
          <path d="M7.5 7.5 10.5 16.5M16.5 7.5 13.5 16.5M8 6h8" />
        </svg>
      );
    case 'acquire':
      return (
        <svg {...common}>
          <path d="M3 12a9 9 0 1 0 9-9" />
          <path d="m3 12 3-3M3 12l3 3" />
          <circle cx={18} cy={6} r={1.5} />
        </svg>
      );
    case 'product':
      return (
        <svg {...common}>
          <path d="M6 3h9l5 5v13H6z" />
          <path d="M15 3v5h5M9 13h6M9 17h4" />
        </svg>
      );
    case 'hub':
      return (
        <svg {...common}>
          <rect x={3} y={3} width={7} height={7} />
          <rect x={14} y={3} width={7} height={7} />
          <rect x={3} y={14} width={7} height={7} />
          <rect x={14} y={14} width={7} height={7} />
        </svg>
      );
    case 'doc':
      return (
        <svg {...common}>
          <path d="M6 3h8l4 4v14H6z" />
          <path d="M14 3v4h4" />
        </svg>
      );
    case 'entity':
      return (
        <svg {...common}>
          <circle cx={12} cy={8} r={3} />
          <path d="M5 20c1-4 4-6 7-6s6 2 7 6" />
        </svg>
      );
    case 'vessel':
      return (
        <svg {...common}>
          <path d="M3 16c2 2 4 2 6 0s4-2 6 0 4 2 6 0" />
          <path d="M5 16V9h14v7M8 9V6h8v3M12 6V3" />
        </svg>
      );
    case 'org':
      return (
        <svg {...common}>
          <path d="M4 21V8l8-5 8 5v13" />
          <path d="M4 21h16M10 21v-5h4v5M9 11h.01M15 11h.01M9 14h.01M15 14h.01" />
        </svg>
      );
    case 'person':
      return (
        <svg {...common}>
          <circle cx={12} cy={8} r={4} />
          <path d="M4 21c0-4 4-7 8-7s8 3 8 7" />
        </svg>
      );
    case 'location':
      return (
        <svg {...common}>
          <path d="M12 22s8-7 8-13a8 8 0 1 0-16 0c0 6 8 13 8 13z" />
          <circle cx={12} cy={9} r={3} />
        </svg>
      );
    case 'indicator':
      return (
        <svg {...common}>
          <path d="m12 2 3 7h7l-6 4 2 7-6-4-6 4 2-7-6-4h7z" />
        </svg>
      );
    case 'star':
      return (
        <svg {...solid}>
          <path d="m12 2 3 7 7 .6-5 4.8 1.5 7.6-6.5-4-6.5 4L6.9 14.4 2 9.6 9 9z" />
        </svg>
      );
    case 'star-o':
      return (
        <svg {...common}>
          <path d="m12 2 3 7 7 .6-5 4.8 1.5 7.6-6.5-4-6.5 4L6.9 14.4 2 9.6 9 9z" />
        </svg>
      );
    case 'plus':
      return (
        <svg {...common}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case 'arrow-right':
      return (
        <svg {...common}>
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      );
    case 'arrow-up-right':
      return (
        <svg {...common}>
          <path d="M7 17 17 7M9 7h8v8" />
        </svg>
      );
    case 'chevron-right':
      return (
        <svg {...common}>
          <path d="m9 6 6 6-6 6" />
        </svg>
      );
    case 'chevron-down':
      return (
        <svg {...common}>
          <path d="m6 9 6 6 6-6" />
        </svg>
      );
    case 'check':
      return (
        <svg {...common}>
          <path d="M4 12 10 18 20 6" />
        </svg>
      );
    case 'x':
      return (
        <svg {...common}>
          <path d="M6 6 18 18M18 6 6 18" />
        </svg>
      );
    case 'dot':
      return (
        <svg {...solid}>
          <circle cx={12} cy={12} r={4} />
        </svg>
      );
    case 'clock':
      return (
        <svg {...common}>
          <circle cx={12} cy={12} r={9} />
          <path d="M12 7v5l3 2" />
        </svg>
      );
    case 'sparkle':
      return (
        <svg {...common}>
          <path d="M12 3v5M12 16v5M3 12h5M16 12h5M6 6l3 3M15 15l3 3M6 18l3-3M15 9l3-3" />
        </svg>
      );
    case 'play':
      return (
        <svg {...solid}>
          <path d="M7 4v16l13-8z" />
        </svg>
      );
    case 'pause':
      return (
        <svg {...common}>
          <rect x={7} y={5} width={3} height={14} />
          <rect x={14} y={5} width={3} height={14} />
        </svg>
      );
    case 'filter':
      return (
        <svg {...common}>
          <path d="M4 5h16L14 13v7l-4-2v-5z" />
        </svg>
      );
    case 'grid':
      return (
        <svg {...common}>
          <rect x={4} y={4} width={7} height={7} />
          <rect x={13} y={4} width={7} height={7} />
          <rect x={4} y={13} width={7} height={7} />
          <rect x={13} y={13} width={7} height={7} />
        </svg>
      );
    case 'list':
      return (
        <svg {...common}>
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      );
    case 'layers':
      return (
        <svg {...common}>
          <path d="m12 3 9 5-9 5-9-5zM3 13l9 5 9-5M3 18l9 5 9-5" />
        </svg>
      );
    case 'bolt':
      return (
        <svg {...common}>
          <path d="M13 2 4 14h6l-1 8 9-12h-6z" />
        </svg>
      );
    case 'upload':
      return (
        <svg {...common}>
          <path d="M12 15V3M7 8l5-5 5 5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
      );
    case 'download':
      return (
        <svg {...common}>
          <path d="M12 3v12M7 10l5 5 5-5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
      );
    case 'eye':
      return (
        <svg {...common}>
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
          <circle cx={12} cy={12} r={3} />
        </svg>
      );
    case 'flag':
      return (
        <svg {...common}>
          <path d="M4 22V4c6-3 8 3 14 0v10c-6 3-8-3-14 0" />
        </svg>
      );
    case 'link':
      return (
        <svg {...common}>
          <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1.5 1.5" />
          <path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1.5-1.5" />
        </svg>
      );
    case 'refresh':
      return (
        <svg {...common}>
          <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
          <path d="M21 3v5h-5" />
        </svg>
      );
    case 'menu-dots':
      return (
        <svg {...solid}>
          <circle cx={5} cy={12} r={1.5} />
          <circle cx={12} cy={12} r={1.5} />
          <circle cx={19} cy={12} r={1.5} />
        </svg>
      );
    default:
      return null;
  }
}

export default Icon;
