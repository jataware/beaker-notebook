from dataclasses import dataclass
from typing import TypeAlias, Optional, Literal, TypeVar, Generic, Callable, TypedDict, overload

from pydantic import BaseModel, Field


class AnalysisCategory(BaseModel):
    id: str
    display_label: str
    color: Optional[str] = None
    icon: Optional[str] = None


class AnalysisIssue(BaseModel):
    id: str
    title: str
    description: str = Field(default="Description goes here")
    prompt_description: Optional[str] = Field(default=None)
    severity: Literal["major", "minor", "warning", "info", "hint"] = Field(default="info")
    link: Optional[str] = Field(default=None)
    category: Optional[AnalysisCategory] = Field(default=None)


class AnalysisAnnotation(BaseModel):
    cell_id: str
    issue: AnalysisIssue
    start: int
    end: int
    title_override: Optional[str] = None
    message_override: Optional[str] = None
    message_extra: Optional[str] = None
AnalysisAnnotations: TypeAlias = list[AnalysisAnnotation]


@dataclass
class AnalysisCodeCellLine:
    cell_id: str
    start_pos: int
    end_pos: int
    line_num: int
    content: str


@dataclass
class AnalysisCodeCell:
    cell_id: str
    notebook_id: str
    content: str
    _lines: Optional[list[AnalysisCodeCellLine]] = None

    @property
    def lines(self) -> list[AnalysisCodeCellLine]:
        if self._lines is not None:
            return self._lines
        offset = 0
        lines = self.content.splitlines(keepends=True)
        if len(lines) == 0:
            lines = [""]
        line_list: list[AnalysisCodeCellLine] = []
        for line_num, line_content in enumerate(lines, start=0):
            line_len = len(line_content)
            line_list.append(AnalysisCodeCellLine(
                cell_id=self.cell_id,
                start_pos=offset,
                end_pos=offset + line_len,
                line_num=line_num,
                content=line_content,
            ))
            offset += line_len
        self._lines = line_list
        return line_list

    def absolute_position(self, line_num: int, line_offset: int=0) -> int:
        return self.lines[line_num].start_pos + line_offset


class AnalysisCodeCells(list[AnalysisCodeCell]):
    _line_ref: dict[tuple[str, int], AnalysisCodeCellLine] = None
    _line_map: dict[int, tuple[int, int]]

    def __init__(self, *args, **kwargs):
        self._line_ref = {}
        self._line_map = {}
        super().__init__(*args, **kwargs)
        offset = 0
        for cell_idx, cell in enumerate(self):
            cell_lines = cell.lines
            for line in cell_lines:
                combined_line_num = line.line_num + offset
                self._line_ref[(cell.cell_id, line.line_num)] = line
                self._line_map[combined_line_num] = (cell_idx, line.line_num)
            offset += len(cell_lines)

    @property
    def lines(self) -> list[dict]:
        line_by_cell = []
        offset = 0
        for cell in self:
            cell_lines = cell.lines
            for line in cell_lines:
                content = line.content
                if content and not content.endswith("\n"):
                    content = content + "\n"
                line_by_cell.append({
                    "cell_id": cell.cell_id,
                    "line_num": line.line_num,
                    "content": content,
                })
            offset += len(cell_lines)
        return line_by_cell

    @property
    def formatted_code(self):
        lines = self.lines
        spacing = len(str(len(lines)))
        formatted_code = (
            "# {cell_id} / {line_num} : {content}\n" +
            "".join((
                f"{line['cell_id']} / {(line['line_num']):{spacing}} : {line['content']}"
                for line in lines
            ))
        )
        return formatted_code

    @property
    def raw_code(self) -> str:
        parts = []
        for cell in self:
            content = cell.content
            if not content.endswith("\n"):
                content += "\n"
            parts.append(content)
        return "".join(parts)

    def get_cell_line(self, cell_id: str, line_num: int) -> AnalysisCodeCellLine | None:
        return self._line_ref.get((cell_id, line_num), None)

    def resolve_line_position(self, line_num: int) -> AnalysisCodeCellLine | None:
        code_cell_idx, code_cell_line = self._line_map.get(line_num, (None, None))
        if code_cell_idx is None:
            return None
        code_cell = self[code_cell_idx]
        line = self._line_ref.get((code_cell.cell_id, code_cell_line), None)
        return code_cell.cell_id, line
