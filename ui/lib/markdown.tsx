'use client';

/**
 * Enhanced Markdown renderer for ADAM model answers.
 * Supports:
 * - Fenced code blocks (```lang ... ```) with copy-to-clipboard button
 * - Markdown tables (| col | col |) with headers, borders, and zebra striping
 * - Blockquotes (> quote)
 * - Headings (#, ##, ###)
 * - Ordered & Unordered lists
 * - Inline code, bold, italic
 * - Full Dark Mode parity
 */

import React, { Fragment, useState, type ReactNode } from 'react';
import { Copy, Check } from 'lucide-react';

/** Inline code, bold, then italic. Order matters — bold must win over italic. */
const INLINE_PATTERN = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(INLINE_PATTERN).filter((p) => p !== '');

  return parts.map((part, i) => {
    const key = `${keyPrefix}-i${i}`;

    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={key}
          className="px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-950/50 text-purple-900 dark:text-purple-300 border border-purple-200/60 dark:border-purple-800/60 font-mono text-[0.88em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={key} className="font-semibold text-slate-900 dark:text-slate-100">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={key} className="italic text-slate-800 dark:text-slate-200">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <Fragment key={key}>{part}</Fragment>;
  });
}

function CodeBlockCard({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-slate-900 text-slate-100 shadow-sm text-xs">
      <div className="flex items-center justify-between px-3.5 py-1.5 bg-slate-950/80 border-b border-slate-800/80 text-[11px] font-mono text-slate-400">
        <span className="uppercase tracking-wider font-semibold text-purple-400">
          {language || 'code'}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
          title="Copy code to clipboard"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3 text-slate-400" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3.5 overflow-x-auto font-mono text-[12px] leading-relaxed text-slate-200">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function TableBlock({ rows }: { rows: string[][] }) {
  if (rows.length === 0) return null;
  const header = rows[0];
  const body = rows.slice(1);

  return (
    <div className="my-3 overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 shadow-xs">
      <table className="w-full text-left border-collapse text-xs">
        <thead>
          <tr className="bg-slate-50 dark:bg-[#151c2a] border-b border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100">
            {header.map((col, idx) => (
              <th key={idx} className="px-3.5 py-2 font-semibold">
                {renderInline(col.trim(), `th-${idx}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 bg-white dark:bg-[#111726]">
          {body.map((row, ri) => (
            <tr
              key={ri}
              className="hover:bg-purple-50/30 dark:hover:bg-purple-950/20 transition-colors"
            >
              {row.map((cell, ci) => (
                <td key={ci} className="px-3.5 py-2 text-slate-700 dark:text-slate-300">
                  {renderInline(cell.trim(), `td-${ri}-${ci}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'h'; level: number; text: string }
  | { kind: 'hr' }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'code'; language: string; code: string }
  | { kind: 'table'; rows: string[][] };

const HEADING = /^\s{0,3}(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*+•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const RULE = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/;
const BLOCKQUOTE = /^\s*>\s?(.*)$/;
const TABLE_ROW = /^\|(.+)\|$/;
const TABLE_DELIM = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/;

/** Group lines into blocks */
function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = text.split('\n');
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine.replace(/\s+$/, '');

    // Fenced Code Block
    if (line.trim().startsWith('```')) {
      const language = line.trim().slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      blocks.push({ kind: 'code', language, code: codeLines.join('\n') });
      i++;
      continue;
    }

    // Markdown Table
    if (TABLE_ROW.test(line.trim())) {
      const tableRows: string[][] = [];
      while (i < lines.length && TABLE_ROW.test(lines[i].trim())) {
        const rowStr = lines[i].trim();
        // check if separator row like |---|---|
        if (!TABLE_DELIM.test(rowStr)) {
          const cells = rowStr
            .slice(1, -1)
            .split('|')
            .map((c) => c.trim());
          tableRows.push(cells);
        }
        i++;
      }
      if (tableRows.length > 0) {
        blocks.push({ kind: 'table', rows: tableRows });
      }
      continue;
    }

    // Blockquote
    const quoteMatch = BLOCKQUOTE.exec(line);
    if (quoteMatch) {
      const quoteLines: string[] = [quoteMatch[1]];
      i++;
      while (i < lines.length && BLOCKQUOTE.test(lines[i])) {
        const qm = BLOCKQUOTE.exec(lines[i]);
        if (qm) quoteLines.push(qm[1]);
        i++;
      }
      blocks.push({ kind: 'quote', lines: quoteLines });
      continue;
    }

    // Empty line
    if (line.trim() === '') {
      const last = blocks[blocks.length - 1];
      if (last && last.kind === 'p') blocks.push({ kind: 'p', lines: [] });
      i++;
      continue;
    }

    // Rule
    const rule = RULE.exec(line);
    if (rule) {
      blocks.push({ kind: 'hr' });
      i++;
      continue;
    }

    // Heading
    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: 'h', level: heading[1].length, text: heading[2] });
      i++;
      continue;
    }

    // Numbered List
    const numbered = NUMBERED.exec(line);
    if (numbered) {
      const last = blocks[blocks.length - 1];
      if (last && last.kind === 'ol') last.items.push(numbered[1]);
      else blocks.push({ kind: 'ol', items: [numbered[1]] });
      i++;
      continue;
    }

    // Bullet List
    const bullet = BULLET.exec(line);
    if (bullet) {
      const last = blocks[blocks.length - 1];
      if (last && last.kind === 'ul') last.items.push(bullet[1]);
      else blocks.push({ kind: 'ul', items: [bullet[1]] });
      i++;
      continue;
    }

    // Standard paragraph
    const last = blocks[blocks.length - 1];
    if (last && last.kind === 'p' && last.lines.length > 0) {
      last.lines.push(line);
    } else {
      blocks.push({ kind: 'p', lines: [line] });
    }
    i++;
  }

  return blocks.filter((b) => b.kind !== 'p' || b.lines.length > 0);
}

/** Renders a model answer with SaaS-grade typography matching light & dark themes */
export function Markdown({ text }: { text: string }) {
  const blocks = parseBlocks(text);

  return (
    <div className="space-y-2.5">
      {blocks.map((block, bi) => {
        const key = `b${bi}`;

        switch (block.kind) {
          case 'code':
            return <CodeBlockCard key={key} language={block.language} code={block.code} />;

          case 'table':
            return <TableBlock key={key} rows={block.rows} />;

          case 'quote':
            return (
              <blockquote
                key={key}
                className="my-2 border-l-2 border-purple-500 pl-3.5 py-0.5 text-slate-600 dark:text-slate-400 italic text-xs leading-relaxed"
              >
                {block.lines.map((l, li) => (
                  <Fragment key={`${key}-q${li}`}>
                    {li > 0 && <br />}
                    {renderInline(l, `${key}-q${li}`)}
                  </Fragment>
                ))}
              </blockquote>
            );

          case 'hr':
            return <hr key={key} className="border-slate-200 dark:border-slate-800 my-3" />;

          case 'h': {
            const size =
              block.level <= 2 ? 'text-[15px]' : block.level === 3 ? 'text-sm' : 'text-xs';
            return (
              <p
                key={key}
                className={`${size} font-semibold text-slate-900 dark:text-slate-100 mt-3 first:mt-0`}
              >
                {renderInline(block.text, key)}
              </p>
            );
          }

          case 'ul':
            return (
              <ul key={key} className="list-disc pl-5 space-y-1 marker:text-purple-600 dark:marker:text-purple-400 text-xs">
                {block.items.map((item, ii) => (
                  <li key={`${key}-${ii}`}>{renderInline(item, `${key}-${ii}`)}</li>
                ))}
              </ul>
            );

          case 'ol':
            return (
              <ol key={key} className="list-decimal pl-5 space-y-1 marker:text-purple-600 dark:marker:text-purple-400 text-xs">
                {block.items.map((item, ii) => (
                  <li key={`${key}-${ii}`}>{renderInline(item, `${key}-${ii}`)}</li>
                ))}
              </ol>
            );

          default:
            return (
              <p key={key} className="leading-relaxed text-slate-800 dark:text-slate-200 text-xs sm:text-sm">
                {block.lines.map((line, li) => (
                  <Fragment key={`${key}-l${li}`}>
                    {li > 0 && <br />}
                    {renderInline(line, `${key}-l${li}`)}
                  </Fragment>
                ))}
              </p>
            );
        }
      })}
    </div>
  );
}
