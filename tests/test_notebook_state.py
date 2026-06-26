"""
Tests for beaker_notebook.lib.notebook_state.

Focused on rendering of error outputs, whose nbformat ``traceback`` field is a
list of strings (one entry per line). Regression coverage for the crash where
that list was passed straight to ``xml.sax.saxutils.escape``, raising
``AttributeError: 'list' object has no attribute 'replace'``.
"""

import nbformat

from beaker_notebook.lib.notebook_state import (
    _error_output,
    format_cell,
)


def _error_output_node(ename="ValueError", evalue="boom", traceback=None):
    return nbformat.v4.new_output(
        "error",
        ename=ename,
        evalue=evalue,
        traceback=traceback if traceback is not None else [],
    )


def _code_cell_with_error(traceback):
    cell = nbformat.v4.new_code_cell(source="raise ValueError('boom')")
    cell.outputs = [_error_output_node(traceback=traceback)]
    return cell


def test_error_output_joins_list_traceback():
    output = _error_output_node(traceback=["line one\n", "line two\n", "line three"])
    rendered = _error_output(output, "cell:output:0")
    assert "line one" in rendered
    assert "line two" in rendered
    assert "line three" in rendered


def test_error_output_escapes_xml_in_traceback():
    output = _error_output_node(
        ename="TypeError",
        evalue="bad <thing> & stuff",
        traceback=["Traceback <module> & co", "  if a < b > c: pass"],
    )
    rendered = _error_output(output, "cell:output:0")
    # The traceback body must be XML-escaped, not raw.
    assert "&amp;" in rendered
    assert "&lt;" in rendered
    assert "<module>" not in rendered


def test_error_output_empty_traceback_does_not_crash():
    output = _error_output_node(traceback=[])
    rendered = _error_output(output, "cell:output:0")
    assert "<traceback>" in rendered


def test_format_cell_renders_error_output():
    cell = _code_cell_with_error(["Traceback (most recent call last):\n", "ValueError: boom\n"])
    rendered = format_cell(cell)
    assert 'type="error"' in rendered
    assert 'ename="ValueError"' in rendered
    assert "ValueError: boom" in rendered
