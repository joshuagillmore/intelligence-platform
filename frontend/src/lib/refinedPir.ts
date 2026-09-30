/**
 * Pull the refined PIR out of a model's free-prose refinement.
 *
 * The refined requirement is whatever follows a label such as "Refined PIR:",
 * "Proposed refined PIR is:", "Revised version:", in any of the shapes models
 * produce: bolded, numbered, a heading with the value on the next line, a table
 * row, or mid-sentence. Returns null when there is no such label; the caller
 * then keeps the analyst's own text rather than guessing.
 */

// "refined PIR", "proposed refined PIR", "revised version (of the PIR)",
// "improved requirement", "suggested PIR".
const LABEL =
  '(?:refined|revised|improved|proposed|suggested)(?:\\s+(?:refined|revised))?\\s+' +
  '(?:pir|version(?:\\s+of\\s+the\\s+pir)?|requirement|question)';

// Label then a colon (optionally "is:" / "would be:"), value after it.
const INLINE = new RegExp(`\\b${LABEL}(?:\\s+(?:is|would\\s+be|reads))?\\s*[:\\u2014\\u2013]\\s*(.*)$`, 'i');
// A line that is only the label (a heading); the value is on the next line.
const HEADING = new RegExp(`^(?:the\\s+)?${LABEL}\\s*:?$`, 'i');

const QUOTES = /^["'“”‘’]+|["'“”‘’]+$/g;

/** Strip markdown dressing from one line: headings, quotes, list markers,
 *  numbering, emphasis and code marks. Table pipes are handled separately. */
function normalise(line: string): string {
  return line
    .replace(/^\s*(?:#{1,6}\s+|>\s*)+/, '')
    .replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/, '')
    .replace(/[*_`]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/** The value itself: quotes removed, and cut at the closing quote when the
 *  sentence carries on after it. */
function cleanValue(raw: string): string {
  let value = normalise(raw);
  const open = value.match(/^["“‘']/);
  if (open) {
    const close = open[0] === '“' ? '”' : open[0] === '‘' ? '’' : open[0];
    const end = value.indexOf(close, 1);
    if (end > 0) value = value.slice(1, end);
  }
  return value.replace(QUOTES, '').trim();
}

function tableCells(line: string): string[] | null {
  if (!line.trim().startsWith('|')) return null;
  return line.split('|').slice(1, -1).map((c) => normalise(c));
}

export function extractRefinedPir(text: string): string | null {
  if (!text) return null;
  const lines = text.split(/\r?\n/);
  const labelOnly = new RegExp(`^${LABEL}$`, 'i');

  for (let i = 0; i < lines.length; i++) {
    const cells = tableCells(lines[i]);
    if (cells) {
      // | Refined PIR | <value> |
      const at = cells.findIndex((c) => labelOnly.test(c.replace(/:$/, '')));
      if (at >= 0 && cells[at + 1]) {
        const value = cleanValue(cells[at + 1]);
        if (value) return value;
      }
      continue;
    }

    const line = normalise(lines[i]);
    if (!line) continue;

    const inline = line.match(INLINE);
    if (inline) {
      const value = cleanValue(inline[1]);
      if (value) return value;
      // "Refined PIR:" with nothing after it: the value is on the next line.
    }
    if (inline || HEADING.test(line)) {
      for (let j = i + 1; j < lines.length; j++) {
        const next = cleanValue(lines[j]);
        if (next) return next;
      }
    }
  }
  return null;
}
