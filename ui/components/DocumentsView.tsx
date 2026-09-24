'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  FolderClosed,
  Search,
  Upload,
  FileText,
  Calendar,
  Layers,
  X,
  AlertCircle,
} from 'lucide-react';
import type { DepartmentItem, DocumentDetail, DocumentSummary } from '@/lib/types';
import { fetchDocuments, fetchDocumentDetails, uploadDocument } from '@/lib/api';

interface DocumentsViewProps {
  userId: string;
  clearanceLevel: string;
  departments: DepartmentItem[];
}

export default function DocumentsView({
  userId,
  clearanceLevel,
  departments,
}: DocumentsViewProps) {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState('ALL');
  const [selectedClass, setSelectedClass] = useState('ALL');
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [docDetail, setDocDetail] = useState<DocumentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Upload Dialog State
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadGoNum, setUploadGoNum] = useState('');
  const [uploadDept, setUploadDept] = useState(departments[0]?.id || 'FINANCE_TREASURY');
  const [uploadClass, setUploadClass] = useState('PUBLIC');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    const data = await fetchDocuments(
      {
        departmentId: selectedDept,
        classification: selectedClass,
        search: search || null,
        limit: 50,
      },
      { userId, clearanceLevel },
    );
    setDocs(data.items);
    setTotal(data.total);
    setLoading(false);
  }, [selectedDept, selectedClass, search, userId, clearanceLevel]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Load document details when clicked
  const handleSelectDoc = async (id: string) => {
    setSelectedDocId(id);
    setDetailLoading(true);
    try {
      const detail = await fetchDocumentDetails(id, { userId, clearanceLevel });
      setDocDetail(detail);
    } catch (err) {
      console.error(err);
      setDocDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !uploadTitle.trim()) return;

    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('title', uploadTitle.trim());
    formData.append('department_id', uploadDept);
    formData.append('classification', uploadClass);
    if (uploadGoNum.trim()) formData.append('go_number', uploadGoNum.trim());

    try {
      await uploadDocument(formData, { userId, clearanceLevel });
      setUploadOpen(false);
      setUploadFile(null);
      setUploadTitle('');
      setUploadGoNum('');
      loadDocuments();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#f8fafc] dark:bg-[#090d16] overflow-hidden transition-colors">
      {/* Top Controls Bar */}
      <div className="p-6 border-b border-slate-200/80 dark:border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white/70 dark:bg-[#0d121e]/70 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <FolderClosed className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Uttarakhand Public Records Repository
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 text-xs font-semibold border border-purple-200/80 dark:border-purple-800">
              {total} Documents
            </span>
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Searchable government orders, manuals, rules, and statutory circulars
          </p>
        </div>

        {/* Upload Document Button */}
        <button
          type="button"
          onClick={() => setUploadOpen(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-purple-600 dark:hover:bg-purple-500 text-white text-xs font-semibold shadow-xs transition-all shrink-0"
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Upload Document</span>
        </button>
      </div>

      {/* Filter Row */}
      <div className="px-6 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-slate-50/50 dark:bg-[#0c111c] flex flex-wrap items-center gap-3 shrink-0">
        {/* Search */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-700 dark:text-slate-200 focus-within:border-purple-400 dark:focus-within:border-purple-600 min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search by title or ID…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent outline-none w-full placeholder-slate-400 dark:placeholder-slate-500"
          />
          {search && (
            <button onClick={() => setSearch('')} className="text-slate-400 hover:text-slate-600">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Department Filter */}
        <select
          value={selectedDept}
          onChange={(e) => setSelectedDept(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-purple-400"
        >
          <option value="ALL">All Departments</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>

        {/* Classification Filter */}
        <select
          value={selectedClass}
          onChange={(e) => setSelectedClass(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-purple-400"
        >
          <option value="ALL">All Classifications</option>
          <option value="PUBLIC">PUBLIC</option>
          <option value="INTERNAL">INTERNAL</option>
          <option value="RESTRICTED">RESTRICTED</option>
          <option value="CONFIDENTIAL">CONFIDENTIAL</option>
        </select>
      </div>

      {/* Main Table / Grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-slate-400 dark:text-slate-500">
            Loading repository records…
          </div>
        ) : docs.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-slate-400 dark:text-slate-500">
            <FolderClosed className="w-10 h-10 stroke-[1.5] text-slate-300 dark:text-slate-600 mb-2" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">No documents found</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              Try adjusting your search query or department filters.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {docs.map((d) => (
              <div
                key={d.id}
                onClick={() => handleSelectDoc(d.id)}
                className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-xs hover:shadow-md hover:border-purple-300 dark:hover:border-purple-700 transition-all cursor-pointer flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                      {d.department_id.replace(/_/g, ' ')}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        d.classification === 'PUBLIC'
                          ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                          : d.classification === 'RESTRICTED'
                          ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                          : d.classification === 'CONFIDENTIAL'
                          ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800'
                          : 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
                      }`}
                    >
                      {d.classification}
                    </span>
                  </div>

                  <h3 className="text-xs font-semibold text-slate-900 dark:text-slate-100 line-clamp-2 leading-relaxed group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                    {d.title}
                  </h3>

                  {d.go_number && (
                    <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400 mt-1.5">
                      GO: {d.go_number}
                    </p>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500">
                  <div className="flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5" />
                    <span>{d.page_count} pages</span>
                  </div>
                  {d.issued_on && (
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      <span>{d.issued_on}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Document Detail Modal */}
      {selectedDocId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl max-w-2xl w-full overflow-hidden max-h-[85vh] flex flex-col animate-in zoom-in-95">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 shrink-0 bg-slate-50/50 dark:bg-[#131b2c]/50">
              <div className="flex items-center gap-2 min-w-0 pr-4">
                <FileText className="w-5 h-5 text-purple-600 dark:text-purple-400 shrink-0" />
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                  {docDetail?.title || 'Document Details'}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDocId(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-5 flex-1">
              {detailLoading ? (
                <div className="py-12 text-center text-xs text-slate-400">Loading details…</div>
              ) : docDetail ? (
                <>
                  {/* Meta Chips */}
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 font-semibold text-slate-700 dark:text-slate-300">
                      Dept: {docDetail.department_id.replace(/_/g, ' ')}
                    </span>
                    <span className="px-2.5 py-1 rounded-lg bg-purple-50 dark:bg-purple-950/60 font-semibold text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                      Clearance: {docDetail.classification}
                    </span>
                    {docDetail.version?.go_number && (
                      <span className="px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/60 font-mono text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                        GO: {docDetail.version.go_number}
                      </span>
                    )}
                    <span className="px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 font-semibold border border-emerald-200 dark:border-emerald-800">
                      Status: {docDetail.lifecycle_status}
                    </span>
                  </div>

                  {/* SHA256 */}
                  {docDetail.version?.sha256 && (
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#161d2d] border border-slate-200 dark:border-slate-800 text-[11px] font-mono text-slate-500 dark:text-slate-400 break-all">
                      <span className="font-semibold text-slate-700 dark:text-slate-300">SHA-256: </span>
                      {docDetail.version.sha256}
                    </div>
                  )}

                  {/* Precedents Section */}
                  {docDetail.precedents && docDetail.precedents.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-slate-900 dark:text-slate-100 mb-2">Precedent Citations</h4>
                      <div className="space-y-1.5">
                        {docDetail.precedents.map((pr) => (
                          <div
                            key={pr.id}
                            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#161d2d] text-xs flex items-center justify-between"
                          >
                            <span className="font-medium text-slate-800 dark:text-slate-200">{pr.raw_citation_text}</span>
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-100 dark:bg-purple-900/60 text-purple-800 dark:text-purple-300">
                              {pr.relation_type}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pages breakdown */}
                  <div>
                    <h4 className="text-xs font-semibold text-slate-900 dark:text-slate-100 mb-2">
                      Extracted Pages ({docDetail.pages.length})
                    </h4>
                    <div className="space-y-2">
                      {docDetail.pages.map((p) => (
                        <div
                          key={p.id}
                          className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-[#161d2d] text-xs"
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-semibold text-slate-800 dark:text-slate-200">
                              Page {p.page_number}
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                              {p.review_status}
                            </span>
                          </div>
                          <p className="text-slate-600 dark:text-slate-400 line-clamp-3 leading-relaxed font-mono text-[11px]">
                            {p.text_preview || '(No text extracted)'}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-rose-500">Failed to load document details.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Upload Document Modal */}
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
          <form
            onSubmit={handleUploadSubmit}
            className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl max-w-lg w-full overflow-hidden animate-in zoom-in-95"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Upload Official Government Order</h2>
              </div>
              <button
                type="button"
                onClick={() => setUploadOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {uploadError && (
                <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Document Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Revision of Dearness Allowance Rates 2026"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-800 dark:text-slate-100 outline-none focus:border-purple-400"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    GO / Circular Number
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. UK/FIN/2026/1042"
                    value={uploadGoNum}
                    onChange={(e) => setUploadGoNum(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-800 dark:text-slate-100 outline-none focus:border-purple-400"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Department
                  </label>
                  <select
                    value={uploadDept}
                    onChange={(e) => setUploadDept(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-100 outline-none bg-white dark:bg-[#131926] focus:border-purple-400"
                  >
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Security Classification
                </label>
                <select
                  value={uploadClass}
                  onChange={(e) => setUploadClass(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-100 outline-none bg-white dark:bg-[#131926] focus:border-purple-400"
                >
                  <option value="PUBLIC">PUBLIC</option>
                  <option value="INTERNAL">INTERNAL</option>
                  <option value="RESTRICTED">RESTRICTED</option>
                  <option value="CONFIDENTIAL">CONFIDENTIAL</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  PDF Document File <span className="text-rose-500">*</span>
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-600 dark:text-slate-400 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-purple-50 dark:file:bg-purple-950/60 file:text-purple-700 dark:file:text-purple-300 hover:file:bg-purple-100 cursor-pointer"
                />
                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
                  File will be verified through InputValidator (magic bytes &amp; security gate).
                </p>
              </div>
            </div>

            <div className="px-6 py-3.5 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-[#131b2c]/70 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setUploadOpen(false)}
                className="px-4 py-2 text-xs font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploading || !uploadFile || !uploadTitle.trim()}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:bg-slate-300 dark:disabled:bg-slate-800 text-white text-xs font-semibold shadow-xs transition-all flex items-center gap-1.5"
              >
                {uploading ? 'Validating…' : 'Submit for Ingestion'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
