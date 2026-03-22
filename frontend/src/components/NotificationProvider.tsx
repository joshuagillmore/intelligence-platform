'use client';
import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface Notification {
  id: string;
  title: string;
  message: string;
  type: 'info' | 'success' | 'error' | 'processing';
  link?: string;
  timestamp: Date;
}

interface NotificationContextType {
  notifications: Notification[];
  addNotification: (n: Omit<Notification, 'id' | 'timestamp'>) => string;
  updateNotification: (id: string, updates: Partial<Notification>) => void;
  removeNotification: (id: string) => void;
}

const NotificationContext = createContext<NotificationContextType>({
  notifications: [],
  addNotification: () => '',
  updateNotification: () => {},
  removeNotification: () => {},
});

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addNotification = useCallback((n: Omit<Notification, 'id' | 'timestamp'>) => {
    const id = Math.random().toString(36).slice(2);
    setNotifications(prev => [{...n, id, timestamp: new Date()}, ...prev]);
    // Auto-remove non-processing notifications after 10s
    if (n.type !== 'processing') {
      setTimeout(() => setNotifications(prev => prev.filter(x => x.id !== id)), 10000);
    }
    return id;
  }, []);

  const updateNotification = useCallback((id: string, updates: Partial<Notification>) => {
    setNotifications(prev => prev.map(n => n.id === id ? {...n, ...updates} : n));
    // Auto-remove after update if success/error
    if (updates.type && updates.type !== 'processing') {
      setTimeout(() => setNotifications(prev => prev.filter(x => x.id !== id)), 10000);
    }
  }, []);

  const removeNotification = useCallback((id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  }, []);

  return (
    <NotificationContext.Provider value={{ notifications, addNotification, updateNotification, removeNotification }}>
      {children}
      {/* Notification Toast Area */}
      <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
        {notifications.map(n => (
          <div key={n.id} className={`rounded-lg border p-3 shadow-lg text-sm ${
            n.type === 'processing' ? 'bg-navy-800 border-accent-blue' :
            n.type === 'success' ? 'bg-navy-800 border-green-500' :
            n.type === 'error' ? 'bg-navy-800 border-red-500' :
            'bg-navy-800 border-navy-600'
          }`}>
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                {n.type === 'processing' && (
                  <div className="w-4 h-4 border-2 border-navy-600 border-t-accent-blue rounded-full animate-spin" />
                )}
                {n.type === 'success' && <span className="text-green-400">&#10003;</span>}
                {n.type === 'error' && <span className="text-red-400">&#10007;</span>}
                <span className="font-medium text-gray-200">{n.title}</span>
              </div>
              <button onClick={() => removeNotification(n.id)} className="text-gray-500 hover:text-gray-300 text-xs">&#10005;</button>
            </div>
            <p className="text-gray-400 text-xs mt-1">{n.message}</p>
            {n.link && (
              <a href={n.link} className="text-accent-blue text-xs hover:underline mt-1 inline-block">View result &rarr;</a>
            )}
          </div>
        ))}
      </div>
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  return useContext(NotificationContext);
}
