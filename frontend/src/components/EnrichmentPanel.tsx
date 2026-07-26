/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { useState, useEffect } from 'react';
import { enrichmentApi } from '@/lib/api';
import { TYPE_ICON } from '@/lib/entityStyles';

const GEO_TYPES = [
  'Location', 'Country', 'City', 'Region', 'Province', 'Governorate',
  'District', 'Facility', 'Base', 'Port', 'Airbase', 'Embassy',
];
const ENRICHABLE_TYPES = ['IPAddress', 'Domain', 'Vulnerability', 'EmailAddress', ...GEO_TYPES];

interface Props {
  entityId: string;
  entityType: string;
  properties?: Record<string, any>;
  /** Called after a successful run so the parent can refetch the entity. */
  onEnriched?: () => void;
}

function parseJson(value: any): any {
  if (!value) return null;
  if (typeof value === 'object') return value;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function statusClass(status?: string): string {
  switch (status) {
    case 'ok':
      return 'bg-green-900/30 text-green-400';
    case 'cached':
      return 'bg-blue-900/30 text-blue-400';
    case 'timeout':
      return 'bg-yellow-900/30 text-yellow-400';
    case 'error':
      return 'bg-red-900/30 text-red-400';
    default:
      return 'bg-gray-800 text-gray-400';
  }
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-xs text-gray-300 mb-0.5">
      <span className="text-gray-400">{label}:</span> {value}
    </div>
  );
}

/**
 * Shared cyber-enrichment panel embedded in both the /network entity detail
 * panel and the /cyber IOC expand-row. Renders the enrichment fields already on
 * the node (asn/geo/dns/whois/cvss/KEV/certs) and an Investigate action.
 */
export default function EnrichmentPanel({ entityId, entityType, properties = {}, onEnriched }: Props) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Show enrichment the backend has already cached. Without this the panel only
  // ever populated from a fresh Investigate click, so a previously-enriched
  // observable still read "No enrichment yet" — the results were persisted and
  // served by GET /enrichment/entities/{id}, just never requested.
  // Declared before the early return below so hook order stays stable.
  useEffect(() => {
    if (!ENRICHABLE_TYPES.includes(entityType)) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await enrichmentApi.getCached(entityId);
        const cached = data?.cached;
        if (!cancelled && cached && Object.keys(cached).length > 0) setStatus(cached);
      } catch {
        /* nothing cached for this observable yet — leave the empty state */
      }
    })();
    return () => { cancelled = true; };
  }, [entityId, entityType]);

  if (!ENRICHABLE_TYPES.includes(entityType)) return null;

  const enriched = properties.enriched === true;
  const isGeo = GEO_TYPES.includes(entityType);
  const title = isGeo ? 'Geo Enrichment' : 'Cyber Enrichment';
  const actionVerb = isGeo ? 'Geolocate' : 'Investigate';

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const { data } = await enrichmentApi.investigate(entityId);
      setStatus(data?.providers || null);
      onEnriched?.();
    } catch {
      setError('Enrichment failed — check the collection egress and provider availability.');
    } finally {
      setBusy(false);
    }
  }

  const dns = parseJson(properties.dns_records);
  const geo = parseJson(properties.geolocation);
  const mx = parseJson(properties.mx_records);
  const kev = properties.known_exploited === true;
  const products: string[] = Array.isArray(properties.affected_products) ? properties.affected_products : [];
  const issuers: string[] = Array.isArray(properties.cert_issuers) ? properties.cert_issuers : [];

  return (
    <div className="mt-4 border-t border-navy-700 pt-4">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-semibold text-gray-200 flex items-center gap-1">
          <span>{TYPE_ICON[entityType] || (isGeo ? '📍' : '🔎')}</span> {title}
        </h4>
        <button
          onClick={run}
          disabled={busy}
          className="text-xs px-2 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-50"
        >
          {busy ? `${actionVerb}…` : enriched ? `Re-${actionVerb.toLowerCase()}` : actionVerb}
        </button>
      </div>

      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
      {!enriched && !status && (
        <p className="text-xs text-gray-400">
          {isGeo
            ? 'No geo data yet. Geolocate to resolve coordinates + admin hierarchy (country / province / county / city / neighbourhood / postal).'
            : 'No enrichment yet. Run Investigate to pull WHOIS / DNS / GeoIP / CVSS / KEV.'}
        </p>
      )}

      {kev && (
        <div className="mb-2 inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-400 font-semibold">
          ⚠ Known Exploited (CISA KEV)
          {properties.kev_date_added ? ` · ${properties.kev_date_added}` : ''}
        </div>
      )}
      {properties.cvss_score != null && (
        <Field
          label="CVSS"
          value={`${properties.cvss_score}${properties.severity ? ` (${properties.severity})` : ''}`}
        />
      )}
      {properties.description ? <Field label="Description" value={String(properties.description)} /> : null}
      {products.length > 0 && <Field label="Affected" value={products.slice(0, 8).join(', ')} />}

      {properties.asn ? <Field label="ASN" value={String(properties.asn)} /> : null}
      {geo && (
        <Field
          label="Location"
          value={
            [geo.city, geo.region, geo.country].filter(Boolean).join(', ') +
            (geo.org ? ` · ${geo.org}` : '')
          }
        />
      )}
      {properties.net_name ? <Field label="Netblock" value={String(properties.net_name)} /> : null}
      {properties.registrar ? <Field label="Registrar" value={String(properties.registrar)} /> : null}
      {properties.registrant ? <Field label="Registrant" value={String(properties.registrant)} /> : null}
      {properties.registration_date ? (
        <Field label="Registered" value={String(properties.registration_date)} />
      ) : null}
      {dns && (
        <div className="mt-1">
          <span className="text-xs text-gray-400">DNS</span>
          <div className="mt-0.5 space-y-0.5">
            {Object.entries(dns).map(([rtype, vals]) => (
              <div key={rtype} className="text-xs text-gray-300">
                <span className="text-cyan-400">{rtype}</span>:{' '}
                {(Array.isArray(vals) ? vals : [vals]).slice(0, 5).join(', ')}
              </div>
            ))}
          </div>
        </div>
      )}
      {issuers.length > 0 && <Field label="Cert issuers" value={issuers.slice(0, 3).join(' · ')} />}
      {properties.cert_san_count != null && (
        <Field label="Cert SANs" value={String(properties.cert_san_count)} />
      )}

      {/* Email */}
      {properties.disposable === true && (
        <div className="mb-2 inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-yellow-900/30 text-yellow-400 font-semibold">
          ⚠ Disposable / throwaway domain
        </div>
      )}
      {properties.email_domain ? <Field label="Email domain" value={String(properties.email_domain)} /> : null}
      {properties.email_domain != null && (
        <Field label="Accepts mail" value={properties.has_mx ? 'Yes (MX present)' : 'No MX record'} />
      )}
      {properties.email_domain != null && (
        <Field label="Gravatar" value={properties.gravatar ? 'present' : 'none'} />
      )}
      {Array.isArray(mx) && mx.length > 0 && <Field label="MX" value={mx.slice(0, 4).join(', ')} />}

      {/* Geography (Nominatim admin hierarchy) */}
      {properties.country ? <Field label="Country" value={String(properties.country)} /> : null}
      {properties.admin1 ? <Field label="State / Province" value={String(properties.admin1)} /> : null}
      {properties.admin2 ? <Field label="County / District" value={String(properties.admin2)} /> : null}
      {properties.city && properties.city !== properties.admin1 ? (
        <Field label="City" value={String(properties.city)} />
      ) : null}
      {properties.neighbourhood ? <Field label="Neighbourhood" value={String(properties.neighbourhood)} /> : null}
      {properties.postal_code ? <Field label="Postal" value={String(properties.postal_code)} /> : null}
      {isGeo && properties.latitude != null && properties.longitude != null ? (
        <Field
          label="Coords"
          value={`${Number(properties.latitude).toFixed(5)}, ${Number(properties.longitude).toFixed(5)}`}
        />
      ) : null}
      {isGeo && properties.mgrs ? <Field label="MGRS" value={String(properties.mgrs)} /> : null}

      {properties.enriched_at ? (
        <p className="text-[10px] text-gray-500 mt-2">Enriched {String(properties.enriched_at)}</p>
      ) : null}

      {status && (
        <div className="mt-2 flex flex-wrap gap-1">
          {Object.entries(status).map(([name, s]: [string, any]) => (
            <span key={name} className={`text-[10px] px-1.5 py-0.5 rounded ${statusClass(s?.status)}`}>
              {name}: {s?.status || '—'}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
