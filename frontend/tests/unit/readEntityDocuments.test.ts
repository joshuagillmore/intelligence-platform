import { describe, it, expect } from 'vitest';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { entitiesApi, readEntityDocuments } from '@/lib/api';

/**
 * The evidence chain reads one `GET /entities/{id}/documents` page (contract 6:
 * `{documents: [{id, name, url, source_doc_id, mention_count, passages:
 * [{text, offset}]}], count, total}`) instead of asking every document in the
 * project whether it mentions the entity.
 */
describe('readEntityDocuments', () => {
  const body = {
    documents: [
      {
        id: 'doc-1', name: 'Report A', url: 'https://example.org/a', source_doc_id: 'doc-1', mention_count: 3,
        passages: [{ text: 'APT-X used the loader', offset: 120 }, { text: 'APT-X again', offset: 900 }],
      },
      { id: 'doc-2', name: '', url: '', source_doc_id: 'doc-2', mention_count: 1, passages: [] },
    ],
    count: 2,
    total: 7,
  };

  it('reads the contract shape', () => {
    const page = readEntityDocuments(body);
    expect(page.total).toBe(7);
    expect(page.count).toBe(2);
    expect(page.documents[0]).toEqual(body.documents[0]);
  });

  it('names an unnamed document by its id', () => {
    expect(readEntityDocuments(body).documents[1].name).toBe('doc-2');
  });

  it('drops rows without an id and passages without text', () => {
    const page = readEntityDocuments({
      documents: [{ name: 'no id' }, { id: 'doc-3', passages: [{ offset: 1 }, { text: 'kept' }] }],
      count: 2,
      total: 2,
    });
    expect(page.documents.map((d) => d.id)).toEqual(['doc-3']);
    expect(page.documents[0].passages).toEqual([{ text: 'kept', offset: 0 }]);
    expect(page.documents[0].mention_count).toBe(0);
  });

  it('never reports a total below what it returned', () => {
    expect(readEntityDocuments({ documents: body.documents }).total).toBe(2);
  });

  it.each([null, [], { docs: [] }, { documents: 'x' }])('throws on %j instead of reading "no documents"', (bad) => {
    expect(() => readEntityDocuments(bad)).toThrow(/Unexpected entity documents response shape/);
  });
});

describe('entitiesApi.documents', () => {
  it('asks for one page of the entity\'s documents', async () => {
    let captured: InternalAxiosRequestConfig | undefined;
    const adapter: AxiosAdapter = async (config) => {
      captured = config;
      return { data: { documents: [], count: 0, total: 0 }, status: 200, statusText: 'OK', headers: {}, config };
    };
    // The adapter is per-instance config; route this one call through it.
    const { default: api } = await import('@/lib/api');
    const original = api.defaults.adapter;
    api.defaults.adapter = adapter;
    try {
      await entitiesApi.documents('ent-1', 50, 0);
    } finally {
      api.defaults.adapter = original;
    }
    expect(captured?.url).toBe('/entities/ent-1/documents');
    expect(captured?.params).toEqual({ limit: 50, offset: 0 });
  });
});
