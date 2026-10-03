'use client';

import { useState, useEffect } from 'react';
import { CheckSquare, Check, Edit3, FileText, RefreshCw, X } from 'lucide-react';
import type { ReviewPageItem } from '@/lib/types';
import { fetchReviewPages, approveReviewPage, correctReviewPage } from '@/lib/api';

interface ReviewViewProps {
  userId: string;
}

export default function ReviewView({ userId }: ReviewViewProps) {
  const [pages, setPages] = useState<ReviewPageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [correctingPage, setCorrectingPage] = useState<ReviewPageItem | null>(null);
  const [correctionText, setCorrectionText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    const data = await fetchReviewPages('ALL');
    setPages(data);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const handleApprove = async (pageId: string) => {
    await approveReviewPage(pageId, userId);
    setPages((prev) =>
      prev.map((p) => (p.id === pageId ? { ...p, review_status: 'REVIEWED' } : p)),
    );
  };

  const handleStartCorrection = (p: ReviewPageItem) => {
    setCorrectingPage(p);
    setCorrectionText(p.selected_text || p.clean_text || p.ocr_text || '');
  };

  const handleSaveCorrection = async () => {
    if (!correctingPage) return;
    setSubmitting(true);
    await correctReviewPage(correctingPage.id, correctionText, userId);
    setPages((prev) =>
      prev.map((p) =>
        p.id === correctingPage.id
          ? { ...p, review_status: 'CORRECTED', selected_text: correctionText }
          : p,
      ),
    );
    setCorrectingPage(null);
    setSubmitting(false);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#f8fafc] dark:bg-[#090d16] overflow-hidden transition-colors">
      {/* Header */}
      <div className="p-6 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-white/70 dark:bg-[#0d121e]/70 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <CheckSquare className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Human-in-the-Loop QA &amp; Review Queue
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 text-xs font-semibold border border-purple-200/80 dark:border-purple-800">
              {pages.length} Pages In Queue
            </span>
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Phase 02 Quality Gate: Review low-confidence, scanned, or flagged Uttarakhand document transcripts
          </p>
        </div>

        <button
          type="button"
          onClick={load}
          className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 shadow-xs transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-slate-400">
            Loading review queue…
          </div>
        ) : pages.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-slate-400 dark:text-slate-500">
            <CheckSquare className="w-10 h-10 stroke-[1.5] text-emerald-400 mb-2" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Review queue is clear</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              All ingested document pages are auto-approved or already reviewed.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {pages.map((p) => (
              <div
                key={p.id}
                className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-xs flex flex-col gap-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                      <span className="font-semibold text-xs text-slate-900 dark:text-slate-100">
                        {p.document_title}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-[10px] font-mono text-slate-700 dark:text-slate-300">
                        Page {p.page_number}
                      </span>
                    </div>
                    {p.go_number && (
                      <p className="text-[11px] font-mono text-slate-400 mt-0.5">GO: {p.go_number}</p>
                    )}
                  </div>

                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                      p.review_status === 'REVIEWED'
                        ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                        : p.review_status === 'CORRECTED'
                        ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
                        : 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                    }`}
                  >
                    {p.review_status}
                  </span>
                </div>

                {/* Text excerpt preview */}
                <div className="p-3 rounded-xl bg-slate-50/80 dark:bg-[#161d2d] border border-slate-200 dark:border-slate-800 text-xs text-slate-700 dark:text-slate-300 font-mono line-clamp-3 leading-relaxed">
                  {p.selected_text || p.clean_text || '(No text extracted)'}
                </div>

                {/* Actions */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 dark:text-slate-500">
                    <span>Words: {p.word_count}</span>
                    {p.text_confidence !== null && p.text_confidence !== undefined && (
                      <span>Confidence: {p.text_confidence * 100}%</span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleStartCorrection(p)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                      <span>Correct</span>
                    </button>
                    <button
                      type="button"
                      disabled={p.review_status === 'REVIEWED'}
                      onClick={() => handleApprove(p.id)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 text-white text-xs font-semibold transition-colors"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>{p.review_status === 'REVIEWED' ? 'Approved' : 'Approve'}</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Correction Dialog */}
      {correctingPage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl max-w-xl w-full overflow-hidden animate-in zoom-in-95">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Correct Document Page {correctingPage.page_number}
              </h2>
              <button
                type="button"
                onClick={() => setCorrectingPage(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-3">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Original born-digital and OCR text are preserved immutably. Your correction will be saved as an authoritative ReviewAnnotation.
              </p>
              <textarea
                rows={8}
                value={correctionText}
                onChange={(e) => setCorrectionText(e.target.value)}
                className="w-full p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs font-mono text-slate-800 dark:text-slate-100 outline-none focus:border-purple-300/50 dark:focus:border-purple-500/40 focus:reflection-glow-subtle transition-all leading-relaxed resize-none"
              />
            </div>

            <div className="px-6 py-3.5 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-[#131b2c]/70 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setCorrectingPage(null)}
                className="px-4 py-2 text-xs font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleSaveCorrection}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-xs"
              >
                {submitting ? 'Saving…' : 'Save Correction'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
