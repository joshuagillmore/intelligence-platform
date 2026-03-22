'use client';
import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { useNotifications, useNotificationCount } from '@/components/NotificationProvider';

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

export default function MobileHeader() {
  const router = useRouter();
  const { activeProject } = useProject();
  const { notifications, removeNotification } = useNotifications();
  const unreadCount = useNotificationCount();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const notifRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (showSearch && searchRef.current) searchRef.current.focus();
  }, [showSearch]);

  function handleSearch(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setSearchQuery('');
      setShowSearch(false);
    }
  }

  return (
    <header className="fixed top-0 w-full z-50 bg-[#0e1321] border-b border-white/5 md:hidden">
      <div className="flex items-center justify-between px-4 h-14">
        <div className="flex items-center gap-2.5">
          <span className="material-symbols-outlined text-[#3b82f6] text-xl">radar</span>
          <span className="text-[#3b82f6] font-black text-base tracking-tighter">SENTINEL_INTEL</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSearch(!showSearch)}
            className="p-2 rounded-full hover:bg-white/5 transition-colors"
          >
            <span className="material-symbols-outlined text-gray-500 text-xl">search</span>
          </button>
          <div className="relative" ref={notifRef}>
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="p-2 rounded-full hover:bg-white/5 transition-colors relative"
            >
              <span className="material-symbols-outlined text-gray-400 text-xl">notifications</span>
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-[8px] font-bold rounded-full flex items-center justify-center">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>
            {showNotifications && (
              <div className="absolute right-0 top-full mt-1 w-72 bg-[#0e1321] border border-[#1a1f2e] rounded-lg shadow-xl z-50 max-h-72 overflow-y-auto">
                <div className="px-3 py-2 border-b border-[#1a1f2e] flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-300">Notifications</span>
                </div>
                {notifications.length === 0 ? (
                  <div className="px-3 py-6 text-center text-xs text-gray-500">No notifications</div>
                ) : (
                  notifications.slice(0, 10).map(n => (
                    <div key={n.id} className="px-3 py-2 border-b border-[#1a1f2e]/50 hover:bg-[#1a1f2e]/50">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[11px] font-medium text-gray-200 truncate">{n.title}</span>
                        <button onClick={() => removeNotification(n.id)} className="text-gray-600 text-[10px]">&times;</button>
                      </div>
                      <p className="text-[10px] text-gray-500 mt-0.5">{n.message}</p>
                      <p className="text-[9px] text-gray-600 mt-0.5" suppressHydrationWarning>{formatTimeAgo(n.timestamp)}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      {/* Search bar slide-down */}
      {showSearch && (
        <div className="px-4 pb-3">
          <input
            ref={searchRef}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={handleSearch}
            placeholder={activeProject ? `Search ${activeProject.name}...` : 'Search...'}
            className="w-full bg-[#090e1c] border border-[#1a1f2e] rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-[#3b82f6]"
          />
        </div>
      )}
    </header>
  );
}
