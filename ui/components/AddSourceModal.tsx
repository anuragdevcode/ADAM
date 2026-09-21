'use client';

import { useState } from 'react';
import { X, Globe, Database, FolderPlus, Plug, CheckCircle2, AlertCircle, Loader2, Sparkles } from 'lucide-react';
import { createSource, testSourceConnection } from '@/lib/api';
import type { SourceItem } from '@/lib/types';

interface AddSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSourceCreated: (src: SourceItem) => void;
}

type SourceType = 'WEBSITE' | 'DATABASE' | 'FILE_UPLOAD' | 'CUSTOM';

export default function AddSourceModal({ isOpen, onClose, onSourceCreated }: AddSourceModalProps) {
  const [sourceType, setSourceType] = useState<SourceType>('WEBSITE');
  const [name, setName] = useState('');
  const [departmentId, setDepartmentId] = useState('GENERAL_ADMINISTRATION');
  const [classification, setClassification] = useState('PUBLIC');
  const [refreshCadence, setRefreshCadence] = useState('WEEKLY');
  const [rateLimit, setRateLimit] = useState(30);

  // Website fields
  const [websiteDomain, setWebsiteDomain] = useState('');
  const [pathPrefix, setPathPrefix] = useState('/');
  const [sitemapUrl, setSitemapUrl] = useState('');

  // Database fields
  const [connectionUri, setConnectionUri] = useState('');
  const [tableName, setTableName] = useState('');
  const [watermarkColumn, setWatermarkColumn] = useState('updated_at');
  const [idColumn, setIdColumn] = useState('id');

  // File batch fields
  const [batchDir, setBatchDir] = useState('');

  // State
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleTestDirect = async () => {
    setTesting(true);
    setTestResult(null);
    setError(null);
    try {
      if (sourceType === 'WEBSITE' && !websiteDomain) {
        setTestResult({ success: false, message: 'Please enter a permitted domain to test.' });
        return;
      }
      if (sourceType === 'DATABASE' && !connectionUri) {
        setTestResult({ success: false, message: 'Please enter a connection URI to test.' });
        return;
      }

      // Build temporary config payload
      const configJson: Record<string, unknown> = {};
      const permittedDomains = websiteDomain ? [websiteDomain.trim().replace(/^https?:\/\//, '')] : [];
      if (sourceType === 'DATABASE') {
        configJson.connection_uri = connectionUri.trim();
        configJson.table_name = tableName.trim();
      }

      // Temporary source submission for test
      const res = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim() || 'Temporary Connection Test',
          department_id: departmentId,
          source_type: sourceType,
          permitted_domains: permittedDomains,
          permitted_path_prefixes: [pathPrefix.trim() || '/'],
          config_json: configJson,
        }),
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        setTestResult({ success: false, message: err?.detail || 'Connection test failed.' });
        return;
      }
      const newSrc = await res.json();
      const testRes = await testSourceConnection(newSrc.id);
      setTestResult(testRes);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection test failed.';
      setTestResult({ success: false, message: msg });
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Source name is required.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const configJson: Record<string, unknown> = {};
      const permittedDomains = websiteDomain ? [websiteDomain.trim().replace(/^https?:\/\//, '')] : [];

      if (sourceType === 'WEBSITE') {
        if (sitemapUrl) configJson.sitemap_url = sitemapUrl.trim();
      } else if (sourceType === 'DATABASE') {
        if (!connectionUri) throw new Error('Database connection URI is required.');
        configJson.connection_uri = connectionUri.trim();
        configJson.table_name = tableName.trim();
        configJson.watermark_column = watermarkColumn.trim();
        configJson.id_column = idColumn.trim();
      } else if (sourceType === 'FILE_UPLOAD') {
        if (batchDir) configJson.batch_dir = batchDir.trim();
      }

      const res = await createSource({
        name: name.trim(),
        department_id: departmentId,
        source_type: sourceType,
        permitted_domains: permittedDomains,
        permitted_path_prefixes: [pathPrefix.trim() || '/'],
        config_json: configJson,
        access_classification: classification,
        refresh_cadence: refreshCadence,
        rate_limit_per_minute: rateLimit,
      });

      onSourceCreated({
        id: res.id,
        name: res.name,
        department_id: departmentId,
        owner_name: 'Administrative Officer',
        source_type: sourceType,
        permitted_domains: permittedDomains,
        base_url: permittedDomains[0] || '',
        config_json: configJson,
        status: 'APPROVED',
        refresh_cadence: refreshCadence,
        access_classification: classification,
        document_count: 0,
        created_at: new Date().toISOString(),
      });

      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to onboard data source.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-3xl border border-gray-100 shadow-2xl max-w-xl w-full overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-6 border-b border-gray-100 flex items-center justify-between bg-purple-50/40">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-purple-600 text-white flex items-center justify-center shadow-xs">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Onboard Government Data Source</h2>
              <p className="text-[11px] text-gray-500">Configure websites, databases, or local files for ingestion</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Source Type Selector */}
        <div className="p-6 pb-2 border-b border-gray-100 bg-gray-50/50">
          <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Select Ingestion Connector Type
          </label>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => setSourceType('WEBSITE')}
              className={`p-3 rounded-2xl border text-left transition-all flex flex-col gap-1.5 ${
                sourceType === 'WEBSITE'
                  ? 'border-purple-600 bg-purple-50/50 text-purple-900 shadow-xs'
                  : 'border-gray-200 bg-white hover:border-gray-300 text-gray-700'
              }`}
            >
              <Globe className="w-4 h-4 text-purple-600" />
              <span className="text-xs font-semibold">Web Portal</span>
              <span className="text-[10px] text-gray-400 leading-tight">Crawl portal URLs &amp; sitemaps</span>
            </button>

            <button
              type="button"
              onClick={() => setSourceType('DATABASE')}
              className={`p-3 rounded-2xl border text-left transition-all flex flex-col gap-1.5 ${
                sourceType === 'DATABASE'
                  ? 'border-purple-600 bg-purple-50/50 text-purple-900 shadow-xs'
                  : 'border-gray-200 bg-white hover:border-gray-300 text-gray-700'
              }`}
            >
              <Database className="w-4 h-4 text-indigo-600" />
              <span className="text-xs font-semibold">SQL Database</span>
              <span className="text-[10px] text-gray-400 leading-tight">Postgres, MySQL, SQLite sync</span>
            </button>

            <button
              type="button"
              onClick={() => setSourceType('FILE_UPLOAD')}
              className={`p-3 rounded-2xl border text-left transition-all flex flex-col gap-1.5 ${
                sourceType === 'FILE_UPLOAD'
                  ? 'border-purple-600 bg-purple-50/50 text-purple-900 shadow-xs'
                  : 'border-gray-200 bg-white hover:border-gray-300 text-gray-700'
              }`}
            >
              <FolderPlus className="w-4 h-4 text-emerald-600" />
              <span className="text-xs font-semibold">Batch / Files</span>
              <span className="text-[10px] text-gray-400 leading-tight">Local dir or multipart files</span>
            </button>
          </div>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto space-y-4 flex-1">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {testResult && (
            <div
              className={`p-3 rounded-xl border text-xs flex items-center gap-2 ${
                testResult.success
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                  : 'bg-amber-50 border-amber-200 text-amber-800'
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
              )}
              <span>{testResult.message}</span>
            </div>
          )}

          {/* Common Fields */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Source Name *</label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Finance Dept Treasury Circulars"
              className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white"
            />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Department</label>
              <select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white"
              >
                <option value="GENERAL_ADMINISTRATION">General Administration</option>
                <option value="FINANCE_TREASURY">Finance &amp; Treasury</option>
                <option value="RURAL_DEVELOPMENT">Rural Development</option>
                <option value="AUDIT_DIRECTORATE">Audit Directorate</option>
                <option value="BOARD_OF_REVENUE">Board of Revenue</option>
                <option value="LEGAL_AFFAIRS">Legal Affairs</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Clearance Level</label>
              <select
                value={classification}
                onChange={(e) => setClassification(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white"
              >
                <option value="PUBLIC">PUBLIC</option>
                <option value="RESTRICTED">RESTRICTED</option>
                <option value="CONFIDENTIAL">CONFIDENTIAL</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Sync Cadence</label>
              <select
                value={refreshCadence}
                onChange={(e) => setRefreshCadence(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white"
              >
                <option value="MANUAL">MANUAL</option>
                <option value="DAILY">DAILY</option>
                <option value="WEEKLY">WEEKLY</option>
                <option value="MONTHLY">MONTHLY</option>
              </select>
            </div>
          </div>

          {/* Type-Specific Fields */}
          {sourceType === 'WEBSITE' && (
            <div className="space-y-3 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Permitted Domain *</label>
                <input
                  type="text"
                  required
                  value={websiteDomain}
                  onChange={(e) => setWebsiteDomain(e.target.value)}
                  placeholder="e.g. ekosh.uk.gov.in"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Path Prefix</label>
                  <input
                    type="text"
                    value={pathPrefix}
                    onChange={(e) => setPathPrefix(e.target.value)}
                    placeholder="/orders/"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Rate Limit / min</label>
                  <input
                    type="number"
                    min={5}
                    max={120}
                    value={rateLimit}
                    onChange={(e) => setRateLimit(Number(e.target.value))}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Optional Sitemap URL</label>
                <input
                  type="url"
                  value={sitemapUrl}
                  onChange={(e) => setSitemapUrl(e.target.value)}
                  placeholder="https://ekosh.uk.gov.in/sitemap.xml"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono text-[11px]"
                />
              </div>
            </div>
          )}

          {sourceType === 'DATABASE' && (
            <div className="space-y-3 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Database Connection URI *</label>
                <input
                  type="text"
                  required
                  value={connectionUri}
                  onChange={(e) => setConnectionUri(e.target.value)}
                  placeholder="postgresql://user:pass@host:5432/gov_db"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono text-[11px]"
                />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Table Name *</label>
                  <input
                    type="text"
                    required
                    value={tableName}
                    onChange={(e) => setTableName(e.target.value)}
                    placeholder="official_orders"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Watermark Col</label>
                  <input
                    type="text"
                    value={watermarkColumn}
                    onChange={(e) => setWatermarkColumn(e.target.value)}
                    placeholder="updated_at"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">ID Column</label>
                  <input
                    type="text"
                    value={idColumn}
                    onChange={(e) => setIdColumn(e.target.value)}
                    placeholder="id"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono"
                  />
                </div>
              </div>
            </div>
          )}

          {sourceType === 'FILE_UPLOAD' && (
            <div className="space-y-3 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Local Directory Path (Optional)</label>
                <input
                  type="text"
                  value={batchDir}
                  onChange={(e) => setBatchDir(e.target.value)}
                  placeholder="/Users/officer/Downloads/uk_go_batches"
                  className="w-full px-3 py-2 text-xs rounded-xl border border-gray-200 focus:outline-hidden focus:border-purple-500 bg-white font-mono text-[11px]"
                />
                <p className="text-[10px] text-gray-400 mt-1">
                  Leave empty to upload multipart files directly through the control plane.
                </p>
              </div>
            </div>
          )}

          {/* Footer Actions */}
          <div className="pt-4 border-t border-gray-100 flex items-center justify-between">
            <button
              type="button"
              disabled={testing || submitting}
              onClick={handleTestDirect}
              className="px-3.5 py-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-semibold text-gray-700 flex items-center gap-1.5 transition-all"
            >
              {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-600" /> : <Plug className="w-3.5 h-3.5 text-purple-600" />}
              <span>Test Connection</span>
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-3.5 py-2 rounded-xl text-xs font-medium text-gray-600 hover:bg-gray-100 transition-all"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 active:scale-[0.98] text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-all"
              >
                {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>Save &amp; Onboard</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
