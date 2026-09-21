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
      // Backend returns sanitised error messages — safe to display
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred.';
      // Never display raw stack traces or credentials
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-purple-600" />
            <h2 className="text-sm font-semibold text-gray-900">Add Remote API</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {step === 'form' && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-xs text-gray-500">
                Connect a remote LLM API. ADAM will validate the endpoint, detect the
                protocol, and run behavioural attestation before making models available.
              </p>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-700">Provider Name *</label>
                <input
                  type="text"
                  required
                  maxLength={80}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. My LLM Server"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-700">Endpoint URL *</label>
                <input
                  type="url"
                  required
                  maxLength={500}
                  value={endpointUrl}
                  onChange={(e) => setEndpointUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 font-mono"
                />
                <p className="text-[10px] text-gray-400">Must be a public HTTPS endpoint. Private IPs are blocked.</p>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-700">Display Name (optional)</label>
                <input
                  type="text"
                  maxLength={80}
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g. Production LLM"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-700">
                  <Key className="inline w-3 h-3 mr-1 text-gray-400" />
                  API Key (optional)
                </label>
                <input
                  type="password"
                  maxLength={512}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 font-mono"
                  autoComplete="off"
                />
                <p className="text-[10px] text-gray-400">
                  Sent securely to the backend only. Never stored in the browser.
                </p>
              </div>

              <button
                type="submit"
                className="w-full py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-xl transition-colors"
              >
                Validate & Connect
              </button>
            </form>
          )}

          {step === 'validating' && (
            <div className="flex flex-col items-center gap-4 py-8">
              <Loader2 className="w-8 h-8 text-purple-600 animate-spin" />
              <div className="text-center">
                <p className="text-sm font-medium text-gray-900">Validating endpoint…</p>
                <p className="text-xs text-gray-500 mt-1">Checking SSRF safety, protocol, and authentication</p>
              </div>
            </div>
          )}

          {step === 'success' && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-green-700">
                <CheckCircle className="w-5 h-5" />
                <p className="text-sm font-semibold">Provider connected</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-4 space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">Name</span>
                  <span className="font-medium text-gray-900">{result.display_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Protocol</span>
                  <span className="font-medium text-gray-900">{protocolLabel(result.protocol)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Status</span>
                  <span className={`font-medium capitalize ${
                    result.status === 'active' ? 'text-green-700' : 'text-amber-600'
                  }`}>{result.status}</span>
                </div>
              </div>
              <p className="text-xs text-gray-500">
                Models from this provider will appear in the model dropdown after attestation.
              </p>
              <button
                type="button"
                onClick={onClose}
                className="w-full py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-xl transition-colors"
              >
                Done
              </button>
            </div>
          )}

          {step === 'error' && (
            <div className="space-y-4">
              <div className="flex items-start gap-2 text-red-700">
                <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold">Connection failed</p>
                  <p className="text-xs text-red-600 mt-1 break-words">{errorMessage}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setStep('form')}
                  className="flex-1 py-2 px-4 border border-gray-200 hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-xl transition-colors"
                >
                  Try again
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-xl transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
