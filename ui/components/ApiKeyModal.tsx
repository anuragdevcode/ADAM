'use client';

import { useState, useEffect } from 'react';
import { Key, Eye, EyeOff, CheckCircle2, AlertCircle, Loader2, ExternalLink, ShieldCheck, X } from 'lucide-react';
import { validateGeminiKey } from '@/lib/api';

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onKeySaved: (key: string) => void;
  onKeyCleared: () => void;
  currentKey: string | null;
}

export default function ApiKeyModal({
  isOpen,
  onClose,
  onKeySaved,
  onKeyCleared,
  currentKey,
}: ApiKeyModalProps) {
  const [keyValue, setKeyValue] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [feedbackMessage, setFeedbackMessage] = useState('');

  useEffect(() => {
    if (isOpen) {
      setKeyValue(currentKey || '');
      setStatus('idle');
      setFeedbackMessage('');
    }
  }, [isOpen, currentKey]);

  if (!isOpen) return null;

  const handleVerifyAndSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanKey = keyValue.trim();
    if (!cleanKey) {
      setStatus('error');
      setFeedbackMessage('Please enter an API key.');
      return;
    }

    setIsValidating(true);
    setStatus('idle');
    setFeedbackMessage('');

    try {
      const res = await validateGeminiKey(cleanKey);
      if (res.valid) {
        setStatus('success');
        setFeedbackMessage(res.message || 'Key verified successfully!');
        onKeySaved(cleanKey);
        setTimeout(() => {
          onClose();
        }, 1200);
      } else {
        setStatus('error');
        setFeedbackMessage(res.message || 'API key validation failed. Please verify the key in Google AI Studio.');
      }
    } catch (err) {
      setStatus('error');
      setFeedbackMessage(`Error verifying key: ${err}`);
    } finally {
      setIsValidating(false);
    }
  };

  const handleClear = () => {
    setKeyValue('');
    setStatus('idle');
    setFeedbackMessage('');
    onKeyCleared();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white dark:bg-[#111726] w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden animate-in zoom-in-95">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-[#131b2c]/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-purple-100 dark:bg-purple-950/60 flex items-center justify-center text-purple-700 dark:text-purple-300">
              <Key className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">Google Gemini API Key</h3>
              <p className="text-[11px] text-slate-400 dark:text-slate-500">Cloud Models &amp; Multimodal Voice</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleVerifyAndSave} className="p-6 space-y-4">
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
              API Key (Google AI Studio)
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="AIzaSy..."
                autoComplete="off"
                spellCheck="false"
                className="w-full px-3.5 py-2.5 pr-10 text-xs font-mono rounded-xl border border-slate-200 dark:border-slate-800 focus:outline-none focus:border-purple-600 bg-white dark:bg-[#131926] text-slate-800 dark:text-slate-100"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Feedback messages */}
          {status === 'success' && (
            <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 flex items-start gap-2 text-xs">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
              <span>{feedbackMessage}</span>
            </div>
          )}

          {status === 'error' && (
            <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-300 flex items-start gap-2 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
              <span>{feedbackMessage}</span>
            </div>
          )}

          {/* Security & Privacy Notice */}
          <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#161d2d] border border-slate-200 dark:border-slate-800 text-[11px] text-slate-600 dark:text-slate-400 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
              <ShieldCheck className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
              <span>Local Security Guarantee</span>
            </div>
            <p className="leading-relaxed">
              Your key is saved locally in your browser storage and sent strictly via request headers to your local ADAM server. It is never logged in database records or shared.
            </p>
          </div>

          <div className="flex items-center justify-between pt-1">
            <a
              href="https://aistudio.google.com/app/apikey"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300 font-semibold inline-flex items-center gap-1"
            >
              Get Gemini API Key <ExternalLink className="w-3 h-3" />
            </a>

            {currentKey && (
              <button
                type="button"
                onClick={handleClear}
                className="text-[11px] text-rose-600 dark:text-rose-400 hover:underline font-semibold"
              >
                Remove Key
              </button>
            )}
          </div>

          {/* Footer Actions */}
          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isValidating}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 inline-flex items-center gap-1.5 shadow-xs transition-all"
            >
              {isValidating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Verifying…</span>
                </>
              ) : (
                <span>Verify &amp; Save</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
