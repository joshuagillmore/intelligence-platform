'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi, watchlistApi } from '@/lib/api';

const navItems = [
  { name: 'Projects', href: '/', icon: 'folder_open' },
  { name: 'Collections', href: '/collections', icon: 'database' },
  { name: 'Data Sources', href: '/data-sources', icon: 'satellite_alt' },
  { name: 'Network Analysis', href: '/network', icon: 'hub' },
  { name: 'Geo-Intelligence', href: '/geo', icon: 'public' },
  { name: 'Cyber', href: '/cyber', icon: 'security' },
  { name: 'Products & Artefacts', href: '/products', icon: 'description' },
  { name: 'Admin', href: '/admin', icon: 'admin_panel_settings' },
];

const secondaryItems = [
  { name: 'Timeline', href: '/timeline', icon: 'timeline' },
  { name: 'Watchlist', href: '/watchlist', icon: 'star' },
  { name: 'LLM Hub', href: '/llm-hub', icon: 'smart_toy' },
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
    <aside className="w-56 bg-[#0e1321] border-r border-[#1a1f2e] flex flex-col h-screen fixed left-0 top-0 z-40">
      {/* Branding */}
      <div className="px-5 py-5 flex flex-col gap-0.5">
        <span className="text-[#adc6ff] font-black text-sm tracking-tight">SENTINEL</span>
        <span className="text-[10px] tracking-widest uppercase font-medium text-gray-500">V.2.4-ALPHA</span>
      </div>

      {/* Active Project */}
      {activeProject && (
        <div className="px-5 pb-3">
          <p className="text-[9px] text-gray-500 uppercase tracking-widest font-bold mb-0.5">Active Project</p>
          <p className="text-xs font-semibold text-gray-200 truncate">{activeProject.name}</p>
        </div>
      )}

      {/* Search */}
      <div className="px-4 pb-3">
        <div className="relative">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-sm">search</span>
          <input
            type="text"
            data-search-input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search... (Ctrl+K)"
            className="w-full bg-[#090e1c] border border-[#1a1f2e] rounded-sm pl-8 pr-3 py-1.5 text-[10px] text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-[#3b82f6] tracking-wide"
          />
        </div>
      </div>

      {/* Primary Navigation */}
      <nav className="flex-1 py-1 overflow-y-auto space-y-0.5">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider transition-colors ${
              isActive(item.href)
                ? 'bg-[#1a1f2e] text-[#adc6ff] border-l-2 border-[#3b82f6]'
                : 'text-gray-500 hover:text-gray-300 hover:bg-[#1a1f2e]/50'
            }`}
          >
            <span className={`material-symbols-outlined text-lg ${isActive(item.href) ? 'text-[#adc6ff]' : ''}`}>{item.icon}</span>
            <span className="flex-1 truncate">{item.name}</span>
            {item.name === 'Collections' && activeCollections > 0 && (
              <span className="w-2 h-2 rounded-full bg-[#3b82f6] animate-pulse" title={`${activeCollections} active task${activeCollections > 1 ? 's' : ''}`} />
            )}
          </Link>
        ))}

        {/* Divider */}
        <div className="mx-4 my-2 border-t border-[#1a1f2e]" />

        {secondaryItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-2 text-[10px] font-medium uppercase tracking-wider transition-colors ${
              isActive(item.href)
                ? 'bg-[#1a1f2e] text-[#adc6ff] border-l-2 border-[#3b82f6]'
                : 'text-gray-500 hover:text-gray-300 hover:bg-[#1a1f2e]/50'
            }`}
          >
            <span className={`material-symbols-outlined text-base ${isActive(item.href) ? 'text-[#adc6ff]' : ''}`}>{item.icon}</span>
            <span className="flex-1">{item.name}</span>
            {item.name === 'Watchlist' && watchlistCount > 0 && (
              <span className="min-w-[18px] h-[18px] rounded-full bg-[#3b82f6]/20 text-[#adc6ff] text-[9px] flex items-center justify-center font-bold">{watchlistCount}</span>
            )}
          </Link>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="mt-auto border-t border-[#1a1f2e] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
          <span className="text-[9px] tracking-widest text-gray-500 uppercase font-medium">System Nominal</span>
        </div>
      </div>
    </aside>
  );
}
