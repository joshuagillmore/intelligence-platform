// Mock data for the Sentinel UI prototype.
// Used when real backend data is unavailable or for design/demo purposes.
// Real API integration is in src/lib/api.ts.

export type EntityType = 'VESSEL' | 'ORG' | 'PERSON' | 'LOCATION' | 'INDICATOR';

export interface MockEntity {
  id: string;
  name: string;
  type: EntityType;
  confidence: number;
  watched: boolean;
  flag: string;
  risk: 'low' | 'medium' | 'high';
}

export interface MockEdge {
  a: string;
  b: string;
  label: string;
  weight: number;
}

export interface MockDocument {
  id: string;
  title: string;
  kind: 'PDF' | 'HTML' | 'CSV' | 'JSON' | 'TXT';
  source: string;
  reliability: 'A' | 'B' | 'C';
  date: string;
  pages: number | null;
  ingested: string;
}

export const PROJECT = {
  id: 'proj-arctic-shift',
  name: 'ARCTIC SHIFT',
  codename: 'ARCTIC SHIFT',
  classification: 'U//FOUO',
  priority: 'high' as const,
  status: 'active' as const,
  opened: '2026-03-04',
  analyst: 'L. Marín',
  team: 'NORTHERN DESK · OSINT',
  summary:
    'Anomalous maritime activity and shell-company footprints tied to sanctioned vessels moving through the Northern Sea Route since Q1 2026.',
  pir: 'What entities, vessels, and shell companies are enabling sanctioned cargo transits of the Northern Sea Route, and through which ports and financial intermediaries?',
  stats: {
    entities: 1847,
    relationships: 5212,
    documents: 342,
    sources: 28,
    confidence: 0.72,
    lastAcquired: '2m ago',
  },
};

export const OTHER_PROJECTS = [
  { id: 'p2', name: 'LONGBOW DRIFT',   classification: 'U//FOUO', priority: 'medium',   entities: 612,  docs: 89,  updated: '3h ago',  status: 'active' },
  { id: 'p3', name: 'KESTREL CACHE',   classification: 'U',        priority: 'low',      entities: 203,  docs: 34,  updated: '2d ago',  status: 'monitoring' },
  { id: 'p4', name: 'GRAPHITE MIRROR', classification: 'U//FOUO', priority: 'critical', entities: 2914, docs: 501, updated: '14m ago', status: 'active' },
  { id: 'p5', name: 'BLUE HARVEST',    classification: 'U',        priority: 'medium',   entities: 487,  docs: 71,  updated: '1d ago',  status: 'paused' },
];

export const ENTITIES: MockEntity[] = [
  { id: 'e1', name: 'MV Northstar Auriga',          type: 'VESSEL',    confidence: 0.91, watched: true,  flag: 'IMO 9487214',         risk: 'high'   },
  { id: 'e2', name: 'Polar Freight Holdings',       type: 'ORG',       confidence: 0.88, watched: true,  flag: 'shell company',       risk: 'high'   },
  { id: 'e3', name: 'Dmitri Volkov',                type: 'PERSON',    confidence: 0.76, watched: false, flag: 'nominal director',    risk: 'medium' },
  { id: 'e4', name: 'Murmansk Port Terminal 4',     type: 'LOCATION',  confidence: 0.95, watched: false, flag: 'RU',                  risk: 'medium' },
  { id: 'e5', name: 'BoreaBank AG',                 type: 'ORG',       confidence: 0.82, watched: true,  flag: 'correspondent',       risk: 'high'   },
  { id: 'e6', name: 'Rotterdam Zuidhaven',          type: 'LOCATION',  confidence: 0.93, watched: false, flag: 'NL',                  risk: 'low'    },
  { id: 'e7', name: 'Svalbard transshipment zone',  type: 'LOCATION',  confidence: 0.77, watched: false, flag: 'NO',                  risk: 'medium' },
  { id: 'e8', name: 'Orion Maritime Services',      type: 'ORG',       confidence: 0.70, watched: false, flag: 'broker',              risk: 'medium' },
  { id: 'e9', name: 'Katja Renko',                  type: 'PERSON',    confidence: 0.61, watched: false, flag: 'beneficial owner',    risk: 'medium' },
  { id: 'e10', name: 'STIX bundle 2026-0412',       type: 'INDICATOR', confidence: 1.00, watched: false, flag: 'cyber feed',          risk: 'low'    },
];

export const EDGES: MockEdge[] = [
  { a: 'e1', b: 'e2', label: 'owned_by',          weight: 0.9 },
  { a: 'e2', b: 'e3', label: 'director',          weight: 0.7 },
  { a: 'e1', b: 'e4', label: 'docked_at',         weight: 0.6 },
  { a: 'e2', b: 'e5', label: 'banked_at',         weight: 0.8 },
  { a: 'e1', b: 'e6', label: 'scheduled_to',      weight: 0.5 },
  { a: 'e1', b: 'e7', label: 'loitered_near',     weight: 0.7 },
  { a: 'e2', b: 'e8', label: 'contracted',        weight: 0.6 },
  { a: 'e8', b: 'e9', label: 'controlled_by',     weight: 0.5 },
  { a: 'e5', b: 'e9', label: 'account_signatory', weight: 0.4 },
  { a: 'e7', b: 'e10', label: 'refers_to',        weight: 0.3 },
  { a: 'e3', b: 'e9', label: 'associate',         weight: 0.4 },
];

export const DOCUMENTS: MockDocument[] = [
  { id: 'd1', title: 'Kystvakten sighting report 2026-0408', kind: 'PDF',  source: 'Norwegian Coast Guard bulletin', reliability: 'B', date: '2026-04-08', pages: 4,    ingested: '2h ago' },
  { id: 'd2', title: 'Equasis record — IMO 9487214',          kind: 'HTML', source: 'equasis.org',                    reliability: 'A', date: '2026-04-05', pages: 1,    ingested: '6h ago' },
  { id: 'd3', title: 'OFAC SDN list update (maritime)',       kind: 'CSV',  source: 'treasury.gov',                   reliability: 'A', date: '2026-04-02', pages: null, ingested: '1d ago' },
  { id: 'd4', title: 'Company extract — Polar Freight Holdings', kind: 'PDF', source: 'OpenCorporates',               reliability: 'B', date: '2026-03-28', pages: 11,   ingested: '1d ago' },
  { id: 'd5', title: 'AIS track anomaly — Northstar Auriga',  kind: 'JSON', source: 'MarineCadastre feed',            reliability: 'A', date: '2026-04-10', pages: null, ingested: '12m ago' },
  { id: 'd6', title: 'Telegram channel @arctic_shipping digest', kind: 'TXT', source: 'Telegram monitor',             reliability: 'C', date: '2026-04-09', pages: 3,    ingested: '5h ago' },
  { id: 'd7', title: 'FinCEN GTO amendment re: Baltic correspondent banks', kind: 'PDF', source: 'fincen.gov',        reliability: 'A', date: '2026-03-19', pages: 22,   ingested: '4d ago' },
];

export type AgentStatus = 'done' | 'running' | 'pending' | 'failed';
export interface AgentStep {
  id: string;
  kind: 'decompose' | 'source' | 'tool' | 'extract' | 'synth' | 'review';
  title: string;
  status: AgentStatus;
  duration: number | null;
  tool?: string;
  detail?: string | string[];
  result?: string;
}

export const AGENT_PLAN: { pir: string; refinedAt: string; steps: AgentStep[] } = {
  pir: 'Identify vessels, shell companies, and ports facilitating sanctioned cargo transits of the NSR.',
  refinedAt: '—',
  steps: [
    { id: 's1', kind: 'decompose', title: 'Decompose PIR into sub-questions', status: 'done', duration: 800, detail: [
      'Which vessels have anomalous AIS patterns along NSR?',
      'Which legal entities own or charter those vessels?',
      'Which banks clear payments for those entities?',
      'Which ports appear repeatedly in their schedules?',
    ]},
    { id: 's2', kind: 'source', title: 'Select sources', status: 'done', duration: 400, detail: [
      'MarineCadastre AIS feed', 'Equasis vessel registry', 'OpenCorporates', 'OFAC SDN list', 'Norwegian Coast Guard bulletins', 'Telegram: @arctic_shipping',
    ]},
    { id: 's3', kind: 'tool', title: 'Run MarineCadastre anomaly scan', tool: 'marine_cadastre.query', status: 'done', duration: 2400, result: '14 vessels with loitering anomalies near Svalbard' },
    { id: 's4', kind: 'tool', title: 'Resolve vessels → owners',         tool: 'equasis.lookup',       status: 'done', duration: 1800, result: '11 / 14 resolved; 3 shell-company registrations' },
    { id: 's5', kind: 'tool', title: 'Cross-check OFAC SDN',              tool: 'ofac.match',           status: 'done', duration: 600,  result: '2 direct matches; 1 beneficial-owner match' },
    { id: 's6', kind: 'extract', title: 'Extract entities & relationships', status: 'running', duration: null, detail: 'processing 4 / 7 documents' },
    { id: 's7', kind: 'synth', title: 'Synthesize subgraph & draft findings', status: 'pending', duration: null },
    { id: 's8', kind: 'review', title: 'Flag low-confidence claims for review', status: 'pending', duration: null },
  ],
};

export type AnswerSegment =
  | { kind: 'text'; text: string }
  | { kind: 'ref'; entity: string; text: string };

export const SAMPLE_QA: {
  question: string;
  answer: AnswerSegment[];
  citations: { docId: string; excerpt: string; page: number | null }[];
  confidence: number;
  evidenceGraph: string[];
} = {
  question: 'How is Polar Freight Holdings connected to sanctioned cargo movements?',
  answer: [
    { kind: 'text', text: 'Polar Freight Holdings appears as the registered owner of ' },
    { kind: 'ref',  entity: 'e1', text: 'MV Northstar Auriga' },
    { kind: 'text', text: ', a vessel recorded with AIS anomalies near ' },
    { kind: 'ref',  entity: 'e7', text: 'Svalbard transshipment zone' },
    { kind: 'text', text: ' on 3 separate occasions in March–April 2026. The company is banked through ' },
    { kind: 'ref',  entity: 'e5', text: 'BoreaBank AG' },
    { kind: 'text', text: ', which also clears funds for two other shell entities associated with ' },
    { kind: 'ref',  entity: 'e9', text: 'Katja Renko' },
    { kind: 'text', text: '. Confidence is moderate; the beneficial-ownership chain rests on a single OpenCorporates filing and one Telegram-sourced claim. ' },
  ],
  citations: [
    { docId: 'd4', excerpt: '...Director of record: Dmitri Volkov. Beneficial owner disclosed as Katja Renko via nominee arrangement dated 2024-11-02...', page: 3 },
    { docId: 'd2', excerpt: '...Registered owner: Polar Freight Holdings (Cyprus). Operator: Orion Maritime Services...', page: 1 },
    { docId: 'd5', excerpt: '...vessel dwell of 9.3h outside normal traffic lanes at 78.91°N, 20.44°E; AIS intermittent...', page: null },
    { docId: 'd1', excerpt: '...Kystvakten boarding 2026-04-08: crew manifest inconsistent with declared cargo...', page: 2 },
  ],
  confidence: 0.68,
  evidenceGraph: ['e2', 'e1', 'e7', 'e5', 'e9', 'e3'],
};

export const PERSONAS = [
  { id: 'analyst', name: 'All-source Analyst',     glyph: '§', desc: 'Balanced prose, cites all source types, probability language (Words of Estimative Probability).', temp: 0.3 },
  { id: 'cyber',   name: 'Cyber Threat Analyst',   glyph: '◈', desc: 'TTPs, MITRE refs, IoCs highlighted. Technical register.', temp: 0.2 },
  { id: 'geo',     name: 'Geopolitical Analyst',   glyph: '✦', desc: 'Strategic framing, historical parallels, second-order effects.', temp: 0.5 },
  { id: 'exec',    name: 'Executive Brief',        glyph: '▲', desc: 'Tight prose, BLUF-first, no jargon. Max 300 words.', temp: 0.25 },
  { id: 'red',     name: 'Red Team',               glyph: '✕', desc: 'Argues the alternative hypothesis. Probes assumptions.', temp: 0.7 },
];

export const REPORT_TYPES = [
  { id: 'intsum',     name: 'INTSUM',     full: 'Intelligence Summary' },
  { id: 'intrep',     name: 'INTREP',     full: 'Intelligence Report' },
  { id: 'assessment', name: 'Assessment', full: 'Analytic Assessment with ACH' },
  { id: 'tip',        name: 'Tipper',     full: 'Time-sensitive tipping report' },
  { id: 'brief',      name: '1-pager',    full: 'Executive one-pager' },
];

export const ACTIVITY = [
  { t: '2m ago',  kind: 'acquire', text: 'MarineCadastre feed returned 3 new AIS anomalies' },
  { t: '12m ago', kind: 'extract', text: 'Extracted 41 entities from 2 documents' },
  { t: '34m ago', kind: 'assess',  text: 'Assessment "Polar Freight ownership" saved (P=0.68)' },
  { t: '1h ago',  kind: 'acquire', text: 'Telegram monitor matched 2 posts to watchlist' },
  { t: '2h ago',  kind: 'graph',   text: 'Community detection: 4 clusters identified' },
  { t: '4h ago',  kind: 'product', text: '"NSR Transit Patterns" INTSUM drafted by analyst persona' },
];

export const COLLECTION_SOURCES = [
  { id: 'cs1', name: 'MarineCadastre AIS',         type: 'feed',    status: 'active',   cadence: 'every 15m', lastRun: '2m ago',  records: 4812, errors: 0 },
  { id: 'cs2', name: 'Equasis vessel registry',    type: 'scraper', status: 'active',   cadence: 'daily',     lastRun: '3h ago',  records: 214,  errors: 0 },
  { id: 'cs3', name: 'OpenCorporates',             type: 'api',     status: 'active',   cadence: 'on-demand', lastRun: '1d ago',  records: 88,   errors: 1 },
  { id: 'cs4', name: 'OFAC SDN list',              type: 'feed',    status: 'active',   cadence: 'daily',     lastRun: '6h ago',  records: 12,   errors: 0 },
  { id: 'cs5', name: 'Kystvakten bulletins',       type: 'scraper', status: 'active',   cadence: 'daily',     lastRun: '4h ago',  records: 6,    errors: 0 },
  { id: 'cs6', name: 'Telegram @arctic_shipping',  type: 'monitor', status: 'degraded', cadence: 'every 30m', lastRun: '32m ago', records: 41,   errors: 3 },
  { id: 'cs7', name: 'Reddit r/maritime',          type: 'monitor', status: 'paused',   cadence: 'every 2h',  lastRun: '2d ago',  records: 9,    errors: 0 },
];

// ============================================================================
// EXTENDED — analysis, lenses, network analysis
// ============================================================================

export interface TimelinePoint {
  t: number;
  c: number;
  n: number;
  label: string;
  docId?: string;
  tone?: 'neutral' | 'up' | 'down' | 'now';
}

export const CONFIDENCE_TIMELINE_PROJECT: { start: string; end: string; points: TimelinePoint[] } = {
  start: '2026-03-04',
  end:   '2026-04-12',
  points: [
    { t: 0.00, c: 0.20, n: 1,  label: 'Project opened',                        tone: 'neutral' },
    { t: 0.08, c: 0.24, n: 4,  label: 'OFAC SDN cross-check',                  docId: 'd3', tone: 'up' },
    { t: 0.18, c: 0.32, n: 12, label: 'OpenCorporates extracts',               docId: 'd4', tone: 'up' },
    { t: 0.28, c: 0.41, n: 28, label: 'AIS anomaly batch · 14 vessels',        docId: 'd5', tone: 'up' },
    { t: 0.40, c: 0.38, n: 31, label: 'Telegram claim contradicted by HUMINT', tone: 'down' },
    { t: 0.52, c: 0.49, n: 47, label: 'Equasis ownership chain resolved',      docId: 'd2', tone: 'up' },
    { t: 0.66, c: 0.58, n: 66, label: 'Kystvakten boarding report',            docId: 'd1', tone: 'up' },
    { t: 0.78, c: 0.62, n: 78, label: 'FinCEN GTO amendment',                  docId: 'd7', tone: 'up' },
    { t: 0.92, c: 0.72, n: 89, label: 'Coast Guard manifest discrepancies',    tone: 'up' },
    { t: 1.00, c: 0.72, n: 89, label: 'Current',                                tone: 'now' },
  ],
};

export const CONFIDENCE_TIMELINE_ENTITY: Record<string, { t: number; c: number; label: string }[]> = {
  e2: [
    { t: 0.0,  c: 0.30, label: '+ first sighting' },
    { t: 0.2,  c: 0.48, label: '+ Cyprus filing' },
    { t: 0.45, c: 0.62, label: '+ ownership of Auriga' },
    { t: 0.7,  c: 0.72, label: '+ BoreaBank link' },
    { t: 1.0,  c: 0.88, label: 'now' },
  ],
};

export type ACHRating = 'CC' | 'C' | 'N' | 'I' | 'II';

export const HYPOTHESES = [
  { id: 'h1', label: 'H1', title: 'Coordinated sanctions evasion',         description: 'A single coordinated network using shell companies, common correspondent banking, and dark-AIS transits to move sanctioned cargo through the NSR.', score: 0.68, delta: +0.06, status: 'leading' as const },
  { id: 'h2', label: 'H2', title: 'Independent grey-market operators',      description: 'Multiple unrelated grey-market operators incidentally exhibit similar patterns; the apparent network is coincidence.', score: 0.21, delta: -0.04, status: 'weakening' as const },
  { id: 'h3', label: 'H3', title: 'Routine commercial activity, misread',   description: 'AIS anomalies and shell structures are explainable by legitimate commercial confidentiality; sanctions implications are an artifact of OSINT framing.', score: 0.11, delta: -0.02, status: 'weak' as const },
];

export interface ACHEvidence {
  id: string;
  title: string;
  docId: string | null;
  reliability: 'A' | 'B' | 'C';
  diagnosticity: number;
  ratings: Record<string, ACHRating>;
}

export const ACH_EVIDENCE: ACHEvidence[] = [
  { id: 'ev1', title: 'Cyprus shell-company registration for Polar Freight',     docId: 'd4',  reliability: 'B', diagnosticity: 0.62, ratings: { h1: 'CC', h2: 'C',  h3: 'I'  } },
  { id: 'ev2', title: 'AIS dark periods near Svalbard',                          docId: 'd5',  reliability: 'A', diagnosticity: 0.78, ratings: { h1: 'CC', h2: 'C',  h3: 'I'  } },
  { id: 'ev3', title: 'Common correspondent bank (BoreaBank) for 3 entities',    docId: 'd7',  reliability: 'A', diagnosticity: 0.85, ratings: { h1: 'CC', h2: 'II', h3: 'I'  } },
  { id: 'ev4', title: 'Diverse vessel classes & flags',                          docId: 'd2',  reliability: 'A', diagnosticity: 0.42, ratings: { h1: 'I',  h2: 'CC', h3: 'C'  } },
  { id: 'ev5', title: 'Kystvakten manifest inconsistencies',                     docId: 'd1',  reliability: 'B', diagnosticity: 0.55, ratings: { h1: 'C',  h2: 'N',  h3: 'I'  } },
  { id: 'ev6', title: 'Shared beneficial owner across 2 entities',               docId: 'd4',  reliability: 'B', diagnosticity: 0.71, ratings: { h1: 'CC', h2: 'II', h3: 'I'  } },
  { id: 'ev7', title: 'No SIGINT corroboration available',                       docId: null,  reliability: 'C', diagnosticity: 0.25, ratings: { h1: 'I',  h2: 'N',  h3: 'C'  } },
  { id: 'ev8', title: 'Some declared cargo is legitimate',                       docId: 'd1',  reliability: 'B', diagnosticity: 0.30, ratings: { h1: 'C',  h2: 'C',  h3: 'CC' } },
];

export const ACH_RATINGS: Record<ACHRating, { label: string; symbol: string; color: string }> = {
  CC: { label: 'Strongly consistent',     symbol: '++', color: 'var(--live)' },
  C:  { label: 'Consistent',              symbol: '+',  color: 'var(--live)' },
  N:  { label: 'Neutral',                 symbol: '·',  color: 'var(--fg-3)' },
  I:  { label: 'Inconsistent',            symbol: '−',  color: 'var(--warn)' },
  II: { label: 'Strongly inconsistent',   symbol: '−−', color: 'var(--warn)' },
};

export const ACH_SUGGESTIONS = [
  { id: 'sg1', q: 'SWIFT MT202 traffic between BoreaBank AG and Russian correspondents', distinguishes: ['h1', 'h2'], cost: 'high',   method: 'request via partner' },
  { id: 'sg2', q: 'Cargo manifest for Northstar Auriga, March transit',                  distinguishes: ['h1', 'h3'], cost: 'medium', method: 'FOIA · Norwegian customs' },
  { id: 'sg3', q: 'Common director / agent across the 3 shell entities',                 distinguishes: ['h1', 'h2'], cost: 'low',    method: 'OpenCorporates pivot' },
  { id: 'sg4', q: 'Sanctioned-cargo declarations at Murmansk T4 from 2025',              distinguishes: ['h1', 'h3'], cost: 'low',    method: 'OSINT scrape' },
];

export type PinKind = 'entity' | 'quote' | 'note' | 'finding' | 'gap';
export interface PinItem {
  id: string;
  kind: PinKind;
  x: number;
  y: number;
  w?: number;
  entityId?: string;
  cluster?: string;
  text?: string;
  source?: string;
  author?: string;
  confidence?: number;
}

export const PIN_ITEMS: PinItem[] = [
  { id: 'p1', kind: 'entity', x: 80,  y: 80,  entityId: 'e2', cluster: 'ownership' },
  { id: 'p2', kind: 'entity', x: 290, y: 80,  entityId: 'e1', cluster: 'ownership' },
  { id: 'p3', kind: 'entity', x: 500, y: 80,  entityId: 'e7', cluster: 'transit'   },
  { id: 'p4', kind: 'entity', x: 80,  y: 280, entityId: 'e3', cluster: 'ownership' },
  { id: 'p5', kind: 'entity', x: 80,  y: 460, entityId: 'e5', cluster: 'finance'   },
  { id: 'p6', kind: 'entity', x: 290, y: 460, entityId: 'e9', cluster: 'finance'   },
  { id: 'p7', kind: 'quote',  x: 290, y: 250, w: 230, text: '"Registered owner: Polar Freight Holdings (Cyprus). Operator: Orion Maritime Services."', source: 'Equasis · d2' },
  { id: 'p8', kind: 'quote',  x: 500, y: 230, w: 230, text: '"Vessel dwell of 9.3h outside normal traffic lanes at 78.91°N, 20.44°E; AIS intermittent."', source: 'AIS feed · d5' },
  { id: 'p9', kind: 'note',   x: 540, y: 410, w: 220, text: 'Three vessels, three Cyprus registrations, one bank. Look for shared agent of record.', author: 'L. Marín' },
  { id: 'p10', kind: 'finding', x: 290, y: 620, w: 280, text: 'BoreaBank clears for at least 2 entities controlled by Renko.', confidence: 0.62 },
  { id: 'p11', kind: 'gap',     x: 600, y: 580, w: 200, text: 'SWIFT MT202 between BoreaBank and RU counterparties — no access.' },
];

export const PIN_CONNECTIONS = [
  { a: 'p1', b: 'p2', label: 'owns'      },
  { a: 'p2', b: 'p3', label: 'loitered'  },
  { a: 'p1', b: 'p7' },
  { a: 'p3', b: 'p8' },
  { a: 'p1', b: 'p5', label: 'banks at'  },
  { a: 'p5', b: 'p6', label: 'signatory' },
  { a: 'p4', b: 'p1', label: 'director'  },
  { a: 'p6', b: 'p10' },
  { a: 'p9', b: 'p3' },
];

export interface GeoLocation {
  id: string;
  entityId?: string;
  name: string;
  lat: number;
  lon: number;
  kind: 'port' | 'anomaly';
  events: number;
  country: string;
}

export const GEO_LOCATIONS: GeoLocation[] = [
  { id: 'g1',  entityId: 'e4', name: 'Murmansk Port T4',              lat: 68.97, lon: 33.05, kind: 'port',     events: 8,  country: 'RU' },
  { id: 'g2',  entityId: 'e6', name: 'Rotterdam Zuidhaven',           lat: 51.90, lon:  4.43, kind: 'port',     events: 12, country: 'NL' },
  { id: 'g3',  entityId: 'e7', name: 'Svalbard transshipment zone',   lat: 78.91, lon: 20.44, kind: 'anomaly',  events: 3,  country: 'NO' },
  { id: 'g4',  name: 'Tromsø',                                          lat: 69.65, lon: 18.96, kind: 'port',     events: 2,  country: 'NO' },
  { id: 'g5',  name: 'Hammerfest',                                      lat: 70.66, lon: 23.68, kind: 'port',     events: 1,  country: 'NO' },
  { id: 'g6',  name: 'Kirkenes',                                        lat: 69.73, lon: 30.05, kind: 'port',     events: 1,  country: 'NO' },
  { id: 'g7',  name: 'Arkhangelsk',                                     lat: 64.54, lon: 40.55, kind: 'port',     events: 2,  country: 'RU' },
  { id: 'g8',  name: 'Loitering · 2026-03-12',                          lat: 78.42, lon: 22.10, kind: 'anomaly',  events: 1,  country: 'IH' },
  { id: 'g9',  name: 'Loitering · 2026-03-29',                          lat: 79.10, lon: 19.50, kind: 'anomaly',  events: 1,  country: 'IH' },
  { id: 'g10', name: 'Loitering · 2026-04-08',                          lat: 78.91, lon: 20.44, kind: 'anomaly',  events: 1,  country: 'IH' },
];

export interface GeoTrack {
  id: string;
  vessel: string;
  anomaly: boolean;
  waypoints: { lat: number; lon: number }[];
}

export const GEO_TRACKS: GeoTrack[] = [
  { id: 't1', vessel: 'MV Northstar Auriga', anomaly: true, waypoints: [
    { lat: 51.90, lon:  4.43 }, { lat: 60.40, lon:  5.30 }, { lat: 69.65, lon: 18.96 },
    { lat: 78.42, lon: 22.10 }, { lat: 78.91, lon: 20.44 }, { lat: 79.10, lon: 19.50 },
    { lat: 68.97, lon: 33.05 },
  ]},
  { id: 't2', vessel: 'MV Borealis Charm', anomaly: true, waypoints: [
    { lat: 51.90, lon: 4.43 }, { lat: 69.65, lon: 18.96 }, { lat: 78.91, lon: 20.44 }, { lat: 68.97, lon: 33.05 },
  ]},
  { id: 't3', vessel: 'MV Tundra Drift',   anomaly: false, waypoints: [
    { lat: 51.90, lon: 4.43 }, { lat: 70.66, lon: 23.68 }, { lat: 68.97, lon: 33.05 },
  ]},
];

export interface CyberIoC {
  id: string;
  kind: 'Domain' | 'IPAddress' | 'Hash' | 'TTP' | 'Vulnerability';
  value: string;
  firstSeen: string;
  activity: string;
  context: string;
  rels: number;
  confidence: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  enriched: boolean;
  attributed: boolean;
}

export const CYBER_IOCS: CyberIoC[] = [
  { id: 'ioc1',  kind: 'Domain',         value: 'polar-freight-holdings[.]eu', firstSeen: '2026-02-14', activity: 'last seen 4d ago', context: 'Linked: NORTHWIND-7',           rels: 5, confidence: 0.90, severity: 'high',     enriched: true,  attributed: true  },
  { id: 'ioc2',  kind: 'IPAddress',      value: '185.214.47.118',              firstSeen: '2026-03-02', activity: 'active',           context: 'Hosting for shell-co websites', rels: 4, confidence: 0.70, severity: 'critical', enriched: true,  attributed: true  },
  { id: 'ioc3',  kind: 'Hash',           value: '4f9c2b7e…b7a1',               firstSeen: '2026-03-18', activity: '1 detonation',     context: 'Phishing lure document',        rels: 2, confidence: 0.60, severity: 'high',     enriched: false, attributed: false },
  { id: 'ioc4',  kind: 'IPAddress',      value: '91.215.183.42',               firstSeen: '2026-03-29', activity: 'active',           context: 'C2 candidate · AS200651',       rels: 3, confidence: 0.80, severity: 'high',     enriched: true,  attributed: true  },
  { id: 'ioc5',  kind: 'TTP',            value: 'T1566 · Phishing',            firstSeen: '2026-03-18', activity: '1 observation',    context: 'Maritime-themed lure',          rels: 1, confidence: 0.85, severity: 'medium',   enriched: true,  attributed: false },
  { id: 'ioc6',  kind: 'TTP',            value: 'T1036 · Masquerading',        firstSeen: '2026-03-12', activity: '3 observations',   context: 'AIS spoofing via MMSI changer', rels: 3, confidence: 0.80, severity: 'high',     enriched: true,  attributed: true  },
  { id: 'ioc7',  kind: 'TTP',            value: 'T1027 · Obfuscated Files',    firstSeen: '2026-02-22', activity: '5 observations',   context: 'Shell-company nesting',         rels: 5, confidence: 0.90, severity: 'high',     enriched: true,  attributed: true  },
  { id: 'ioc8',  kind: 'Vulnerability',  value: 'CVE-2025-4419',               firstSeen: '2026-01-29', activity: 'unpatched fleet',  context: 'AIS transponder firmware',      rels: 2, confidence: 0.75, severity: 'medium',   enriched: true,  attributed: false },
  { id: 'ioc9',  kind: 'Domain',         value: 'orion-maritime[.]eu',         firstSeen: '2026-01-29', activity: 'low traffic',      context: 'Operator front',                rels: 4, confidence: 0.85, severity: 'low',      enriched: true,  attributed: true  },
  { id: 'ioc10', kind: 'Hash',           value: '8a14e9b2…0e3c',               firstSeen: '2026-04-02', activity: '0 detonations',    context: 'Stealer payload, unfired',      rels: 1, confidence: 0.60, severity: 'medium',   enriched: false, attributed: false },
];

export interface MitreTechnique {
  id: string;
  name: string;
  seen: boolean;
  observations?: number;
  severity?: 'medium' | 'high';
}
export interface MitreTactic {
  id: string;
  name: string;
  techniques: MitreTechnique[];
}

export const CYBER_TTP_MATRIX: { tactics: MitreTactic[] } = {
  tactics: [
    { id: 'TA0001', name: 'Initial Access', techniques: [
      { id: 'T1566', name: 'Phishing',                       seen: true,  observations: 1, severity: 'high' },
      { id: 'T1190', name: 'Exploit Public-Facing App',      seen: false },
      { id: 'T1078', name: 'Valid Accounts',                 seen: true,  observations: 2 },
      { id: 'T1195', name: 'Supply Chain Compromise',        seen: false },
    ]},
    { id: 'TA0002', name: 'Execution', techniques: [
      { id: 'T1059', name: 'Command & Scripting',            seen: false },
      { id: 'T1203', name: 'Exploitation for Client Exec',   seen: false },
      { id: 'T1204', name: 'User Execution',                 seen: true,  observations: 1 },
    ]},
    { id: 'TA0003', name: 'Persistence', techniques: [
      { id: 'T1547', name: 'Boot/Logon Autostart',           seen: false },
      { id: 'T1053', name: 'Scheduled Task/Job',             seen: false },
      { id: 'T1136', name: 'Create Account',                 seen: true,  observations: 3 },
    ]},
    { id: 'TA0005', name: 'Defense Evasion', techniques: [
      { id: 'T1036', name: 'Masquerading',                   seen: true,  observations: 3, severity: 'high' },
      { id: 'T1027', name: 'Obfuscated Files',               seen: true,  observations: 5, severity: 'high' },
      { id: 'T1070', name: 'Indicator Removal',              seen: true,  observations: 2 },
    ]},
    { id: 'TA0006', name: 'Credential Access', techniques: [
      { id: 'T1003', name: 'OS Credential Dumping',          seen: false },
      { id: 'T1110', name: 'Brute Force',                    seen: false },
      { id: 'T1555', name: 'Credentials from Stores',        seen: false },
    ]},
    { id: 'TA0007', name: 'Discovery', techniques: [
      { id: 'T1082', name: 'System Information',             seen: false },
      { id: 'T1083', name: 'File and Directory',             seen: false },
      { id: 'T1046', name: 'Network Service Scan',           seen: true, observations: 1 },
    ]},
    { id: 'TA0011', name: 'Command & Control', techniques: [
      { id: 'T1071', name: 'Application Layer Protocol',     seen: true,  observations: 2 },
      { id: 'T1105', name: 'Ingress Tool Transfer',          seen: false },
      { id: 'T1573', name: 'Encrypted Channel',              seen: true,  observations: 1 },
    ]},
    { id: 'TA0010', name: 'Exfiltration', techniques: [
      { id: 'T1567', name: 'Exfil Over Web Service',         seen: false },
      { id: 'T1048', name: 'Exfil Over Alt Protocol',        seen: false },
    ]},
    { id: 'TA0040', name: 'Impact', techniques: [
      { id: 'T1486', name: 'Data Encrypted for Impact',      seen: false },
      { id: 'T1489', name: 'Service Stop',                   seen: false },
      { id: 'T1499', name: 'Endpoint DoS',                   seen: false },
    ]},
  ],
};

export const CYBER_THREAT_ACTORS = [
  {
    id: 'ta1', name: 'NORTHWIND-7', type: 'cluster' as const,
    confidence: 0.55, motivation: 'sanctions evasion · profit',
    aka: ['UNC-2104'], origin: 'mixed', overlap: 'Polar Freight cluster',
    profile: 'Loosely-affiliated cluster operating maritime sanctions-evasion infrastructure. Overlap with Polar Freight Holdings inferred via shared AS, lure-document metadata, and beneficial-owner reuse. No SIGINT corroboration; assessment is open-source only.',
    rels: 8,
  },
  {
    id: 'ta2', name: 'KESTREL FANG', type: 'state-aligned' as const,
    confidence: 0.32, motivation: 'state interest', aka: [] as string[],
    origin: '—', overlap: 'AIS-spoof toolkit',
    profile: null as string | null,
    rels: 2,
  },
];

export const ANOMALY_DIGEST = [
  { kind: 'community' as const, title: 'New community forming around BoreaBank AG',     detail: '4 entities clustered in the last 18h',  delta: '+4',   tint: 'var(--cite)'   },
  { kind: 'degree'    as const, title: 'Polar Freight Holdings · degree +3',           detail: 'three new relationships ingested today', delta: '+3',   tint: 'var(--signal)' },
  { kind: 'pattern'   as const, title: 'Pattern match: Tundra Drift fits Auriga schedule', detail: 'sister-vessel hypothesis at 71% similarity', delta: '0.71', tint: 'var(--violet)' },
];

export const NETWORK_CENTRALITY = [
  { id: 'e2', entity: 'Polar Freight Holdings',       type: 'ORG',       degree: 9, betweenness: 0.412, eigenvector: 0.781, pagerank: 0.148, closeness: 0.583 },
  { id: 'e1', entity: 'MV Northstar Auriga',          type: 'VESSEL',    degree: 7, betweenness: 0.388, eigenvector: 0.642, pagerank: 0.124, closeness: 0.541 },
  { id: 'e5', entity: 'BoreaBank AG',                 type: 'ORG',       degree: 6, betweenness: 0.301, eigenvector: 0.514, pagerank: 0.098, closeness: 0.502 },
  { id: 'e9', entity: 'Katja Renko',                  type: 'PERSON',    degree: 5, betweenness: 0.256, eigenvector: 0.421, pagerank: 0.082, closeness: 0.475 },
  { id: 'e8', entity: 'Orion Maritime Services',      type: 'ORG',       degree: 4, betweenness: 0.198, eigenvector: 0.358, pagerank: 0.071, closeness: 0.443 },
  { id: 'e7', entity: 'Svalbard transshipment zone',  type: 'LOCATION',  degree: 4, betweenness: 0.142, eigenvector: 0.291, pagerank: 0.061, closeness: 0.411 },
  { id: 'e3', entity: 'Dmitri Volkov',                type: 'PERSON',    degree: 3, betweenness: 0.092, eigenvector: 0.227, pagerank: 0.048, closeness: 0.382 },
  { id: 'e4', entity: 'Murmansk Port Terminal 4',     type: 'LOCATION',  degree: 3, betweenness: 0.085, eigenvector: 0.201, pagerank: 0.044, closeness: 0.371 },
  { id: 'e6', entity: 'Rotterdam Zuidhaven',          type: 'LOCATION',  degree: 2, betweenness: 0.041, eigenvector: 0.158, pagerank: 0.033, closeness: 0.328 },
  { id: 'e10', entity: 'STIX bundle 2026-0412',       type: 'INDICATOR', degree: 2, betweenness: 0.038, eigenvector: 0.142, pagerank: 0.029, closeness: 0.311 },
];

export const STRUCTURAL_HOLES = [
  { id: 'e2', entity: 'Polar Freight Holdings',     type: 'ORG',    constraint: 0.18, effectiveSize: 4.2, degree: 9, isBroker: true,  bridges: 'Owners ↔ Bank ↔ Operators' },
  { id: 'e5', entity: 'BoreaBank AG',               type: 'ORG',    constraint: 0.22, effectiveSize: 3.6, degree: 6, isBroker: true,  bridges: 'Finance ↔ Beneficial owners' },
  { id: 'e9', entity: 'Katja Renko',                type: 'PERSON', constraint: 0.28, effectiveSize: 2.9, degree: 5, isBroker: true,  bridges: 'Shell entities ↔ Banking' },
  { id: 'e1', entity: 'MV Northstar Auriga',        type: 'VESSEL', constraint: 0.36, effectiveSize: 2.4, degree: 7, isBroker: false, bridges: '—' },
  { id: 'e8', entity: 'Orion Maritime Services',    type: 'ORG',    constraint: 0.41, effectiveSize: 2.1, degree: 4, isBroker: false, bridges: '—' },
];

export const COMMUNITY_MAP: Record<string, number> = {
  e1: 0, e2: 0, e3: 0, e8: 0,
  e5: 1, e9: 1,
  e4: 2, e6: 2, e7: 2,
  e10: 3,
};
export const COMMUNITY_META = [
  { id: 0, label: 'Ownership / Operations', tint: 'oklch(0.55 0.13 295)', members: 4 },
  { id: 1, label: 'Finance & Banking',      tint: 'var(--signal-ink)',    members: 2 },
  { id: 2, label: 'Geography',              tint: 'oklch(0.56 0.12 155)', members: 3 },
  { id: 3, label: 'Cyber indicators',       tint: 'var(--cite)',          members: 1 },
];

export const EGO_NETWORK = {
  center: 'e2',
  hops: 2,
  nodes: [
    { id: 'e2', name: 'Polar Freight Holdings',       type: 'ORG',       hop: 0, localPagerank: 0.42, localBetweenness: 0.51 },
    { id: 'e1', name: 'MV Northstar Auriga',          type: 'VESSEL',    hop: 1, localPagerank: 0.18, localBetweenness: 0.22 },
    { id: 'e3', name: 'Dmitri Volkov',                type: 'PERSON',    hop: 1, localPagerank: 0.09, localBetweenness: 0.06 },
    { id: 'e5', name: 'BoreaBank AG',                 type: 'ORG',       hop: 1, localPagerank: 0.14, localBetweenness: 0.17 },
    { id: 'e8', name: 'Orion Maritime Services',      type: 'ORG',       hop: 1, localPagerank: 0.08, localBetweenness: 0.04 },
    { id: 'e4', name: 'Murmansk Port T4',             type: 'LOCATION',  hop: 2, localPagerank: 0.04, localBetweenness: 0.01 },
    { id: 'e6', name: 'Rotterdam Zuidhaven',          type: 'LOCATION',  hop: 2, localPagerank: 0.03, localBetweenness: 0.00 },
    { id: 'e7', name: 'Svalbard zone',                type: 'LOCATION',  hop: 2, localPagerank: 0.05, localBetweenness: 0.02 },
    { id: 'e9', name: 'Katja Renko',                  type: 'PERSON',    hop: 2, localPagerank: 0.07, localBetweenness: 0.03 },
  ],
};

export const INFLUENCE_RESULT = {
  seeds: ['e2'],
  threshold: 0.3,
  steps: [
    { step: 0, newlyActivated: ['e2'],             cumulative: 1, label: 'seed' },
    { step: 1, newlyActivated: ['e1', 'e3', 'e5'], cumulative: 4, label: 'direct neighbors' },
    { step: 2, newlyActivated: ['e9', 'e7', 'e6'], cumulative: 7, label: 'second-order' },
    { step: 3, newlyActivated: ['e4', 'e8'],       cumulative: 9, label: 'tertiary cascade' },
  ],
  totalActivated: 9,
  totalNodes: 10,
  reachRatio: 0.9,
};

export const SHORTEST_PATH_SAMPLE = {
  source: 'e2', target: 'e4',
  path: ['e2', 'e1', 'e4'],
  length: 2,
  hops: [
    { from: 'e2', to: 'e1', rel: 'owns',      confidence: 0.91 },
    { from: 'e1', to: 'e4', rel: 'docked_at', confidence: 0.60 },
  ],
};

export const NETWORK_SNAPSHOTS = [
  { id: 'snap1', name: 'Polar Freight cluster',   entities: ['e1', 'e2', 'e3', 'e5', 'e8', 'e9'], created: '2026-04-09', author: 'L. Marín' },
  { id: 'snap2', name: 'Arctic transit corridor', entities: ['e1', 'e4', 'e6', 'e7'],             created: '2026-04-05', author: 'L. Marín' },
  { id: 'snap3', name: 'Sanctions-flagged subset', entities: ['e2', 'e5', 'e9'],                  created: '2026-03-28', author: 'A. Choi' },
];

export const NETWORK_NOTES = [
  { id: 'n1', t: '34m ago', author: 'L. Marín', kind: 'observation' as const, title: 'Volkov→Renko nominee chain',
    body: 'Volkov listed as director of record. Beneficial-owner filings (OpenCorporates 2024-11-02) name Renko via nominee arrangement. Need to confirm consistency with two other Cyprus filings.',
    entities: ['e3', 'e9'] },
  { id: 'n2', t: '2h ago',  author: 'L. Marín', kind: 'hypothesis'  as const, title: 'BoreaBank as common correspondent',
    body: 'Three entities banked through BoreaBank AG. Plausibly a sanctioned-cargo clearing channel. Diagnostic test would be SWIFT MT202 flow patterns.',
    entities: ['e5', 'e2', 'e9'] },
  { id: 'n3', t: '1d ago',  author: 'A. Choi',  kind: 'gap'         as const, title: 'No SIGINT corroboration',
    body: 'OSINT is consistent but no second-source confirmation. Recommend formal SIGINT request via partner.',
    entities: ['e2'] },
];

export const EDGE_METADATA: Record<string, { firstSeen: string; lastSeen: string; confidence: number; evidence: number; docs: string[] }> = {
  'e1|e2|owned_by':          { firstSeen: '2026-02-14', lastSeen: '2026-04-08', confidence: 0.91, evidence: 4, docs: ['d2', 'd4'] },
  'e2|e3|director':          { firstSeen: '2026-02-22', lastSeen: '2026-04-04', confidence: 0.74, evidence: 2, docs: ['d4'] },
  'e1|e4|docked_at':         { firstSeen: '2026-03-12', lastSeen: '2026-04-08', confidence: 0.60, evidence: 3, docs: ['d1', 'd5'] },
  'e2|e5|banked_at':         { firstSeen: '2026-01-29', lastSeen: '2026-04-10', confidence: 0.84, evidence: 5, docs: ['d7', 'd4'] },
  'e1|e6|scheduled_to':      { firstSeen: '2026-04-02', lastSeen: '2026-04-10', confidence: 0.55, evidence: 1, docs: ['d2'] },
  'e1|e7|loitered_near':     { firstSeen: '2026-03-12', lastSeen: '2026-04-10', confidence: 0.78, evidence: 6, docs: ['d5', 'd1'] },
  'e2|e8|contracted':        { firstSeen: '2026-02-22', lastSeen: '2026-03-30', confidence: 0.66, evidence: 2, docs: ['d4'] },
  'e8|e9|controlled_by':     { firstSeen: '2026-03-15', lastSeen: '2026-04-02', confidence: 0.49, evidence: 1, docs: ['d4'] },
  'e5|e9|account_signatory': { firstSeen: '2026-01-29', lastSeen: '2026-04-10', confidence: 0.42, evidence: 2, docs: ['d7'] },
  'e7|e10|refers_to':        { firstSeen: '2026-04-04', lastSeen: '2026-04-12', confidence: 0.30, evidence: 1, docs: [] },
  'e3|e9|associate':         { firstSeen: '2026-02-28', lastSeen: '2026-04-02', confidence: 0.44, evidence: 1, docs: ['d6'] },
};

// ============================================================================
// V2: Review queue / Notifications / Search index / Provenance
// ============================================================================

export interface ReviewItem {
  id: string;
  kind: 'relationship' | 'entity' | 'merge';
  status: 'pending' | 'approved' | 'rejected';
  claim: string;
  basis: string;
  entities: string[];
  source: string | null;
  flagged: string;
  reason: 'single-source' | 'inferred' | 'auto-tagged' | 'dedup' | 'verified';
}

export const REVIEW_QUEUE: ReviewItem[] = [
  { id: 'rq1', kind: 'relationship', status: 'pending', claim: 'Murmansk Port Terminal 4 facilitates transshipment of sanctioned cargo', basis: 'Single Telegram-sourced claim (reliability C)', entities: ['e4'], source: 'd6', flagged: '12m ago', reason: 'single-source' },
  { id: 'rq2', kind: 'entity', status: 'pending', claim: 'Orion Maritime Services is controlled by Katja Renko', basis: 'Inferred from overlapping signatory; no direct filing', entities: ['e8', 'e9'], source: 'd4', flagged: '12m ago', reason: 'inferred' },
  { id: 'rq3', kind: 'relationship', status: 'pending', claim: 'STIX bundle 2026-0412 refers to Svalbard transshipment zone', basis: 'Geo-tag match only; no analyst confirmation', entities: ['e10', 'e7'], source: null, flagged: '12m ago', reason: 'auto-tagged' },
  { id: 'rq4', kind: 'merge', status: 'pending', claim: 'Merge "Borea Bank AG" into "BoreaBank AG"', basis: 'Name similarity 0.94; same registration', entities: ['e5'], source: 'd7', flagged: '1h ago', reason: 'dedup' },
  { id: 'rq5', kind: 'entity', status: 'approved', claim: 'Dmitri Volkov is director of record for Polar Freight Holdings', basis: 'OpenCorporates filing, confirmed', entities: ['e3', 'e2'], source: 'd4', flagged: '3h ago', reason: 'verified' },
];

export interface AppNotification {
  id: string;
  type: 'evidence' | 'agent' | 'change' | 'community' | 'product' | 'watch';
  t: string;
  read: boolean;
  title: string;
  body: string;
  entity?: string;
  action: string;  // route name
}

export const APP_NOTIFICATIONS: AppNotification[] = [
  { id: 'nt1', type: 'evidence',  t: '2m ago',  read: false, title: 'New evidence on watched entity', body: 'MarineCadastre returned a 3rd AIS anomaly for MV Northstar Auriga', entity: 'e1', action: 'network' },
  { id: 'nt2', type: 'agent',     t: '12m ago', read: false, title: 'Agent run completed',           body: 'Run R-0412-04 finished · +41 entities, +78 relationships, 3 flagged for review',                  action: 'review' },
  { id: 'nt3', type: 'change',    t: '34m ago', read: false, title: 'Relationship change',           body: 'Polar Freight Holdings degree increased +3 (now 9)',                                              entity: 'e2', action: 'network' },
  { id: 'nt4', type: 'community', t: '1h ago',  read: true,  title: 'New community forming',         body: '4 entities clustered around BoreaBank AG in the last 18h',                                        action: 'network' },
  { id: 'nt5', type: 'product',   t: '2h ago',  read: true,  title: 'Product needs review',          body: '"Northstar Auriga · entity brief" moved to In Review',                                            action: 'products' },
  { id: 'nt6', type: 'watch',     t: '5h ago',  read: true,  title: 'Watchlist match',               body: 'Telegram monitor matched 2 posts mentioning BoreaBank AG',                                        entity: 'e5', action: 'network' },
];

export interface SearchHit {
  kind: 'entity' | 'document' | 'product' | 'question';
  id: string;
  label: string;
  meta: string;
  view: string;
}

export const SEARCH_INDEX: SearchHit[] = [
  { kind: 'entity',   id: 'e1', label: 'MV Northstar Auriga',         meta: 'VESSEL · IMO 9487214',           view: 'network' },
  { kind: 'entity',   id: 'e2', label: 'Polar Freight Holdings',      meta: 'ORG · Cyprus shell',             view: 'network' },
  { kind: 'entity',   id: 'e5', label: 'BoreaBank AG',                meta: 'ORG · correspondent bank',       view: 'network' },
  { kind: 'entity',   id: 'e9', label: 'Katja Renko',                 meta: 'PERSON · beneficial owner',      view: 'network' },
  { kind: 'entity',   id: 'e4', label: 'Murmansk Port Terminal 4',    meta: 'LOCATION · RU',                  view: 'geo' },
  { kind: 'entity',   id: 'e7', label: 'Svalbard transshipment zone', meta: 'LOCATION · NO',                  view: 'geo' },
  { kind: 'document', id: 'd4', label: 'Company extract — Polar Freight Holdings', meta: 'PDF · OpenCorporates · REL.B', view: 'documents' },
  { kind: 'document', id: 'd2', label: 'Equasis record — IMO 9487214',             meta: 'HTML · equasis.org · REL.A',   view: 'documents' },
  { kind: 'document', id: 'd7', label: 'FinCEN GTO amendment',                     meta: 'PDF · fincen.gov · REL.A',     view: 'documents' },
  { kind: 'product',  id: 'p1', label: 'NSR Transit Patterns',                     meta: 'INTSUM · final · 2026-04-09',  view: 'products' },
  { kind: 'product',  id: 'p2', label: 'Northstar Auriga · entity brief',          meta: '1-pager · in review',          view: 'products' },
  { kind: 'question', id: 'q1', label: 'How is Polar Freight connected to sanctioned movements?', meta: 'asked 12m ago', view: 'network' },
  { kind: 'question', id: 'q2', label: 'Which ports appear most in shell-company schedules?',     meta: 'asked 2h ago',  view: 'network' },
];

// ============================================================================
// V2: Topics radial mindmap
// ============================================================================

export interface TopicNode {
  id: string;
  name: string;
  count?: number;
  kind?: 'category' | 'topic';
  kw?: string[];
  entities?: string[];
  children?: TopicNode[];
}

export const TOPIC_TREE: TopicNode = {
  id: 'root', name: 'ARCTIC SHIFT · Knowledge Base',
  children: [
    { id: 'cat-vessels', name: 'Maritime · Vessels', count: 14, kind: 'category', children: [
      { id: 'top-anom-vessels', name: 'Anomalous AIS patterns', count: 14, kind: 'topic', kw: ['AIS', 'loitering', 'dark period', 'NSR', 'Svalbard'], entities: ['e1'] },
      { id: 'top-shell-owned',  name: 'Shell-owned vessels',  count: 3,  kind: 'topic', kw: ['Cyprus', 'beneficial owner', 'nominee'],             entities: ['e1'] },
    ]},
    { id: 'cat-finance', name: 'Finance & Banking', count: 8, kind: 'category', children: [
      { id: 'top-correspondent',  name: 'Correspondent banking',   count: 5, kind: 'topic', kw: ['BoreaBank', 'SWIFT', 'MT202', 'clearing'], entities: ['e5'] },
      { id: 'top-shell-finance',  name: 'Shell-company finance',   count: 3, kind: 'topic', kw: ['nominee', 'signatory', 'Cyprus'],         entities: ['e2', 'e9'] },
    ]},
    { id: 'cat-actors', name: 'People & Roles', count: 6, kind: 'category', children: [
      { id: 'top-directors',  name: 'Directors of record', count: 3, kind: 'topic', kw: ['Volkov', 'director', 'filing'],         entities: ['e3'] },
      { id: 'top-beneficial', name: 'Beneficial owners',   count: 3, kind: 'topic', kw: ['Renko', 'beneficial owner', 'nominee'], entities: ['e9'] },
    ]},
    { id: 'cat-geo', name: 'Geography', count: 12, kind: 'category', children: [
      { id: 'top-ports-ru',   name: 'Russian ports',             count: 3, kind: 'topic', kw: ['Murmansk', 'Arkhangelsk', 'NSR'],     entities: ['e4'] },
      { id: 'top-ports-no',   name: 'Norwegian ports',           count: 4, kind: 'topic', kw: ['Tromsø', 'Kirkenes', 'Hammerfest'],   entities: [] as string[] },
      { id: 'top-transship',  name: 'Transshipment zones',       count: 3, kind: 'topic', kw: ['Svalbard', 'dwell', 'loiter'],        entities: ['e7'] },
      { id: 'top-discharge',  name: 'European discharge ports',  count: 2, kind: 'topic', kw: ['Rotterdam', 'Zuidhaven'],             entities: ['e6'] },
    ]},
    { id: 'cat-cyber', name: 'Cyber & Indicators', count: 9, kind: 'category', children: [
      { id: 'top-ais-spoof',    name: 'AIS spoofing TTPs',                count: 4, kind: 'topic', kw: ['T1036', 'masquerading', 'MMSI'],       entities: ['e10'] },
      { id: 'top-shell-infra',  name: 'Shell-company infrastructure',     count: 5, kind: 'topic', kw: ['domain', 'AS200651', 'phishing'],     entities: [] as string[] },
    ]},
    { id: 'cat-sanctions', name: 'Sanctions & Regulatory', count: 5, kind: 'category', children: [
      { id: 'top-ofac',    name: 'OFAC matches',         count: 2, kind: 'topic', kw: ['SDN', 'OFAC', 'sanctioned'],     entities: [] as string[] },
      { id: 'top-fincen',  name: 'FinCEN advisories',    count: 3, kind: 'topic', kw: ['FinCEN', 'GTO', 'Baltic'],       entities: [] as string[] },
    ]},
  ],
};

export const TOPIC_SUMMARIES: Record<string, string> = {
  'top-anom-vessels': 'Across 90 days of AIS feed data, 14 vessels exhibited loitering anomalies near the Svalbard transshipment zone, with dwells of 6–9 hours outside normal traffic lanes and intermittent AIS transmissions. Three resolved to opaque corporate structures in Cyprus and the Marshall Islands. Most frequent culprits: MV Northstar Auriga, MV Borealis Charm, MV Tundra Drift.',
  'top-correspondent': 'BoreaBank AG appears as a common correspondent bank for at least three entities in this case. FinCEN’s GTO amendment of March 2026 specifically references Baltic correspondent banks as a typology of concern. Critical gap: SWIFT MT202 flows between BoreaBank and Russian counterparties are not accessible via OSINT.',
  'top-shell-finance':  'Three entities in scope (Polar Freight Holdings, Orion Maritime Services, and a third subsidiary) share signatories and registered addresses. Nominee arrangements obscure ultimate beneficial ownership. Cyprus and Marshall Islands jurisdictions are common.',
  'top-directors':      'Dmitri Volkov is the named director of record for at least two entities, with single-director corporate structures and no other listed officers. Filing-history amendments cluster around beneficial-ownership disclosures.',
  'top-beneficial':     'Katja Renko is named as beneficial owner via nominee arrangement in OpenCorporates filings dated 2024-11-02. The nominee filing references a holding chain through two intermediary entities registered in the Marshall Islands.',
  'top-transship':      'Svalbard transshipment zone shows recurring vessel dwell patterns of 6–9 hours with intermittent AIS transmissions. Geo-fenced for monitoring.',
  'top-ais-spoof':      'T1036 (Masquerading) observed via MMSI changer activity correlated with AIS spoofing events. Three vessels confirmed to have transmitted spoofed identities during sanctioned-cargo loading windows.',
};

// ============================================================================
// V2: Provenance trail — chain of custody for a claim/entity/edge
// ============================================================================

export interface ProvenanceStep {
  step: 'source' | 'extraction' | 'resolution' | 'relationship' | 'assessment' | 'product';
  label: string;
  meta: string;
  detail: string;
}

export const PROVENANCE_DEMO: ProvenanceStep[] = [
  { step: 'source',       label: 'OpenCorporates extract',       meta: 'd4 · reliability B',         detail: 'Company registration retrieved 2026-03-28' },
  { step: 'extraction',   label: 'Entity extracted',             meta: 'hybrid · NLP+LLM',           detail: 'ORG recognized; name normalized from "Polar Freight Holdings Ltd"' },
  { step: 'resolution',   label: 'Deduplicated',                 meta: '2 mentions merged',          detail: 'Merged with "Polar Freight Holdings (Cyprus)" from Equasis (d2)' },
  { step: 'relationship', label: 'Linked to MV Northstar Auriga', meta: 'owned_by',                  detail: 'Inferred from registration + Equasis cross-check' },
  { step: 'assessment',   label: 'Assessment recorded',          meta: 'L. Marín · 34m ago',         detail: '"Likely the registered owner..." — analyst confirmation' },
  { step: 'product',      label: 'Cited in INTSUM',              meta: 'NSR Transit Patterns',       detail: 'Used in Key Judgment 1, published 2026-04-09' },
];
