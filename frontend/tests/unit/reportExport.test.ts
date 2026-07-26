import { describe, it, expect } from 'vitest';
import {
  buildProductFilename,
  buildProductMarkdown,
  formatFileDate,
  formatProductDate,
  normalizeClassification,
  slugify,
  type ProductDocument,
} from '@/lib/reportExport';

/**
 * The Products view exports a drafted report as Markdown (lossless — the body
 * already is Markdown) and prints it via the browser. These helpers build the
 * file: the header block, the filename, and the classification marking, which
 * must come from the project data and never be invented.
 */

const baseDoc: ProductDocument = {
  title: 'APT29 Infrastructure Assessment',
  reportType: 'Threat Assessment',
  classification: 'SECRET',
  projectName: 'Nordwind',
  // Local-time construction so the formatted date matches the parts asserted below.
  generatedAt: new Date(2026, 6, 25, 14, 30),
  entities: ['APT29', 'Cozy Bear'],
  content: '## Key Judgements\n\nIt is **likely** that...\n',
};

describe('normalizeClassification', () => {
  it('upper-cases and de-underscores a project level', () => {
    expect(normalizeClassification('top_secret')).toBe('TOP SECRET');
    expect(normalizeClassification('unclassified')).toBe('UNCLASSIFIED');
  });

  it('collapses separators and surrounding whitespace', () => {
    expect(normalizeClassification('  secret--noforn ')).toBe('SECRET NOFORN');
  });

  it('returns null when the project carries no marking, rather than inventing one', () => {
    expect(normalizeClassification('')).toBeNull();
    expect(normalizeClassification('   ')).toBeNull();
    expect(normalizeClassification(undefined)).toBeNull();
    expect(normalizeClassification(null)).toBeNull();
  });
});

describe('formatProductDate / formatFileDate', () => {
  it('renders a locale-independent cover date', () => {
    expect(formatProductDate(new Date(2026, 6, 25))).toBe('25 July 2026');
    expect(formatProductDate(new Date(2026, 0, 1))).toBe('1 January 2026');
  });

  it('renders a sortable, zero-padded file date', () => {
    expect(formatFileDate(new Date(2026, 0, 5))).toBe('2026-01-05');
  });

  it('is safe on an invalid date (a saved report with no created_at)', () => {
    expect(formatProductDate(new Date('nope'))).toBe('');
    expect(formatFileDate(new Date('nope'))).toBe('');
  });
});

describe('slugify / buildProductFilename', () => {
  it('slugs a title into filename-safe text', () => {
    expect(slugify('APT29: Infrastructure & Tradecraft')).toBe('apt29-infrastructure-tradecraft');
  });

  it('strips diacritics and trailing separators', () => {
    expect(slugify('Opération Café —')).toBe('operation-cafe');
  });

  it('falls back to "report" when nothing survives', () => {
    expect(slugify('???')).toBe('report');
    expect(slugify('')).toBe('report');
  });

  it('names the file after the product and its date', () => {
    expect(buildProductFilename(baseDoc, 'md')).toBe('apt29-infrastructure-assessment_2026-07-25.md');
  });
});

describe('buildProductMarkdown', () => {
  it('opens with YAML front matter carrying the dissemination metadata', () => {
    const md = buildProductMarkdown(baseDoc);
    const frontMatter = md.split('---')[1];
    expect(md.startsWith('---\n')).toBe(true);
    expect(frontMatter).toContain('title: "APT29 Infrastructure Assessment"');
    expect(frontMatter).toContain('report_type: "Threat Assessment"');
    expect(frontMatter).toContain('classification: "SECRET"');
    expect(frontMatter).toContain('project: "Nordwind"');
    expect(frontMatter).toContain('generated: ');
    expect(frontMatter).toContain('  - "APT29"');
    expect(frontMatter).toContain('  - "Cozy Bear"');
    expect(frontMatter).toContain('generator: "SENTINEL');
  });

  it('renders a human-readable cover block above the body', () => {
    const md = buildProductMarkdown(baseDoc);
    expect(md).toContain('# APT29 Infrastructure Assessment');
    expect(md).toContain('*Threat Assessment · Nordwind · 25 July 2026*');
    expect(md).toContain('**Entities covered:** APT29, Cozy Bear');
  });

  it('marks the product top and bottom when the project is classified', () => {
    const md = buildProductMarkdown(baseDoc);
    const markings = md.match(/\*\*SECRET\*\*/g) ?? [];
    expect(markings).toHaveLength(2);
    expect(md.trimEnd().endsWith('**SECRET**')).toBe(true);
  });

  it('omits the marking entirely for an unclassified-by-omission project', () => {
    const md = buildProductMarkdown({ ...baseDoc, classification: null });
    expect(md).not.toContain('classification:');
    // The body still exports; only the invented marking is absent.
    expect(md).toContain('# APT29 Infrastructure Assessment');
  });

  it('preserves the drafted Markdown body verbatim', () => {
    const md = buildProductMarkdown(baseDoc);
    expect(md).toContain('## Key Judgements');
    expect(md).toContain('It is **likely** that...');
  });

  it('quotes YAML-hostile titles so the front matter stays parseable', () => {
    const md = buildProductMarkdown({ ...baseDoc, title: 'Q3: "Sandworm" \\ ops' });
    expect(md).toContain('title: "Q3: \\"Sandworm\\" \\\\ ops"');
  });

  it('omits the entity list when coverage could not be resolved', () => {
    const md = buildProductMarkdown({ ...baseDoc, entities: [] });
    expect(md).not.toContain('entities:');
    expect(md).not.toContain('**Entities covered:**');
  });
});
