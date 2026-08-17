from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_permission
from app.api.routes.graph import DepthParam
from app.models.envelope import Envelope, Meta
from app.repositories import entity_repo, graph_repo, provenance_repo
from app.security.roles import Permission
from app.services import provenance as provenance_service

router = APIRouter(
    prefix="/api/entities",
    tags=["entities"],
    dependencies=[Depends(require_permission(Permission.ENTITY_READ))],
)


@router.get("")
async def list_entities(
    type: str = "Person",
    # A band, not a minimum score. See `build_browse_filters` for why a numeric
    # threshold across mixed subject types compares incomparable numbers.
    band: str | None = Query(None),
    city: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    try:
        nodes, total = await graph_repo.list_entities(driver, type, band, city, page, page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Envelope(data=nodes, meta=Meta(total=total, page=page, page_size=page_size))


@router.get("/{entity_id}")
async def get_entity(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    node = await graph_repo.get_node_by_human_id(driver, entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    node["connections"] = await entity_repo.get_connection_summary(driver, entity_id)
    return Envelope(data=node)


@router.get("/{entity_id}/provenance")
async def get_entity_provenance(
    entity_id: str, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    """Per-attribute provenance for one entity.

    Answers, for every value the profile page displays: which source reported
    it, when ARGUS learned it, whether the stored value still matches what was
    reported, and whether any assertion or conflict bears on it.

    This is what makes "every displayed fact resolves to an observation or is
    explicitly marked inferred" a property of the system rather than a claim in
    a document. A value with no provenance comes back as `unattributed` — the
    one thing that must never happen is a value rendering as though it were
    sourced when nothing accounts for it.
    """
    node = await graph_repo.get_node_by_human_id(driver, entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    resolved = await provenance_service.attribute_provenance(entity_id, node["properties"])
    assertions = await provenance_repo.assertions_for_subject(entity_id, include_ended=True)
    # Conflicts are a grouping of the assertions already loaded, and only
    # current ones can conflict — a withdrawn claim is not a live disagreement.
    conflicts = provenance_repo.find_conflicts(entity_id, [a for a in assertions if a.is_current])
    sources = await provenance_repo.sources_for_subject(entity_id)

    return Envelope(
        data={
            "subject_ref": entity_id,
            "attributes": resolved.attributes,
            # Carried so the client can tell "no source reported this field"
            # from "the observation that did was outside the window read".
            "observations_examined": resolved.observations_examined,
            "observations_total": resolved.observations_total,
            "attributes_complete": resolved.complete,
            "assertions": [a.model_dump(mode="json") for a in assertions],
            "conflicts": [c.model_dump(mode="json") for c in conflicts],
            "sources": [s.model_dump(mode="json") for s in sources],
        }
    )


@router.get("/{entity_id}/graph")
async def get_entity_graph(
    entity_id: str, depth: int = DepthParam, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    subgraph = await graph_repo.get_neighborhood(driver, entity_id, depth=depth)
    return Envelope(data=subgraph)


@router.get("/{entity_id}/timeline")
async def get_entity_timeline(
    entity_id: str,
    limit: int = Query(200, ge=1, le=1000),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    timeline = await entity_repo.get_entity_timeline(driver, entity_id, limit=limit)
    return Envelope(data=timeline)


@router.get("/{entity_id}/cases")
async def get_entity_cases(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    cases = await entity_repo.get_related_cases(driver, entity_id)
    return Envelope(data=cases)


@router.get("/{entity_id}/alerts")
async def get_entity_alerts(
    entity_id: str,
    limit: int = Query(20, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    alerts = await entity_repo.get_related_alerts(driver, entity_id, limit=limit)
    return Envelope(data=alerts)
