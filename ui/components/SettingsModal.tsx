'use client';

import { useState, useEffect } from 'react';
import { X, Shield, User, Building2, Save, Check, Lock } from 'lucide-react';
import type { DepartmentItem } from '@/lib/types';
import { fetchUserPreferences, saveUserPreferences } from '@/lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
  onUpdateUserId: (id: string) => void;
  clearanceLevel: string;
  onUpdateClearanceLevel: (lvl: string) => void;
  departmentId: string;
  onUpdateDepartmentId: (dept: string) => void;
  departments: DepartmentItem[];
}

const CLEARANCE_LEVELS = [
  { id: 'PUBLIC', name: 'PUBLIC', desc: 'Standard public government gazettes & circulars' },
  { id: 'INTERNAL', name: 'INTERNAL', desc: 'Internal departmental working documents & draft orders' },
  { id: 'RESTRICTED', name: 'RESTRICTED', desc: 'Protected state financial ceilings & audit deliberations' },
  { id: 'CONFIDENTIAL', name: 'CONFIDENTIAL', desc: 'Confidential vigilance inquiry & high-sensitivity records' },
];

export default function SettingsModal({
  isOpen,
  onClose,
  userId,
  onUpdateUserId,
  clearanceLevel,
  onUpdateClearanceLevel,
  departmentId,
  onUpdateDepartmentId,
  departments,
}: SettingsModalProps) {
  const [tempUserId, setTempUserId] = useState(userId);
  const [optIn, setOptIn] = useState(false);
  const [languagePref, setLanguagePref] = useState('bilingual');
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    setTempUserId(userId);
    if (isOpen && userId) {
      fetchUserPreferences(userId).then((p) => {
        setOptIn(p.opt_in);
        if (p.preferences && typeof p.preferences.language === 'string') {
          setLanguagePref(p.preferences.language);
        }
      });
    }
  }, [isOpen, userId]);

  if (!isOpen) return null;

  const handleSave = async () => {
    onUpdateUserId(tempUserId);
    await saveUserPreferences(tempUserId, optIn, 'UI display language and response formatting', {
      language: languagePref,
      last_updated: new Date().toISOString(),
    });
    setSavedSuccess(true);
    setTimeout(() => {
      setSavedSuccess(false);
      onClose();
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-surface rounded-3xl border border-line shadow-2xl max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-line">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-brand-soft text-brand flex items-center justify-center">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-ink">Officer Context &amp; Security Governance</h2>
              <p className="text-[11px] text-ink-faint">Manage identity, classification clearance, and memory preferences</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-ink-faint hover:text-ink-secondary hover:bg-surface-sunken"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5 max-h-[75vh] overflow-y-auto">
          {/* Officer ID input */}
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-1.5 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-ink-faint" />
              <span>Officer User Identifier (X-User-Id)</span>
            </label>
            <input
              type="text"
              value={tempUserId}
              onChange={(e) => setTempUserId(e.target.value)}
              placeholder="e.g. officer_anurag_singh"
              className="w-full px-3.5 py-2 rounded-xl border border-line text-xs text-ink focus:border-brand-border focus:ring-1 focus:ring-brand outline-none"
            />
            <p className="text-[10px] text-ink-faint mt-1">
              Controls access audits and private conversation session ownership.
            </p>
          </div>

          {/* Department Assignment */}
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-1.5 flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5 text-ink-faint" />
              <span>Department Assignment (X-Department-Id)</span>
            </label>
            <select
              value={departmentId}
              onChange={(e) => onUpdateDepartmentId(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-line text-xs text-ink focus:border-brand-border outline-none bg-surface"
            >
              <option value="ALL">All State Departments (General Clearance)</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          {/* Clearance Level Radios */}
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-2 flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-ink-faint" />
              <span>Security Clearance Ceiling (X-Clearance-Level)</span>
            </label>
            <div className="space-y-2">
              {CLEARANCE_LEVELS.map((lvl) => {
                const isSelected = clearanceLevel === lvl.id;
                return (
                  <div
                    key={lvl.id}
                    onClick={() => onUpdateClearanceLevel(lvl.id)}
                    className={`flex items-start gap-3 p-3 rounded-2xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-brand-border bg-brand-soft/60 shadow-xs'
                        : 'border-line hover:border-line-strong bg-surface'
                    }`}
                  >
                    <div
                      className={`w-4 h-4 rounded-full border mt-0.5 flex items-center justify-center shrink-0 ${
                        isSelected ? 'border-brand bg-brand text-white' : 'border-line-strong'
                      }`}
                    >
                      {isSelected && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-ink">{lvl.name}</span>
                        {lvl.id !== 'PUBLIC' && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-warn-soft text-warn">
                            PROTECTED
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-ink-muted mt-0.5">{lvl.desc}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Persistent Preferences (Phase 05 Opt-In) */}
          <div className="pt-3 border-t border-line">
            <div className="flex items-center justify-between mb-2">
              <div>
                <span className="text-xs font-semibold text-ink">Encrypted Preference Storage</span>
                <p className="text-[10px] text-ink-faint">Explicit opt-in under governance standards</p>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <div
                  onClick={() => setOptIn(!optIn)}
                  className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 ${
                    optIn ? 'bg-brand' : 'bg-surface-sunken'
                  }`}
                >
                  <div
                    className={`w-4 h-4 rounded-full bg-surface shadow-xs transition-transform ${
                      optIn ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </div>
              </label>
            </div>

            {optIn && (
              <div className="mt-3 p-3 rounded-2xl bg-surface-subtle border border-line/60 space-y-2">
                <label className="block text-[11px] font-medium text-ink-secondary">Response Linguistic Register</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: 'hi', name: 'Hindi' },
                    { id: 'en', name: 'English' },
                    { id: 'bilingual', name: 'Bilingual' },
                  ].map((lang) => (
                    <button
                      key={lang.id}
                      type="button"
                      onClick={() => setLanguagePref(lang.id)}
                      className={`py-1.5 text-xs rounded-xl border text-center transition-all ${
                        languagePref === lang.id
                          ? 'border-brand-border bg-brand-soft text-brand font-semibold'
                          : 'border-line bg-surface text-ink-secondary'
                      }`}
                    >
                      {lang.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-line bg-surface-subtle flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-ink-muted hover:text-ink transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand hover:bg-brand-hover text-white text-xs font-semibold shadow-xs transition-all"
          >
            {savedSuccess ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
            <span>{savedSuccess ? 'Saved!' : 'Save Changes'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
