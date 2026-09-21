/**
 * Minimal Markdown renderer for model answers.
 *
 * The models emit Markdown (`**bold**`, bullet lists, headings, inline code),
 * which would otherwise print with literal asterisks. This renders the formatted
 * elements safely without dangerouslySetInnerHTML.
 */
import { Fragment, type ReactNode } from 'react';

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
          className="px-1.5 py-0.5 rounded bg-purple-50 text-purple-900 border border-purple-100 font-mono text-[0.88em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={key} className="font-semibold text-gray-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={key} className="italic">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <Fragment key={key}>{part}</Fragment>;
  });
}

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'h'; level: number; text: string }
  | { kind: 'hr' };

const HEADING = /^\s{0,3}(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*+•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const RULE = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/;

/** Group lines into blocks, merging runs of list items and paragraph lines. */
function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];

  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(/\s+$/, '');
    const last = blocks[blocks.length - 1];

    if (line.trim() === '') {
      if (last && last.kind === 'p') blocks.push({ kind: 'p', lines: [] });
      continue;
    }

    const rule = RULE.exec(line);
    if (rule) {
      blocks.push({ kind: 'hr' });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: 'h', level: heading[1].length, text: heading[2] });
      continue;
    }

    const numbered = NUMBERED.exec(line);
    if (numbered) {
      if (last && last.kind === 'ol') last.items.push(numbered[1]);
      else blocks.push({ kind: 'ol', items: [numbered[1]] });
      continue;
    }

    const bullet = BULLET.exec(line);
    if (bullet) {
      if (last && last.kind === 'ul') last.items.push(bullet[1]);
      else blocks.push({ kind: 'ul', items: [bullet[1]] });
      continue;
    }

    if (last && last.kind === 'p' && last.lines.length > 0) last.lines.push(line);
    else blocks.push({ kind: 'p', lines: [line] });
  }

  return blocks.filter((b) => b.kind !== 'p' || b.lines.length > 0);
}

/** Renders a model answer as formatted prose matching the purple/gray UI design. */
export function Markdown({ text }: { text: string }) {
  const blocks = parseBlocks(text);

  return (
    <div className="space-y-2.5">
      {blocks.map((block, bi) => {
        const key = `b${bi}`;

        switch (block.kind) {
          case 'hr':
            return <hr key={key} className="border-gray-200 my-3" />;

          case 'h': {
            const size =
              block.level <= 2 ? 'text-[15px]' : block.level === 3 ? 'text-sm' : 'text-xs';
            return (
              <p key={key} className={`${size} font-semibold text-gray-900 mt-3 first:mt-0`}>
                {renderInline(block.text, key)}
              </p>
            );
          }

          case 'ul':
            return (
              <ul key={key} className="list-disc pl-5 space-y-1 marker:text-purple-500">
                {block.items.map((item, ii) => (
                  <li key={`${key}-${ii}`}>{renderInline(item, `${key}-${ii}`)}</li>
                ))}
              </ul>
            );

          case 'ol':
            return (
              <ol key={key} className="list-decimal pl-5 space-y-1 marker:text-purple-500">
                {block.items.map((item, ii) => (
                  <li key={`${key}-${ii}`}>{renderInline(item, `${key}-${ii}`)}</li>
                ))}
              </ol>
            );

          default:
            return (
              <p key={key} className="leading-relaxed text-gray-800">
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
