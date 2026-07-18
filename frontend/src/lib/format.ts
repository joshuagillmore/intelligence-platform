// Small display-formatting helpers.

/**
 * Convert a snake_case / kebab-case identifier into a human-readable Title Case
 * label for display, e.g. `report_writing` -> "Report Writing", `web_scrape` -> "Web Scrape".
 * The raw identifier should still be used as the key/value for API calls.
 */
export const humanize = (s: string): string =>
  (s || '').replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
