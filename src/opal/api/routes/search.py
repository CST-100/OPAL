"""Global search endpoint."""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import or_

from opal.api.deps import DbSession
from opal.db.models import Part, Supplier
from opal.db.models.dataset import Dataset
from opal.db.models.execution import ProcedureInstance
from opal.db.models.issue import Issue
from opal.db.models.procedure import MasterProcedure
from opal.db.models.purchase import Purchase
from opal.db.models.risk import Risk
from opal.db.models.workcenter import Workcenter

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    """A single search result."""

    entity_type: str
    id: int
    label: str
    sublabel: str | None = None
    url: str
    status: str | None = None


@router.get("", response_model=list[SearchResult])
async def search(
    db: DbSession,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(5, ge=1, le=20, description="Max results per entity type"),
) -> list[SearchResult]:
    """Search across all entity types."""
    term = f"%{q}%"
    results: list[SearchResult] = []

    # Parts
    parts = (
        db.query(Part)
        .filter(
            Part.deleted_at.is_(None),
            or_(
                Part.name.ilike(term),
                Part.internal_pn.ilike(term),
                Part.external_pn.ilike(term),
                Part.description.ilike(term),
            ),
        )
        .order_by(Part.id.desc())
        .limit(limit)
        .all()
    )
    for p in parts:
        results.append(SearchResult(
            entity_type="part",
            id=p.id,
            label=p.name,
            sublabel=p.internal_pn or p.external_pn,
            url=f"/parts/{p.id}",
        ))

    # Issues
    issues = (
        db.query(Issue)
        .filter(
            Issue.deleted_at.is_(None),
            or_(
                Issue.title.ilike(term),
                Issue.description.ilike(term),
            ),
        )
        .order_by(Issue.id.desc())
        .limit(limit)
        .all()
    )
    for i in issues:
        status_val = i.status.value if hasattr(i.status, "value") else i.status
        results.append(SearchResult(
            entity_type="issue",
            id=i.id,
            label=i.title,
            sublabel=f"#{i.id}",
            url=f"/issues/{i.id}",
            status=status_val,
        ))

    # Procedures
    procedures = (
        db.query(MasterProcedure)
        .filter(
            MasterProcedure.deleted_at.is_(None),
            MasterProcedure.name.ilike(term),
        )
        .order_by(MasterProcedure.id.desc())
        .limit(limit)
        .all()
    )
    for p in procedures:
        status_val = p.status.value if hasattr(p.status, "value") else p.status
        results.append(SearchResult(
            entity_type="procedure",
            id=p.id,
            label=p.name,
            sublabel=f"#{p.id}",
            url=f"/procedures/{p.id}",
            status=status_val,
        ))

    # Executions
    instances = (
        db.query(ProcedureInstance)
        .filter(
            or_(
                ProcedureInstance.work_order_number.ilike(term),
            ),
        )
        .order_by(ProcedureInstance.id.desc())
        .limit(limit)
        .all()
    )
    for inst in instances:
        status_val = inst.status.value if hasattr(inst.status, "value") else inst.status
        results.append(SearchResult(
            entity_type="execution",
            id=inst.id,
            label=f"Execution #{inst.id}",
            sublabel=inst.work_order_number,
            url=f"/executions/{inst.id}",
            status=status_val,
        ))

    # Risks
    risks = (
        db.query(Risk)
        .filter(
            Risk.deleted_at.is_(None),
            or_(
                Risk.title.ilike(term),
                Risk.description.ilike(term),
            ),
        )
        .order_by(Risk.id.desc())
        .limit(limit)
        .all()
    )
    for r in risks:
        status_val = r.status.value if hasattr(r.status, "value") else r.status
        results.append(SearchResult(
            entity_type="risk",
            id=r.id,
            label=r.title,
            sublabel=f"#{r.id}",
            url=f"/risks/{r.id}",
            status=status_val,
        ))

    # Suppliers
    suppliers = (
        db.query(Supplier)
        .filter(
            Supplier.deleted_at.is_(None),
            or_(
                Supplier.name.ilike(term),
                Supplier.code.ilike(term),
            ),
        )
        .order_by(Supplier.name)
        .limit(limit)
        .all()
    )
    for s in suppliers:
        results.append(SearchResult(
            entity_type="supplier",
            id=s.id,
            label=s.name,
            sublabel=s.code,
            url=f"/suppliers/{s.id}",
        ))

    # Purchases
    purchases = (
        db.query(Purchase)
        .filter(
            or_(
                Purchase.reference.ilike(term),
                Purchase.notes.ilike(term),
            ),
        )
        .order_by(Purchase.id.desc())
        .limit(limit)
        .all()
    )
    for po in purchases:
        status_val = po.status.value if hasattr(po.status, "value") else po.status
        results.append(SearchResult(
            entity_type="purchase",
            id=po.id,
            label=f"PO-{po.id}",
            sublabel=po.reference,
            url=f"/purchases/{po.id}",
            status=status_val,
        ))

    # Datasets
    datasets = (
        db.query(Dataset)
        .filter(
            Dataset.deleted_at.is_(None),
            Dataset.name.ilike(term),
        )
        .order_by(Dataset.id.desc())
        .limit(limit)
        .all()
    )
    for d in datasets:
        results.append(SearchResult(
            entity_type="dataset",
            id=d.id,
            label=d.name,
            sublabel=f"#{d.id}",
            url=f"/datasets/{d.id}",
        ))

    # Workcenters
    workcenters = (
        db.query(Workcenter)
        .filter(
            or_(
                Workcenter.name.ilike(term),
                Workcenter.code.ilike(term),
            ),
        )
        .order_by(Workcenter.code)
        .limit(limit)
        .all()
    )
    for w in workcenters:
        results.append(SearchResult(
            entity_type="workcenter",
            id=w.id,
            label=w.name,
            sublabel=w.code,
            url=f"/workcenters/{w.id}",
        ))

    return results
