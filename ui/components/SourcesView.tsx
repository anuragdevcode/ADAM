'use client';

import { useState, useEffect, useRef } from 'react';
import {
  Database,
  Play,
  Pause,
  RefreshCw,
  Plus,
  Upload,
  Globe,
  FolderPlus,
  Plug,
  CheckCircle2,
  AlertCircle,
  StopCircle,
  RotateCcw,
  ListFilter,
  Layers,
  FileText,
  Trash2,
  Landmark,
  ShieldCheck,
} from 'lucide-react';
import type { SourceItem, IngestionJobItemRecord } from '@/lib/types';
import {
  fetchSources,
  toggleSourceStatus,
  deleteSource,
  testSourceConnection,
  triggerIngestionJob,
  fetchIngestionJobs,
  pauseJob,
  resumeJob,
  stopJob,
  retryJob,
  seedOfficialSources,
} from '@/lib/api';
import AddSourceModal from './AddSourceModal';
import IngestionJobItemsDrawer from './IngestionJobItemsDrawer';

type ControlTab = 'SOURCES' | 'JOBS' | 'HISTORY';

function getOfficialConnectorInfo(source: SourceItem): { label: string; connector: string } | null {
  const cfg = source.config_json || {};
  const cid = String(cfg.connector_id || '').toLowerCase();
  const id = (source.id || '').toLowerCase();
  const domains = (source.permitted_domains || []).map((d) => d.toLowerCase());

  if (cid === 'ekosh' || id.includes('ekosh') || domains.some((d) => d.includes('ekosh.uk.gov.in'))) {
    return { label: 'eKosh IFMS Treasury', connector: 'EkoshTreasuryConnector' };
  }
  if (cid === 'ukrd' || id.includes('ukrd') || domains.some((d) => d.includes('ukrd.uk.gov.in'))) {
    return { label: 'UKRD Rural Development', connector: 'UkrdConnector' };
  }
  if (cid === 'egazette' || id.includes('egazette') || domains.some((d) => d.includes('gazettes.uk.gov.in'))) {
    return { label: 'Official State e-Gazette', connector: 'EGazetteConnector' };
  }
  if (cid === 'itda' || id.includes('itda') || id.includes('sample_batch')) {
    return { label: 'ITDA Curated Batch', connector: 'ITDASampleBatchConnector' };
  }
  if (cid === 'audit' || id.includes('audit') || domains.some((d) => d.includes('uttarakhandaudit'))) {
    return { label: 'Audit Directorate', connector: 'GenericWebsiteConnector' };
  }
  if (cid === 'bor' || id.includes('bor') || domains.some((d) => d.includes('bor.uk.gov.in'))) {
    return { label: 'Board of Revenue', connector: 'GenericWebsiteConnector' };
  }
  return null;
}

export default function SourcesView() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [jobs, setJobs] = useState<IngestionJobItemRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [seedingLoading, setSeedingLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<ControlTab>('SOURCES');

  // Modals & Drawers
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedJobForItems, setSelectedJobForItems] = useState<IngestionJobItemRecord | null>(null);

  // Per-source action loading state
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ sourceId: string; success: boolean; message: string } | null>(null);

  // Hidden file input for fast batch upload
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadTargetSourceId, setUploadTargetSourceId] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [srcData, jobData] = await Promise.all([fetchSources(), fetchIngestionJobs()]);
      setSources(srcData);
      setJobs(jobData);
    } catch (err) {
      console.error('Failed to load sources or jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Polling lock and mount state
  const isPollingRef = useRef(false);

  // Poll active jobs if any are currently executing
  useEffect(() => {
    let isMounted = true;
    const hasActiveJobs = jobs.some((j) =>
      ['QUEUED', 'DISCOVERY', 'PROCESSING', 'DRAINING', 'CANCELLING'].includes(j.status)
    );

    if (!hasActiveJobs) return;

    const interval = setInterval(async () => {
      if (isPollingRef.current) return;
      isPollingRef.current = true;
      try {
        const [updatedJobs, updatedSources] = await Promise.all([
          fetchIngestionJobs(),
          fetchSources(),
        ]);
        if (isMounted) {
          setJobs(updatedJobs);
          setSources(updatedSources);
        }
      } catch (err) {
        console.error('Polling error in SourcesView:', err);
      } finally {
        isPollingRef.current = false;
      }
    }, 2500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [jobs]);

  // Source action handlers
  const handleToggleStatus = async (id: string) => {
    setActionLoadingId(id);
    try {
      const updated = await toggleSourceStatus(id);
      setSources((prev) => prev.map((s) => (s.id === id ? { ...s, status: updated.status } : s)));
    } catch (err) {
      console.error(err);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleTestSource = async (id: string) => {
    setActionLoadingId(id);
    setTestResult(null);
    try {
      const res = await testSourceConnection(id);
      setTestResult({ sourceId: id, success: res.success, message: res.message });
      setTimeout(() => setTestResult(null), 6000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection test failed';
      setTestResult({ sourceId: id, success: false, message: msg });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDeleteSource = async (id: string) => {
    if (!confirm('Are you sure you want to remove this data source? Past ingested documents remain preserved.')) return;
    setActionLoadingId(id);
    try {
      await deleteSource(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      console.error(err);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleTriggerSync = async (sourceId: string, jobType: 'FULL' | 'INCREMENTAL') => {
    setActionLoadingId(sourceId);
    try {
      await triggerIngestionJob({ source_id: sourceId, job_type: jobType });
      const updatedJobs = await fetchIngestionJobs();
      setJobs(updatedJobs);
      setActiveTab('JOBS');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to trigger ${jobType} sync: ${msg}`);
    } finally {
      setActionLoadingId(null);
    }
  };

  // Job action handlers
  const handlePauseJob = async (jobId: string) => {
    try {
      await pauseJob(jobId);
      const updatedJobs = await fetchIngestionJobs();
      setJobs(updatedJobs);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to pause job';
      alert(msg);
    }
  };

  const handleResumeJob = async (jobId: string) => {
    try {
      await resumeJob(jobId);
      const updatedJobs = await fetchIngestionJobs();
      setJobs(updatedJobs);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to resume job';
      alert(msg);
    }
  };

  const handleStopJob = async (jobId: string) => {
    try {
      await stopJob(jobId);
      const updatedJobs = await fetchIngestionJobs();
      setJobs(updatedJobs);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to stop job';
      alert(msg);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    try {
      await retryJob(jobId);
      const updatedJobs = await fetchIngestionJobs();
      setJobs(updatedJobs);
      setActiveTab('JOBS');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to retry failed items';
      alert(msg);
    }
  };

  const handleSeedOfficialSources = async () => {
    setSeedingLoading(true);
    try {
      await seedOfficialSources();
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to seed official sources';
      alert(msg);
    } finally {
      setSeedingLoading(false);
    }
  };

  // Quick file upload handler
  const handleFilePickerSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const targetId = uploadTargetSourceId || sources[0]?.id;
    if (!targetId) {
      alert('Please onboard a data source first.');
      return;
    }

    try {
      setLoading(true);
      await triggerIngestionJob({
        source_id: targetId,
        job_type: 'FULL',
        files: Array.from(files),
      });
      const updatedJobs = await fetchIngestionJobs();
      setJobs(updatedJobs);
      setActiveTab('JOBS');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to upload files: ${msg}`);
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setUploadTargetSourceId(null);
    }
  };

  // Aggregates
  const totalDocsIngested = sources.reduce((acc, s) => acc + (s.document_count || 0), 0);
  const activeJobs = jobs.filter((j) =>
    ['QUEUED', 'DISCOVERY', 'PROCESSING', 'DRAINING', 'CANCELLING'].includes(j.status)
  );
  const historyJobs = jobs.filter((j) =>
    ['COMPLETED', 'PARTIAL_SUCCESS', 'FAILED', 'CANCELLED', 'PAUSED'].includes(j.status)
  );

  return (
    <div className="flex-1 flex flex-col h-full bg-[#fcfcfc] overflow-hidden">
      {/* Top Header */}
      <div className="p-6 border-b border-gray-100 flex items-center justify-between bg-white/80 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-purple-600 text-white flex items-center justify-center shadow-xs">
              <Database className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-semibold text-gray-800">
                  Government Data Sources &amp; Ingestion Operating System
                </h1>
                <span className="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 text-xs font-semibold">
                  {sources.length} Sources
                </span>
                <span className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-semibold">
                  {totalDocsIngested} Documents
                </span>
                {activeJobs.length > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-semibold animate-pulse flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                    {activeJobs.length} Ingesting
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Pluggable Portals • Relational Databases • Batch Files • Deduplication &amp; Checkpoints
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Quick upload input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.csv,.json"
            onChange={handleFilePickerSelect}
            className="hidden"
          />

          <button
            type="button"
            onClick={() => {
              if (fileInputRef.current) fileInputRef.current.click();
            }}
            className="p-2 px-3 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-medium text-gray-700 flex items-center gap-1.5 shadow-xs transition-all"
            title="Directly upload PDF, DOCX, or text files for extraction"
          >
            <Upload className="w-3.5 h-3.5 text-purple-600" />
            <span>Upload Files</span>
          </button>

          <button
            type="button"
            disabled={seedingLoading}
            onClick={handleSeedOfficialSources}
            className="p-2 px-3 rounded-xl border border-purple-200 bg-purple-50 hover:bg-purple-100 active:scale-[0.98] text-xs font-semibold text-purple-700 flex items-center gap-1.5 shadow-2xs transition-all disabled:opacity-50"
            title="Populate authentic Uttarakhand sources (eKosh, UKRD, e-Gazette, ITDA Samples)"
          >
            {seedingLoading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-700" />
            ) : (
              <Landmark className="w-3.5 h-3.5 text-purple-700" />
            )}
            <span>Seed Official Sources</span>
          </button>

          <button
            type="button"
            onClick={() => setIsAddModalOpen(true)}
            className="p-2 px-3 rounded-xl bg-purple-600 hover:bg-purple-700 active:scale-[0.98] text-xs font-semibold text-white flex items-center gap-1.5 shadow-xs transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Data Source</span>
          </button>

          <button
            type="button"
            onClick={loadData}
            className="p-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-medium text-gray-600 flex items-center gap-1.5 shadow-xs"
            title="Refresh Sources &amp; Jobs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-purple-600' : ''}`} />
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="px-6 pt-3 border-b border-gray-100 flex items-center gap-4 bg-white/50 shrink-0 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setActiveTab('SOURCES')}
          className={`pb-3 transition-all flex items-center gap-1.5 border-b-2 ${
            activeTab === 'SOURCES'
              ? 'border-purple-600 text-purple-700 font-bold'
              : 'border-transparent text-gray-500 hover:text-gray-800'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Data Sources Directory</span>
          <span className="ml-1 px-1.5 py-0.2 rounded-full bg-gray-100 text-gray-600 text-[10px]">
            {sources.length}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('JOBS')}
          className={`pb-3 transition-all flex items-center gap-1.5 border-b-2 ${
            activeTab === 'JOBS'
              ? 'border-purple-600 text-purple-700 font-bold'
              : 'border-transparent text-gray-500 hover:text-gray-800'
          }`}
        >
          <RotateCcw className="w-4 h-4" />
          <span>Active Control Plane</span>
          {activeJobs.length > 0 && (
            <span className="ml-1 px-1.5 py-0.2 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold">
              {activeJobs.length} active
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('HISTORY')}
          className={`pb-3 transition-all flex items-center gap-1.5 border-b-2 ${
            activeTab === 'HISTORY'
              ? 'border-purple-600 text-purple-700 font-bold'
              : 'border-transparent text-gray-500 hover:text-gray-800'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Ingestion History &amp; Audit</span>
          <span className="ml-1 px-1.5 py-0.2 rounded-full bg-gray-100 text-gray-600 text-[10px]">
            {historyJobs.length}
          </span>
        </button>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* TAB 1: Sources Directory */}
        {activeTab === 'SOURCES' && (
          <div>
            {sources.length === 0 ? (
              <div className="py-16 px-4 flex flex-col items-center justify-center text-center max-w-lg mx-auto">
                <div className="w-14 h-14 rounded-3xl bg-purple-50 border border-purple-100 flex items-center justify-center shadow-xs mb-4">
                  <Landmark className="w-7 h-7 text-purple-600" />
                </div>
                <h3 className="text-base font-bold text-gray-900 mb-1">
                  No Data Sources Onboarded Yet
                </h3>
                <p className="text-xs text-gray-500 mb-6 leading-relaxed">
                  Get started by seeding the official Uttarakhand state government playbook (eKosh Treasury, UKRD Rural Development, State e-Gazette, and ITDA Verified Batch), or register a custom source.
                </p>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={seedingLoading}
                    onClick={handleSeedOfficialSources}
                    className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 active:scale-[0.98] text-white text-xs font-semibold shadow-xs flex items-center gap-2 transition-all disabled:opacity-50"
                  >
                    {seedingLoading ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Landmark className="w-3.5 h-3.5" />
                    )}
                    <span>Seed Official Playbook (1-Click)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(true)}
                    className="px-3.5 py-2.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Custom Source</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {sources.map((src) => {
                  const isApproved = src.status === 'APPROVED';
                  const isActing = actionLoadingId === src.id;
                  const stype = (src.source_type || 'WEBSITE').toUpperCase();
                  const testMsg = testResult && testResult.sourceId === src.id ? testResult : null;
                  const officialInfo = getOfficialConnectorInfo(src);

                  return (
                    <div
                      key={src.id}
                      className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs flex flex-col justify-between hover:shadow-sm transition-all"
                    >
                      <div>
                        {/* Header Pills */}
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-gray-100 text-gray-600">
                              {src.department_id.replace(/_/g, ' ')}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded-md text-[10px] font-semibold flex items-center gap-1 ${
                                stype === 'DATABASE'
                                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                  : stype === 'FILE_UPLOAD'
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : 'bg-purple-50 text-purple-700 border border-purple-200'
                              }`}
                            >
                              {stype === 'DATABASE' ? (
                                <Database className="w-2.5 h-2.5" />
                              ) : stype === 'FILE_UPLOAD' ? (
                                <FolderPlus className="w-2.5 h-2.5" />
                              ) : (
                                <Globe className="w-2.5 h-2.5" />
                              )}
                              <span>{stype}</span>
                            </span>
                            {officialInfo && (
                              <span
                                className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-100/90 text-purple-900 border border-purple-200 flex items-center gap-1 shadow-2xs"
                                title={`Official Uttarakhand Governed Connector: ${officialInfo.connector}`}
                              >
                                <Landmark className="w-3 h-3 text-purple-700" />
                                <span>{officialInfo.label}</span>
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-1.5">
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                                isApproved
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : 'bg-amber-50 text-amber-700 border border-amber-200'
                              }`}
                            >
                              {src.status}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleDeleteSource(src.id)}
                              className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-all"
                              title="Delete source"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        {/* Title & Metadata */}
                        <h3 className="text-sm font-semibold text-gray-900 line-clamp-1 mb-1">
                          {src.name}
                        </h3>

                        <div className="text-[11px] text-gray-400 space-y-1 mt-2">
                          <p className="truncate font-mono text-[10px] text-gray-600">
                            <span className="text-gray-400">Locator: </span>
                            {stype === 'DATABASE'
                              ? String(src.config_json?.connection_uri || 'External DB')
                              : src.base_url || 'N/A'}
                          </p>
                          <div className="flex items-center gap-4 text-gray-500">
                            <span>Cadence: {src.refresh_cadence}</span>
                            <span>Clearance: {src.access_classification}</span>
                          </div>
                          {officialInfo && (
                            <div className="flex items-center gap-1.5 text-[10px] text-purple-800">
                              <ShieldCheck className="w-3.5 h-3.5 text-purple-600 shrink-0" />
                              <span className="text-gray-400">Governed Connector:</span>
                              <span className="font-mono font-semibold px-1.5 py-0.2 rounded bg-purple-50 border border-purple-100">
                                {officialInfo.connector}
                              </span>
                            </div>
                          )}
                          {src.last_run_at && (
                            <p className="text-[10px] text-purple-700">
                              Last Run: {new Date(src.last_run_at).toLocaleString()} ({src.last_run_status})
                            </p>
                          )}
                        </div>

                        {/* Connection Test Message Alert */}
                        {testMsg && (
                          <div
                            className={`mt-2 p-2 rounded-xl text-xs flex items-center gap-1.5 ${
                              testMsg.success
                                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                                : 'bg-amber-50 text-amber-800 border border-amber-200'
                            }`}
                          >
                            {testMsg.success ? (
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                            ) : (
                              <AlertCircle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                            )}
                            <span className="truncate">{testMsg.message}</span>
                          </div>
                        )}
                      </div>

                      {/* Footer Actions */}
                      <div className="mt-4 pt-3 border-t border-gray-50 flex items-center justify-between gap-2 flex-wrap">
                        <span className="text-xs font-semibold text-purple-700">
                          {src.document_count} docs indexed
                        </span>

                        <div className="flex items-center gap-1.5">
                          {/* Test Connection Button */}
                          <button
                            type="button"
                            disabled={isActing}
                            onClick={() => handleTestSource(src.id)}
                            className="px-2 py-1 rounded-lg border border-gray-200 text-[11px] font-medium text-gray-600 hover:bg-gray-50 transition-all flex items-center gap-1"
                            title="Verify reachability"
                          >
                            <Plug className="w-3 h-3 text-purple-600" />
                            <span>Test</span>
                          </button>

                          {/* Pause / Approve Toggle */}
                          <button
                            type="button"
                            disabled={isActing}
                            onClick={() => handleToggleStatus(src.id)}
                            className={`px-2 py-1 rounded-lg text-[11px] font-medium transition-all flex items-center gap-1 ${
                              isApproved
                                ? 'bg-amber-50 hover:bg-amber-100 text-amber-800'
                                : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-800'
                            }`}
                          >
                            {isApproved ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                            <span>{isApproved ? 'Pause' : 'Approve'}</span>
                          </button>

                          {/* Run Full Sync */}
                          <button
                            type="button"
                            disabled={isActing || !isApproved}
                            onClick={() => handleTriggerSync(src.id, 'FULL')}
                            className="px-2.5 py-1 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-semibold shadow-2xs transition-all flex items-center gap-1 disabled:opacity-40"
                            title="Trigger a full crawl and ingestion pass"
                          >
                            <Play className="w-3 h-3" />
                            <span>Run Ingest</span>
                          </button>

                          {/* Run Incremental Sync */}
                          <button
                            type="button"
                            disabled={isActing || !isApproved}
                            onClick={() => handleTriggerSync(src.id, 'INCREMENTAL')}
                            className="px-2 py-1 rounded-lg border border-purple-200 text-purple-700 hover:bg-purple-50 text-[11px] font-medium transition-all flex items-center gap-1 disabled:opacity-40"
                            title="Trigger incremental sync since last watermark"
                          >
                            <span>Sync &Delta;</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: Active Control Plane Jobs */}
        {activeTab === 'JOBS' && (
          <div className="space-y-4">
            {activeJobs.length === 0 ? (
              <div className="h-64 flex flex-col items-center justify-center text-xs text-gray-400 gap-2">
                <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                <p>All ingestion jobs are idle or completed. Zero active tasks.</p>
                <p className="text-[11px] text-gray-400">Click &quot;Run Ingest&quot; on any source to launch a job.</p>
              </div>
            ) : (
              activeJobs.map((job) => {
                const isProcessing = job.status === 'PROCESSING' || job.status === 'DISCOVERY';
                const isDraining = job.status === 'DRAINING';
                const isCancelling = job.status === 'CANCELLING';

                return (
                  <div
                    key={job.id}
                    className="p-5 rounded-2xl border border-gray-100 bg-white shadow-xs flex flex-col gap-3"
                  >
                    {/* Job Card Header */}
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-gray-900">{job.source_name}</span>
                          <span className="px-2 py-0.5 rounded-full font-mono text-[10px] bg-purple-50 text-purple-700 font-bold">
                            {job.id}
                          </span>
                          <span className="px-2 py-0.5 rounded-md text-[10px] bg-gray-100 text-gray-600 font-semibold">
                            {job.job_type}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5">
                          Stage:{' '}
                          <span className="font-semibold text-purple-700 uppercase">{job.current_stage}</span>
                          {job.started_at && ` • Started ${new Date(job.started_at).toLocaleTimeString()}`}
                        </p>
                      </div>

                      {/* Job Controls */}
                      <div className="flex items-center gap-1.5">
                        {isProcessing && (
                          <button
                            type="button"
                            onClick={() => handlePauseJob(job.id)}
                            className="px-2.5 py-1.5 rounded-xl border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-semibold flex items-center gap-1 transition-all"
                          >
                            <Pause className="w-3.5 h-3.5" />
                            <span>Pause</span>
                          </button>
                        )}

                        {job.status === 'PAUSED' && (
                          <button
                            type="button"
                            onClick={() => handleResumeJob(job.id)}
                            className="px-2.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold flex items-center gap-1 transition-all"
                          >
                            <Play className="w-3.5 h-3.5" />
                            <span>Resume</span>
                          </button>
                        )}

                        {(isProcessing || isDraining) && (
                          <button
                            type="button"
                            onClick={() => handleStopJob(job.id)}
                            className="px-2.5 py-1.5 rounded-xl border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold flex items-center gap-1 transition-all"
                          >
                            <StopCircle className="w-3.5 h-3.5" />
                            <span>Stop</span>
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => setSelectedJobForItems(job)}
                          className="px-2.5 py-1.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold flex items-center gap-1 transition-all"
                        >
                          <ListFilter className="w-3.5 h-3.5 text-purple-600" />
                          <span>View Items</span>
                        </button>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs font-semibold text-gray-700">
                        <span>{job.progress_pct.toFixed(0)}% Completed</span>
                        <span>{job.count_ingested + job.count_skipped + job.count_failed} / {job.count_found || '?'} items</span>
                      </div>
                      <div className="w-full h-2.5 rounded-full bg-gray-100 overflow-hidden">
                        <div
                          className={`h-full transition-all duration-300 ${
                            isDraining ? 'bg-amber-500' : isCancelling ? 'bg-red-500' : 'bg-purple-600'
                          }`}
                          style={{ width: `${Math.max(3, job.progress_pct)}%` }}
                        />
                      </div>
                    </div>

                    {/* Stage Metrics Counters */}
                    <div className="flex items-center gap-3 text-xs pt-1">
                      <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 font-semibold">
                        ✓ {job.count_ingested} Ingested
                      </span>
                      <span className="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 font-semibold">
                        ⚡ {job.count_skipped} Deduplicated
                      </span>
                      {job.count_failed > 0 && (
                        <span className="px-2 py-0.5 rounded-md bg-red-50 text-red-700 font-semibold">
                          ✗ {job.count_failed} Failed
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* TAB 3: Ingestion History */}
        {activeTab === 'HISTORY' && (
          <div className="space-y-3">
            {historyJobs.length === 0 ? (
              <div className="h-64 flex items-center justify-center text-xs text-gray-400">
                No past ingestion runs recorded.
              </div>
            ) : (
              historyJobs.map((job) => {
                const isSuccess = job.status === 'COMPLETED';
                const isPartial = job.status === 'PARTIAL_SUCCESS';
                const isFailed = job.status === 'FAILED';
                const isCancelled = job.status === 'CANCELLED';

                return (
                  <div
                    key={job.id}
                    className="p-4 rounded-2xl border border-gray-100 bg-white hover:border-gray-200 transition-all shadow-2xs flex items-center justify-between gap-4 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-gray-900">{job.source_name}</span>
                        <span className="font-mono text-[10px] text-gray-400">{job.id}</span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            isSuccess
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : isPartial
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : isFailed
                              ? 'bg-red-50 text-red-700 border border-red-200'
                              : isCancelled
                              ? 'bg-gray-100 text-gray-700 border border-gray-200'
                              : 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {job.status}
                        </span>
                      </div>
                      <div className="text-[11px] text-gray-400 mt-1 flex items-center gap-3">
                        <span>Type: {job.job_type}</span>
                        <span>Ingested: {job.count_ingested}</span>
                        <span>Deduped: {job.count_skipped}</span>
                        {job.count_failed > 0 && <span className="text-red-600">Failed: {job.count_failed}</span>}
                        {job.started_at && (
                          <span>{new Date(job.started_at).toLocaleString()}</span>
                        )}
                      </div>
                      {job.error_message && (
                        <p className="text-[11px] text-red-600 mt-1 font-mono truncate max-w-md">
                          {job.error_message}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {job.count_failed > 0 && (
                        <button
                          type="button"
                          onClick={() => handleRetryJob(job.id)}
                          className="px-2.5 py-1.5 rounded-xl border border-purple-200 bg-purple-50 hover:bg-purple-100 text-purple-700 text-xs font-semibold flex items-center gap-1 transition-all"
                          title="Retry only failed items"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Retry Failures</span>
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => setSelectedJobForItems(job)}
                        className="px-2.5 py-1.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-medium flex items-center gap-1 transition-all"
                      >
                        <ListFilter className="w-3.5 h-3.5 text-purple-600" />
                        <span>Items</span>
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Add Source Wizard Modal */}
      <AddSourceModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSourceCreated={(newSrc) => {
          setSources((prev) => [newSrc, ...prev]);
        }}
      />

      {/* Paginated Job Items Drawer */}
      <IngestionJobItemsDrawer
        job={selectedJobForItems}
        onClose={() => setSelectedJobForItems(null)}
      />
    </div>
  );
}
