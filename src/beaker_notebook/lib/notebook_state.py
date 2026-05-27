import json
from typing import Any, Optional, TypedDict, Callable
from xml.sax.saxutils import escape as _xml_escape, quoteattr as _xml_quoteattr

import nbformat
from nbformat import NotebookNode

from beaker_notebook.lib.utils import normalize_notebook

DEFAULT_TRUNCATION_LIMIT = 200
DEFAULT_TRUNCATION_RATIO = (4/5)


def _block(tag: str, attributes: dict[str, Any], *contents: str|None) -> str:
    attr_str = " ".join(
        f'{key}={_xml_quoteattr("" if value is None else str(value))}'
        for key, value in attributes.items()
    )
    header = f'<{tag} {attr_str}>' if attr_str else f'<{tag}>'
    footer = f'</{tag}>'
    return "\n".join((
        section for section in (
            header,
            *contents,
            footer,
        )
        if section is not None
    ))


def _truncate(value: str, limit: int = DEFAULT_TRUNCATION_LIMIT, ratio: float = DEFAULT_TRUNCATION_RATIO) -> str:
    if len(value) <= limit:
        return value
    split = int(limit * ratio)
    remainder = limit - split
    chars_removed = len(value) - limit
    return f"{value[:split]}<... {chars_removed} characters truncated ...>{value[-remainder:]}"


def _query_content(cell: NotebookNode) -> str:
    metadata = cell.get("metadata", {}) or {}
    return metadata.get("prompt", "") or cell.get("source", "")

def _thought_content(cell: NotebookNode) -> str:
    metadata = cell.get("metadata", {}) or {}
    thought = metadata.get("thought", {}) or {}
    if isinstance(thought, dict):
        return thought.get("thought", "") or cell.get("source", "")
    return str(thought)

def _response_content(cell: NotebookNode) -> str:
    return cell.source

def _default_content(cell: NotebookNode) -> str:
    return cell.source

cell_content_dispatch: dict[str, Callable[[NotebookNode], str]] = {
    "query": _query_content,
    "thought": _thought_content,
    "response": _response_content,
    "default": _default_content,
}

def _maybe_truncate(value: str, truncate: bool) -> str:
    return _truncate(value) if truncate else value


_MULTIMEDIA_PREFIXES = ("image/", "audio/", "video/")


def is_multimedia_mimetype(mimetype: str) -> bool:
    return mimetype.startswith(_MULTIMEDIA_PREFIXES)


def _include_mimetype(mimetype: str, exclude_media: bool) -> bool:
    if not exclude_media:
        return True
    return not is_multimedia_mimetype(mimetype)


def _data_record_attrs(mimetype: str, ref: str) -> dict[str, str]:
    attrs: dict[str, str] = {"mimetype": mimetype}
    if is_multimedia_mimetype(mimetype):
        attrs["ref"] = f"{ref}:{mimetype}"
    return attrs


def _stream_output(output: NotebookNode, ref: str, truncate: bool=True, exclude_media: bool=False) -> str:
    stream_content = _maybe_truncate(output.text, truncate)
    text = _block("text", {}, _xml_escape(stream_content))
    return _block(
        "output",
        {"type": output.output_type, "name": output.get("name")},
        text,
    )

def _display_data_output(output: NotebookNode, ref: str, truncate: bool=True, exclude_media: bool=False) -> str:
    data_values = "\n".join(
        _block(
            "data-record",
            _data_record_attrs(mimetype, ref),
            _xml_escape(_maybe_truncate(value, truncate)),
        )
        for mimetype, value in output.data.items()
        if _include_mimetype(mimetype, exclude_media)
    )
    metadata_values = "\n".join(
        _block(
            "metadata-record",
            {"mimetype": mimetype},
            _xml_escape(_maybe_truncate(json.dumps(value), truncate)),
        )
        for mimetype, value in output.metadata.items()
    )
    data = _block("data", {}, data_values) if data_values else None
    metadata = _block("metadata", {}, metadata_values) if metadata_values else None
    return _block("output", {"type": output.output_type}, data, metadata)

def _execute_result_output(output: NotebookNode, ref: str, truncate: bool=True, exclude_media: bool=False) -> str:
    data_values = "\n".join(
        _block(
            "data-record",
            _data_record_attrs(mimetype, ref),
            _xml_escape(_maybe_truncate(value, truncate)),
        )
        for mimetype, value in output.data.items()
        if _include_mimetype(mimetype, exclude_media)
    )
    metadata_values = "\n".join(
        _block(
            "metadata-record",
            {"mimetype": mimetype},
            _xml_escape(_maybe_truncate(json.dumps(value), truncate)),
        )
        for mimetype, value in output.metadata.items()
    )
    data = _block("data", {}, data_values) if data_values else None
    metadata = _block("metadata", {}, metadata_values) if metadata_values else None
    return _block(
        "output",
        {"type": output.output_type, "execution_count": output.execution_count},
        data,
        metadata,
    )

def _error_output(output: NotebookNode, ref: str, truncate: bool=True, exclude_media: bool=False) -> str:
    traceback = _maybe_truncate((output.traceback or ""), truncate)
    return _block(
        "output",
        {"type": output.output_type, "ename": output.get("ename"), "evalue": output.get("evalue")},
        _block("traceback", {}, _xml_escape(traceback)),
    )

output_dispatch: dict[str, Callable[[NotebookNode, str, bool, bool], str]] = {
    "stream": _stream_output,
    "display_data": _display_data_output,
    "execute_result": _execute_result_output,
    "error": _error_output,
}

def _collect_content(cell, cell_type=None, truncate: bool=True) -> str:
    cell_content_fn = cell_content_dispatch.get(cell_type, cell_content_dispatch["default"])
    cell_content = _truncate(cell_content_fn(cell)) if truncate else cell_content_fn(cell)
    return cell_content

def _collect_outputs(cell: NotebookNode, truncate: bool=True, exclude_media: bool=False) -> str:
    if "outputs" not in cell:
        return ""
    result = []
    for offset, output in enumerate(cell.outputs):
        output_fn = output_dispatch.get(output.output_type, None)
        if output_fn is None:
            raise ValueError(f"Unknown output type '{output.output_type}'")
        ref = f"{cell.id}:output:{offset}"
        result.append(output_fn(output, ref, truncate, exclude_media))
    return "\n".join(result)


def _collect_cells(
    cells: list[NotebookNode],
    truncate_content: bool=True,
    truncate_outputs: bool=True,
    exclude_media: bool=False,
) -> str:
    cell_info = []
    for cell in cells:
        cell_data = format_cell(
            cell,
            truncate_content=truncate_content,
            truncate_outputs=truncate_outputs,
            exclude_media=exclude_media,
        )
        cell_info.append(cell_data)
    return "\n".join(cell_info)


def format_cell(cell: NotebookNode, truncate_content: bool=True, truncate_outputs: bool=True, exclude_media: bool=False) -> str:
    cell_id = cell.get("id", "null")
    cell_metadata = cell.get("metadata", {})
    cell_type = cell_metadata.get("beaker_cell_type", None) or cell.get("cell_type", "unknown")
    cell_content = _collect_content(cell, cell_type, truncate=truncate_content)
    cell_outputs = _collect_outputs(cell, truncate=truncate_outputs, exclude_media=exclude_media)
    content = _block("content", {}, _xml_escape(cell_content)) if cell_content else None
    outputs = _block("outputs", {}, cell_outputs) if cell_outputs else None
    return _block("notebook-cell", {"type": cell_type, "id": cell_id}, content, outputs)


def notebook_state_to_xml(
        notebook_state: dict|NotebookNode,
        notebook_session_id: str,
        notebook_context: dict,
        kernelspec: Optional[dict]=None,
        truncate_content: bool=True,
        truncate_outputs: bool=True,
        exclude_media: bool=False,
) -> str:
    nb: NotebookNode = normalize_notebook(notebook_state)
    metadata = nb.metadata
    if not kernelspec:
        kernelspec = metadata.get("kernelspec", {})
    context_info = _block("context-info", {}, _xml_escape(json.dumps(notebook_context)))
    kernel_info = _block("kernel-info", {}, _xml_escape(json.dumps(kernelspec)))
    cell_info = _collect_cells(
        nb.cells,
        truncate_content=truncate_content,
        truncate_outputs=truncate_outputs,
        exclude_media=exclude_media,
    )
    notebook_cells = _block("notebook-cells", {}, cell_info)
    return _block(
        "notebook",
        {"session-id": notebook_session_id},
        context_info,
        kernel_info,
        notebook_cells,
    )
