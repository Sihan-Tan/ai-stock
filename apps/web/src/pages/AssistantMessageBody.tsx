import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { detectContentKind, tryParseJson } from "./detectContentKind";
import { JsonCodeBlock } from "./JsonCodeBlock";

type Props = {
  content: string;
  streaming: boolean;
};

const mdComponents: Components = {
  pre: ({ children }) => <>{children}</>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  code: ({ className, children, ...rest }) => {
    const text = String(children).replace(/\n$/, "");
    const lang = /language-(\w+)/.exec(className || "")?.[1];
    const isBlock = Boolean(className) || text.includes("\n");
    if (isBlock && lang === "json" && tryParseJson(text) !== null) {
      return <JsonCodeBlock text={text} />;
    }
    if (isBlock) {
      return (
        <pre className="research-md-pre">
          <code className={className} {...rest}>
            {children}
          </code>
        </pre>
      );
    }
    return (
      <code className="research-md-inline-code" {...rest}>
        {children}
      </code>
    );
  },
};

/**
 * 助手消息体：流式纯文本，完成后 Markdown/JSON。
 * @param props.content 消息文本
 * @param props.streaming 是否仍在流式生成
 */
export function AssistantMessageBody({ content, streaming }: Props) {
  if (streaming) {
    return (
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--desk-text)]">
        {content || "…"}
      </pre>
    );
  }

  if (!content.trim()) {
    return (
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--desk-text)]" />
    );
  }

  if (detectContentKind(content) === "json") {
    return <JsonCodeBlock text={content} />;
  }

  return (
    <div className="research-md text-sm text-[var(--desk-text)]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
