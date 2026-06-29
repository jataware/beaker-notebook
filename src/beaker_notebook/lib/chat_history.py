"""Beaker-specific, round-trippable serialization envelope for agent chat history.

This module defines :class:`BeakerChatHistoryDoc`, a versioned envelope that
wraps an Archytas :class:`~archytas.chat_history.ChatHistory` for inclusion in a
saved notebook. It adds two things on top of the Archytas serde:

  * A Beaker *envelope* schema (:data:`BEAKER_CHAT_HISTORY_SCHEMA`), versioned
    independently of the Archytas envelope it carries, reified via the same
    :class:`~archytas.chat_history.SerdeSchema` mechanism so the format can be
    inspected, compared, and versioned. A change to the Beaker envelope
    (metadata block, compression) bumps this schema; Archytas message/record
    drift bumps the Archytas schemas instead.
  * An optional *cell-link* overlay (:data:`CELL_LINKS_SCHEMA`, versioned on its
    own so the link shape can drift independently of the envelope) mapping
    chat-history record ``uuid``s to the notebook cell(s) they produced. The
    overlay is advisory only: a missing, partial, or stale mapping never
    prevents the history from being reconstructed, so the history stays fully
    functional when notebook cells drift (deleted, edited, reordered, or never
    matched). Full message bodies are always retained -- cell links are an
    overlay, not a storage dependency, so there is no dedupe-by-reference.

The link value is a small tagged union keyed by message kind, because the
record types map to cells differently:

  * ``human`` -- the ReAct-loop-initiating ``HumanMessage``; maps to one query
    cell.
  * ``ai`` -- an ``AIMessage`` carrying a thought plus tool calls; maps to an
    optional thought cell and, per tool call, zero-or-more cells (a list, so a
    single tool call that emits several cells is representable).
  * ``tool`` -- a ``ToolMessage`` (a tool result); maps to zero-or-more cells
    for its one tool call.

Cardinality is encoded by the ``cells`` lists, so no per-tool schema variants
are needed: ``run_code`` happens to be one code cell today, but a tool that
emits several cells, or none, fits the same shape. Within a ``cells`` list,
presence vs. absence is meaningful for drift diagnosis: a tool call that
*should* have a cell but could not be matched carries an empty ``cells`` list,
whereas a non-cell-bearing tool call is simply omitted from ``tool_calls``.

On save, the agent's ``system_message`` and ``system_preamble`` are
intentionally dropped from the wrapped Archytas payload: both are regenerated
from the agent/context at load time, so persisting a snapshot would only risk
staleness. The ``user_preamble`` is retained -- it can carry user-authored text
that cannot be regenerated. (Archytas serializes all three faithfully; the
omission is Beaker's load-policy choice, applied here.)

The inner Archytas history payload may optionally be stored as base64-encoded
gzip to keep large histories compact; the envelope (schema, metadata, cell
links) is always left in cleartext so the document remains inspectable without
decompression.

Scope: this module handles the *format* only. Computing cell links from a live
notebook and wiring save/load/rehydration into the notebook file are handled
elsewhere (see beaker-notebook#225).
"""

import base64
import copy
import gzip
import json
import warnings
from dataclasses import dataclass, field, asdict
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Collection,
    Mapping,
    Optional,
    Union,
)

from archytas.chat_history import ChatHistory, SerdeSchema

if TYPE_CHECKING:
    from archytas.models.base import BaseArchytasModel

__all__ = [
    "BEAKER_CHAT_HISTORY_SCHEMA",
    "CELL_LINKS_SCHEMA",
    "CellRef",
    "ToolCallLink",
    "HumanCellLink",
    "AICellLink",
    "ToolCellLink",
    "CellLink",
    "BeakerChatHistoryDoc",
]


# Envelope schema for the Beaker chat-history document. Versioned independently
# of the Archytas ``CHAT_HISTORY_SCHEMA`` it wraps.
BEAKER_CHAT_HISTORY_SCHEMA = SerdeSchema(name="beaker.ChatHistory", version=1)

# Schema for the cell-link overlay. Versioned separately from the envelope so
# the (more volatile) link shape can evolve without bumping the document schema.
CELL_LINKS_SCHEMA = SerdeSchema(name="beaker.ChatHistoryCellLinks", version=1)

# Histories whose serialized Archytas payload exceeds this many bytes are
# gzip+base64 compressed when ``compress="auto"``.
DEFAULT_COMPRESS_THRESHOLD = 64 * 1024

# Encoding markers for the inner ``history`` payload.
_ENCODING_JSON = "json"
_ENCODING_GZIP_B64 = "gzip+base64"

# Fields in the Archytas history payload that Beaker intentionally clears when
# saving. Both are regenerated from the agent/context at load time, so a stored
# snapshot would only go stale. The user preamble is deliberately NOT listed --
# it can carry user-authored text that cannot be regenerated.
_OMITTED_HISTORY_FIELDS = ("system_message", "system_preamble")

# Sentinel so callers can omit summarizers (letting Archytas apply its own
# defaults) while still being able to pass ``None`` to disable them explicitly.
_UNSET: Any = object()


def _check_schema(data: Mapping[str, Any], expected: SerdeSchema, key: str = "format") -> None:
    """Warn (never raise) when the document's declared schema is absent or drifts.

    Mirrors the lenient posture of the Archytas serde: older/newer envelopes are
    still loaded best-effort, but the drift is surfaced for inspection.
    """
    raw = data.get(key)
    if not raw:
        warnings.warn(
            f"Beaker chat-history document is missing a '{key}' schema marker; "
            f"expected {expected.to_dict()}. Attempting to load anyway.",
            stacklevel=3,
        )
        return
    found = SerdeSchema.from_dict(raw)
    if not found.is_compatible(expected):
        warnings.warn(
            f"Beaker chat-history document schema {found.to_dict()} is not "
            f"compatible with expected {expected.to_dict()}. Attempting to load anyway.",
            stacklevel=3,
        )


def _compress_history(payload: Mapping[str, Any]) -> str:
    """gzip+base64 a JSON-compatible payload into an ASCII string."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def _decompress_history(blob: str) -> dict[str, Any]:
    """Inverse of :func:`_compress_history`."""
    raw = gzip.decompress(base64.b64decode(blob.encode("ascii")))
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# Cell-link overlay value types (tagged union keyed by message ``kind``).
# ---------------------------------------------------------------------------


@dataclass
class CellRef:
    """A single notebook cell, tagged with its ``beaker_cell_type``.

    ``cell_type`` is the cell's role (``code``, ``user_question``, ``response``,
    ``error`` ...); ``cell`` is its notebook cell id.
    """

    cell: str
    cell_type: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.cell_type, "cell": self.cell}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CellRef":
        return cls(cell=data["cell"], cell_type=data["type"])


@dataclass
class ToolCallLink:
    """The cell(s) produced by a single tool call.

    ``cells`` holds zero-or-more :class:`CellRef`. An empty list marks a
    cell-bearing tool call whose cell could not be matched (drift); a tool call
    that never produces a cell is simply omitted from its message's
    ``tool_calls`` rather than carried as an empty entry.
    """

    tool: str
    cells: list[CellRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "cells": [c.to_dict() for c in self.cells]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ToolCallLink":
        return cls(
            tool=data["tool"],
            cells=[CellRef.from_dict(c) for c in data.get("cells") or []],
        )


@dataclass
class HumanCellLink:
    """Link for a ``HumanMessage`` (the loop-initiating query) -> one query cell.

    ``cell`` is ``None`` when no query cell could be matched (drift).
    """

    kind: ClassVar[str] = "human"
    cell: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "cell": self.cell}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HumanCellLink":
        return cls(cell=data.get("cell"))


@dataclass
class AICellLink:
    """Link for an ``AIMessage`` -> an optional thought cell plus per-tool-call cells.

    ``thought_cell`` is ``None`` for the terminal AIMessage (``final_answer`` /
    ``fail_task`` thoughts are not rendered) or when a thought cell could not be
    matched. ``tool_calls`` is keyed by ``tool_call_id``.
    """

    kind: ClassVar[str] = "ai"
    thought_cell: Optional[str] = None
    tool_calls: dict[str, ToolCallLink] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "thought_cell": self.thought_cell,
            "tool_calls": {
                tool_call_id: link.to_dict()
                for tool_call_id, link in self.tool_calls.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AICellLink":
        return cls(
            thought_cell=data.get("thought_cell"),
            tool_calls={
                tool_call_id: ToolCallLink.from_dict(link)
                for tool_call_id, link in (data.get("tool_calls") or {}).items()
            },
        )


@dataclass
class ToolCellLink:
    """Link for a ``ToolMessage`` (one tool result) -> zero-or-more cells.

    Carries ``tool_call_id``/``tool`` so a tool result resolves to its cell(s)
    directly, without having to walk back to the calling AIMessage.
    """

    kind: ClassVar[str] = "tool"
    tool_call_id: str = ""
    tool: str = ""
    cells: list[CellRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tool_call_id": self.tool_call_id,
            "tool": self.tool,
            "cells": [c.to_dict() for c in self.cells],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ToolCellLink":
        return cls(
            tool_call_id=data.get("tool_call_id", ""),
            tool=data.get("tool", ""),
            cells=[CellRef.from_dict(c) for c in data.get("cells") or []],
        )


CellLink = Union[HumanCellLink, AICellLink, ToolCellLink]

_CELL_LINK_TYPES: dict[str, type] = {
    HumanCellLink.kind: HumanCellLink,
    AICellLink.kind: AICellLink,
    ToolCellLink.kind: ToolCellLink,
}


def _cell_link_from_dict(data: Mapping[str, Any]) -> CellLink:
    """Dispatch a serialized cell link to its concrete type by ``kind``."""
    kind = data.get("kind")
    link_cls = _CELL_LINK_TYPES.get(kind)
    if link_cls is None:
        raise ValueError(f"Unknown cell-link kind: {kind!r}")
    return link_cls.from_dict(data)


def _link_cell_ids(link: CellLink) -> list[str]:
    """All notebook cell ids referenced by a single link (order-preserving)."""
    if isinstance(link, HumanCellLink):
        return [link.cell] if link.cell else []
    if isinstance(link, AICellLink):
        ids: list[str] = []
        if link.thought_cell:
            ids.append(link.thought_cell)
        for tool_call in link.tool_calls.values():
            ids.extend(ref.cell for ref in tool_call.cells)
        return ids
    if isinstance(link, ToolCellLink):
        return [ref.cell for ref in link.cells]
    return []


@dataclass
class Model:
    """
    A round-trippable representation of the model associated with the chat history

    If the model changes, any token counts are no longer trustworthy and should be invalidated.
    """

    provider: str
    model_name: str
    context_window: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Model":
        return cls(**data)



@dataclass
class BeakerChatHistoryDoc:
    """A versioned, round-trippable Beaker envelope around an Archytas ChatHistory.

    Attributes:
        history: The wrapped Archytas chat history.
        cell_links: Advisory mapping of chat-history record ``uuid`` ->
            :class:`CellLink`. Optional and lossy by design (see module
            docstring).
        metadata: Beaker-specific, non-reconstructive metadata (e.g. context
            slug). Free-form and round-tripped verbatim.
    """

    history: ChatHistory
    cell_links: dict[str, CellLink] = field(default_factory=dict)
    model: Model = field(default_factory=lambda: Model(provider="None", model_name="None"))
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_history(
        cls,
        history: ChatHistory,
        cell_links: Optional[Mapping[str, CellLink]] = None,
        model: Optional[Model] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "BeakerChatHistoryDoc":
        """Build a document from a live history plus an optional cell-link overlay."""
        return cls(
            history=history,
            cell_links=dict(cell_links or {}),
            model=model,
            metadata=dict(metadata or {}),
        )

    # -- cell-link helpers ---------------------------------------------------

    def link_for(self, record_uuid: str) -> Optional[CellLink]:
        """Return the :class:`CellLink` for ``record_uuid``, or ``None``."""
        return self.cell_links.get(record_uuid)

    def referenced_cell_ids(self) -> set[str]:
        """All notebook cell ids referenced anywhere in the overlay."""
        ids: set[str] = set()
        for link in self.cell_links.values():
            ids.update(_link_cell_ids(link))
        return ids

    def prune_cell_links(self, valid_cell_ids: Collection[str]) -> list[str]:
        """Drop references to cells no longer present in the notebook.

        Removes any :class:`CellRef` (and nulls any scalar ``cell`` /
        ``thought_cell``) whose target is not in ``valid_cell_ids``, leaving the
        record entries in place so a now-empty link still documents the drift.
        Returns the removed cell ids (with multiplicity). The history itself is
        unaffected.
        """
        valid = set(valid_cell_ids)
        dropped: list[str] = []

        def _filter(cells: list[CellRef]) -> list[CellRef]:
            kept: list[CellRef] = []
            for ref in cells:
                if ref.cell in valid:
                    kept.append(ref)
                else:
                    dropped.append(ref.cell)
            return kept

        for link in self.cell_links.values():
            if isinstance(link, HumanCellLink):
                if link.cell is not None and link.cell not in valid:
                    dropped.append(link.cell)
                    link.cell = None
            elif isinstance(link, AICellLink):
                if link.thought_cell is not None and link.thought_cell not in valid:
                    dropped.append(link.thought_cell)
                    link.thought_cell = None
                for tool_call in link.tool_calls.values():
                    tool_call.cells = _filter(tool_call.cells)
            elif isinstance(link, ToolCellLink):
                link.cells = _filter(link.cells)

        return dropped

    # -- serde ---------------------------------------------------------------

    def to_dict(
        self,
        compress: bool | str = False,
        compress_threshold: int = DEFAULT_COMPRESS_THRESHOLD,
    ) -> dict[str, Any]:
        """Serialize to a JSON-compatible envelope document.

        Args:
            compress: ``True``/``False`` (default) to force or forbid
                gzip+base64 of the inner Archytas history payload, or ``"auto"``
                to compress only when the serialized payload exceeds
                ``compress_threshold`` bytes.
            compress_threshold: Byte threshold for ``compress="auto"``.
        """
        history_payload = self.history.to_dict()

        if isinstance(compress, str):
            if compress != "auto":
                raise ValueError(f"Unknown compress mode: {compress!r}")
            measured = len(
                json.dumps(history_payload, separators=(",", ":")).encode("utf-8")
            )
            do_compress = measured > compress_threshold
        else:
            do_compress = bool(compress)

        if do_compress:
            history_field: Any = _compress_history(history_payload)
            encoding = _ENCODING_GZIP_B64
        else:
            history_field = history_payload
            encoding = _ENCODING_JSON

        metadata = copy.deepcopy(self.metadata)
        metadata["omissions_on_save"] = _OMITTED_HISTORY_FIELDS

        return {
            "format": BEAKER_CHAT_HISTORY_SCHEMA.to_dict(),
            "cell_links_format": CELL_LINKS_SCHEMA.to_dict(),
            "metadata": metadata,
            "cell_links": {
                record_uuid: link.to_dict()
                for record_uuid, link in self.cell_links.items()
            },
            "history_encoding": encoding,
            "history": history_field,
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        model: Optional["BaseArchytasModel"] = None,
        loop_summarizer: Optional[Callable] = _UNSET,
        history_summarizer: Optional[Callable] = _UNSET,
    ) -> "BeakerChatHistoryDoc":
        """Reconstruct from :meth:`to_dict` output.

        ``model`` and the summarizers are not should not be rehydrated from
        the serialized document as model is a runtime concern. Therefore we
        supply live ones to attach to the reconstructed :class:`ChatHistory`.
        Omit the summarizers to let Archytas apply its own defaults, or pass
        ``None`` to disable them explicitly. Individual cell links that cannot
        be parsed are skipped with a warning rather than failing the load --
        the overlay is advisory.
        """
        _check_schema(data, expected=BEAKER_CHAT_HISTORY_SCHEMA)

        encoding = data.get("history_encoding", _ENCODING_JSON)
        history_field = data.get("history")
        if encoding == _ENCODING_GZIP_B64:
            if not isinstance(history_field, str):
                raise ValueError(
                    "history_encoding is 'gzip+base64' but 'history' is not a string."
                )
            history_payload = _decompress_history(history_field)
        elif encoding == _ENCODING_JSON:
            history_payload = dict(history_field or {})
        else:
            raise ValueError(f"Unknown history_encoding: {encoding!r}")

        history_kwargs: dict[str, Any] = {"model": model}
        if loop_summarizer is not _UNSET:
            history_kwargs["loop_summarizer"] = loop_summarizer
        if history_summarizer is not _UNSET:
            history_kwargs["history_summarizer"] = history_summarizer
        history = ChatHistory.from_dict(history_payload, **history_kwargs)

        raw_links = data.get("cell_links") or {}
        if raw_links:
            _check_schema(data, expected=CELL_LINKS_SCHEMA, key="cell_links_format")
        cell_links: dict[str, CellLink] = {}
        for record_uuid, raw in raw_links.items():
            try:
                cell_links[record_uuid] = _cell_link_from_dict(raw)
            except (KeyError, ValueError, TypeError) as exc:
                warnings.warn(
                    f"Skipping unparseable cell link for record {record_uuid!r}: {exc}",
                    stacklevel=2,
                )

        return cls(
            history=history,
            cell_links=cell_links,
            metadata=dict(data.get("metadata") or {}),
        )
