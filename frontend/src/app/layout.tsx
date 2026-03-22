import type { Metadata } from "next";
import "./globals.css";
import { ProjectProvider } from '@/lib/ProjectContext';
import { NotificationProvider } from '@/components/NotificationProvider';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';
import StatusBar from '@/components/StatusBar';

export const metadata: Metadata = {
  title: "Intelligence Platform",
  description: "AI-powered intelligence analyst workbench",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-navy-900 text-gray-100 font-sans antialiased">
        <ProjectProvider>
          <NotificationProvider>
            <KeyboardShortcuts />
            {children}
            <StatusBar />
          </NotificationProvider>
        </ProjectProvider>
      </body>
    </html>
  );
}
