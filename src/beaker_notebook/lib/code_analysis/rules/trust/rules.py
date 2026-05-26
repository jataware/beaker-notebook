from typing import TYPE_CHECKING
from tree_sitter import Tree, Node

from ..base import AnalysisASTRule, AnalysisLLMRule
from ...analysis_types import AnalysisCodeCells, AnalysisCategory, AnalysisCodeCellLine, AnalysisAnnotation

if TYPE_CHECKING:
    from ...analyzer import AnalysisEngine

class TrustCategoryRule(AnalysisLLMRule):
    """Trust rule that wraps an AnalysisCategory for LLM analysis"""
    annotation_type: AnalysisCategory

    def __init__(self, annotation_type: AnalysisCategory):
        super().__init__(id=f"trust_analysis_{annotation_type.id}", prompt=None)
        self.annotation_type = annotation_type

    @property
    def query(self) -> str:
        content = []
        content.append(f"""
# {self.annotation_type.display_label} ({self.annotation_type.id})""".strip())
        for annotation in self.annotation_type.issues:
            content.append(
                f"""\
## {annotation.title} ({annotation.id})
    id: {annotation.id}
    severity: {annotation.severity}
    description/instructions: \\
```
{annotation.description}
```"""
            )
        return "\n\n".join(content)

def trust_literal_check_filter(cells: AnalysisCodeCells, tree: Tree, analyzer: "AnalysisEngine", rule: AnalysisASTRule) -> list[AnalysisAnnotation]:
    """Filter function for checking literal values in code for trust analysis"""
    language = analyzer.language
    query = language.query(
        """
(
 (comment)* @comment
 .
 (expression_statement
  (assignment
    left: (_) @left
    right: ([
        (string)
        (integer)
        (float)
        [
            (list
                ([(string) (integer) (float)])
            )
            (tuple
                ([(string) (integer) (float)])
            )
        ]
    ].) @right
   ) @assignment
 )
 .
 (comment)* @comment
)
"""
    )
    raw_matches = query.matches(tree.root_node)

    results: list[AnalysisAnnotation] = []
    for _, match in raw_matches:
        match_node = match["right"][0]
        if match_node.type in ["list", "tuple"]:
            nodes = [node for node in match_node.named_children if node.type in ('string', 'integer', 'float')]
        else:
            nodes = [match_node]
        for node in nodes:
            start_line, start_line_offset = node.start_point
            end_line, end_line_offset = node.end_point
            start_unfurled_line: AnalysisCodeCellLine
            end_unfurled_line: AnalysisCodeCellLine
            cell_id, start_unfurled_line = cells.resolve_line_position(start_line)
            end_unfurled_line = start_unfurled_line if end_line == start_line else cells.resolve_line_position(end_line)[1]

            result = AnalysisAnnotation(
                cell_id=cell_id,
                start=start_unfurled_line.start_pos + start_line_offset,
                end=end_unfurled_line.start_pos + end_line_offset,
                issue=rule.issue,
                extra_info=None,
            )
            results.append(result)
    return results

from .categories import literal_value_issue, ungrounded_fact, ungrounded_value, ungrounded_methodology, assumption
# Concrete trust rule instances
literal_rules = [
    AnalysisASTRule(
        id="trust_literal_check",
        issue=literal_value_issue,
        filter=trust_literal_check_filter,
    ),
]

grounding_rules = [
    AnalysisLLMRule(
        id="trust_ungrounded_fact",
        issue=ungrounded_fact,
    ),
    AnalysisLLMRule(
        id="trust_ungrounded_value",
        issue=ungrounded_value,
    ),
    AnalysisLLMRule(
        id="trust_ungrounded_methodology",
        issue=ungrounded_methodology,
    ),
]

assumption_rules = [
    AnalysisLLMRule(
        id="trust_assumption",
        issue=assumption,
    ),
]

all_rules = [
    *literal_rules,
    *grounding_rules,
    *assumption_rules,
]

ast_rules = [
    rule for rule in all_rules if isinstance(rule, AnalysisASTRule)
]

llm_rules = [
    rule for rule in all_rules if isinstance(rule, AnalysisLLMRule)
]
