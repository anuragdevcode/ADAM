'use client';

import React, { useState } from 'react';
import {
  Shield,
  Lock,
  User,
  Eye,
  EyeOff,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Building2,
  FileText,
  Globe,
  Sun,
  Moon,
} from 'lucide-react';
import { useTheme } from './ThemeProvider';
import { loginUser, registerUser } from '@/lib/api';
import type { AuthUser } from '@/lib/types';

interface LoginPageProps {
  onLoginSuccess: (user: AuthUser, token?: string) => void;
  onContinueAsGuest: () => void;
}

type AuthMode = 'login' | 'register';

const DEMO_PRESETS = [
  {
    role: 'Secretariat Admin',
    badge: 'CONFIDENTIAL',
    badgeColor: 'bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 border-purple-200 dark:border-purple-800',
    username: 'admin',
    password: 'dev-admin-password-2026',
    dept: 'General Administration',
  },
  {
    role: 'Records Officer',
    badge: 'INTERNAL',
    badgeColor: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    username: 'officer_finance',
    password: 'officer-secure-pass-2026',
    dept: 'Finance & Treasury',
  },
  {
    role: 'Audit Directorate',
    badge: 'RESTRICTED',
    badgeColor: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border-amber-200 dark:border-amber-800',
    username: 'auditor_uk',
    password: 'auditor-secure-pass-2026',
    dept: 'Audit Directorate',
  },
];

const DEPARTMENTS = [
  { id: 'GENERAL_ADMIN', name: 'General Administration (GAD)' },
  { id: 'FINANCE_TREASURY', name: 'Finance & Treasury (eKosh)' },
  { id: 'RURAL_DEVELOPMENT', name: 'Rural Development (UKRD)' },
  { id: 'BOARD_OF_REVENUE', name: 'Board of Revenue (BOR)' },
  { id: 'AUDIT_DIRECTORATE', name: 'Audit Directorate' },
  { id: 'EDUCATION', name: 'School & Higher Education' },
];

export default function LoginPage({ onLoginSuccess, onContinueAsGuest }: LoginPageProps) {
  const { resolvedTheme, toggleTheme } = useTheme();

  const [mode, setMode] = useState<AuthMode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [departmentId, setDepartmentId] = useState('GENERAL_ADMIN');

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleApplyPreset = (preset: typeof DEMO_PRESETS[0]) => {
    setUsername(preset.username);
    setPassword(preset.password);
    setErrorMessage(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    const cleanUser = username.trim();
    if (!cleanUser) {
      setErrorMessage('Username is required.');
      return;
    }
    if (!password) {
      setErrorMessage('Password is required.');
      return;
    }

    setIsLoading(true);

    try {
      if (mode === 'login') {
        const res = await loginUser(cleanUser, password);
        if (res.ok && res.data) {
          setSuccessMessage('Authenticated successfully. Initializing workspace...');
          setTimeout(() => {
            onLoginSuccess(res.data!.user, res.data!.access_token);
          }, 350);
        } else {
          setErrorMessage(res.error || 'Invalid credentials or user does not exist.');
        }
      } else {
        // Registration
        if (cleanUser.length < 3) {
          setErrorMessage('Username must be at least 3 characters.');
          setIsLoading(false);
          return;
        }
        if (password.length < 8) {
          setErrorMessage('Password must be at least 8 characters long.');
          setIsLoading(false);
          return;
        }

        const res = await registerUser({
          username: cleanUser,
          password,
          full_name: fullName.trim(),
          email: email.trim() || undefined,
          department_id: departmentId,
        });

        if (res.ok && res.data) {
          setSuccessMessage('Account registered and verified. Entering workspace...');
          setTimeout(() => {
            onLoginSuccess(res.data!.user, res.data!.access_token);
          }, 400);
        } else {
          setErrorMessage(res.error || 'Registration failed.');
        }
      }
    } catch (err) {
      setErrorMessage(`Network error occurred (${err}). Please ensure the ADAM backend is running.`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex flex-col bg-[#f8fafc] dark:bg-[#090d16] text-[#0f172a] dark:text-[#f1f5f9] select-none transition-colors duration-150 relative overflow-y-auto">
      {/* Top Navbar */}
      <header className="w-full h-16 border-b border-slate-200/80 dark:border-slate-800/80 px-6 sm:px-10 flex items-center justify-between shrink-0 bg-white/70 dark:bg-[#0c111c]/70 backdrop-blur-md sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-radial-purple flex items-center justify-center shadow-xs sovereign-orb" style={{ width: 32, height: 32 }} />
          <div>
            <span className="font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-1.5 text-base">
              ADAM
              <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-950/80 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                Sovereign Workstation
              </span>
            </span>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 hidden sm:block">
              Government of Uttarakhand · लोक अभिलेख अभिसूचना प्रणाली
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Theme Toggle */}
          <button
            type="button"
            onClick={toggleTheme}
            className="w-9 h-9 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 border border-slate-200/80 dark:border-zinc-700/80 flex items-center justify-center shadow-xs transition-all"
            title={`Switch to ${resolvedTheme === 'dark' ? 'Light' : 'Dark'} Mode`}
            aria-label="Toggle Theme"
          >
            {resolvedTheme === 'dark' ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-slate-700" />
            )}
          </button>
        </div>
      </header>

      {/* Main Hero & Form Split Area */}
      <main className="flex-1 flex items-center justify-center p-4 sm:p-8 lg:p-12 relative z-10">
        {/* Ambient background glow */}
        <div
          aria-hidden="true"
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[720px] h-[720px] rounded-full pointer-events-none opacity-25 dark:opacity-35 bg-[radial-gradient(circle_at_center,rgba(147,51,234,0.18)_0%,rgba(124,58,237,0.06)_50%,transparent_70%)]"
        />

        <div className="w-full max-w-5xl bg-white dark:bg-[#0d1322] border border-slate-200/90 dark:border-slate-800/90 rounded-2xl shadow-xl shadow-slate-900/5 dark:shadow-black/40 overflow-hidden grid grid-cols-1 lg:grid-cols-12 relative z-20">
          
          {/* Left Column: Sovereign Enclave Showcase */}
          <div className="lg:col-span-5 p-8 sm:p-10 bg-slate-50/70 dark:bg-[#111728]/70 border-b lg:border-b-0 lg:border-r border-slate-200/80 dark:border-slate-800/80 flex flex-col justify-between relative overflow-hidden">
            <div>
              {/* Sovereign Badge */}
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider text-purple-700 dark:text-purple-300 bg-purple-100/90 dark:bg-purple-950/80 border border-purple-200 dark:border-purple-800/80 mb-6">
                <Shield className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                <span>State Enclave Security</span>
              </div>

              <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-3">
                Authoritative Government Intelligence
              </h2>

              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mb-8">
                Search, verify, and reason over official Uttarakhand Government Orders, gazette notifications, and departmental finance records with immutable provenance.
              </p>

              {/* Key Trust Pillars */}
              <div className="space-y-4 mb-8">
                <div className="flex items-start gap-3 text-xs">
                  <div className="w-6 h-6 rounded-lg bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0 mt-0.5 border border-purple-200/60 dark:border-purple-800/60">
                    <FileText className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <strong className="font-semibold text-slate-900 dark:text-slate-100 block">Strict Statutory Grounding</strong>
                    <span className="text-slate-500 dark:text-slate-400">Zero hallucinations — every response references exact page numbers and GO IDs.</span>
                  </div>
                </div>

                <div className="flex items-start gap-3 text-xs">
                  <div className="w-6 h-6 rounded-lg bg-blue-100 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0 mt-0.5 border border-blue-200/60 dark:border-blue-800/60">
                    <Lock className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <strong className="font-semibold text-slate-900 dark:text-slate-100 block">Multi-Tier Security Clearance</strong>
                    <span className="text-slate-500 dark:text-slate-400">Enforced ACL boundaries from Public notices to Confidential vigilance files.</span>
                  </div>
                </div>

                <div className="flex items-start gap-3 text-xs">
                  <div className="w-6 h-6 rounded-lg bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0 mt-0.5 border border-emerald-200/60 dark:border-emerald-800/60">
                    <Globe className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <strong className="font-semibold text-slate-900 dark:text-slate-100 block">Air-Gapped Sovereign Hardware</strong>
                    <span className="text-slate-500 dark:text-slate-400">Deployed directly within State Data Centre infrastructure with zero external egress.</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Demo Credentials Box */}
            <div className="pt-6 border-t border-slate-200 dark:border-slate-800">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block mb-2.5">
                Quick Enclave Sign-In (Pre-Seeded)
              </span>
              <div className="flex flex-wrap gap-2">
                {DEMO_PRESETS.map((preset) => (
                  <button
                    key={preset.username}
                    type="button"
                    onClick={() => handleApplyPreset(preset)}
                    className="px-2.5 py-1.5 rounded-lg bg-white dark:bg-slate-800/90 border border-slate-200 dark:border-slate-700/80 hover:border-purple-400 dark:hover:border-purple-500 text-left transition-all text-xs shadow-xs group"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-slate-800 dark:text-slate-200 group-hover:text-purple-600 dark:group-hover:text-purple-400">
                        {preset.role}
                      </span>
                      <span className={`text-[9px] px-1 py-0.2 rounded font-bold border ${preset.badgeColor}`}>
                        {preset.badge}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Authentication Form */}
          <div className="lg:col-span-7 p-8 sm:p-12 flex flex-col justify-center">
            {/* Mode Switcher Tabs */}
            <div className="flex items-center border-b border-slate-200 dark:border-slate-800 mb-8">
              <button
                type="button"
                onClick={() => {
                  setMode('login');
                  setErrorMessage(null);
                }}
                className={`pb-3 text-sm font-semibold transition-all relative ${
                  mode === 'login'
                    ? 'text-purple-600 dark:text-purple-400'
                    : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
              >
                Officer Sign In
                {mode === 'login' && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-600 dark:bg-purple-500 rounded-full" />
                )}
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode('register');
                  setErrorMessage(null);
                }}
                className={`pb-3 ml-6 text-sm font-semibold transition-all relative ${
                  mode === 'register'
                    ? 'text-purple-600 dark:text-purple-400'
                    : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
              >
                Register New User
                {mode === 'register' && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-600 dark:bg-purple-500 rounded-full" />
                )}
              </button>
            </div>

            {/* Error & Success Banners */}
            {errorMessage && (
              <div
                role="alert"
                className="mb-6 p-3.5 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 text-xs flex items-start gap-2.5 animate-in fade-in slide-in-from-top-1"
              >
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="font-semibold block">Authentication Notice</strong>
                  <span>{errorMessage}</span>
                </div>
              </div>
            )}

            {successMessage && (
              <div
                role="status"
                className="mb-6 p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/60 text-emerald-700 dark:text-emerald-300 text-xs flex items-start gap-2.5 animate-in fade-in slide-in-from-top-1"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="font-semibold block">Success</strong>
                  <span>{successMessage}</span>
                </div>
              </div>
            )}

            {/* Main Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Registration Specific Fields */}
              {mode === 'register' && (
                <>
                  <div>
                    <label
                      htmlFor="full-name-input"
                      className="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-1.5"
                    >
                      Full Official Name
                    </label>
                    <input
                      id="full-name-input"
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="e.g. Ramesh Chandra Pant"
                      className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700/80 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="email-input"
                      className="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-1.5"
                    >
                      Official Email (Optional)
                    </label>
                    <input
                      id="email-input"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="e.g. officer@uk.gov.in"
                      className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700/80 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="department-select"
                      className="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-1.5"
                    >
                      Department / Organization
                    </label>
                    <div className="relative">
                      <select
                        id="department-select"
                        value={departmentId}
                        onChange={(e) => setDepartmentId(e.target.value)}
                        className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700/80 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all appearance-none"
                      >
                        {DEPARTMENTS.map((dept) => (
                          <option key={dept.id} value={dept.id}>
                            {dept.name}
                          </option>
                        ))}
                      </select>
                      <Building2 className="w-4 h-4 text-slate-400 absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                  </div>
                </>
              )}

              {/* Username Input */}
              <div>
                <label
                  htmlFor="username-input"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-1.5"
                >
                  Username / Officer ID <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <input
                    id="username-input"
                    type="text"
                    required
                    autoFocus
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="e.g. admin or officer_name"
                    className="w-full pl-10 pr-3.5 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700/80 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all"
                  />
                  <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
              </div>

              {/* Password Input */}
              <div>
                <label
                  htmlFor="password-input"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-1.5"
                >
                  Password <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <input
                    id="password-input"
                    type={showPassword ? 'text' : 'password'}
                    required
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full pl-10 pr-10 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700/80 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all font-mono"
                  />
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 absolute right-3 top-1/2 -translate-y-1/2 rounded focus:outline-none"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Submit Button */}
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 active:scale-[0.99] disabled:opacity-50 disabled:pointer-events-none shadow-md shadow-purple-600/20 transition-all flex items-center justify-center gap-2 group"
                >
                  {isLoading ? (
                    <>
                      <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                      <span>Verifying Cryptographic Enclave...</span>
                    </>
                  ) : (
                    <>
                      <span>{mode === 'login' ? 'Sign In to Workstation' : 'Complete Registration'}</span>
                      <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Public Access Divider */}
            <div className="relative my-6 text-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200 dark:border-slate-800" />
              </div>
              <span className="relative px-3 text-xs bg-white dark:bg-[#0d1322] text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                or
              </span>
            </div>

            {/* Continue as Public Citizen Viewer */}
            <button
              type="button"
              onClick={onContinueAsGuest}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300 bg-slate-100 hover:bg-slate-200/80 dark:bg-slate-800/80 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700/80 transition-all flex items-center justify-center gap-2"
            >
              <Globe className="w-3.5 h-3.5 text-slate-500" />
              <span>Continue with Public Clearance (Citizen Access)</span>
            </button>

            {/* Statutory Compliance Footer */}
            <div className="mt-8 pt-4 border-t border-slate-100 dark:border-slate-800/60 flex items-center justify-center gap-2 text-[11px] text-slate-400 dark:text-slate-500 text-center">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span>DPDP Act 2023 Compliant · State Data Centre Enclave</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
