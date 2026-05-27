"""Tests for AnalysisAgent.code_analysis tool."""

import codecs
import dill
from unittest.mock import MagicMock

import pytest

from beaker_notebook.lib.code_analysis.analysis_agent import (
    AnalysisAgent,
    AnalysisResult,
)


def _agent_instance() -> AnalysisAgent:
    return AnalysisAgent.__new__(AnalysisAgent)


def _make_result(rule_id: str = "RULE_A", line: int = 1) -> AnalysisResult:
    return AnalysisResult(
        issue_type="ISSUE_X",
        analysis_rule_id=rule_id,
        code_start_line=line,
        code_end_line=line,
    )


def test_code_analysis_returns_base64_encoded_dill():
    agent = _agent_instance()
    loop = MagicMock()
    loop.STOP_SUCCESS = "STOP_SUCCESS"

    items = [_make_result("R1", 3), _make_result("R2", 5)]
    encoded = AnalysisAgent.code_analysis(agent, analysis_list=items, loop=loop)

    # Round-trip the payload
    raw = codecs.decode(encoded.encode(), "base64")
    decoded = dill.loads(raw)
    assert isinstance(decoded, list)
    assert len(decoded) == 2
    assert {r.analysis_rule_id for r in decoded} == {"R1", "R2"}


def test_code_analysis_stops_react_loop():
    agent = _agent_instance()
    loop = MagicMock()
    loop.STOP_SUCCESS = object()
    AnalysisAgent.code_analysis(agent, analysis_list=[_make_result()], loop=loop)
    loop.set_state.assert_called_once_with(loop.STOP_SUCCESS)


def test_code_analysis_empty_list_still_succeeds():
    agent = _agent_instance()
    loop = MagicMock()
    encoded = AnalysisAgent.code_analysis(agent, analysis_list=[], loop=loop)
    decoded = dill.loads(codecs.decode(encoded.encode(), "base64"))
    assert decoded == []
    loop.set_state.assert_called_once_with(loop.STOP_SUCCESS)
