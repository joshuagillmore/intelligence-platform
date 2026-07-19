'use client';

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownProps {
  content: string;
  className?: string;
}

/**
 * Renders LLM-generated markdown (reports, hypotheses, topic summaries, chat
 * answers) for the navy dark theme. GFM (tables, strikethrough, etc.) is
 * enabled via remark-gfm. Raw HTML is intentionally NOT enabled (no
 * rehype-raw) to keep untrusted LLM output XSS-safe.
 */
const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-lg font-bold text-gray-100 mt-4 mb-2 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-bold text-gray-100 mt-3 mb-2 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-bold text-gray-100 mt-3 mb-1.5 first:mt-0">{children}</h3>
  ),
  p: ({ children }) => <p className="text-gray-300 leading-relaxed my-2">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-gray-100">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="text-gray-300">{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent-blue underline"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-3">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-navy-600 bg-navy-800 px-3 py-1.5 text-left font-semibold text-gray-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-navy-600 px-3 py-1.5 text-gray-300">{children}</td>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-navy-600 pl-3 italic text-gray-400 my-2">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-navy-700 my-4" />,
  pre: ({ children }) => (
    <pre className="bg-navy-900 border border-navy-700 rounded p-3 overflow-x-auto my-3">
      {children}
    </pre>
  ),
  // react-markdown v9+ no longer passes an `inline` prop to the `code`
  // renderer, so block vs inline code is distinguished by whether remark
  // attached a `language-*` className (only fenced/indented code blocks get
  // one; inline code spans never do).
  code: ({ className, children, ...props }) => {
    const isBlock = /(?:^|\s)language-/.test(className ?? '');
    if (isBlock) {
      return (
        <code className={`font-mono text-xs text-gray-300 ${className ?? ''}`} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="bg-navy-800 text-accent-cyan rounded px-1 py-0.5 text-[0.85em] font-mono"
        {...props}
      >
        {children}
      </code>
    );
  },
};

export default function Markdown({ content, className }: MarkdownProps) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
