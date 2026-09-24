'use client';

import { useState } from 'react';
import { X, Globe, Key, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { registerProvider } from '@/lib/api';
import type { ProviderRegistrationResult } from '@/lib/types';

interface AddProviderModalProps {
  onClose: () => void;
  onRegistered?: (result: ProviderRegistrationResult) => void;
}

type RegistrationStep = 'form' | 'validating' | 'success' | 'error';

export default function AddProviderModal({ onClose, onRegistered }: AddProviderModalProps) {
  const [name, setName] = useState('');
  const [endpointUrl, setEndpointUrl] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [step, setStep] = useState<RegistrationStep>('form');
  const [errorMessage, setErrorMessage] = useState('');
  const [result, setResult] = useState<ProviderRegistrationResult | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStep('validating');
    setErrorMessage('');

    try {
      const res = await registerProvider(
        {
          name: name.trim(),
          endpoint_url: endpointUrl.trim(),
          display_name: displayName.trim() || undefined,
        },
        apiKey.trim() || null,
      );
      if (res) {
        setResult(res);
        setStep('success');
        onRegistered?.(res);
      } else {
        setErrorMessage('Registration failed. Please check the endpoint and try again.');
        setStep('error');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred.';
      const safeMsg = msg.replace(/key[:\s]+[A-Za-z0-9_\-]{8,}/gi, '[REDACTED]').slice(0, 300);
      setErrorMessage(safeMsg);
      setStep('error');
    }
  };

  const protocolLabel = (protocol: string) => {
    switch (protocol) {
      case 'openai_compatible': return 'OpenAI-Compatible API';
      case 'gemini_compatible': return 'Gemini-Compatible API';
      default: return 'Unknown Protocol';
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl w-full max-w-md mx-4 overflow-hidden animate-in zoom-in-95">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50">
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Add Remote API</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {step === 'form' && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Connect a remote LLM API. ADAM will validate the endpoint, detect the
                protocol, and run behavioural attestation before making models available.
              </p>

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">Provider Name *</label>
                <input
                  type="text"
                  required
                  maxLength={80}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. My LLM Server"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-800 dark:text-slate-100 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">Endpoint URL *</label>
                <input
                  type="url"
                  required
                  maxLength={500}
                  value={endpointUrl}
                  onChange={(e) => setEndpointUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-800 dark:text-slate-100 focus:outline-none focus:border-purple-500 font-mono"
                />
                <p className="text-[10px] text-slate-400">Must be a public HTTPS endpoint. Private IPs are blocked.</p>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">Display Name (optional)</label>
                <input
                  type="text"
                  maxLength={80}
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g. Production LLM"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-800 dark:text-slate-100 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <Key className="inline w-3 h-3 mr-1 text-slate-400" />
                  API Key (optional)
                </label>
                <input
                  type="password"
                  maxLength={512}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-800 dark:text-slate-100 focus:outline-none focus:border-purple-500 font-mono"
                  autoComplete="off"
                />
                <p className="text-[10px] text-slate-400">
                  Sent securely to the backend only. Never stored in the browser.
                </p>
              </div>

              <button
                type="submit"
                className="w-full py-2.5 px-4 bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-colors"
              >
                Validate &amp; Connect
              </button>
            </form>
          )}

          {step === 'validating' && (
            <div className="flex flex-col items-center gap-4 py-8">
              <Loader2 className="w-8 h-8 text-purple-600 animate-spin" />
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Validating endpoint…</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Checking SSRF safety, protocol, and authentication</p>
              </div>
            </div>
          )}

          {step === 'success' && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                <CheckCircle className="w-5 h-5" />
                <p className="text-sm font-semibold">Provider connected</p>
              </div>
              <div className="bg-slate-50 dark:bg-[#161d2d] border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Name</span>
                  <span className="font-semibold text-slate-900 dark:text-slate-100">{result.display_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Protocol</span>
                  <span className="font-semibold text-slate-900 dark:text-slate-100">{protocolLabel(result.protocol)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Status</span>
                  <span className={`font-semibold capitalize ${
                    result.status === 'active' ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'
                  }`}>{result.status}</span>
                </div>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Models from this provider will appear in the model dropdown after attestation.
              </p>
              <button
                type="button"
                onClick={onClose}
                className="w-full py-2.5 px-4 bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-colors"
              >
                Done
              </button>
            </div>
          )}

          {step === 'error' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                <AlertCircle className="w-5 h-5" />
                <p className="text-sm font-semibold">Connection Failed</p>
              </div>
              <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/60 rounded-xl text-xs text-rose-800 dark:text-rose-300">
                {errorMessage}
              </div>
              <button
                type="button"
                onClick={() => setStep('form')}
                className="w-full py-2.5 px-4 bg-slate-900 dark:bg-slate-700 hover:bg-slate-800 text-white text-xs font-semibold rounded-xl transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
