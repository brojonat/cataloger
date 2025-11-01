"""Context summary generation for agent context."""

from html.parser import HTMLParser

import structlog

from cataloger.storage.s3 import S3Storage

log = structlog.get_logger()


class HTMLStripper(HTMLParser):
    """Strip HTML tags from text for token efficiency."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_data(self):
        return "".join(self.text)


def strip_html_tags(html: str) -> str:
    """Remove HTML tags from string, keeping only text content.

    Args:
        html: HTML string

    Returns:
        Plain text with tags removed
    """
    stripper = HTMLStripper()
    stripper.feed(html)
    return stripper.get_data()


def generate_context_summary(
    storage: S3Storage,
    prefix: str,
    timestamp: str | None = None,
) -> str:
    """Generate HTML summary of previous catalog context.

    This bundles together:
    - Previous catalog HTML results
    - Previous summary analysis
    - Python scripts that were executed
    - User comments/feedback

    Args:
        storage: S3Storage instance
        prefix: S3 prefix (e.g., "customer-123/orders")
        timestamp: Specific timestamp, or None for latest

    Returns:
        HTML summary document
    """
    # Get the timestamp to use
    if timestamp is None:
        timestamps = storage.list_timestamps(prefix, limit=1)
        if not timestamps:
            log.info("context.no_previous", prefix=prefix)
            return _generate_empty_context_html(prefix)
        timestamp = timestamps[0]

    log.info("context.generate", prefix=prefix, timestamp=timestamp)

    # Fetch all components
    catalog_html = _fetch_optional(storage.read_html, prefix, timestamp, "catalog.html")
    summary_html = _fetch_optional(
        storage.read_html, prefix, timestamp, "recent_summary.html"
    )
    catalog_script = _fetch_optional(
        storage.read_script, prefix, timestamp, "catalog_script.py"
    )
    summary_script = _fetch_optional(
        storage.read_script, prefix, timestamp, "summary_script.py"
    )
    comments = storage.list_comments(prefix, timestamp)

    # Read all comment contents
    comment_contents = []
    for comment_info in comments:
        content = storage.read_comment(prefix, timestamp, comment_info["filename"])
        if content:
            comment_contents.append(
                {
                    "user": comment_info["user"],
                    "date": comment_info["date"],
                    "content": content,
                }
            )

    # Generate HTML summary
    html = _build_context_html(
        prefix=prefix,
        timestamp=timestamp,
        catalog_html=catalog_html,
        summary_html=summary_html,
        catalog_script=catalog_script,
        summary_script=summary_script,
        comments=comment_contents,
    )

    log.info("context.generated", prefix=prefix, timestamp=timestamp, size=len(html))
    return html


def _fetch_optional(func, *args):
    """Fetch content, returning None if not found."""
    try:
        return func(*args)
    except Exception as e:
        log.debug("context.fetch_optional.error", error=str(e))
        return None


def _generate_empty_context_html(prefix: str) -> str:
    """Generate HTML for when there is no previous context."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Context Summary - {prefix}</title>
    <style>
        body {{ font-family: sans-serif; max-width: 1200px; margin: 40px auto; padding: 20px; }}
        .empty {{ color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <h1>Context Summary: {prefix}</h1>
    <p class="empty">No previous catalog found. This will be the first run.</p>
</body>
</html>"""


def _build_context_html(
    prefix: str,
    timestamp: str,
    catalog_html: str | None,
    summary_html: str | None,
    catalog_script: str | None,
    summary_script: str | None,
    comments: list[dict],
) -> str:
    """Build the complete context summary HTML."""

    # Build sections
    sections = []

    # Header
    sections.append(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Context Summary - {prefix}</title>
    <style>
        body {{
            font-family: sans-serif;
            max-width: 1200px;
            margin: 40px auto;
            padding: 20px;
            line-height: 1.6;
        }}
        h1 {{ color: #333; border-bottom: 2px solid #2563eb; padding-bottom: 10px; }}
        h2 {{ color: #2563eb; margin-top: 40px; }}
        h3 {{ color: #666; }}
        .section {{ margin-bottom: 40px; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
        .comment {{
            background: #f8fafc;
            border-left: 4px solid #2563eb;
            padding: 15px;
            margin: 15px 0;
        }}
        .comment-meta {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 8px;
        }}
        .comment-user {{ font-weight: bold; }}
        pre {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        .catalog-content {{
            border: 1px solid #e2e8f0;
            padding: 20px;
            border-radius: 5px;
            background: #ffffff;
        }}
        .empty {{ color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <h1>Context Summary: {prefix}</h1>
    <p class="timestamp">Previous catalog from: <strong>{timestamp}</strong></p>
""")

    # User Comments Section (first, as they're most important for context)
    if comments:
        sections.append('<div class="section">')
        sections.append("<h2>User Comments & Feedback</h2>")
        for comment in comments:
            sections.append(f"""
<div class="comment">
    <div class="comment-meta">
        <span class="comment-user">{comment["user"]}</span>
        <span>({comment["date"]})</span>
    </div>
    <div class="comment-content">{_escape_html(comment["content"])}</div>
</div>
""")
        sections.append("</div>")
    else:
        sections.append('<div class="section">')
        sections.append("<h2>User Comments & Feedback</h2>")
        sections.append('<p class="empty">No comments on previous catalog.</p>')
        sections.append("</div>")

    # Catalog Results
    if catalog_html:
        sections.append('<div class="section">')
        sections.append("<h2>Previous Catalog Results</h2>")
        sections.append('<div class="catalog-content">')
        sections.append(catalog_html)
        sections.append("</div>")
        sections.append("</div>")

    # Summary Analysis
    if summary_html:
        sections.append('<div class="section">')
        sections.append("<h2>Previous Summary Analysis</h2>")
        sections.append('<div class="catalog-content">')
        sections.append(summary_html)
        sections.append("</div>")
        sections.append("</div>")

    # Python Scripts
    if catalog_script or summary_script:
        sections.append('<div class="section">')
        sections.append("<h2>Python Scripts</h2>")

        if catalog_script:
            sections.append("<h3>Catalog Script</h3>")
            sections.append(f"<pre>{_escape_html(catalog_script)}</pre>")

        if summary_script:
            sections.append("<h3>Summary Script</h3>")
            sections.append(f"<pre>{_escape_html(summary_script)}</pre>")

        sections.append("</div>")

    # Footer
    sections.append("</body>")
    sections.append("</html>")

    return "\n".join(sections)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
