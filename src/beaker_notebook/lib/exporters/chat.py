import html
from datetime import date
from typing import Any

from nbformat import NotebookNode
from traitlets.config import default
from nbconvert.exporters.exporter import Exporter
from nbconvert.filters import markdown2html


# Cell label icons — collected here for easy customization
ICON_USER = "\U0001f464"       # 👤
ICON_AGENT = "\U0001f916"      # 🤖
ICON_THOUGHT = "\U0001f4ad"    # 💭
ICON_CODE = "\u2328\ufe0f"     # ⌨️
ICON_NOTEBOOK = "\U0001f4d3"   # 📓

CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #f5f6fa;
  color: #1a1a2e;
  line-height: 1.65;
  padding: 2rem 1rem;
}
.notebook-header {
  max-width: 900px;
  margin: 0 auto 2rem;
  padding: 1.5rem 2rem;
  background: linear-gradient(135deg, #0f3460, #16213e);
  color: white;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
.notebook-header h1 { font-size: 1.5rem; margin-bottom: 0.3rem; }
.notebook-header p { opacity: 0.75; font-size: 0.9rem; }
.cell {
  max-width: 900px;
  margin: 0 auto 1.2rem;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
}
.cell-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 0.4rem 1rem;
}
.cell-content { padding: 1rem 1.4rem; }

/* User cells */
.user-cell { background: #fff; border-left: 4px solid #4361ee; }
.user-cell .cell-label { background: #eef0ff; color: #4361ee; }
.user-cell .cell-content { font-size: 1rem; white-space: pre-wrap; }

/* Agent response cells */
.agent-cell { background: #fff; border-left: 4px solid #0ead69; }
.agent-cell .cell-label { background: #e8faf2; color: #0ead69; }

/* Thought cells */
.thought-cell { background: #fdfcf7; border-left: 4px solid #f4a261; }
.thought-cell .cell-label { background: #fff4e8; color: #e07b39; }

/* Code cells */
.code-cell { background: #1e1e2e; border-left: 4px solid #7c3aed; }
.code-cell .cell-label { background: #2d2b55; color: #a78bfa; }
.code-block {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 1rem 1.4rem;
  font-family: "Fira Code", "Cascadia Code", "Consolas", monospace;
  font-size: 0.82rem;
  overflow-x: auto;
  white-space: pre;
}
.outputs { padding: 0.8rem 1.4rem; background: #fff; border-top: 1px solid #e2e8f0; overflow-x: auto; display: grid; }
.output-stream {
  font-family: monospace;
  font-size: 0.82rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.6rem 0.9rem;
  overflow-x: auto;
  white-space: pre-wrap;
  color: #334155;
  margin-bottom: 0.5rem;
}
.output-error {
  font-family: monospace;
  font-size: 0.82rem;
  background: #fff1f2;
  border: 1px solid #fecdd3;
  border-radius: 6px;
  padding: 0.6rem 0.9rem;
  color: #be123c;
  overflow-x: auto;
  white-space: pre-wrap;
}
.output-image { text-align: center; padding: 0.5rem 0; }
.output-image img { max-width: 100%; border-radius: 6px; box-shadow: 0 1px 6px rgba(0,0,0,0.1); }

/* Markdown body styles */
.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 {
  margin: 1rem 0 0.5rem; color: #1a1a2e;
}
.markdown-body h1 { font-size: 1.4rem; }
.markdown-body h2 { font-size: 1.2rem; }
.markdown-body h3 { font-size: 1.05rem; }
.markdown-body h4 { font-size: 0.95rem; }
.markdown-body p { margin: 0.5rem 0; }
.markdown-body ul, .markdown-body ol { padding-left: 1.5rem; margin: 0.4rem 0; }
.markdown-body li { margin: 0.2rem 0; }
.markdown-body code {
  background: #f1f5f9; padding: 0.1em 0.35em; border-radius: 4px;
  font-family: monospace; font-size: 0.88em; color: #7c3aed;
}
.markdown-body strong { font-weight: 700; color: #0f3460; }
.markdown-body hr { border: none; border-top: 1px solid #e2e8f0; margin: 0.8rem 0; }
.markdown-body blockquote {
  border-left: 3px solid #cbd5e1; padding-left: 0.8rem;
  color: #64748b; margin: 0.5rem 0; font-size: 0.9rem;
}
.markdown-body table {
  border-collapse: collapse; margin: 0.5rem 0; width: 100%;
}
.markdown-body th, .markdown-body td {
  border: 1px solid #e2e8f0; padding: 0.4rem 0.6rem; text-align: left;
}
.markdown-body th { background: #f8fafc; font-weight: 700; }
.md-cell { background: #fff; border-left: 4px solid #94a3b8; }
.md-cell .cell-content { font-size: 0.95rem; }

/* DataFrame / HTML table outputs inside code cells */
.outputs table {
  border-collapse: collapse; margin: 0.5rem 0; width: 100%;
  font-size: 0.82rem; font-family: monospace;
}
.outputs th, .outputs td {
  border: 1px solid #e2e8f0; padding: 0.35rem 0.6rem; text-align: left;
}
.outputs th {
  background: #f1f5f9; font-weight: 700; color: #1a1a2e;
  position: sticky; top: 0;
}
.outputs tr:nth-child(even) { background: #f8fafc; }
.outputs tr:hover { background: #eef0ff; }
"""


def _normalize_source(source: Any) -> str:
    """Normalize cell source to a single string."""
    if isinstance(source, list):
        return "".join(source)
    return source or ""


def _strip_speaker_prefix(text: str) -> str:
    """Strip common speaker prefixes like '**Beaker Agent:**  ' from cell source."""
    prefixes = [
        "**Beaker Agent:**",
        "**Agent Question:**",
        "**User Response:**",
    ]
    stripped = text.lstrip()
    for prefix in prefixes:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].lstrip()
            break
    return stripped


def _render_outputs(outputs: list[dict]) -> str:
    """Render code cell outputs to HTML."""
    if not outputs:
        return ""
    parts: list[str] = []
    for output in outputs:
        output_type = output.get("output_type", "")
        if output_type == "stream":
            text = output.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            parts.append(f'<pre class="output-stream">{html.escape(text)}</pre>')
        elif output_type == "error":
            traceback = output.get("traceback", [])
            text = "\n".join(traceback)
            # Strip ANSI escape codes
            import re
            text = re.sub(r"\x1b\[[0-9;]*m", "", text)
            parts.append(f'<pre class="output-error">{html.escape(text)}</pre>')
        elif output_type in ("display_data", "execute_result"):
            data = output.get("data", {})
            if "image/png" in data:
                b64 = data["image/png"]
                if isinstance(b64, list):
                    b64 = "".join(b64)
                parts.append(
                    f'<div class="output-image">'
                    f'<img src="data:image/png;base64,{b64}">'
                    f'</div>'
                )
            elif "text/html" in data:
                html_content = data["text/html"]
                if isinstance(html_content, list):
                    html_content = "".join(html_content)
                parts.append(html_content)
            elif "text/plain" in data:
                text = data["text/plain"]
                if isinstance(text, list):
                    text = "".join(text)
                parts.append(f'<pre class="output-stream">{html.escape(text)}</pre>')
    if not parts:
        return ""
    return f'<div class="outputs">{"".join(parts)}</div>'


def _render_user_cell(content: str) -> str:
    return (
        f'<div class="cell user-cell">\n'
        f'  <div class="cell-label">{ICON_USER} User</div>\n'
        f'  <div class="cell-content">{html.escape(content)}</div>\n'
        f'</div>'
    )


def _render_agent_cell(source: str) -> str:
    rendered = markdown2html(_strip_speaker_prefix(source))
    return (
        f'<div class="cell agent-cell">\n'
        f'  <div class="cell-label">{ICON_AGENT} Beaker Agent</div>\n'
        f'  <div class="cell-content markdown-body">{rendered}</div>\n'
        f'</div>'
    )


def _render_thought_cell(source: str) -> str:
    rendered = markdown2html(_strip_speaker_prefix(source))
    return (
        f'<div class="cell thought-cell">\n'
        f'  <div class="cell-label">{ICON_THOUGHT} Beaker Agent (thinking)</div>\n'
        f'  <div class="cell-content markdown-body">{rendered}</div>\n'
        f'</div>'
    )


def _render_code_cell(source: str, outputs: list[dict]) -> str:
    outputs_html = _render_outputs(outputs)
    return (
        f'<div class="cell code-cell">\n'
        f'  <div class="cell-label">{ICON_CODE} Code</div>\n'
        f'  <pre class="code-block"><code>{html.escape(source)}</code></pre>\n'
        f'  {outputs_html}\n'
        f'</div>'
    )


def _render_markdown_cell(source: str) -> str:
    rendered = markdown2html(source)
    return (
        f'<div class="cell md-cell">\n'
        f'  <div class="cell-content markdown-body">{rendered}</div>\n'
        f'</div>'
    )


class ChatExporter(Exporter):
    """
    Exports a Beaker notebook as a self-contained HTML chat conversation.
    """
    export_from_notebook = "notebook"
    output_mimetype = "text/html"

    @default("file_extension")
    def _file_extension_default(self) -> str:
        return ".html"

    def from_notebook_node(
        self, nb: NotebookNode, resources: dict | None = None, **kwargs: Any
    ) -> tuple[str, dict]:
        resources = self._init_resources(resources)

        title = nb.metadata.get("title", "Beaker Notebook")
        export_date = date.today().isoformat()

        cell_html_parts: list[str] = []

        for cell in nb.cells:
            meta = cell.get("metadata", {})
            source = _normalize_source(cell.get("source", ""))
            cell_type = cell.get("cell_type", "")
            beaker_type = meta.get("beaker_cell_type")
            outputs = cell.get("outputs", [])

            # Skip original child cells (duplicated by flattened view)
            if meta.get("beakerQueryCellChild"):
                continue

            # Query container cell -> render as User cell from prompt
            if meta.get("parentQueryCell"):
                prompt = _normalize_source(meta.get("prompt", source))
                cell_html_parts.append(_render_user_cell(prompt))
                continue

            # Flattened beaker cells
            if beaker_type == "thought":
                cell_html_parts.append(_render_thought_cell(source))
            elif beaker_type == "code":
                cell_html_parts.append(_render_code_cell(source, outputs))
            elif beaker_type == "response":
                cell_html_parts.append(_render_agent_cell(source))
            elif beaker_type == "user_question":
                cell_html_parts.append(_render_agent_cell(source))
            elif beaker_type == "user_answer":
                cell_html_parts.append(_render_user_cell(source))
            # Plain cells (no beaker metadata)
            elif cell_type == "code":
                cell_html_parts.append(_render_code_cell(source, outputs))
            elif cell_type == "markdown":
                cell_html_parts.append(_render_markdown_cell(source))
            # raw cells or anything else: skip
            else:
                continue

        body = "\n".join(cell_html_parts)

        output = (
            f'<!DOCTYPE html>\n'
            f'<html lang="en">\n'
            f'<head>\n'
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>Beaker Notebook — {html.escape(title)}</title>\n'
            f'<style>\n{CSS}</style>\n'
            f'</head>\n'
            f'<body>\n'
            f'<div class="notebook-header">\n'
            f'  <h1>{ICON_NOTEBOOK} {html.escape(title)}</h1>\n'
            f'  <p>Beaker Notebook · Exported {export_date}</p>\n'
            f'</div>\n\n'
            f'{body}\n'
            f'</body>\n'
            f'</html>\n'
        )

        return output, resources
