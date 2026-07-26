'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import Markdown from './Markdown';
import { APP_NAME, APP_VERSION } from '@/lib/branding';
import { formatProductDate, type ProductDocument } from '@/lib/reportExport';
import './printableProduct.css';

/**
 * The printable/PDF form of a finished intelligence product.
 *
 * Renders nothing on screen (`.print-document { display: none }`) and takes
 * over the page entirely under `@media print`, so "Export PDF" is just
 * `window.print()` — the browser's own print-to-PDF, no PDF dependency, works
 * offline, and reuses the same XSS-safe <Markdown> renderer as the screen view
 * so the analytic structure (headings, tables, probability language) survives.
 *
 * It portals to <body> because the print stylesheet hides every other body
 * child; nesting it inside the page tree would hide it along with its ancestor.
 * The portal mounts after hydration, so SSR and first client render agree.
 */
export default function PrintableProduct({ doc }: { doc: ProductDocument | null }) {
  const [container, setContainer] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setContainer(document.body);
  }, []);

  if (!container || !doc) return null;

  const date = formatProductDate(doc.generatedAt);

  return createPortal(
    <article id="sentinel-print-root" className="print-document" aria-hidden="true">
      {/* Marking repeats on every page (fixed position, inside the page margin). */}
      {doc.classification && (
        <div className="print-marking print-marking-top">{doc.classification}</div>
      )}

      <header className="print-header">
        <div className="print-org">{APP_NAME} &middot; Intelligence Product</div>
        <h1 className="print-title">{doc.title}</h1>
        <dl className="print-meta">
          <dt>Report type</dt>
          <dd>{doc.reportType}</dd>
          <dt>Project</dt>
          <dd>{doc.projectName}</dd>
          {doc.classification && (
            <>
              <dt>Classification</dt>
              <dd>{doc.classification}</dd>
            </>
          )}
          {date && (
            <>
              <dt>Date</dt>
              <dd>{date}</dd>
            </>
          )}
          {doc.entities.length > 0 && (
            <>
              <dt>Entities covered</dt>
              <dd>{doc.entities.join(', ')}</dd>
            </>
          )}
        </dl>
      </header>

      <div className="print-body">
        <Markdown content={doc.content} />
      </div>

      <footer className="print-footer">
        Produced with {APP_NAME} {APP_VERSION} from the {doc.projectName} knowledge graph
        {date ? ` on ${date}` : ''}.
        {doc.classification ? ` Handle in accordance with the ${doc.classification} marking.` : ''}
      </footer>

      {doc.classification && (
        <div className="print-marking print-marking-bottom">{doc.classification}</div>
      )}
    </article>,
    container,
  );
}
