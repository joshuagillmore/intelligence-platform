import type { Metadata } from "next";
import "./globals.css";
import { ProjectProvider } from '@/lib/ProjectContext';
import { NotificationProvider } from '@/components/NotificationProvider';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';
import StatusBar from '@/components/StatusBar';
import MobileHeader from '@/components/MobileHeader';
import MobileBottomNav from '@/components/MobileBottomNav';

export const metadata: Metadata = {
  title: "Intelligence Platform",
  description: "AI-powered intelligence analyst workbench",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-navy-900 text-gray-100 font-sans antialiased">
        <ProjectProvider>
          <NotificationProvider>
            <KeyboardShortcuts />
            <MobileHeader />
            {children}
            <StatusBar />
            <MobileBottomNav />
          </NotificationProvider>
        </ProjectProvider>
      </body>
    </html>
  );
}
