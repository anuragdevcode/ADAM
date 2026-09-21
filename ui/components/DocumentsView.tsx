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
      <div className="p-6 border-b border-gray-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white/70 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <FolderClosed className="w-5 h-5 text-purple-600" />
            <h1 className="text-base font-semibold text-gray-800">
              Uttarakhand Public Records Repository
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 text-xs font-medium">
              {total} Documents
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
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
      <div className="px-6 py-3 border-b border-gray-100 bg-gray-50/50 flex flex-wrap items-center gap-3 shrink-0">
        {/* Search */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-xs text-gray-600 focus-within:border-purple-300 min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search by title or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent outline-none w-full placeholder-gray-400"
          />
          {search && (
            <button onClick={() => setSearch('')} className="text-gray-400 hover:text-gray-600">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Department Filter */}
        <select
          value={selectedDept}
          onChange={(e) => setSelectedDept(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-xs text-gray-700 outline-none focus:border-purple-300"
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
          className="px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-xs text-gray-700 outline-none focus:border-purple-300"
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
          <div className="h-64 flex items-center justify-center text-xs text-gray-400">
            Loading repository records...
          </div>
        ) : docs.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-gray-400">
            <FolderClosed className="w-10 h-10 stroke-[1.5] text-gray-300 mb-2" />
            <p className="text-sm font-medium text-gray-600">No documents found</p>
            <p className="text-xs text-gray-400 mt-1">
              Try adjusting your search query or department filters.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {docs.map((d) => (
              <div
                key={d.id}
                onClick={() => handleSelectDoc(d.id)}
                className="bg-white rounded-2xl border border-gray-100 p-4 shadow-xs hover:shadow-md hover:border-purple-200 transition-all cursor-pointer flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-gray-100 text-gray-600">
                      {d.department_id.replace(/_/g, ' ')}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        d.classification === 'PUBLIC'
                          ? 'bg-emerald-50 text-emerald-700'
                          : d.classification === 'RESTRICTED'
                          ? 'bg-amber-50 text-amber-700'
                          : d.classification === 'CONFIDENTIAL'
                          ? 'bg-rose-50 text-rose-700'
                          : 'bg-blue-50 text-blue-700'
                      }`}
                    >
                      {d.classification}
                    </span>
                  </div>

                  <h3 className="text-xs font-semibold text-gray-800 line-clamp-2 leading-relaxed">
                    {d.title}
                  </h3>

                  {d.go_number && (
                    <p className="text-[11px] font-mono text-gray-500 mt-1.5">
                      GO: {d.go_number}
                    </p>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-gray-50 flex items-center justify-between text-[11px] text-gray-400">
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
          <div className="bg-white rounded-3xl border border-gray-100 shadow-2xl max-w-2xl w-full overflow-hidden max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
              <div className="flex items-center gap-2 min-w-0 pr-4">
                <FileText className="w-5 h-5 text-purple-600 shrink-0" />
                <h2 className="text-sm font-semibold text-gray-800 truncate">
                  {docDetail?.title || 'Document Details'}
                </h2>
              </div>
              <button
                onClick={() => setSelectedDocId(null)}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-5 flex-1">
              {detailLoading ? (
                <div className="py-12 text-center text-xs text-gray-400">Loading details…</div>
              ) : docDetail ? (
                <>
                  {/* Meta Chips */}
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="px-2.5 py-1 rounded-lg bg-gray-100 font-medium text-gray-700">
                      Dept: {docDetail.department_id.replace(/_/g, ' ')}
                    </span>
                    <span className="px-2.5 py-1 rounded-lg bg-purple-50 font-medium text-purple-700">
                      Clearance: {docDetail.classification}
                    </span>
                    {docDetail.version?.go_number && (
                      <span className="px-2.5 py-1 rounded-lg bg-blue-50 font-mono text-blue-700">
                        GO: {docDetail.version.go_number}
                      </span>
                    )}
                    <span className="px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 font-medium">
                      Status: {docDetail.lifecycle_status}
                    </span>
                  </div>

                  {/* SHA256 */}
                  {docDetail.version?.sha256 && (
                    <div className="p-3 rounded-xl bg-gray-50 border border-gray-100 text-[11px] font-mono text-gray-500 break-all">
                      <span className="font-semibold text-gray-700">SHA-256: </span>
                      {docDetail.version.sha256}
                    </div>
                  )}

                  {/* Precedents Section */}
                  {docDetail.precedents && docDetail.precedents.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-gray-700 mb-2">Precedent Citations</h4>
                      <div className="space-y-1.5">
                        {docDetail.precedents.map((pr) => (
                          <div
                            key={pr.id}
                            className="p-2.5 rounded-xl border border-gray-200/80 bg-gray-50 text-xs flex items-center justify-between"
                          >
                            <span className="font-medium text-gray-800">{pr.raw_citation_text}</span>
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-100 text-purple-800">
                              {pr.relation_type}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pages breakdown */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-700 mb-2">
                      Extracted Pages ({docDetail.pages.length})
                    </h4>
                    <div className="space-y-2">
                      {docDetail.pages.map((p) => (
                        <div
                          key={p.id}
                          className="p-3 rounded-2xl border border-gray-100 bg-gray-50/70 text-xs"
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-semibold text-gray-800">
                              Page {p.page_number}
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-200 text-gray-700">
                              {p.review_status}
                            </span>
                          </div>
                          <p className="text-gray-600 line-clamp-3 leading-relaxed font-mono text-[11px]">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <form
            onSubmit={handleUploadSubmit}
            className="bg-white rounded-3xl border border-gray-100 shadow-2xl max-w-lg w-full overflow-hidden"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-purple-600" />
                <h2 className="text-sm font-semibold text-gray-800">Upload Official Government Order</h2>
              </div>
              <button
                type="button"
                onClick={() => setUploadOpen(false)}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {uploadError && (
                <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Document Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Revision of Dearness Allowance Rates 2026"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-800 outline-none focus:border-purple-400"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    GO / Circular Number
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. UK/FIN/2026/1042"
                    value={uploadGoNum}
                    onChange={(e) => setUploadGoNum(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-800 outline-none focus:border-purple-400"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Department
                  </label>
                  <select
                    value={uploadDept}
                    onChange={(e) => setUploadDept(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-800 outline-none bg-white focus:border-purple-400"
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
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Security Classification
                </label>
                <select
                  value={uploadClass}
                  onChange={(e) => setUploadClass(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-800 outline-none bg-white focus:border-purple-400"
                >
                  <option value="PUBLIC">PUBLIC</option>
                  <option value="INTERNAL">INTERNAL</option>
                  <option value="RESTRICTED">RESTRICTED</option>
                  <option value="CONFIDENTIAL">CONFIDENTIAL</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  PDF Document File <span className="text-rose-500">*</span>
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-gray-600 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-purple-50 file:text-purple-700 hover:file:bg-purple-100 cursor-pointer"
                />
                <p className="text-[10px] text-gray-400 mt-1">
                  File will be verified through InputValidator (magic bytes &amp; security gate).
                </p>
              </div>
            </div>

            <div className="px-6 py-3.5 border-t border-gray-100 bg-gray-50/70 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setUploadOpen(false)}
                className="px-4 py-2 text-xs font-medium text-gray-500 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploading || !uploadFile || !uploadTitle.trim()}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 text-white text-xs font-semibold shadow-xs transition-all flex items-center gap-1.5"
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
