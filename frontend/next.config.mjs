/**
 * Hosts the browser is allowed to load images from, beyond this origin.
 *
 * Every entry is a tile or icon host `components/GeoMap.tsx` actually loads:
 * the three basemaps in its switcher (OpenStreetMap, OpenTopoMap, EOX
 * Sentinel-2) and Leaflet's default marker icons on cdnjs. Anything else
 * (image markdown in a scraped document, say) is refused by the browser, so a
 * page cannot be made to fetch from an adversary's server. Adding a basemap
 * means adding its host here, and dropping one means removing it;
 * `tests/unit/csp.test.ts` fails until you do either.
 */
const IMAGE_HOSTS = [
  'https://tile.openstreetmap.org',
  'https://*.tile.opentopomap.org',
  'https://tiles.maps.eox.at',
  'https://cdnjs.cloudflare.com',
];

/** The origin of `NEXT_PUBLIC_API_URL` when the API lives elsewhere, or ''. */
function apiOrigin(value) {
  if (!value) return '';
  try {
    return new URL(value).origin;
  } catch {
    return '';
  }
}

/**
 * The Content-Security-Policy sent with every page.
 *
 * Next 15's App Router hydrates through inline scripts and injects inline
 * styles (next/font, the dev overlay), so `script-src` and `style-src` need
 * 'unsafe-inline'; dev mode also needs 'unsafe-eval' for webpack's eval source
 * maps and a websocket for hot reload. The Material Symbols stylesheet and its
 * font files come from Google Fonts (`app/layout.tsx`).
 */
export function contentSecurityPolicy({ dev = false, apiUrl = '' } = {}) {
  const api = apiOrigin(apiUrl);
  const directives = {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'", ...(dev ? ["'unsafe-eval'"] : [])],
    'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
    'img-src': ["'self'", 'data:', 'blob:', ...IMAGE_HOSTS],
    'font-src': ["'self'", 'data:', 'https://fonts.gstatic.com'],
    'connect-src': ["'self'", ...(api ? [api] : []), ...(dev ? ['ws:', 'wss:'] : [])],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, values]) => `${name} ${values.join(' ')}`)
    .join('; ');
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // The standalone image does not ship sharp, and every image here is a static
  // asset or a map tile, so there is nothing for the optimiser to do.
  images: { unoptimized: true },
  experimental: {
    proxyTimeout: 300000,
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: contentSecurityPolicy({
              dev: process.env.NODE_ENV !== 'production',
              apiUrl: process.env.NEXT_PUBLIC_API_URL,
            }),
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL || 'http://backend:8000'}/api/:path*`,
      },
      {
        source: '/health',
        destination: `${process.env.BACKEND_URL || 'http://backend:8000'}/health`,
      },
    ];
  },
};

export default nextConfig;
