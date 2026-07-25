import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup, screen } from '@testing-library/react';
import PrintableProduct from '@/components/PrintableProduct';
import type { ProductDocument } from '@/lib/reportExport';

/**
 * The printable product is the "Export PDF" path: it renders nothing on screen
 * and takes over the page under @media print, so the browser's own
 * print-to-PDF produces a finished, marked, chrome-free document.
 */

const doc: ProductDocument = {
  title: 'APT29 Infrastructure Assessment',
  reportType: 'Threat Assessment',
  classification: 'SECRET',
  projectName: 'Nordwind',
  generatedAt: new Date(2026, 6, 25),
  entities: ['APT29', 'Cozy Bear'],
  content: '## Key Judgements\n\nIt is **likely** that infrastructure persists.\n',
};

afterEach(cleanup);

describe('PrintableProduct', () => {
  it('renders nothing when there is no product to print', () => {
    render(<PrintableProduct doc={null} />);
    expect(document.getElementById('sentinel-print-root')).toBeNull();
  });

  it('portals to <body> so the print stylesheet can hide every other body child', () => {
    render(<PrintableProduct doc={doc} />);
    const root = document.getElementById('sentinel-print-root');
    expect(root).not.toBeNull();
    expect(root?.parentElement).toBe(document.body);
    expect(root).toHaveClass('print-document');
  });

  it('carries the classification marking top and bottom, plus in the cover block', () => {
    render(<PrintableProduct doc={doc} />);
    const markings = document.querySelectorAll('.print-marking');
    expect(markings).toHaveLength(2);
    markings.forEach(m => expect(m.textContent).toBe('SECRET'));
    expect(document.querySelector('.print-meta')?.textContent).toContain('SECRET');
  });

  it('omits the marking when the project carries none, rather than inventing one', () => {
    render(<PrintableProduct doc={{ ...doc, classification: null }} />);
    expect(document.querySelectorAll('.print-marking')).toHaveLength(0);
    expect(document.querySelector('.print-meta')?.textContent).not.toContain('SECRET');
  });

  it('shows title, type, project, date and coverage on the cover', () => {
    render(<PrintableProduct doc={doc} />);
    expect(screen.getByText('APT29 Infrastructure Assessment')).toBeInTheDocument();
    const meta = document.querySelector('.print-meta')?.textContent ?? '';
    expect(meta).toContain('Threat Assessment');
    expect(meta).toContain('Nordwind');
    expect(meta).toContain('25 July 2026');
    expect(meta).toContain('APT29, Cozy Bear');
  });

  it('renders the body through the Markdown renderer, keeping its structure', () => {
    render(<PrintableProduct doc={doc} />);
    const body = document.querySelector('.print-body');
    expect(body?.querySelector('h2')?.textContent).toBe('Key Judgements');
    expect(body?.querySelector('strong')?.textContent).toBe('likely');
  });

  it('does not render raw HTML embedded in LLM output (XSS-safe)', () => {
    render(<PrintableProduct doc={{ ...doc, content: 'Body <img src=x onerror="alert(1)">' }} />);
    const body = document.querySelector('.print-body');
    expect(body?.querySelector('img')).toBeNull();
    expect(body?.textContent).toContain('Body');
  });
});
