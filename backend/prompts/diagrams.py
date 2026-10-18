"""Hướng dẫn sơ đồ; chỉ thêm khi câu hỏi cần tính năng này."""

from __future__ import annotations
import re
import unicodedata


DIAGRAM_PROMPT = """
## Mermaid diagrams
Use one fenced mermaid block per diagram, with a brief introduction and explanation. Add YAML frontmatter
(--- / title: ... / ---); activity/use-case titles start with “Sơ đồ hoạt động: ”/“Sơ đồ use case: ” for UI classification.
Use ASCII alphanumeric/underscore IDs, never reserved end/class/subgraph; quote labels with Unicode or punctuation.
Use classDiagram for UML classes (+ - # ~ visibility; <<interface>>/<<abstract>>; <|-- inheritance, ..|> implementation,
*-- composition, o-- aggregation, --> association, ..> dependency; quoted multiplicities).
Use sequenceDiagram with actor/participant, ->>/-->>, activate/deactivate and alt/opt/loop/par as needed.
Activities without lanes use stateDiagram-v2, [*] start/end, ID: label; declare <<choice>>/<<fork>>/<<join>> states
before their first use. Activities with lanes use swimlane-beta with default vertical lanes (no LR): each lane is
subgraph ID["label"] … end, every node including start/end inside a lane, cross-lane edges after all subgraphs.
Start S@{ shape: sm-circ }, end X@{ shape: fr-circ }, action A(label), decision C{"question?"}, fork/join J@{ shape: fork }.
Use-case diagrams are approximate flowchart LR: actor ((label)), use case (["label"]), system subgraph; disclose
the approximation. Use erDiagram for ERD, flowchart TD for flowcharts, stateDiagram-v2 for states.
No HTML labels, click directives, %%{init}%% or unsolicited color changes.
""".strip()


_DIAGRAM_WORDS = re.compile(
    r"(?<![a-z0-9])(so do|luu do|bieu do|diagram|uml|erd|flowchart|mermaid|activity|sequence|use ?case|swimlane"
    r"|draw\.?io|gantt|mindmap)(?![a-z0-9])"
)


def build_diagram_guide(question: str) -> str:
    """Hướng dẫn vẽ sơ đồ khi vài tin nhắn gần đây nói tới sơ đồ; không thì chuỗi rỗng."""
    folded = unicodedata.normalize("NFD", question.lower().replace("đ", "d"))
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    if not _DIAGRAM_WORDS.search(folded):
        return ""
    return "\n\n" + DIAGRAM_PROMPT
