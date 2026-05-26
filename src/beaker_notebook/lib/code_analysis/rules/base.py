import codecs
import dill
from abc import ABC, abstractmethod
from tree_sitter import Tree, Node, Parser, Language
from typing import TypeVar, Callable, Optional, TYPE_CHECKING, cast

from ..analysis_agent import AnalysisResult
from ..analysis_types import AnalysisCodeCells, AnalysisIssue, AnalysisAnnotation, AnalysisAnnotations

if TYPE_CHECKING:
    from ..analyzer import AnalysisEngine

InternalRepr = TypeVar("InternalRepr")

class AnalysisRule(ABC):
    id: str
    issue: AnalysisIssue

    def __init__(self, id, issue):
        self.id = id
        self.issue = issue

    @classmethod
    @abstractmethod
    async def analyze(cls, cells: AnalysisCodeCells, data: InternalRepr, rules: "list[AnalysisRule]", analyzer: "AnalysisEngine") -> AnalysisAnnotations:
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def preprocess_cells(cls, cells: AnalysisCodeCells,  analyzer: "AnalysisEngine") -> InternalRepr:
        raise NotImplementedError()


class AnalysisASTRule(AnalysisRule):
    filter: Callable

    def __init__(self, id: str, issue, filter: Callable):
        super().__init__(id, issue)
        self.filter = filter

    @classmethod
    async def analyze(cls, cells: AnalysisCodeCells, data: Tree, rules: "list[AnalysisASTRule]", analyzer: "AnalysisEngine") -> AnalysisAnnotations:
        results: list[AnalysisResult] = []
        for rule in rules:
            for result in rule.filter(cells, data, analyzer, rule):
                match result:
                    case AnalysisAnnotation():
                        results.append(result)
                    case _:
                        raise Exception("Result is not a type we can handle.")

        return results

    @classmethod
    def preprocess_cells(cls, cells: AnalysisCodeCells, analyzer) -> Tree:
        code = cells.raw_code
        if not isinstance(code, bytes):
            code = code.encode()
        parser = Parser(analyzer.language)
        tree = parser.parse(code)
        return tree


class AnalysisLLMRule(AnalysisRule):
    rule_prompt: Optional[str]

    def __init__(self, id: str, issue: AnalysisIssue, prompt: Optional[str] = None):
        super().__init__(id, issue)
        if prompt is None:
            prompt = issue.prompt_description
        self.rule_prompt = prompt

    @property
    def query(self) -> str:
        query = f"""\
id: `{self.id}`
instructions:
```
{self.rule_prompt.strip()}
```
"""
        return query

    @classmethod
    async def analyze(cls, cells: AnalysisCodeCells, data: str, rules: "list[AnalysisLLMRule]", analyzer: "AnalysisEngine") -> AnalysisAnnotations:
        from ..analysis_agent import AnalysisResult, AnalysisAgent
        from ...config import config
        rule_index = {rule.id: rule for rule in rules}
        model = config.get_model()
        beaker_kernel = analyzer.context.beaker_kernel if getattr(analyzer, 'context', None) else None
        agent = AnalysisAgent(
            model=model,
            beaker_kernel = beaker_kernel
        )
        agent.add_context(f"""\
Code to run rules against:
```
{data}
```
""")
        formatted_rules = [rule.query for rule in rules]
        joined_rules = "\n====\n".join(formatted_rules)
        raw_result = await agent.react_async(query=joined_rules)
        try:
            raw_result = raw_result.encode()
            raw_result = codecs.decode(raw_result, 'base64')
        except:
            pass
        try:
            # Attempt to unpickle/undill the result.
            raw_result = cast(list[AnalysisResult], dill.loads(raw_result))
        except dill.UnpicklingError:
            # Allow result to pass through as returned.
            pass

        results = []
        for annotation in raw_result:
            rule = rule_index.get(annotation.issue_type)
            start_line = cells.get_cell_line(annotation.cell_id, annotation.code_start_line)
            end_line = cells.get_cell_line(annotation.cell_id, annotation.code_end_line)
            result = AnalysisAnnotation(
                cell_id=annotation.cell_id,
                issue=rule.issue,
                start=start_line.start_pos,
                end=end_line.end_pos,
                message_extra=annotation.extra_info
            )
            results.append(result)

        return results

    @classmethod
    def preprocess_cells(cls, cells, analyzer) -> str:
        return cells.formatted_code
