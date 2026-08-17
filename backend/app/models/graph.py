from typing import Any

from pydantic import BaseModel


class NodeAssessment(BaseModel):
    """ARGUS's own assessment of an entity, as carried on a graph node.

    `score` is optional and stays optional all the way to the client. A subject
    ARGUS could not assess has no score — not zero — so nothing downstream can
    sort it alongside one that was examined and found unremarkable. `coverage`
    is the share of the model that could be evaluated, and it travels with the
    score everywhere so the number is never displayed without its denominator.
    """

    band: str
    score: float | None = None
    coverage: float | None = None
    model: str | None = None
    assessed_at: str | None = None


class GraphNode(BaseModel):
    id: str  # human-readable ID, e.g. PRS-0000442
    uuid: str
    label: str  # Neo4j node label: Person, Organization, Account, ...
    name: str
    # Replaces `risk_score: float = 0.0`, which carried the scenario
    # generator's planted number and defaulted to a reassuring zero for every
    # entity that had none (audit G-08). None here means "no assessment", and
    # the client has to handle it rather than being handed a plausible default.
    assessment: NodeAssessment | None = None
    properties: dict[str, Any] = {}


class GraphEdge(BaseModel):
    id: str
    source: str  # human-readable ID
    target: str  # human-readable ID
    type: str
    properties: dict[str, Any] = {}


class Subgraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class PathResult(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    length: int
