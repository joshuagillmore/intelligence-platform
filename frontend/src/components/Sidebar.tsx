'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi, watchlistApi } from '@/lib/api';

const navItems = [
  { name: 'Projects', href: '/', icon: 'P' },
  { name: 'Collections', href: '/collections', icon: 'C' },
  { name: 'Data Sources', href: '/data-sources', icon: 'D' },
  { name: 'Network Analysis', href: '/network', icon: 'N' },
  { name: 'Timeline', href: '/timeline', icon: 'T' },
  { name: 'Watchlist', href: '/watchlist', icon: '\u2B50' },
  { name: 'Geo-Intelligence', href: '/geo', icon: 'G' },
  { name: 'Cyber', href: '/cyber', icon: 'S' },
  { name: 'Products', href: '/products', icon: 'R' },
  { name: 'LLM Hub', href: '/llm-hub', icon: 'L' },
  { name: 'Admin', href: '/admin', icon: 'A' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { activeProject } = useProject();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCollections, setActiveCollections] = useState(0);
  const [watchlistCount, setWatchlistCount] = useState(0);

  useEffect(() => {
    async function fetchBadges() {
      try {
        const colRes = await collectionsApi.list();
        const active = (colRes.data || []).filter((c: { status?: string }) => {
          const s = c.status?.toUpperCase();
          return s === 'PENDING' || s === 'STARTED' || s === 'PROGRESS' || s === 'RUNNING';
        });
        setActiveCollections(active.length);
      } catch { /* ignore */ }

      if (activeProject) {
        try {
          const wRes = await watchlistApi.list(activeProject.id);
          const items = wRes.data?.items || wRes.data || [];
          setWatchlistCount(Array.isArray(items) ? items.length : 0);
        } catch { /* ignore */ }
      }
    }
    fetchBadges();
    const interval = setInterval(fetchBadges, 30000);
    return () => clearInterval(interval);
  }, [activeProject]);

  const isActive = (href: string) => {
    if (href === '/' && (pathname === '/' || pathname.startsWith('/project/'))) return true;
    return pathname === href || pathname.startsWith(href + '/');
  };

  function handleSearchKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setSearchQuery('');
    }
  }

  return (
    <aside className="w-56 bg-navy-800 border-r border-navy-600 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-4 border-b border-navy-600">
        <h1 className="text-lg font-bold text-accent-blue">Intel Platform</h1>
        <p className="text-xs text-gray-500 mt-1">Analyst Workbench</p>
      </div>
      <div className="px-4 py-2 border-b border-navy-600">
        <p className="text-xs text-gray-500">Active Project</p>
        <p className="text-sm font-medium text-gray-200 truncate">
          {activeProject ? activeProject.name : 'No project selected'}
        </p>
      </div>
      <div className="px-4 py-2 border-b border-navy-600">
        <input
          type="text"
          data-search-input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder="Search... (Ctrl+K)"
          className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue"
        />
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
              isActive(item.href)
                ? 'bg-navy-700 text-accent-blue border-r-2 border-accent-blue'
                : 'text-gray-400 hover:text-gray-200 hover:bg-navy-700'
            }`}
          >
            <span className="w-5 h-5 bg-navy-600 rounded text-xs flex items-center justify-center font-mono">{item.icon}</span>
            <span className="flex-1">{item.name}</span>
            {item.name === 'Collections' && activeCollections > 0 && (
              <span className="w-2 h-2 rounded-full bg-accent-blue animate-pulse" title={`${activeCollections} active task${activeCollections > 1 ? 's' : ''}`} />
            )}
            {item.name === 'Watchlist' && watchlistCount > 0 && (
              <span className="min-w-[18px] h-[18px] rounded-full bg-accent-blue/20 text-accent-blue text-[10px] flex items-center justify-center font-medium">{watchlistCount}</span>
            )}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
