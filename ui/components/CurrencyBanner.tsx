'use client';

import { AlertTriangle } from 'lucide-react';

interface CurrencyBannerProps {
  message: string;
}

export default function CurrencyBanner({ message }: CurrencyBannerProps) {
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-card border border-warn bg-warn-soft px-3.5 py-2.5 text-xs text-warn"
    >
      <AlertTriangle className="w-4 h-4 mt-px shrink-0" />
      <p className="leading-relaxed">
        <span className="font-semibold">Precedent &amp; currency notice: </span>
        {message}
      </p>
    </div>
  );
}
