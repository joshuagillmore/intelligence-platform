'use client';
import React from 'react';

interface HighlightedExcerptProps {
  text: string;
  keywords: string[];
  className?: string;
  maxLength?: number;
}

/**
 * Renders text with keyword matches highlighted in colored spans.
 * Reusable across document cards, search results, and evidence panels.
 */
export default function HighlightedExcerpt({
  text,
  keywords,
  className = '',
  maxLength = 500,
}: HighlightedExcerptProps) {
  if (!text) return null;

  const displayText = maxLength && text.length > maxLength
    ? text.slice(0, maxLength) + '...'
    : text;

  if (!keywords || keywords.length === 0) {
    return <span className={className}>{displayText}</span>;
  }

  // Build a regex that matches any keyword (case-insensitive)
  const escaped = keywords
    .filter(kw => kw.length > 1)
    .map(kw => kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));

  if (escaped.length === 0) {
    return <span className={className}>{displayText}</span>;
  }

  const regex = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = displayText.split(regex);

  return (
    <span className={className}>
      {parts.map((part, i) => {
        const isMatch = keywords.some(
          kw => part.toLowerCase() === kw.toLowerCase()
        );
        if (isMatch) {
          return (
            <mark
              key={i}
              className="bg-purple-500/30 text-purple-200 px-0.5 rounded-sm"
            >
              {part}
            </mark>
          );
        }
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </span>
  );
}
