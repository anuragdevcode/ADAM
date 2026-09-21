'use client';

import { AlertTriangle } from 'lucide-react';

interface CurrencyBannerProps {
  message: string;
}

export default function CurrencyBanner({ message }: CurrencyBannerProps) {
  return (
    <div className="flex items-start gap-2.5 rounded-2xl border border-amber-200/90 bg-amber-50/80 px-4 py-3 text-xs text-amber-900 my-2.5 shadow-sm backdrop-blur-sm">
      <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
      <div>
        <span className="font-semibold text-amber-800">Precedent & Currency Notice: </span>
        <span>{message}</span>
      </div>
    </div>
  );
}
