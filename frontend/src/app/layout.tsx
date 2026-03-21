import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Intelligence Platform",
  description: "AI-powered intelligence analyst workbench",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-navy-900 text-gray-100 font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
