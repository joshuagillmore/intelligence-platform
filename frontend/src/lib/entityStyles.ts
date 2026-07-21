/**
 * Canonical entity styling — one source of truth for how entity types are
 * colored across the app, replacing the copies that had drifted between
 * network / watchlist / cyber / GraphVisualization.
 *
 * Three maps because they render differently:
 *  - TYPE_COLOR_CLASS: Tailwind `bg-*` class for status dots / small chips.
 *  - TYPE_COLOR_HEX:   hex fill for d3 graph nodes.
 *  - TYPE_BADGE_CLASS: bg+text classes for the cyber IOC badges.
 * TYPE_ICON is an optional emoji glyph for compact lists/panels.
 */

export const TYPE_COLOR_CLASS: Record<string, string> = {
  Person: 'bg-orange-500',
  Organization: 'bg-blue-500',
  Location: 'bg-green-500',
  Event: 'bg-yellow-500',
  ThreatActor: 'bg-red-500',
  Campaign: 'bg-indigo-500',
  Malware: 'bg-red-600',
  TTP: 'bg-amber-500',
  IPAddress: 'bg-cyan-500',
  Domain: 'bg-purple-500',
  URL: 'bg-fuchsia-500',
  EmailAddress: 'bg-sky-500',
  Hash: 'bg-pink-500',
  Vulnerability: 'bg-rose-500',
  Document: 'bg-gray-500',
  Report: 'bg-indigo-500',
  Topic: 'bg-teal-500',
};

export const TYPE_COLOR_HEX: Record<string, string> = {
  Person: '#f97316', Organization: '#3b82f6', Location: '#22c55e',
  IPAddress: '#06b6d4', Domain: '#a855f7', URL: '#d946ef', EmailAddress: '#0ea5e9',
  Hash: '#ec4899', ThreatActor: '#ef4444', TTP: '#eab308', Vulnerability: '#f43f5e',
  Document: '#6b7280', Assessment: '#14b8a6', Malware: '#be123c',
  Campaign: '#d946ef', Community: '#8b5cf6', Date: '#94a3b8', Technology: '#06b6d4',
  Weapon: '#f43f5e', Facility: '#84cc16', Software: '#0ea5e9',
  MilitaryUnit: '#dc2626', GovernmentAgency: '#2563eb',
  Country: '#16a34a', City: '#65a30d', Custom: '#78716c',
};

export const TYPE_BADGE_CLASS: Record<string, string> = {
  IPAddress: 'bg-cyan-900/30 text-cyan-400',
  Domain: 'bg-purple-900/30 text-purple-400',
  URL: 'bg-fuchsia-900/30 text-fuchsia-400',
  EmailAddress: 'bg-sky-900/30 text-sky-400',
  Hash: 'bg-pink-900/30 text-pink-400',
  TTP: 'bg-yellow-900/30 text-yellow-400',
  Vulnerability: 'bg-rose-900/30 text-rose-400',
  ThreatActor: 'bg-red-900/30 text-red-400',
  // Core entity types (used by the project dashboard's activity badges).
  Person: 'bg-orange-900/30 text-orange-400',
  Organization: 'bg-blue-900/30 text-blue-400',
  Location: 'bg-green-900/30 text-green-400',
  Document: 'bg-gray-900/30 text-gray-400',
};

export const TYPE_ICON: Record<string, string> = {
  IPAddress: '🌐', Domain: '🔗', URL: '🔗', EmailAddress: '✉️', Hash: '#️⃣',
  Vulnerability: '🛡️', TTP: '🎯', Malware: '☣️', ThreatActor: '🎭', Campaign: '📣',
  Person: '👤', Organization: '🏢', Location: '📍', Event: '📅', Document: '📄',
};

export default TYPE_COLOR_CLASS;
