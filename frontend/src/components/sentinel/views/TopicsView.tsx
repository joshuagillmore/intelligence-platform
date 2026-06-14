'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Btn, Icon, Tag } from '@/components/sentinel';
import { useProject } from '@/lib/ProjectContext';
import { topicsApi } from '@/lib/api';

interface TopicTreeNode {
  id?: string;
  name?: string;
  count?: number;
  children?: TopicTreeNode[];
}

export function TopicsView() {
  const router = useRouter();
  const { activeProject } = useProject();
  const [tree, setTree] = useState<TopicTreeNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!activeProject) { setTree(null); return; }
    setLoading(true);
    setErr(null);
    topicsApi
      .tree(activeProject.id, 'tfidf', 'medium')
      .then((res) => {
        const data = res.data as TopicTreeNode | null;
        setTree(data && typeof data === 'object' && 'children' in data ? data : null);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [activeProject]);

  const branchCount = tree?.children?.length ?? 0;
  const leafCount = (tree?.children ?? []).reduce((acc, b) => acc + (b.children?.length ?? 0), 0);
  const hasContent = branchCount > 0;

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1000, margin: '0 auto', padding: '24px 32px 48px' }}>
        <div style={{ paddingBottom: 16, borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-3)' }}>
              KNOWLEDGE BASE · TOPICS
            </span>
            {hasContent ? (
              <Tag tone="live">{leafCount} TOPIC{leafCount === 1 ? '' : 'S'}</Tag>
            ) : (
              <Tag tone="signal">PENDING</Tag>
            )}
          </div>
          <h1 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 34, fontWeight: 500, letterSpacing: '-0.015em', color: 'var(--ink)', lineHeight: 1.1 }}>
            {activeProject?.name || 'No project'}
            <span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          <p style={{ margin: '8px 0 0', maxWidth: 620, fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.55, color: 'var(--fg-2)' }}>
            Topic mindmap clustered from this project&rsquo;s document corpus.
          </p>
        </div>

        {!activeProject ? (
          <PendingPanel
            icon="hub"
            title="No active project"
            body="Open a project to see its topic tree."
          />
        ) : loading ? (
          <p style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)', letterSpacing: '0.08em' }}>LOADING…</p>
        ) : err || !hasContent ? (
          <PendingPanel
            icon="bolt"
            title={err ? 'Topic tree unavailable' : 'No topics extracted yet'}
            body={
              err
                ? `Backend returned: "${err}". The clustering pipeline may need to run on this project's documents first. The full mindmap experience (radial layout, summaries, drill-down) is available on the legacy /data-sources page.`
                : 'Ingest documents and run clustering to populate the topic mindmap. The legacy /data-sources page renders the full radial mindmap once topics exist.'
            }
            action={
              <Btn variant="signal" icon="arrow-right" size="sm" onClick={() => router.push('/data-sources')}>
                Open mindmap on /data-sources
              </Btn>
            }
          />
        ) : (
          <TopicTreeList tree={tree!} />
        )}
      </div>
    </div>
  );
}

function TopicTreeList({ tree }: { tree: TopicTreeNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {(tree.children ?? []).map((branch, i) => (
        <section
          key={branch.id || i}
          style={{
            padding: '14px 16px',
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
            <h2 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
              {branch.name || 'Untitled branch'}
            </h2>
            {typeof branch.count === 'number' && (
              <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.08em' }}>
                · {branch.count} entit{branch.count === 1 ? 'y' : 'ies'}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {(branch.children ?? []).map((leaf) => (
              <span
                key={leaf.id || leaf.name}
                style={{
                  padding: '3px 8px',
                  background: 'var(--paper)',
                  border: '1px solid var(--line)',
                  borderRadius: 2,
                  fontSize: 12,
                  color: 'var(--ink)',
                }}
              >
                {leaf.name}
              </span>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function PendingPanel({
  icon,
  title,
  body,
  action,
}: {
  icon: string;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      style={{
        padding: '36px 32px',
        background: 'var(--paper-2)',
        border: '1px dashed var(--line)',
        borderRadius: 4,
        display: 'flex',
        gap: 18,
        alignItems: 'flex-start',
      }}
    >
      <span
        style={{
          width: 40, height: 40, borderRadius: 4,
          background: 'var(--paper)', border: '1px solid var(--line)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--fg-2)', flexShrink: 0,
        }}
      >
        <Icon name={icon} size={20} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3 style={{ margin: '0 0 8px', fontFamily: 'var(--serif)', fontSize: 20, fontWeight: 500, color: 'var(--ink)' }}>
          {title}
        </h3>
        <p style={{ margin: '0 0 12px', fontSize: 13.5, lineHeight: 1.55, color: 'var(--fg-2)' }}>
          {body}
        </p>
        {action}
      </div>
    </div>
  );
}
