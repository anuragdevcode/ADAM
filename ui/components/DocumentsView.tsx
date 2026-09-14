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
    <div className="flex-1 flex flex-col h-full bg-[#fcfcfc] overflow-hidden">
      {/* Top Controls Bar */}
      <div className="p-6 border-b border-line flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-surface backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <FolderClosed className="w-5 h-5 text-brand" />
            <h1 className="text-base font-semibold text-ink">
              Uttarakhand Public Records Repository
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-brand-soft text-brand text-xs font-medium">
              {total} Documents
            </span>
          </div>
          <p className="text-xs text-ink-faint mt-0.5">
            Searchable government orders, manuals, rules, and statutory circulars
          </p>
        </div>

        {/* Upload Document Button */}
        <button
          type="button"
          onClick={() => setUploadOpen(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#3b3e45] hover:bg-black text-white text-xs font-semibold shadow-xs transition-all shrink-0"
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Upload Document</span>
        </button>
      </div>

      {/* Filter Row */}
      <div className="px-6 py-3 border-b border-line bg-surface-subtle/50 flex flex-wrap items-center gap-3 shrink-0">
        {/* Search */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-line bg-surface text-xs text-ink-secondary focus-within:border-brand-border min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-ink-faint" />
          <input
            type="text"
            placeholder="Search by title or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent outline-none w-full placeholder-ink-faint"
          />
          {search && (
            <button onClick={() => setSearch('')} className="text-ink-faint hover:text-ink-secondary">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Department Filter */}
        <select
          value={selectedDept}
          onChange={(e) => setSelectedDept(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-line bg-surface text-xs text-ink-secondary outline-none focus:border-brand-border"
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
          className="px-3 py-1.5 rounded-xl border border-line bg-surface text-xs text-ink-secondary outline-none focus:border-brand-border"
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
          <div className="h-64 flex items-center justify-center text-xs text-ink-faint">
            Loading repository records...
          </div>
        ) : docs.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-ink-faint">
            <FolderClosed className="w-10 h-10 stroke-[1.5] text-ink-faint mb-2" />
            <p className="text-sm font-medium text-ink-secondary">No documents found</p>
            <p className="text-xs text-ink-faint mt-1">
              Try adjusting your search query or department filters.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {docs.map((d) => (
              <div
                key={d.id}
                onClick={() => handleSelectDoc(d.id)}
                className="bg-surface rounded-2xl border border-line p-4 shadow-xs hover:shadow-md hover:border-brand-border transition-all cursor-pointer flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-surface-sunken text-ink-secondary">
                      {d.department_id.replace(/_/g, ' ')}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        d.classification === 'PUBLIC'
                          ? 'bg-ok-soft text-ok'
                          : d.classification === 'RESTRICTED'
                          ? 'bg-warn-soft text-warn'
                          : d.classification === 'CONFIDENTIAL'
                          ? 'bg-danger-soft text-danger'
                          : 'bg-blue-50 text-blue-700'
                      }`}
                    >
                      {d.classification}
                    </span>
                  </div>

                  <h3 className="text-xs font-semibold text-ink line-clamp-2 leading-relaxed">
                    {d.title}
                  </h3>

                  {d.go_number && (
                    <p className="text-[11px] font-mono text-ink-muted mt-1.5">
                      GO: {d.go_number}
                    </p>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-line flex items-center justify-between text-[11px] text-ink-faint">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-surface rounded-3xl border border-line shadow-2xl max-w-2xl w-full overflow-hidden max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-line shrink-0">
              <div className="flex items-center gap-2 min-w-0 pr-4">
                <FileText className="w-5 h-5 text-brand shrink-0" />
                <h2 className="text-sm font-semibold text-ink truncate">
                  {docDetail?.title || 'Document Details'}
                </h2>
              </div>
              <button
                onClick={() => setSelectedDocId(null)}
                className="p-1.5 rounded-lg text-ink-faint hover:text-ink-secondary hover:bg-surface-sunken shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-5 flex-1">
              {detailLoading ? (
                <div className="py-12 text-center text-xs text-ink-faint">Loading details…</div>
              ) : docDetail ? (
                <>
                  {/* Meta Chips */}
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="px-2.5 py-1 rounded-lg bg-surface-sunken font-medium text-ink-secondary">
                      Dept: {docDetail.department_id.replace(/_/g, ' ')}
                    </span>
                    <span className="px-2.5 py-1 rounded-lg bg-brand-soft font-medium text-brand">
                      Clearance: {docDetail.classification}
                    </span>
                    {docDetail.version?.go_number && (
                      <span className="px-2.5 py-1 rounded-lg bg-blue-50 font-mono text-blue-700">
                        GO: {docDetail.version.go_number}
                      </span>
                    )}
                    <span className="px-2.5 py-1 rounded-lg bg-ok-soft text-ok font-medium">
                      Status: {docDetail.lifecycle_status}
                    </span>
                  </div>

                  {/* SHA256 */}
                  {docDetail.version?.sha256 && (
                    <div className="p-3 rounded-xl bg-surface-subtle border border-line text-[11px] font-mono text-ink-muted break-all">
                      <span className="font-semibold text-ink-secondary">SHA-256: </span>
                      {docDetail.version.sha256}
                    </div>
                  )}

                  {/* Precedents Section */}
                  {docDetail.precedents && docDetail.precedents.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-ink-secondary mb-2">Precedent Citations</h4>
                      <div className="space-y-1.5">
                        {docDetail.precedents.map((pr) => (
                          <div
                            key={pr.id}
                            className="p-2.5 rounded-xl border border-line/80 bg-surface-subtle text-xs flex items-center justify-between"
                          >
                            <span className="font-medium text-ink">{pr.raw_citation_text}</span>
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-brand-softHover text-brand-active">
                              {pr.relation_type}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pages breakdown */}
                  <div>
                    <h4 className="text-xs font-semibold text-ink-secondary mb-2">
                      Extracted Pages ({docDetail.pages.length})
                    </h4>
                    <div className="space-y-2">
                      {docDetail.pages.map((p) => (
                        <div
                          key={p.id}
                          className="p-3 rounded-2xl border border-line bg-surface-subtle text-xs"
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-semibold text-ink">
                              Page {p.page_number}
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-surface-sunken text-ink-secondary">
                              {p.review_status}
                            </span>
                          </div>
                          <p className="text-ink-secondary line-clamp-3 leading-relaxed font-mono text-[11px]">
                            {p.text_preview || '(No text extracted)'}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-danger">Failed to load document details.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Upload Document Modal */}
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <form
            onSubmit={handleUploadSubmit}
            className="bg-surface rounded-3xl border border-line shadow-2xl max-w-lg w-full overflow-hidden"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-line">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-brand" />
                <h2 className="text-sm font-semibold text-ink">Upload Official Government Order</h2>
              </div>
              <button
                type="button"
                onClick={() => setUploadOpen(false)}
                className="p-1.5 rounded-lg text-ink-faint hover:text-ink-secondary hover:bg-surface-sunken"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {uploadError && (
                <div className="p-3 rounded-xl bg-danger-soft border border-danger text-xs text-danger flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-ink-secondary mb-1">
                  Document Title <span className="text-danger">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Revision of Dearness Allowance Rates 2026"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-line text-xs text-ink outline-none focus:border-brand-border"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink-secondary mb-1">
                    GO / Circular Number
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. UK/FIN/2026/1042"
                    value={uploadGoNum}
                    onChange={(e) => setUploadGoNum(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-line text-xs text-ink outline-none focus:border-brand-border"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink-secondary mb-1">
                    Department
                  </label>
                  <select
                    value={uploadDept}
                    onChange={(e) => setUploadDept(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-line text-xs text-ink outline-none bg-surface focus:border-brand-border"
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
                <label className="block text-xs font-semibold text-ink-secondary mb-1">
                  Security Classification
                </label>
                <select
                  value={uploadClass}
                  onChange={(e) => setUploadClass(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-line text-xs text-ink outline-none bg-surface focus:border-brand-border"
                >
                  <option value="PUBLIC">PUBLIC</option>
                  <option value="INTERNAL">INTERNAL</option>
                  <option value="RESTRICTED">RESTRICTED</option>
                  <option value="CONFIDENTIAL">CONFIDENTIAL</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink-secondary mb-1">
                  PDF Document File <span className="text-danger">*</span>
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-ink-secondary file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-brand-soft file:text-brand hover:file:bg-brand-softHover cursor-pointer"
                />
                <p className="text-[10px] text-ink-faint mt-1">
                  File will be verified through InputValidator (magic bytes &amp; security gate).
                </p>
              </div>
            </div>

            <div className="px-6 py-3.5 border-t border-line bg-surface-subtle flex items-center justify-between">
              <button
                type="button"
                onClick={() => setUploadOpen(false)}
                className="px-4 py-2 text-xs font-medium text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploading || !uploadFile || !uploadTitle.trim()}
                className="px-4 py-2 rounded-xl bg-brand hover:bg-brand-hover disabled:bg-surface-sunken text-white text-xs font-semibold shadow-xs transition-all flex items-center gap-1.5"
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
