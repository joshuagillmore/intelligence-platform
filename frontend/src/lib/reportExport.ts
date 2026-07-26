/**
 * Finished-product export helpers.
 *
 * A drafted report is Markdown all the way through (the LLM writes Markdown,
 * `components/Markdown.tsx` renders it), so Markdown is the lossless export —
 * plain `.txt` threw the structure away. These helpers turn the drafted body
 * plus its dissemination metadata into a self-describing `.md` file, and are
 * shared by the printable layout so both carry the same header block.
 *
 * Pure functions only: no DOM, no network — the Products view owns both.
 */
import { APP_NAME, APP_VERSION } from './branding';

/** A drafted or saved report plus everything a consumer needs on the cover. */
export interface ProductDocument {
  title: string;
  /** Human label, e.g. "Threat Assessment" — not the raw enum value. */
  reportType: string;
  /**
   * Dissemination marking taken verbatim from the project's
   * `classification_level`, or null when the project carries none. Never
   * synthesised — an unmarked project produces an unmarked product.
   */
  classification: string | null;
  projectName: string;
  generatedAt: Date;
  /** Names of the entities the product covers; may be empty. */
  entities: string[];
  /** The analytic body, as Markdown. */
  content: string;
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * Date for the cover block, e.g. "25 July 2026". Formatted from local date
 * parts rather than `toLocaleDateString` so it renders identically in every
 * browser, locale and test environment.
 */
export function formatProductDate(d: Date): string {
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** `YYYY-MM-DD` from local date parts, for filenames. */
export function formatFileDate(d: Date): string {
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Normalise a project's `classification_level` for display: separators become
 * spaces and the whole marking is upper-cased ("top_secret" -> "TOP SECRET").
 * Returns null for a missing/blank level so callers can omit the marking
 * entirely instead of inventing one.
 */
export function normalizeClassification(level?: string | null): string | null {
  const raw = (level ?? '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return raw ? raw.toUpperCase() : null;
}

/** Filename-safe slug; falls back to "report" when nothing survives. */
export function slugify(s: string): string {
  const slug = (s || '')
    .normalize('NFKD')
    // Strip the combining marks NFKD split off (U+0300-U+036F).
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 60)
    .replace(/^-+|-+$/g, '');
  return slug || 'report';
}

/** e.g. `apt29-infrastructure-assessment_2026-07-25.md` */
export function buildProductFilename(doc: ProductDocument, ext: string): string {
  const date = formatFileDate(doc.generatedAt);
  return `${slugify(doc.title)}${date ? `_${date}` : ''}.${ext}`;
}

/** Double-quoted YAML scalar — safe for titles containing `:`, `"` or `\`. */
function yamlString(value: string): string {
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
}

/**
 * Render the finished product as a standalone Markdown document: YAML front
 * matter for tooling (Pandoc, Obsidian, static site generators) followed by a
 * human-readable cover block and the analytic body verbatim.
 */
export function buildProductMarkdown(doc: ProductDocument): string {
  const lines: string[] = ['---'];
  lines.push(`title: ${yamlString(doc.title)}`);
  lines.push(`report_type: ${yamlString(doc.reportType)}`);
  if (doc.classification) lines.push(`classification: ${yamlString(doc.classification)}`);
  lines.push(`project: ${yamlString(doc.projectName)}`);
  if (!Number.isNaN(doc.generatedAt.getTime())) {
    lines.push(`generated: ${doc.generatedAt.toISOString()}`);
  }
  if (doc.entities.length > 0) {
    lines.push('entities:');
    for (const name of doc.entities) lines.push(`  - ${yamlString(name)}`);
  }
  lines.push(`generator: ${yamlString(`${APP_NAME} ${APP_VERSION}`)}`);
  lines.push('---', '');

  if (doc.classification) lines.push(`**${doc.classification}**`, '');

  lines.push(`# ${doc.title}`, '');

  const subtitle = [doc.reportType, doc.projectName, formatProductDate(doc.generatedAt)]
    .filter(Boolean)
    .join(' · ');
  if (subtitle) lines.push(`*${subtitle}*`, '');

  if (doc.entities.length > 0) {
    lines.push(`**Entities covered:** ${doc.entities.join(', ')}`, '');
  }

  lines.push('---', '');
  lines.push(doc.content.trim(), '');

  if (doc.classification) lines.push('---', '', `**${doc.classification}**`, '');

  return lines.join('\n');
}
