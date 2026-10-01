'use client';

import React, { useEffect, useState } from 'react';
import { Shield, Sparkles } from 'lucide-react';

interface SovereignLoadingScreenProps {
  /** If true, the system has finished loading and is ready to fade out */
  isReady?: boolean;
  /** Invoked when fade-out animation completes and the component can unmount */
  onTransitionComplete?: () => void;
  /** Optional custom message */
  statusMessage?: string;
}

const PHASES = [
  { progress: 28, text: 'Initializing Sovereign Cryptographic Enclave...', subtext: 'सॉवरेन सुरक्षा एन्क्लेव सत्यापन...' },
  { progress: 64, text: 'Verifying Clearance & Audit Hash-Chains...', subtext: 'लेखा परीक्षा एवं अधिकार स्तर प्रमाणीकरण...' },
  { progress: 92, text: 'Synchronizing Uttarakhand State Gazettes & Models...', subtext: 'उत्तराखण्ड राज्य शासनादेश व मॉडल्स सिंक्रनाइज़...' },
  { progress: 100, text: 'Workstation Ready.', subtext: 'कार्यक्षेत्र तैयार।' },
];

export default function SovereignLoadingScreen({
  isReady = false,
  onTransitionComplete,
  statusMessage,
}: SovereignLoadingScreenProps) {
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [progress, setProgress] = useState(15);
  const [isExiting, setIsExiting] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  // Check reduced motion preference
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
      setPrefersReducedMotion(mediaQuery.matches);
      const listener = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
      mediaQuery.addEventListener('change', listener);
      return () => mediaQuery.removeEventListener('change', listener);
    }
  }, []);

  // Smooth progress advance
  useEffect(() => {
    if (isReady) {
      setProgress(100);
      setPhaseIndex(PHASES.length - 1);
      const exitTimer = setTimeout(() => {
        setIsExiting(true);
      }, prefersReducedMotion ? 50 : 250);

      const unmountTimer = setTimeout(() => {
        onTransitionComplete?.();
      }, prefersReducedMotion ? 200 : 650);

      return () => {
        clearTimeout(exitTimer);
        clearTimeout(unmountTimer);
      };
    }

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev < 90) {
          const next = prev + (prev < 40 ? 12 : prev < 70 ? 8 : 4);
          if (next >= 65 && phaseIndex < 2) setPhaseIndex(2);
          else if (next >= 30 && phaseIndex < 1) setPhaseIndex(1);
          return next;
        }
        return prev;
      });
    }, 400);

    return () => clearInterval(interval);
  }, [isReady, phaseIndex, onTransitionComplete, prefersReducedMotion]);

  const currentPhase = PHASES[phaseIndex] || PHASES[0];

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="ADAM Workstation is initializing"
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#f8fafc] dark:bg-[#090d16] text-[#0f172a] dark:text-[#f1f5f9] select-none transition-all ${
        prefersReducedMotion ? 'duration-150' : 'duration-500 ease-out'
      } ${
        isExiting
          ? 'opacity-0 scale-[1.02] pointer-events-none filter blur-[4px]'
          : 'opacity-100 scale-100'
      }`}
    >
      {/* Background ambient radial aura */}
      <div
        aria-hidden="true"
        className={`absolute w-[480px] h-[480px] rounded-full pointer-events-none transition-opacity duration-1000 ${
          prefersReducedMotion ? 'opacity-20' : 'opacity-40 animate-pulse'
        } bg-[radial-gradient(circle_at_center,rgba(168,85,247,0.18)_0%,rgba(124,58,237,0.06)_50%,transparent_70%)] dark:bg-[radial-gradient(circle_at_center,rgba(168,85,247,0.22)_0%,rgba(91,33,182,0.08)_50%,transparent_70%)]`}
      />

      {/* Main Center Content */}
      <div className="relative z-10 flex flex-col items-center max-w-sm px-6 text-center">
        {/* Optical Aperture & Sovereign Orb */}
        <div className="relative flex items-center justify-center mb-8">
          {/* Concentric Trust Radar Rings */}
          {!prefersReducedMotion && (
            <>
              <div className="absolute w-28 h-28 rounded-full border border-purple-400/20 dark:border-purple-500/20 animate-ping opacity-30" style={{ animationDuration: '3s' }} />
              <div className="absolute w-20 h-20 rounded-full border border-purple-500/30 dark:border-purple-400/30 animate-pulse" />
            </>
          )}

          {/* The Signature ADAM Sovereign 3D Orb */}
          <div className="sovereign-orb relative shadow-xl shadow-purple-500/20 transition-transform">
            <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent via-white/20 to-white/40 pointer-events-none" />
          </div>
        </div>

        {/* Brand Lockup */}
        <div className="space-y-1 mb-6">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold tracking-wider uppercase text-purple-700 dark:text-purple-300 bg-purple-100/80 dark:bg-purple-950/60 border border-purple-200/80 dark:border-purple-800/60 mb-1">
            <Shield className="w-3 h-3 text-purple-600 dark:text-purple-400" />
            <span>Sovereign Administrative Enclave</span>
          </div>

          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center justify-center gap-1.5">
            <span>ADAM</span>
            <span className="text-xs font-normal px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
              v0.1.0
            </span>
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Government of Uttarakhand · Public Records Intelligence
          </p>
        </div>

        {/* Fluid Progress Bar */}
        <div className="w-full bg-slate-200/70 dark:bg-slate-800/80 rounded-full h-1.5 overflow-hidden mb-3 p-0.5 border border-slate-300/40 dark:border-slate-700/50">
          <div
            className="h-full rounded-full bg-gradient-to-r from-purple-600 via-purple-500 to-indigo-500 transition-all duration-300 ease-out shadow-sm"
            style={{ width: `${Math.min(100, Math.max(8, progress))}%` }}
          />
        </div>

        {/* Phase Status Label */}
        <div className="min-h-[38px] flex flex-col items-center justify-center">
          <p className="text-xs font-medium text-slate-700 dark:text-slate-200 transition-all duration-200">
            {statusMessage || currentPhase.text}
          </p>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5 font-light">
            {currentPhase.subtext}
          </p>
        </div>

        {/* Discrete Security Footer Notice */}
        <div className="mt-8 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
          <Sparkles className="w-3 h-3 text-purple-500/70" />
          <span>Air-Gapped Sovereign Hardware · DPDP Act 2023 Verified</span>
        </div>
      </div>
    </div>
  );
}
