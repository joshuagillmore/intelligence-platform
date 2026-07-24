'use client';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const bottomTabs = [
  { name: 'Projects', href: '/', icon: 'folder_open', iconFilled: 'folder_open' },
  { name: 'Collections', href: '/collections', icon: 'database', iconFilled: 'database' },
  { name: 'Sources', href: '/data-sources', icon: 'satellite_alt', iconFilled: 'satellite_alt' },
  { name: 'Network', href: '/network', icon: 'hub', iconFilled: 'hub' },
];

type Pg = { name: string; href: string; icon: string; adminOnly?: boolean };

const allPages: Pg[] = [
  { name: 'Projects', href: '/', icon: 'folder_open' },
  { name: 'Collections', href: '/collections', icon: 'database' },
  { name: 'Collection Plans', href: '/collection-plans', icon: 'checklist' },
  { name: 'Data Sources', href: '/data-sources', icon: 'satellite_alt' },
  { name: 'Network Analysis', href: '/network', icon: 'hub' },
  { name: 'Geo-Intelligence', href: '/geo', icon: 'public' },
  { name: 'Cyber', href: '/cyber', icon: 'security' },
  { name: 'Products & Artefacts', href: '/products', icon: 'description' },
  { name: 'Timeline', href: '/timeline', icon: 'timeline' },
  { name: 'Watchlist', href: '/watchlist', icon: 'star' },
  { name: 'LLM Hub', href: '/llm-hub', icon: 'smart_toy', adminOnly: true },
  { name: 'Admin', href: '/admin', icon: 'admin_panel_settings', adminOnly: true },
];

export default function MobileBottomNav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [role, setRole] = useState('');
  useEffect(() => {
    if (typeof window !== 'undefined') setRole(localStorage.getItem('auth_role') || 'analyst');
  }, []);

  function isActive(href: string) {
    if (href === '/') return pathname === '/' || pathname.startsWith('/project/');
    return pathname === href || pathname.startsWith(href + '/');
  }

  // Close menu on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [menuOpen]);

  // Close menu on navigation
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <nav className="fixed bottom-0 left-0 w-full z-50 bg-[#0e1321]/95 backdrop-blur-xl border-t border-white/5 shadow-[0_-4px_24px_rgba(0,0,0,0.5)] md:hidden">
      {/* Hamburger menu overlay */}
      {menuOpen && (
        <div ref={menuRef} className="absolute bottom-full left-0 w-full bg-[#0e1321]/98 backdrop-blur-xl border-t border-white/10 rounded-t-2xl shadow-[0_-8px_32px_rgba(0,0,0,0.6)] max-h-[70vh] overflow-y-auto">
          <div className="px-4 pt-4 pb-2">
            <span className="text-[9px] font-bold text-gray-500 uppercase tracking-[0.2em]">All Pages</span>
          </div>
          <div className="px-2 pb-3 space-y-0.5">
            {allPages.filter(page => !page.adminOnly || role === 'admin').map(page => {
              const active = isActive(page.href);
              return (
                <Link
                  key={page.href}
                  href={page.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                    active
                      ? 'bg-accent-blue/10 text-accent-blue'
                      : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                  }`}
                >
                  <span
                    className="material-symbols-outlined text-lg"
                    style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
                  >
                    {page.icon}
                  </span>
                  <span className="text-xs font-medium tracking-wide">{page.name}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Bottom tab bar */}
      <div className="flex justify-around items-center px-2 pb-[env(safe-area-inset-bottom,8px)] pt-2">
        {/* Hamburger menu button */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={menuOpen}
          className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-xl transition-all active:scale-95 duration-150 ${
            menuOpen
              ? 'text-accent-blue bg-accent-blue/10'
              : 'text-gray-500 opacity-60 hover:text-blue-300'
          }`}
        >
          <span className="material-symbols-outlined text-[22px]" aria-hidden="true">
            {menuOpen ? 'close' : 'menu'}
          </span>
          <span className="text-[10px] font-medium tracking-wide mt-0.5">More</span>
        </button>

        {/* Main tabs */}
        {bottomTabs.map(tab => {
          const active = isActive(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-xl transition-all active:scale-95 duration-150 ${
                active
                  ? 'text-accent-blue bg-accent-blue/10'
                  : 'text-gray-500 opacity-60 hover:text-blue-300'
              }`}
            >
              <span
                className="material-symbols-outlined text-[22px]"
                style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
              >
                {active ? tab.iconFilled : tab.icon}
              </span>
              <span className="text-[10px] font-medium tracking-wide mt-0.5">{tab.name}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
