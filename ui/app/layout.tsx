import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-sans' });

export const metadata: Metadata = {
  title: 'ADAM — Uttarakhand Records AI Assistant',
  description:
    'AI-powered search and Q&A for Uttarakhand Government Orders, circulars, and records.',
};

/**
 * Applies the stored theme before first paint so the page never flashes light
 * on the way to dark. Kept inline and dependency-free for that reason.
 */
const themeBootstrap = `(function(){try{var t=localStorage.getItem('adam-theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);}else if(window.matchMedia('(prefers-color-scheme: dark)').matches){document.documentElement.setAttribute('data-theme','dark');}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full ${inter.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className={`${inter.className} h-full bg-bg text-ink antialiased`}>{children}</body>
    </html>
  );
}
