from typing import Any

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str  # human-readable ID, e.g. PRS-0000442
    uuid: str
    label: str  # Neo4j node label: Person, Organization, Account, ...
    name: str
    risk_score: float = 0.0
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
