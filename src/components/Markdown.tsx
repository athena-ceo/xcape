// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

// Renders assistant answers (Markdown) with sanitization. Compact spacing so it sits
// nicely inside a chat bubble.
export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed [&_p]:my-1 [&_ul]:my-1 [&_ul]:pl-5 [&_ul]:list-disc [&_ol]:my-1 [&_ol]:pl-5 [&_ol]:list-decimal [&_li]:my-0.5 [&_a]:text-turquoise-600 [&_a]:underline [&_strong]:font-medium [&_h1]:text-base [&_h2]:text-base [&_h3]:text-sm [&_h1]:font-medium [&_h2]:font-medium [&_h3]:font-medium">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
