"""
Tests for beaker_notebook.lib.chat_history (BeakerChatHistoryDoc serde).

Covers:
- envelope schema marker + JSON-serializability
- round-trip preservation of records, uuids, react_loop_id, summaries
- structured cell-link overlay (human / ai / tool kinds, cells lists)
- cell-link round-trip, drift handling (prune / empty cells), lenient skip
- beaker metadata round-trip
- compression: forced on/off, "auto" thresholding, cleartext envelope
- lenient schema checking (warns, never raises) on missing/incompatible markers
- from_dict summarizer passthrough vs. default
"""

import json
import warnings

import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from archytas.chat_history import ChatHistory, MessageRecord, SummaryRecord

from beaker_notebook.lib.chat_history import (
    BEAKER_CHAT_HISTORY_SCHEMA,
    CELL_LINKS_SCHEMA,
    AICellLink,
    BeakerChatHistoryDoc,
    CellRef,
    HumanCellLink,
    ToolCallLink,
    ToolCellLink,
)


# -- fixtures / helpers --


def _make_history() -> ChatHistory:
    """A history with a system message, three raw records, and one summary.

    Records model one ReAct step: a query (Human), a thought + run_code call
    (AI), and the run_code result (Tool).
    """
    history = ChatHistory(
        messages=[
            HumanMessage(content="what is 2 + 2?"),
            AIMessage(content="computing the sum"),
        ]
    )
    history.add_message(ToolMessage(content="4", tool_call_id="tc1"))
    history.set_system_message("you are a test agent")
    for record in history.raw_records:
        record.react_loop_id = 7
    history.summaries.append(
        SummaryRecord(
            message=SystemMessage(content="summary of earlier turns"),
            summarized_messages={"alpha", "beta"},
        )
    )
    return history


def _make_links(history: ChatHistory) -> dict:
    """A representative overlay: human query, ai thought + tool call, tool result."""
    human_uuid, ai_uuid, tool_uuid = (r.uuid for r in history.raw_records)
    code_ref = CellRef(cell="code-cell", cell_type="code")
    return {
        human_uuid: HumanCellLink(cell="query-cell"),
        ai_uuid: AICellLink(
            thought_cell="thought-cell",
            tool_calls={"tc1": ToolCallLink(tool="run_code", cells=[code_ref])},
        ),
        tool_uuid: ToolCellLink(
            tool_call_id="tc1", tool="run_code", cells=[CellRef(cell="code-cell", cell_type="code")]
        ),
    }


@pytest.fixture
def history() -> ChatHistory:
    return _make_history()


@pytest.fixture
def doc(history: ChatHistory) -> BeakerChatHistoryDoc:
    return BeakerChatHistoryDoc.from_history(
        history,
        cell_links=_make_links(history),
        metadata={"context": "test"},
    )


# -- envelope / schema --


def test_to_dict_carries_schema_markers(doc):
    data = doc.to_dict()
    assert data["format"] == BEAKER_CHAT_HISTORY_SCHEMA.to_dict()
    assert data["format"] == {"schema": "beaker.ChatHistory", "version": 1}
    assert data["cell_links_format"] == CELL_LINKS_SCHEMA.to_dict()
    assert data["cell_links_format"] == {"schema": "beaker.ChatHistoryCellLinks", "version": 1}


def test_to_dict_is_json_serializable(doc):
    # Must survive a real JSON encode/decode (notebook metadata is JSON).
    encoded = json.dumps(doc.to_dict())
    assert isinstance(encoded, str)
    json.loads(encoded)


# -- round-trip preservation (history) --


def test_round_trip_preserves_records_and_uuids(doc, history):
    orig_uuids = [r.uuid for r in history.raw_records]
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))

    assert [r.uuid for r in restored.history.raw_records] == orig_uuids
    assert restored.history.raw_records[0].message.text == "what is 2 + 2?"
    assert restored.history.raw_records[2].message.text == "4"


def test_round_trip_preserves_react_loop_id(doc):
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))
    assert [r.react_loop_id for r in restored.history.raw_records] == [7, 7, 7]


def test_round_trip_preserves_summaries(doc, history):
    sum_uuid = history.summaries[0].uuid
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))

    assert len(restored.history.summaries) == 1
    summary = restored.history.summaries[0]
    assert isinstance(summary, SummaryRecord)
    assert summary.uuid == sum_uuid
    assert summary.summarized_messages == {"alpha", "beta"}


def test_round_trip_preserves_metadata(doc):
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))
    assert restored.metadata == {"context": "test"}


# -- structured cell links --


def test_round_trip_preserves_structured_cell_links(doc, history):
    expected = _make_links(history)
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))
    assert restored.cell_links == expected


def test_cell_link_value_shapes_in_serialized_form(doc, history):
    human_uuid, ai_uuid, tool_uuid = (r.uuid for r in history.raw_records)
    data = doc.to_dict(compress=False)["cell_links"]

    assert data[human_uuid] == {"kind": "human", "cell": "query-cell"}
    assert data[ai_uuid] == {
        "kind": "ai",
        "thought_cell": "thought-cell",
        "tool_calls": {
            "tc1": {"tool": "run_code", "cells": [{"type": "code", "cell": "code-cell"}]}
        },
    }
    assert data[tool_uuid] == {
        "kind": "tool",
        "tool_call_id": "tc1",
        "tool": "run_code",
        "cells": [{"type": "code", "cell": "code-cell"}],
    }


def test_tool_call_supports_multiple_and_zero_cells(history):
    ai_uuid = history.raw_records[1].uuid
    links = {
        ai_uuid: AICellLink(
            tool_calls={
                "many": ToolCallLink(
                    tool="hypothetical",
                    cells=[
                        CellRef(cell="c1", cell_type="code"),
                        CellRef(cell="c2", cell_type="code"),
                    ],
                ),
                "drifted": ToolCallLink(tool="run_code", cells=[]),  # expected-but-unmatched
            }
        )
    }
    doc = BeakerChatHistoryDoc.from_history(history, cell_links=links)
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))

    tool_calls = restored.cell_links[ai_uuid].tool_calls
    assert [r.cell for r in tool_calls["many"].cells] == ["c1", "c2"]
    assert tool_calls["drifted"].cells == []


def test_link_for_and_referenced_cell_ids(doc, history):
    human_uuid = history.raw_records[0].uuid
    assert doc.link_for(human_uuid) == HumanCellLink(cell="query-cell")
    assert doc.link_for("does-not-exist") is None
    assert doc.referenced_cell_ids() == {"query-cell", "thought-cell", "code-cell"}


def test_prune_cell_links_drops_stale_refs(doc, history):
    human_uuid, ai_uuid, tool_uuid = (r.uuid for r in history.raw_records)
    # Keep the query + thought cells; drop the code cell (referenced twice).
    dropped = doc.prune_cell_links(valid_cell_ids={"query-cell", "thought-cell"})

    assert dropped.count("code-cell") == 2
    # Entries remain; the now-empty cells document the drift.
    assert doc.cell_links[ai_uuid].tool_calls["tc1"].cells == []
    assert doc.cell_links[tool_uuid].cells == []
    # Surviving links untouched.
    assert doc.cell_links[human_uuid].cell == "query-cell"
    assert doc.cell_links[ai_uuid].thought_cell == "thought-cell"


def test_prune_nulls_scalar_cells(history):
    human_uuid, ai_uuid = history.raw_records[0].uuid, history.raw_records[1].uuid
    links = {
        human_uuid: HumanCellLink(cell="gone"),
        ai_uuid: AICellLink(thought_cell="also-gone"),
    }
    doc = BeakerChatHistoryDoc.from_history(history, cell_links=links)
    dropped = doc.prune_cell_links(valid_cell_ids=set())

    assert sorted(dropped) == ["also-gone", "gone"]
    assert doc.cell_links[human_uuid].cell is None
    assert doc.cell_links[ai_uuid].thought_cell is None


def test_history_functional_without_cell_links(history):
    doc = BeakerChatHistoryDoc.from_history(history)
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))

    assert restored.cell_links == {}
    assert [r.uuid for r in restored.history.raw_records] == [
        r.uuid for r in history.raw_records
    ]


def test_unparseable_cell_link_is_skipped_with_warning(doc, history):
    data = doc.to_dict(compress=False)
    data["cell_links"]["bogus-uuid"] = {"kind": "nonsense"}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        restored = BeakerChatHistoryDoc.from_dict(data)
    assert any("Skipping unparseable cell link" in str(w.message) for w in caught)
    assert "bogus-uuid" not in restored.cell_links
    # Valid links still loaded.
    assert len(restored.cell_links) == len(history.raw_records)


# -- framing-field omission policy --


def _history_with_preambles() -> ChatHistory:
    history = ChatHistory(messages=[HumanMessage(content="hi")])
    history.set_system_message("you are a test agent")
    history.system_preamble = MessageRecord(message=SystemMessage(content="system preamble"))
    history.user_preamble = MessageRecord(message=HumanMessage(content="user preamble"))
    return history


def test_save_clears_system_message_and_system_preamble():
    doc = BeakerChatHistoryDoc.from_history(_history_with_preambles())
    payload = doc.to_dict(compress=False)["history"]

    assert payload["system_message"] is None
    assert payload["system_preamble"] is None
    # user_preamble is retained (user-authored, not regenerable).
    assert payload["user_preamble"] is not None


def test_round_trip_keeps_user_preamble_drops_regenerable_framing():
    doc = BeakerChatHistoryDoc.from_history(_history_with_preambles())
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))

    assert restored.history.system_message is None
    assert restored.history.system_preamble is None
    assert restored.history.user_preamble is not None
    assert restored.history.user_preamble.message.text == "user preamble"


def test_omission_holds_under_compression():
    doc = BeakerChatHistoryDoc.from_history(_history_with_preambles())
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=True))

    assert restored.history.system_message is None
    assert restored.history.system_preamble is None
    assert restored.history.user_preamble.message.text == "user preamble"


# -- compression --


def test_compress_false_keeps_history_inline(doc):
    data = doc.to_dict(compress=False)
    assert data["history_encoding"] == "json"
    assert isinstance(data["history"], dict)


def test_compress_true_encodes_history_as_string(doc):
    data = doc.to_dict(compress=True)
    assert data["history_encoding"] == "gzip+base64"
    assert isinstance(data["history"], str)


def test_compressed_envelope_stays_cleartext(doc, history):
    # Schema, metadata, and cell links must remain inspectable without
    # decompressing the inner payload.
    data = doc.to_dict(compress=True)
    assert data["format"] == BEAKER_CHAT_HISTORY_SCHEMA.to_dict()
    assert data["cell_links_format"] == CELL_LINKS_SCHEMA.to_dict()
    assert data["metadata"] == {"context": "test"}
    human_uuid = history.raw_records[0].uuid
    assert data["cell_links"][human_uuid] == {"kind": "human", "cell": "query-cell"}


def test_compressed_round_trip(doc, history):
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=True))
    assert [r.uuid for r in restored.history.raw_records] == [
        r.uuid for r in history.raw_records
    ]
    assert restored.history.summaries[0].summarized_messages == {"alpha", "beta"}
    assert restored.cell_links == _make_links(history)


def test_auto_compression_below_threshold_stays_inline(doc):
    data = doc.to_dict(compress="auto", compress_threshold=10**9)
    assert data["history_encoding"] == "json"


def test_auto_compression_above_threshold_compresses(doc):
    data = doc.to_dict(compress="auto", compress_threshold=0)
    assert data["history_encoding"] == "gzip+base64"


def test_invalid_compress_mode_raises(doc):
    with pytest.raises(ValueError):
        doc.to_dict(compress="sometimes")


def test_from_dict_rejects_bad_encoding(doc):
    data = doc.to_dict(compress=False)
    data["history_encoding"] = "rot13"
    with pytest.raises(ValueError):
        BeakerChatHistoryDoc.from_dict(data)


def test_from_dict_rejects_compressed_marker_with_non_string_body(doc):
    data = doc.to_dict(compress=False)
    data["history_encoding"] = "gzip+base64"  # but history is still a dict
    with pytest.raises(ValueError):
        BeakerChatHistoryDoc.from_dict(data)


# -- lenient schema checking --


def test_incompatible_schema_warns_but_loads(doc):
    data = doc.to_dict(compress=False)
    data["format"] = {"schema": "beaker.ChatHistory", "version": 999}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        restored = BeakerChatHistoryDoc.from_dict(data)
    assert any("not compatible" in str(w.message) for w in caught)
    assert len(restored.history.raw_records) == 3


def test_missing_schema_marker_warns_but_loads(doc):
    data = doc.to_dict(compress=False)
    del data["format"]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        restored = BeakerChatHistoryDoc.from_dict(data)
    assert any("missing a 'format'" in str(w.message) for w in caught)
    assert len(restored.history.raw_records) == 3


def test_incompatible_cell_links_schema_warns_but_loads(doc, history):
    data = doc.to_dict(compress=False)
    data["cell_links_format"] = {"schema": "beaker.ChatHistoryCellLinks", "version": 999}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        restored = BeakerChatHistoryDoc.from_dict(data)
    assert any("not compatible" in str(w.message) for w in caught)
    assert restored.cell_links == _make_links(history)


# -- summarizer passthrough --


def test_from_dict_uses_archytas_default_summarizers_when_omitted(doc):
    restored = BeakerChatHistoryDoc.from_dict(doc.to_dict(compress=False))
    # Default omission -> Archytas attaches its own defaults (non-None).
    assert restored.history.loop_summarizer is not None
    assert restored.history.history_summarizer is not None


def test_from_dict_can_disable_summarizers_explicitly(doc):
    restored = BeakerChatHistoryDoc.from_dict(
        doc.to_dict(compress=False),
        loop_summarizer=None,
        history_summarizer=None,
    )
    assert restored.history.loop_summarizer is None
    assert restored.history.history_summarizer is None
