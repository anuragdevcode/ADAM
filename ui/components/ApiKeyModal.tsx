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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white w-full max-w-md rounded-2xl border border-gray-100 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-purple-50/50 to-white">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center text-purple-700">
              <Key className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">Google Gemini API Key</h3>
              <p className="text-[11px] text-gray-500">Cloud Models & Multimodal Voice</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleVerifyAndSave} className="p-6 space-y-4">
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-gray-700">
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
                className="w-full px-3.5 py-2.5 pr-10 text-xs font-mono rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-600 bg-gray-50/50"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Feedback messages */}
          {status === 'success' && (
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-start gap-2 text-xs">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 mt-0.5" />
              <span>{feedbackMessage}</span>
            </div>
          )}

          {status === 'error' && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-800 flex items-start gap-2 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
              <span>{feedbackMessage}</span>
            </div>
          )}

          {/* Security & Privacy Notice */}
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-[11px] text-slate-600 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <ShieldCheck className="w-3.5 h-3.5 text-purple-600" />
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
              className="text-[11px] text-purple-600 hover:text-purple-700 font-medium inline-flex items-center gap-1"
            >
              Get Gemini API Key <ExternalLink className="w-3 h-3" />
            </a>

            {currentKey && (
              <button
                type="button"
                onClick={handleClear}
                className="text-[11px] text-red-600 hover:text-red-700 font-medium"
              >
                Remove Key
              </button>
            )}
          </div>

          {/* Footer Actions */}
          <div className="pt-2 flex items-center justify-end gap-2 border-t border-gray-100">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-2 rounded-xl text-xs font-semibold text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isValidating}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 inline-flex items-center gap-1.5 shadow-sm transition-all"
            >
              {isValidating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Verifying...</span>
                </>
              ) : (
                <span>Verify & Save</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
