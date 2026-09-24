'use client';

import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface CurrencyBannerProps {
  message: string;
}

export default function CurrencyBanner({ message }: CurrencyBannerProps) {
  return (
    <div className="flex items-start gap-2.5 rounded-2xl border border-amber-200/90 dark:border-amber-800/80 bg-amber-50/90 dark:bg-amber-950/40 px-4 py-3 text-xs text-amber-900 dark:text-amber-200 my-2.5 shadow-xs">
      <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
      <div>
        <span className="font-semibold text-amber-800 dark:text-amber-300">Precedent &amp; Currency Notice: </span>
        <span>{message}</span>
      </div>
    </div>
  );
}
