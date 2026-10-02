import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { APP_TITLE, APP_TAGLINE } from '@/lib/branding';
import { ProjectProvider } from '@/lib/ProjectContext';
import { SessionProvider } from '@/lib/SessionContext';
import { AssistantProvider } from '@/lib/AssistantContext';
import { NotificationProvider } from '@/components/NotificationProvider';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';
import StatusBar from '@/components/StatusBar';
import MobileHeader from '@/components/MobileHeader';
import MobileBottomNav from '@/components/MobileBottomNav';
import AssistantPanel from '@/components/AssistantPanel';

// Vendored font files (OFL; licences beside them in ./fonts). `next/font/google`
// downloaded these from Google at build time, so a build failed whenever the
// runner could not reach fonts.googleapis.com (seen in CI as a null parse in
// next/font's loader). Local files make the build deterministic. The Material
// Symbols icon font is still loaded via <link> below — see globals.css.
const inter = localFont({
  src: './fonts/InterVariable.woff2',
  weight: '100 900',
  variable: '--font-inter',
  display: 'swap',
});
const jetbrainsMono = localFont({
  src: [
    { path: './fonts/JetBrainsMono-Regular.woff2', weight: '400', style: 'normal' },
    { path: './fonts/JetBrainsMono-Medium.woff2', weight: '500', style: 'normal' },
  ],
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
        {/* SessionProvider asks /api/auth/me on load: the sign-in gate for
            every view, and the identity the sidebar and nav show. */}
        <SessionProvider>
          <ProjectProvider>
            <NotificationProvider>
              {/* AssistantProvider is inside NotificationProvider because the
                  assistant's "Save as Product" raises notifications, and inside
                  ProjectProvider because the thread is project-scoped. */}
              <AssistantProvider>
                <KeyboardShortcuts />
                <MobileHeader />
                {children}
                <StatusBar />
                <MobileBottomNav />
                {/* One assistant for all 13 views — see components/AssistantPanel. */}
                <AssistantPanel />
              </AssistantProvider>
            </NotificationProvider>
          </ProjectProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
