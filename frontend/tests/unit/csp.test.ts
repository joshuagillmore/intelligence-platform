import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { contentSecurityPolicy } from '../../next.config.mjs';

/**
 * The CSP's img-src is what stops a page from fetching adversary-hosted
 * images, so it must stay narrow; but it must also allow every tile and icon
 * host the geo view really loads, or the map goes blank. These tests read the
 * hosts straight out of GeoMap.tsx so a new basemap cannot drift past the
 * policy unnoticed.
 */
function directive(policy: string, name: string): string[] {
  const part = policy
    .split(';')
    .map((p) => p.trim())
    .find((p) => p.startsWith(`${name} `));
  return part ? part.split(/\s+/).slice(1) : [];
}

function hostAllowed(host: string, sources: string[]): boolean {
  return sources.some((src) => {
    const m = /^https:\/\/(.+)$/.exec(src);
    if (!m) return false;
    const pattern = m[1];
    if (pattern.startsWith('*.')) return host.endsWith(pattern.slice(1));
    return host === pattern;
  });
}

function geoMapImageHosts(): string[] {
  const src = fs.readFileSync(path.resolve(__dirname, '../../src/components/GeoMap.tsx'), 'utf8');
  const urls = [
    ...src.matchAll(/tileLayer\(\s*'(https:\/\/[^']+)'/g),
    ...src.matchAll(/(?:iconRetinaUrl|iconUrl|shadowUrl):\s*'(https:\/\/[^']+)'/g),
  ].map((m) => m[1]);
  // Leaflet's {s} placeholder is a subdomain letter; substitute one so the
  // host is concrete ("a.tile.openstreetmap.org").
  return urls.map((u) => new URL(u.replace('{s}', 'a').replace(/\{[a-z]\}/g, '0')).host);
}

describe('content security policy', () => {
  const policy = contentSecurityPolicy({ dev: false });

  it('forbids framing', () => {
    expect(directive(policy, 'frame-ancestors')).toEqual(["'none'"]);
  });

  it("allows same-origin, data: and blob: images", () => {
    const img = directive(policy, 'img-src');
    expect(img).toEqual(expect.arrayContaining(["'self'", 'data:', 'blob:']));
  });

  it('does not allow images from arbitrary hosts', () => {
    const img = directive(policy, 'img-src');
    expect(img).not.toContain('*');
    expect(img).not.toContain('https:');
    expect(hostAllowed('adversary.example', img)).toBe(false);
  });

  it('allows every tile and icon host GeoMap loads', () => {
    const hosts = geoMapImageHosts();
    // Four basemaps plus the three marker-icon URLs.
    expect(hosts.length).toBeGreaterThanOrEqual(7);
    const img = directive(policy, 'img-src');
    for (const host of hosts) {
      expect(hostAllowed(host, img), `${host} missing from img-src`).toBe(true);
    }
  });

  it('allows the Google Fonts stylesheet and font files layout.tsx loads', () => {
    expect(directive(policy, 'style-src')).toContain('https://fonts.googleapis.com');
    expect(directive(policy, 'font-src')).toContain('https://fonts.gstatic.com');
  });

  it("only allows 'unsafe-eval' in development", () => {
    expect(directive(policy, 'script-src')).not.toContain("'unsafe-eval'");
    expect(directive(contentSecurityPolicy({ dev: true }), 'script-src')).toContain("'unsafe-eval'");
  });

  it('adds an off-origin API to connect-src only when one is configured', () => {
    expect(directive(policy, 'connect-src')).toEqual(["'self'"]);
    const withApi = contentSecurityPolicy({ dev: false, apiUrl: 'https://api.example.org/base' });
    expect(directive(withApi, 'connect-src')).toContain('https://api.example.org');
  });
});
