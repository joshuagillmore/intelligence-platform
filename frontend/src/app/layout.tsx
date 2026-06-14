import type { Metadata } from "next";
import "./globals.css";
import { ProjectProvider } from '@/lib/ProjectContext';
import { NotificationProvider } from '@/components/NotificationProvider';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';
import { SentinelShell } from '@/components/sentinel';

export const metadata: Metadata = {
  title: "Sentinel — Intelligence Platform",
  description: "AI-powered intelligence analyst workbench",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
      </head>
      <body>
        <ProjectProvider>
          <NotificationProvider>
            <KeyboardShortcuts />
            <SentinelShell>{children}</SentinelShell>
          </NotificationProvider>
        </ProjectProvider>
      </body>
    </html>
  );
}
