import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { APP_TITLE, APP_TAGLINE } from '@/lib/branding';
import { ProjectProvider } from '@/lib/ProjectContext';
import { NotificationProvider } from '@/components/NotificationProvider';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';
import StatusBar from '@/components/StatusBar';
import MobileHeader from '@/components/MobileHeader';
import MobileBottomNav from '@/components/MobileBottomNav';

// Self-hosted via next/font (no render-blocking Google CDN request). The
// Material Symbols icon font is still loaded via <link> below — see globals.css.
const inter = Inter({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-inter',
  display: 'swap',
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: APP_TITLE,
  description: `AI-powered ${APP_TAGLINE.toLowerCase()}`,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        {/* Material Symbols is a variable-axis icon font (ligatures + FILL/wght axes); next/font doesn't handle it cleanly, so it stays a <link>. */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
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
