"""Database models."""

from opal.db.models.attachment import Attachment
from opal.db.models.audit import AuditLog
from opal.db.models.container import Container, ContainerItem
from opal.db.models.dataset import DataPoint, Dataset
from opal.db.models.designator import DesignatorSequence
from opal.db.models.execution import ProcedureInstance, StepExecution
from opal.db.models.genealogy import AssemblyComponent
from opal.db.models.inventory import (
    InventoryConsumption,
    InventoryProduction,
    InventoryRecord,
    StockTestResult,
    StockTransfer,
    TestTemplate,
)
from opal.db.models.issue import Issue
from opal.db.models.location import Location
from opal.db.models.issue_comment import IssueComment
from opal.db.models.onshape_link import OnshapeLink, OnshapeSyncLog
from opal.db.models.part import BOMLine, Part, PartRequirement
from opal.db.models.procedure import (
    Kit,
    MasterProcedure,
    ProcedureOutput,
    ProcedureStep,
    ProcedureVersion,
    StepKit,
)
from opal.db.models.purchase import Purchase, PurchaseLine
from opal.db.models.reference import IssueReference, ReferenceType, RiskReference
from opal.db.models.risk import Risk
from opal.db.models.supplier import Supplier
from opal.db.models.user import User
from opal.db.models.workcenter import Workcenter

__all__ = [
    "AssemblyComponent",
    "Attachment",
    "AuditLog",
    "BOMLine",
    "Container",
    "ContainerItem",
    "DataPoint",
    "Dataset",
    "DesignatorSequence",
    "InventoryConsumption",
    "InventoryProduction",
    "InventoryRecord",
    "Issue",
    "IssueComment",
    "IssueReference",
    "Kit",
    "Location",
    "MasterProcedure",
    "OnshapeLink",
    "OnshapeSyncLog",
    "Part",
    "PartRequirement",
    "ProcedureInstance",
    "ProcedureOutput",
    "ProcedureStep",
    "ProcedureVersion",
    "Purchase",
    "PurchaseLine",
    "ReferenceType",
    "Risk",
    "RiskReference",
    "StepExecution",
    "StepKit",
    "StockTestResult",
    "StockTransfer",
    "Supplier",
    "TestTemplate",
    "User",
    "Workcenter",
]
