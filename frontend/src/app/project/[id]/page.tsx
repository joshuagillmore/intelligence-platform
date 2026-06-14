'use client';

// Legacy route — replaced by the Sentinel Hub which renders the active-project
// masthead/dashboard. If anything navigates here (bookmarks, old links), set the
// project as active and bounce to the Hub.

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { projectsApi } from '@/lib/api';
import { useProject } from '@/lib/ProjectContext';

export default function LegacyProjectRedirect() {
  const params = useParams();
  const router = useRouter();
  const { setActiveProject } = useProject();

  useEffect(() => {
    const id = (params?.id as string) || '';
    if (!id) {
      router.replace('/');
      return;
    }
    let cancelled = false;
    projectsApi.get(id).then((res) => {
      if (cancelled) return;
      setActiveProject(res.data);
      router.replace('/');
    }).catch(() => {
      if (!cancelled) router.replace('/');
    });
    return () => { cancelled = true; };
  }, [params, router, setActiveProject]);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        fontFamily: 'var(--mono)',
        fontSize: 11,
        letterSpacing: '0.12em',
        color: 'var(--fg-3)',
      }}
    >
      OPENING PROJECT…
    </div>
  );
}
