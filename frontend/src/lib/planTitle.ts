/** Render a requirement as a one-line title.
 *
 *  Plan names and PIR text come from model output, and model output is
 *  markdown. Titles stored before the backend started stripping it still carry
 *  it, so the plan lists show rows reading
 *  `** > **Refined PIR:** *From 1 January 2024 to the present…` and
 *  `(Actionable, Specific, Measurable, Time-bounded)** > **Priority
 *  Intelligence Requirement (PIR):**…`.
 *
 *  Those are unreadable as titles and identical to each other at a glance,
 *  which is the whole job of a title in a list. This is display-side only: it
 *  does not change what is stored, so it fixes rows already in the database
 *  as well as anything a future provider hands back.
 */

/** Leading structural markdown: heading hashes, blockquote arrows, list
 *  bullets — possibly several in a row, as `** > **` produces. */
const LEADING_MARKUP = /^[\s*_>#-]+/;
/** A bold or italic label the model prefixed, e.g. `**Refined PIR:**`. */
const LABEL_PREFIX = /^\*{1,2}[^*\n]{1,40}:\*{1,2}\s*/;
/** Emphasis runs anywhere in the line. */
const EMPHASIS = /\*{1,3}|_{2,}/g;
/** Single-underscore italics — `_Yi Peng 3_`. Bounded by non-word characters
 *  on both sides so `chunk_text` and other identifiers are left alone. Written
 *  with a capture rather than a lookbehind, which older Safari does not have. */
const ITALIC = /(^|[^A-Za-z0-9_])_([^_\n]{1,80})_(?![A-Za-z0-9_])/g;

/** Labels the model repeats before the actual requirement. Stripped so the
 *  list shows what distinguishes one plan from another, not the boilerplate
 *  every plan shares. */
const RESTATED_LABELS = [
  /^refined\s+pir:\s*/i,
  /^priority\s+intelligence\s+requirement\s*\(pir\):\s*/i,
  /^pir:\s*/i,
];

export function planTitle(raw: string | undefined | null, fallback = 'Untitled requirement'): string {
  if (!raw) return fallback;

  // Collapse to one line first: a title is one line, and the stored text is
  // often a whole markdown block.
  let out = String(raw).replace(/\s+/g, ' ').trim();

  // Alternate between stripping leading markup and a bold label, because the
  // damaged titles interleave them: `** > **Refined PIR:** *From…`.
  for (let i = 0; i < 4; i++) {
    const before = out;
    out = out.replace(LEADING_MARKUP, '');
    out = out.replace(LABEL_PREFIX, '');
    for (const label of RESTATED_LABELS) out = out.replace(label, '');
    if (out === before) break;
  }

  out = out.replace(EMPHASIS, '');
  out = out.replace(ITALIC, '$1$2').trim();
  // A stray closing bracket or colon left by the stripping above.
  out = out.replace(/^[\s:>*_-]+/, '').trim();

  return out || fallback;
}
