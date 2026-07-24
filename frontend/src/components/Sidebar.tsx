'use client';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi, watchlistApi, healthApi } from '@/lib/api';
import { useNotifications, useNotificationCount } from '@/components/NotificationProvider';
import { APP_NAME, APP_VERSION } from '@/lib/branding';

type NavItem = { name: string; href: string; icon: string; adminOnly?: boolean };

const navItems: NavItem[] = [
  { name: 'Projects', href: '/', icon: 'folder_open' },
  { name: 'Collections', href: '/collections', icon: 'database' },
  { name: 'Collection Plans', href: '/collection-plans', icon: 'checklist' },
  { name: 'Data Sources', href: '/data-sources', icon: 'satellite_alt' },
  { name: 'Network Analysis', href: '/network', icon: 'hub' },
  { name: 'Geo-Intelligence', href: '/geo', icon: 'public' },
  { name: 'Cyber', href: '/cyber', icon: 'security' },
  { name: 'Products & Artefacts', href: '/products', icon: 'description' },
  { name: 'Admin', href: '/admin', icon: 'admin_panel_settings', adminOnly: true },
];

const secondaryItems: NavItem[] = [
  { name: 'Timeline', href: '/timeline', icon: 'timeline' },
  { name: 'Watchlist', href: '/watchlist', icon: 'star' },
  { name: 'LLM Hub', href: '/llm-hub', icon: 'smart_toy', adminOnly: true },
];

function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { activeProject } = useProject();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCollections, setActiveCollections] = useState(0);
  const [watchlistCount, setWatchlistCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const { notifications, removeNotification } = useNotifications();
  const unreadCount = useNotificationCount();

  const [username, setUsername] = useState('');
  const [role, setRole] = useState('');
  const [backendHealthy, setBackendHealthy] = useState(true);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setUsername(localStorage.getItem('auth_user') || '');
      setRole(localStorage.getItem('auth_role') || 'analyst');
    }
  }, []);

  // Reflect real backend health (mirrors StatusBar) instead of a hardcoded dot.
  useEffect(() => {
    let cancelled = false;
    async function checkHealth() {
      try {
        await healthApi.check();
        if (!cancelled) setBackendHealthy(true);
      } catch {
        if (!cancelled) setBackendHealthy(false);
      }
    }
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

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

  // Close dropdowns on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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

  function handleSignOut() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    localStorage.removeItem('auth_role');
    window.location.href = '/login';
  }

  const initials = username
    ? username.split(/\s+/).map(w => w.charAt(0).toUpperCase()).slice(0, 2).join('')
    : 'A';

  return (
    <aside className="w-56 bg-[#0e1321] border-r border-navy-800 flex-col h-screen fixed left-0 top-0 z-40 hidden md:flex">
      {/* Branding + Notification Bell */}
      <div className="px-5 py-5 flex items-start justify-between">
        <div className="flex flex-col gap-0.5">
          <span className="text-[#adc6ff] font-black text-sm tracking-tight">{APP_NAME}</span>
          <span className="text-[10px] tracking-widest uppercase font-medium text-gray-500">{APP_VERSION}</span>
        </div>
        {/* Notification Bell */}
        <div className="relative" ref={notifRef}>
          <button
            className="relative p-1.5 hover:bg-navy-800 rounded transition-colors mt-0.5"
            onClick={() => setShowNotifications(!showNotifications)}
            title="Notifications"
            aria-label="Notifications"
          >
            <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>
          {/* Notification Dropdown */}
          {showNotifications && (
            <div className="absolute left-0 top-full mt-1 w-72 bg-[#0e1321] border border-navy-800 rounded-lg shadow-xl z-50 max-h-80 overflow-y-auto">
              <div className="px-3 py-2 border-b border-navy-800 flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-300">Notifications</span>
                {notifications.length > 0 && (
                  <span className="text-[9px] text-gray-500">{notifications.length} item{notifications.length !== 1 ? 's' : ''}</span>
                )}
              </div>
              {notifications.length === 0 ? (
                <div className="px-3 py-6 text-center text-xs text-gray-500">No notifications</div>
              ) : (
                notifications.slice(0, 20).map(n => (
                  <div
                    key={n.id}
                    onClick={() => { if (n.link && typeof window !== 'undefined') window.location.href = n.link; }}
                    className={`px-3 py-2 border-b border-navy-800/50 hover:bg-navy-800/50 transition-colors ${n.link ? 'cursor-pointer' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {n.type === 'processing' && (
                          <div className="w-3 h-3 border-2 border-navy-800 border-t-accent-blue rounded-full animate-spin flex-shrink-0" />
                        )}
                        {n.type === 'success' && <span className="text-green-400 text-xs flex-shrink-0">&#10003;</span>}
                        {n.type === 'error' && <span className="text-red-400 text-xs flex-shrink-0">&#10007;</span>}
                        {n.type === 'info' && <span className="text-blue-400 text-xs flex-shrink-0">&#9432;</span>}
                        <span className="text-[11px] font-medium text-gray-200 truncate">{n.title}</span>
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); removeNotification(n.id); }} className="text-gray-600 hover:text-gray-400 text-[10px] flex-shrink-0" aria-label="Dismiss notification">&times;</button>
                    </div>
                    <p className="text-[10px] text-gray-500 mt-0.5 ml-4.5 line-clamp-2">{n.message}</p>
                    <p className="text-[9px] text-gray-600 mt-0.5 ml-4.5" suppressHydrationWarning>{formatTimeAgo(n.timestamp)}</p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
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
            aria-label="Search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search... (Ctrl+K)"
            className="w-full bg-[#090e1c] border border-navy-800 rounded-sm pl-8 pr-3 py-1.5 text-[10px] text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-accent-blue tracking-wide"
          />
        </div>
      </div>

      {/* Primary Navigation */}
      <nav aria-label="Primary" className="flex-1 py-1 overflow-y-auto space-y-0.5">
        {navItems.filter((item) => !item.adminOnly || role === 'admin').map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider transition-colors ${
              isActive(item.href)
                ? 'bg-navy-800 text-[#adc6ff] border-l-2 border-accent-blue'
                : 'text-gray-500 hover:text-gray-300 hover:bg-navy-800/50'
            }`}
          >
            <span className={`material-symbols-outlined text-lg ${isActive(item.href) ? 'text-[#adc6ff]' : ''}`}>{item.icon}</span>
            <span className="flex-1 truncate">{item.name}</span>
            {item.name === 'Collections' && activeCollections > 0 && (
              <span className="w-2 h-2 rounded-full bg-accent-blue animate-pulse" title={`${activeCollections} active task${activeCollections > 1 ? 's' : ''}`} />
            )}
          </Link>
        ))}

        {/* Divider */}
        <div className="mx-4 my-2 border-t border-navy-800" />

        {secondaryItems.filter((item) => !item.adminOnly || role === 'admin').map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-2 text-[10px] font-medium uppercase tracking-wider transition-colors ${
              isActive(item.href)
                ? 'bg-navy-800 text-[#adc6ff] border-l-2 border-accent-blue'
                : 'text-gray-500 hover:text-gray-300 hover:bg-navy-800/50'
            }`}
          >
            <span className={`material-symbols-outlined text-base ${isActive(item.href) ? 'text-[#adc6ff]' : ''}`}>{item.icon}</span>
            <span className="flex-1">{item.name}</span>
            {item.name === 'Watchlist' && watchlistCount > 0 && (
              <span className="min-w-[18px] h-[18px] rounded-full bg-accent-blue/20 text-[#adc6ff] text-[9px] flex items-center justify-center font-bold">{watchlistCount}</span>
            )}
          </Link>
        ))}
      </nav>

      {/* Bottom section - Analyst Avatar + Sign Out */}
      <div className="mt-auto border-t border-navy-800">
        {/* Analyst Avatar */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-800/50 transition-colors text-left"
          >
            <div className="w-8 h-8 rounded-full bg-accent-blue flex items-center justify-center text-white text-sm font-bold flex-shrink-0" suppressHydrationWarning>
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-200 truncate" suppressHydrationWarning>{username || 'Analyst'}</p>
              <p className="text-[10px] text-gray-500" suppressHydrationWarning>{role || 'analyst'}</p>
            </div>
            <svg className="w-3 h-3 text-gray-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
            </svg>
          </button>
          {/* User Dropdown Menu */}
          {showUserMenu && (
            <div className="absolute bottom-full left-0 w-full mb-1 bg-[#0e1321] border border-navy-800 rounded-lg shadow-xl z-50 overflow-hidden">
              <button
                className="w-full px-4 py-2.5 text-left text-xs text-gray-400 hover:bg-navy-800/50 transition-colors flex items-center gap-2"
                onClick={() => { setShowUserMenu(false); }}
              >
                <span className="material-symbols-outlined text-sm">settings</span>
                Profile Settings <span className="text-gray-600 text-[9px]">(coming soon)</span>
              </button>
              <div className="border-t border-navy-800" />
              <button
                onClick={handleSignOut}
                className="w-full px-4 py-2.5 text-left text-xs text-gray-400 hover:text-red-400 hover:bg-navy-800/50 transition-colors flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-sm">logout</span>
                Sign Out
              </button>
            </div>
          )}
        </div>

        {/* System Status — driven by the real backend health check */}
        <div className="px-4 py-2 border-t border-navy-800">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${backendHealthy ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-red-500'}`} />
            <span className="text-[9px] tracking-widest text-gray-500 uppercase font-medium">{backendHealthy ? 'Systems Nominal' : 'Backend Unreachable'}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
