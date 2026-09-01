import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { openExternal } from "../accounts";

/**
 * Model-authored prose, rendered.
 *
 * The transcript printed the reply as a plain text node, so a user read
 * `**UNINITIALIZED**` and `- ` and backticks as literal characters -- every
 * list, heading and code span the model wrote arrived as punctuation. This is
 * the only surface that displays this kind of prose for reading: the
 * hypothesis, protocol and report panels put it in a `textarea`, where the
 * Markdown source is the thing being edited and must stay visible.
 *
 * Raw HTML is not enabled. `react-markdown` ignores it unless `rehype-raw` is
 * added, and it is not added: the text comes from a model, over a network, and
 * nothing downstream of here is a trust boundary.
 */

/** Protocols a link may use. Anything else is not a link. */
const SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

export function isSafeHref(href: string): boolean {
  try {
    return SAFE_PROTOCOLS.has(new URL(href).protocol);
  } catch {
    // Relative or unparseable. There is no base document to resolve against
    // in a desktop shell, so it cannot be opened either way.
    return false;
  }
}

/**
 * A link that leaves the application rather than navigating it.
 *
 * The shell is the application's own window: letting a model-authored href
 * navigate it would replace the Workbench with a web page and leave no way
 * back. `open_external` refuses anything that is not http(s), so an unsafe
 * scheme is stopped on the Rust side as well -- but a `javascript:` URL should
 * never be rendered as something clickable in the first place.
 */
function Link({
  href,
  children
}: {
  href?: string;
  children?: React.ReactNode;
}): React.JSX.Element {
  if (!href || !isSafeHref(href)) {
    return <span className="md-link-inert">{children}</span>;
  }
  return (
    <a
      href={href}
      className="md-link"
      onClick={(event) => {
        event.preventDefault();
        void openExternal(href).catch(() => {});
      }}
    >
      {children}
    </a>
  );
}

export function Markdown({ children }: { children: string }): React.JSX.Element {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: Link,
          // A fenced block is horizontally scrollable rather than wrapped:
          // wrapping code changes what it says.
          pre: ({ children }) => <pre className="md-pre">{children}</pre>
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
