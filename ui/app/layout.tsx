import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ADAM — Uttarakhand Records AI Assistant',
  description: 'AI-powered search and Q&A for Uttarakhand Government Orders, circulars, and records.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} h-full bg-gray-100 antialiased`}>
        {children}
      </body>
    </html>
  );
}
