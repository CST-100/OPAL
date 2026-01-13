"""OPAL MCP Server implementation."""

import json
import sys
from datetime import datetime, timezone
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from opal.config import get_active_project, get_active_settings
from opal.db.base import SessionLocal
from opal.db.models import (
    BOMLine,
    Issue,
    MasterProcedure,
    Part,
    PartRequirement,
    Risk,
)
from opal.db.models.issue import IssuePriority, IssueStatus, IssueType
from opal.db.models.procedure import ProcedureStatus, ProcedureStep
from opal.db.models.risk import RiskStatus

# Create MCP server
server = Server("opal")


def get_db():
    """Get a database session."""
    return SessionLocal()


def json_response(data: Any) -> list[TextContent]:
    """Create a JSON text response."""
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


# ============ TOOLS ============


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        # Parts
        Tool(
            name="list_parts",
            description="List all parts in the system, optionally filtered by category",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional)",
                    },
                    "search": {
                        "type": "string",
                        "description": "Search term for name or part number (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="get_part",
            description="Get details of a specific part by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "integer",
                        "description": "The part ID",
                    },
                },
                "required": ["part_id"],
            },
        ),
        Tool(
            name="create_part",
            description="Create a new part in the system",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Part name",
                    },
                    "category": {
                        "type": "string",
                        "description": "Part category (e.g., propulsion, structures, avionics)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Part description (optional)",
                    },
                    "external_pn": {
                        "type": "string",
                        "description": "External/manufacturer part number (optional)",
                    },
                    "unit_of_measure": {
                        "type": "string",
                        "description": "Unit of measure (default: each)",
                        "default": "each",
                    },
                    "tier": {
                        "type": "integer",
                        "description": "Inventory tier (1=Flight, 2=Ground, 3=Loose). Default: 1",
                        "default": 1,
                    },
                    "parent_id": {
                        "type": "integer",
                        "description": "Parent assembly ID (optional)",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="get_part_tree",
            description="Get the part hierarchy tree starting from a part or all top-level parts",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "integer",
                        "description": "Starting part ID (optional - if not provided, shows all top-level parts)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Maximum depth to traverse (default: 3)",
                        "default": 3,
                    },
                },
            },
        ),
        Tool(
            name="get_part_consumption_history",
            description="Get detailed history of where a part was consumed (which procedure instances/steps)",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "integer",
                        "description": "The part ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 20)",
                        "default": 20,
                    },
                },
                "required": ["part_id"],
            },
        ),
        # Procedures
        Tool(
            name="list_procedures",
            description="List all procedures in the system",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: draft, active, deprecated (optional)",
                    },
                    "search": {
                        "type": "string",
                        "description": "Search term for procedure name (optional)",
                    },
                },
            },
        ),
        Tool(
            name="create_procedure",
            description="Create a new procedure (draft status)",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Procedure name",
                    },
                    "description": {
                        "type": "string",
                        "description": "Procedure description (optional)",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="add_procedure_step",
            description="Add a step to an existing procedure",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {
                        "type": "integer",
                        "description": "The procedure ID",
                    },
                    "title": {
                        "type": "string",
                        "description": "Step title",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Step instructions (markdown supported)",
                    },
                    "step_number": {
                        "type": "string",
                        "description": "Step number (e.g., '1', '2.1', 'C1' for contingency)",
                    },
                },
                "required": ["procedure_id", "title"],
            },
        ),
        # Issues
        Tool(
            name="list_issues",
            description="List issues, optionally filtered by status or type",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: open, in_progress, resolved, closed",
                    },
                    "issue_type": {
                        "type": "string",
                        "description": "Filter by type: bug, task, improvement, non_conformance",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="create_issue",
            description="Create a new issue to track a problem, task, or improvement",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Issue title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Issue description (optional)",
                    },
                    "issue_type": {
                        "type": "string",
                        "description": "Type: bug, task, improvement, non_conformance (default: task)",
                        "default": "task",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority: low, medium, high, critical (default: medium)",
                        "default": "medium",
                    },
                },
                "required": ["title"],
            },
        ),
        # Risks
        Tool(
            name="list_risks",
            description="List risks, optionally filtered by status",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: identified, analyzing, mitigating, monitoring, closed",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Filter by severity: low, medium, high",
                    },
                },
            },
        ),
        Tool(
            name="create_risk",
            description="Create a new risk to track potential problems",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Risk title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Risk description (optional)",
                    },
                    "probability": {
                        "type": "integer",
                        "description": "Probability score 1-5 (1=rare, 5=almost certain)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "impact": {
                        "type": "integer",
                        "description": "Impact score 1-5 (1=negligible, 5=catastrophic)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "mitigation_plan": {
                        "type": "string",
                        "description": "Mitigation plan (optional)",
                    },
                },
                "required": ["title", "probability", "impact"],
            },
        ),
        # Project info
        Tool(
            name="get_project_info",
            description="Get information about the current OPAL project including tiers, requirements, and part numbering config",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="preview_part_number",
            description="Preview what a part number would look like for a given tier and sequence",
            inputSchema={
                "type": "object",
                "properties": {
                    "tier": {
                        "type": "integer",
                        "description": "Tier level (1, 2, or 3)",
                    },
                    "sequence": {
                        "type": "integer",
                        "description": "Sequence number",
                    },
                },
                "required": ["tier", "sequence"],
            },
        ),
        # Requirements
        Tool(
            name="list_requirements",
            description="List all requirements defined in the project config",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_part_requirements",
            description="List all requirements assigned to a part",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "integer",
                        "description": "The part ID",
                    },
                },
                "required": ["part_id"],
            },
        ),
        Tool(
            name="assign_requirement",
            description="Assign a project requirement to a part",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "integer",
                        "description": "The part ID",
                    },
                    "requirement_id": {
                        "type": "string",
                        "description": "The requirement ID (e.g., REQ-001)",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes about this requirement assignment (optional)",
                    },
                },
                "required": ["part_id", "requirement_id"],
            },
        ),
        Tool(
            name="verify_requirement",
            description="Mark a part requirement as verified",
            inputSchema={
                "type": "object",
                "properties": {
                    "part_requirement_id": {
                        "type": "integer",
                        "description": "The part requirement record ID",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Verification notes (optional)",
                    },
                },
                "required": ["part_requirement_id"],
            },
        ),
        # BOM / Assembly
        Tool(
            name="get_bom",
            description="Get the Bill of Materials (BOM) for an assembly",
            inputSchema={
                "type": "object",
                "properties": {
                    "assembly_id": {
                        "type": "integer",
                        "description": "The assembly part ID",
                    },
                },
                "required": ["assembly_id"],
            },
        ),
        Tool(
            name="add_component",
            description="Add a component to an assembly's BOM",
            inputSchema={
                "type": "object",
                "properties": {
                    "assembly_id": {
                        "type": "integer",
                        "description": "The assembly part ID",
                    },
                    "component_id": {
                        "type": "integer",
                        "description": "The component part ID to add",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity of this component (default: 1)",
                        "default": 1,
                    },
                    "reference_designator": {
                        "type": "string",
                        "description": "Reference designator (e.g., R1, C3) (optional)",
                    },
                },
                "required": ["assembly_id", "component_id"],
            },
        ),
        Tool(
            name="remove_component",
            description="Remove a component from an assembly's BOM",
            inputSchema={
                "type": "object",
                "properties": {
                    "bom_line_id": {
                        "type": "integer",
                        "description": "The BOM line ID to remove",
                    },
                },
                "required": ["bom_line_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    db = get_db()
    try:
        # Parts
        if name == "list_parts":
            return await _list_parts(db, arguments)
        elif name == "get_part":
            return await _get_part(db, arguments)
        elif name == "create_part":
            return await _create_part(db, arguments)
        elif name == "get_part_tree":
            return await _get_part_tree(db, arguments)
        elif name == "get_part_consumption_history":
            return await _get_part_consumption_history(db, arguments)

        # Procedures
        elif name == "list_procedures":
            return await _list_procedures(db, arguments)
        elif name == "create_procedure":
            return await _create_procedure(db, arguments)
        elif name == "add_procedure_step":
            return await _add_procedure_step(db, arguments)

        # Issues
        elif name == "list_issues":
            return await _list_issues(db, arguments)
        elif name == "create_issue":
            return await _create_issue(db, arguments)

        # Risks
        elif name == "list_risks":
            return await _list_risks(db, arguments)
        elif name == "create_risk":
            return await _create_risk(db, arguments)

        # Project
        elif name == "get_project_info":
            return await _get_project_info(db, arguments)
        elif name == "preview_part_number":
            return await _preview_part_number(db, arguments)

        # Requirements
        elif name == "list_requirements":
            return await _list_requirements(db, arguments)
        elif name == "list_part_requirements":
            return await _list_part_requirements(db, arguments)
        elif name == "assign_requirement":
            return await _assign_requirement(db, arguments)
        elif name == "verify_requirement":
            return await _verify_requirement(db, arguments)

        # BOM
        elif name == "get_bom":
            return await _get_bom(db, arguments)
        elif name == "add_component":
            return await _add_component(db, arguments)
        elif name == "remove_component":
            return await _remove_component(db, arguments)

        else:
            return json_response({"error": f"Unknown tool: {name}"})
    finally:
        db.close()


# ============ TOOL IMPLEMENTATIONS ============


async def _list_parts(db, args: dict) -> list[TextContent]:
    """List parts with optional filtering."""
    query = db.query(Part).filter(Part.deleted_at.is_(None))

    if args.get("category"):
        query = query.filter(Part.category == args["category"])

    if args.get("search"):
        search = f"%{args['search']}%"
        query = query.filter(
            (Part.name.ilike(search)) | (Part.internal_pn.ilike(search)) | (Part.external_pn.ilike(search))
        )

    limit = args.get("limit", 50)
    parts = query.order_by(Part.id.desc()).limit(limit).all()

    return json_response({
        "count": len(parts),
        "parts": [
            {
                "id": p.id,
                "internal_pn": p.internal_pn,
                "name": p.name,
                "category": p.category,
                "external_pn": p.external_pn,
                "description": p.description,
                "tier": p.tier,
                "parent_id": p.parent_id,
            }
            for p in parts
        ],
    })


async def _get_part(db, args: dict) -> list[TextContent]:
    """Get a specific part by ID."""
    from opal.db.models import InventoryConsumption, InventoryRecord

    part = db.query(Part).filter(
        Part.id == args["part_id"],
        Part.deleted_at.is_(None),
    ).first()

    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    # Get tier name from project
    tier_name = None
    project = get_active_project()
    if project:
        tier_config = project.get_tier(part.tier)
        if tier_config:
            tier_name = tier_config.name

    # Get children (sub-parts)
    children = db.query(Part).filter(Part.parent_id == part.id, Part.deleted_at.is_(None)).all()

    # Get consumption history (which OPs used this part)
    consumptions = db.query(InventoryConsumption).join(
        InventoryRecord, InventoryConsumption.inventory_record_id == InventoryRecord.id
    ).filter(InventoryRecord.part_id == part.id).order_by(InventoryConsumption.created_at.desc()).limit(10).all()

    return json_response({
        "id": part.id,
        "internal_pn": part.internal_pn,
        "external_pn": part.external_pn,
        "name": part.name,
        "description": part.description,
        "category": part.category,
        "tier": part.tier,
        "tier_name": tier_name,
        "parent_id": part.parent_id,
        "unit_of_measure": part.unit_of_measure,
        "created_at": part.created_at.isoformat(),
        "children": [
            {"id": c.id, "internal_pn": c.internal_pn, "name": c.name}
            for c in children
        ],
        "recent_consumptions": [
            {
                "id": c.id,
                "quantity": float(c.quantity),
                "procedure_instance_id": c.procedure_instance_id,
                "step_execution_id": c.step_execution_id,
                "consumed_at": c.created_at.isoformat(),
            }
            for c in consumptions
        ],
    })


def _generate_internal_pn(db, tier: int) -> str:
    """Generate next internal part number for a given tier."""
    project = get_active_project()
    if not project:
        count = db.query(Part).filter(Part.tier == tier, Part.deleted_at.is_(None)).count()
        return f"PN-{tier}-{str(count + 1).zfill(4)}"

    count = db.query(Part).filter(Part.tier == tier, Part.deleted_at.is_(None)).count()
    return project.generate_part_number(tier, count + 1)


async def _create_part(db, args: dict) -> list[TextContent]:
    """Create a new part."""
    # Validate parent if specified
    parent_id = args.get("parent_id")
    if parent_id:
        parent = db.query(Part).filter(Part.id == parent_id, Part.deleted_at.is_(None)).first()
        if not parent:
            return json_response({"error": f"Parent part {parent_id} not found"})

    tier = args.get("tier", 1)
    project = get_active_project()
    tier_name = None
    if project:
        tier_config = project.get_tier(tier)
        if tier_config:
            tier_name = tier_config.name

    # Generate internal_pn
    internal_pn = _generate_internal_pn(db, tier)

    part = Part(
        name=args["name"],
        internal_pn=internal_pn,
        category=args.get("category"),
        description=args.get("description"),
        external_pn=args.get("external_pn"),
        unit_of_measure=args.get("unit_of_measure", "each"),
        tier=tier,
        parent_id=parent_id,
    )
    db.add(part)
    db.commit()
    db.refresh(part)

    return json_response({
        "success": True,
        "message": f"Created part '{part.name}' with ID {part.id} ({internal_pn})",
        "part": {
            "id": part.id,
            "internal_pn": internal_pn,
            "name": part.name,
            "category": part.category,
            "tier": tier,
            "tier_name": tier_name,
            "parent_id": parent_id,
        },
    })


def _build_part_tree(db, part: Part, depth: int, current_depth: int = 0) -> dict:
    """Recursively build a part tree."""
    result = {
        "id": part.id,
        "internal_pn": part.internal_pn,
        "name": part.name,
        "tier": part.tier,
        "category": part.category,
    }

    if current_depth < depth:
        children = db.query(Part).filter(Part.parent_id == part.id, Part.deleted_at.is_(None)).all()
        if children:
            result["children"] = [
                _build_part_tree(db, child, depth, current_depth + 1)
                for child in children
            ]

    return result


async def _get_part_tree(db, args: dict) -> list[TextContent]:
    """Get part hierarchy tree."""
    depth = args.get("depth", 3)
    part_id = args.get("part_id")

    if part_id:
        # Start from a specific part
        part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
        if not part:
            return json_response({"error": f"Part {part_id} not found"})
        tree = _build_part_tree(db, part, depth)
    else:
        # Get all top-level parts (no parent)
        top_level = db.query(Part).filter(Part.parent_id.is_(None), Part.deleted_at.is_(None)).all()
        tree = {
            "top_level_parts": [
                _build_part_tree(db, p, depth)
                for p in top_level
            ]
        }

    return json_response(tree)


async def _get_part_consumption_history(db, args: dict) -> list[TextContent]:
    """Get detailed consumption history for a part."""
    from opal.db.models import InventoryConsumption, InventoryRecord
    from opal.db.models.execution import ProcedureInstance, StepExecution

    part = db.query(Part).filter(Part.id == args["part_id"], Part.deleted_at.is_(None)).first()
    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    limit = args.get("limit", 20)

    # Get consumption records with related info
    consumptions = db.query(
        InventoryConsumption,
        InventoryRecord,
        ProcedureInstance,
        StepExecution
    ).join(
        InventoryRecord, InventoryConsumption.inventory_record_id == InventoryRecord.id
    ).outerjoin(
        ProcedureInstance, InventoryConsumption.procedure_instance_id == ProcedureInstance.id
    ).outerjoin(
        StepExecution, InventoryConsumption.step_execution_id == StepExecution.id
    ).filter(
        InventoryRecord.part_id == args["part_id"]
    ).order_by(
        InventoryConsumption.created_at.desc()
    ).limit(limit).all()

    history = []
    for consumption, inv_record, proc_instance, step_exec in consumptions:
        entry = {
            "consumption_id": consumption.id,
            "quantity": float(consumption.quantity),
            "usage_type": consumption.usage_type.value if hasattr(consumption.usage_type, 'value') else consumption.usage_type,
            "consumed_at": consumption.created_at.isoformat(),
            "opal_number": inv_record.opal_number,
            "notes": consumption.notes,
        }
        if proc_instance:
            entry["procedure_instance"] = {
                "id": proc_instance.id,
                "procedure_id": proc_instance.procedure_id,
                "work_order_number": proc_instance.work_order_number,
                "status": proc_instance.status.value if hasattr(proc_instance.status, 'value') else proc_instance.status,
            }
        if step_exec:
            entry["step"] = {
                "id": step_exec.id,
                "step_number": step_exec.step_number_str,
            }
        history.append(entry)

    return json_response({
        "part_id": part.id,
        "internal_pn": part.internal_pn,
        "part_name": part.name,
        "total_consumptions": len(history),
        "history": history,
    })


async def _list_procedures(db, args: dict) -> list[TextContent]:
    """List procedures with optional filtering."""
    query = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None))

    if args.get("status"):
        query = query.filter(MasterProcedure.status == args["status"])

    if args.get("search"):
        search = f"%{args['search']}%"
        query = query.filter(MasterProcedure.name.ilike(search))

    procedures = query.order_by(MasterProcedure.id.desc()).limit(50).all()

    return json_response({
        "count": len(procedures),
        "procedures": [
            {
                "id": p.id,
                "name": p.name,
                "status": p.status.value if hasattr(p.status, "value") else p.status,
                "step_count": len(p.steps),
            }
            for p in procedures
        ],
    })


async def _create_procedure(db, args: dict) -> list[TextContent]:
    """Create a new procedure."""
    procedure = MasterProcedure(
        name=args["name"],
        description=args.get("description"),
        status=ProcedureStatus.DRAFT,
    )
    db.add(procedure)
    db.commit()
    db.refresh(procedure)

    return json_response({
        "success": True,
        "message": f"Created procedure '{procedure.name}' with ID {procedure.id}",
        "procedure": {
            "id": procedure.id,
            "name": procedure.name,
            "status": "draft",
        },
    })


async def _add_procedure_step(db, args: dict) -> list[TextContent]:
    """Add a step to a procedure."""
    procedure = db.query(MasterProcedure).filter(
        MasterProcedure.id == args["procedure_id"],
        MasterProcedure.deleted_at.is_(None),
    ).first()

    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    # Determine step order
    existing_steps = len(procedure.steps)
    step_number = args.get("step_number", str(existing_steps + 1))

    step = ProcedureStep(
        procedure_id=procedure.id,
        title=args["title"],
        instructions=args.get("instructions"),
        step_number=step_number,
        order=existing_steps + 1,
    )
    db.add(step)
    db.commit()
    db.refresh(step)

    return json_response({
        "success": True,
        "message": f"Added step '{step.title}' to procedure '{procedure.name}'",
        "step": {
            "id": step.id,
            "step_number": step.step_number,
            "title": step.title,
        },
    })


async def _list_issues(db, args: dict) -> list[TextContent]:
    """List issues with optional filtering."""
    query = db.query(Issue).filter(Issue.deleted_at.is_(None))

    if args.get("status"):
        query = query.filter(Issue.status == args["status"])

    if args.get("issue_type"):
        query = query.filter(Issue.issue_type == args["issue_type"])

    limit = args.get("limit", 50)
    issues = query.order_by(Issue.id.desc()).limit(limit).all()

    return json_response({
        "count": len(issues),
        "issues": [
            {
                "id": i.id,
                "title": i.title,
                "type": i.issue_type.value if hasattr(i.issue_type, "value") else i.issue_type,
                "status": i.status.value if hasattr(i.status, "value") else i.status,
                "priority": i.priority.value if hasattr(i.priority, "value") else i.priority,
            }
            for i in issues
        ],
    })


async def _create_issue(db, args: dict) -> list[TextContent]:
    """Create a new issue."""
    issue_type = args.get("issue_type", "task")
    priority = args.get("priority", "medium")

    issue = Issue(
        title=args["title"],
        description=args.get("description"),
        issue_type=IssueType(issue_type),
        status=IssueStatus.OPEN,
        priority=IssuePriority(priority),
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    return json_response({
        "success": True,
        "message": f"Created issue '{issue.title}' with ID {issue.id}",
        "issue": {
            "id": issue.id,
            "title": issue.title,
            "type": issue_type,
            "priority": priority,
        },
    })


async def _list_risks(db, args: dict) -> list[TextContent]:
    """List risks with optional filtering."""
    query = db.query(Risk).filter(Risk.deleted_at.is_(None))

    if args.get("status"):
        query = query.filter(Risk.status == args["status"])

    risks = query.order_by(Risk.id.desc()).limit(50).all()

    # Filter by severity in Python (computed property)
    if args.get("severity"):
        risks = [r for r in risks if r.severity == args["severity"]]

    return json_response({
        "count": len(risks),
        "risks": [
            {
                "id": r.id,
                "title": r.title,
                "probability": r.probability,
                "impact": r.impact,
                "severity": r.severity,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
            }
            for r in risks
        ],
    })


async def _create_risk(db, args: dict) -> list[TextContent]:
    """Create a new risk."""
    risk = Risk(
        title=args["title"],
        description=args.get("description"),
        probability=args["probability"],
        impact=args["impact"],
        mitigation_plan=args.get("mitigation_plan"),
        status=RiskStatus.IDENTIFIED,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)

    return json_response({
        "success": True,
        "message": f"Created risk '{risk.title}' with ID {risk.id}",
        "risk": {
            "id": risk.id,
            "title": risk.title,
            "probability": risk.probability,
            "impact": risk.impact,
            "severity": risk.severity,
        },
    })


async def _get_project_info(db, args: dict) -> list[TextContent]:
    """Get project information."""
    project = get_active_project()
    settings = get_active_settings()

    # Get counts
    part_count = db.query(Part).filter(Part.deleted_at.is_(None)).count()
    procedure_count = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).count()
    open_issues = db.query(Issue).filter(
        Issue.deleted_at.is_(None),
        Issue.status.in_(["open", "in_progress"]),
    ).count()
    active_risks = db.query(Risk).filter(
        Risk.deleted_at.is_(None),
        Risk.status != "closed",
    ).count()

    info = {
        "database": settings.database_url,
        "counts": {
            "parts": part_count,
            "procedures": procedure_count,
            "open_issues": open_issues,
            "active_risks": active_risks,
        },
    }

    if project:
        info["project"] = {
            "name": project.name,
            "description": project.description,
            "directory": str(project.project_dir),
            "tiers": [
                {
                    "level": t.level,
                    "name": t.name,
                    "code": t.code,
                    "description": t.description,
                }
                for t in project.tiers
            ],
            "part_numbering": {
                "prefix": project.part_numbering.prefix,
                "separator": project.part_numbering.separator,
                "sequence_digits": project.part_numbering.sequence_digits,
                "format": project.part_numbering.format,
            },
            "requirements": [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "category": r.category,
                }
                for r in project.requirements
            ],
            "categories": project.categories,
        }

    return json_response(info)


async def _preview_part_number(db, args: dict) -> list[TextContent]:
    """Preview a part number for a given tier and sequence."""
    project = get_active_project()
    if not project:
        return json_response({"error": "No project loaded"})

    tier = args["tier"]
    sequence = args["sequence"]

    try:
        part_number = project.generate_part_number(tier, sequence)
        tier_config = project.get_tier(tier)
        return json_response({
            "part_number": part_number,
            "tier": tier,
            "tier_name": tier_config.name if tier_config else None,
            "sequence": sequence,
        })
    except ValueError as e:
        return json_response({"error": str(e)})


# ============ REQUIREMENTS TOOLS ============


async def _list_requirements(db, args: dict) -> list[TextContent]:
    """List all project requirements."""
    project = get_active_project()
    if not project:
        return json_response({"error": "No project loaded", "requirements": []})

    return json_response({
        "count": len(project.requirements),
        "requirements": [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "category": r.category,
            }
            for r in project.requirements
        ],
    })


async def _list_part_requirements(db, args: dict) -> list[TextContent]:
    """List requirements assigned to a part."""
    part = db.query(Part).filter(
        Part.id == args["part_id"],
        Part.deleted_at.is_(None),
    ).first()

    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    project = get_active_project()
    reqs = db.query(PartRequirement).filter(PartRequirement.part_id == args["part_id"]).all()

    return json_response({
        "part_id": args["part_id"],
        "part_name": part.name,
        "count": len(reqs),
        "requirements": [
            {
                "id": r.id,
                "requirement_id": r.requirement_id,
                "title": project.get_requirement(r.requirement_id).title if project and project.get_requirement(r.requirement_id) else None,
                "status": r.status,
                "notes": r.notes,
                "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            }
            for r in reqs
        ],
    })


async def _assign_requirement(db, args: dict) -> list[TextContent]:
    """Assign a requirement to a part."""
    part = db.query(Part).filter(
        Part.id == args["part_id"],
        Part.deleted_at.is_(None),
    ).first()

    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    # Check if requirement exists in project
    project = get_active_project()
    req_title = None
    if project:
        req_config = project.get_requirement(args["requirement_id"])
        if req_config:
            req_title = req_config.title
        else:
            return json_response({"error": f"Requirement {args['requirement_id']} not found in project config"})

    # Check if already assigned
    existing = db.query(PartRequirement).filter(
        PartRequirement.part_id == args["part_id"],
        PartRequirement.requirement_id == args["requirement_id"],
    ).first()

    if existing:
        return json_response({"error": f"Requirement {args['requirement_id']} already assigned to part {args['part_id']}"})

    pr = PartRequirement(
        part_id=args["part_id"],
        requirement_id=args["requirement_id"],
        notes=args.get("notes"),
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)

    return json_response({
        "success": True,
        "message": f"Assigned requirement '{req_title or args['requirement_id']}' to part '{part.name}'",
        "part_requirement": {
            "id": pr.id,
            "part_id": pr.part_id,
            "requirement_id": pr.requirement_id,
            "status": pr.status,
        },
    })


async def _verify_requirement(db, args: dict) -> list[TextContent]:
    """Verify a part requirement."""
    pr = db.query(PartRequirement).filter(PartRequirement.id == args["part_requirement_id"]).first()

    if not pr:
        return json_response({"error": f"Part requirement {args['part_requirement_id']} not found"})

    pr.status = "verified"
    pr.verified_at = datetime.now(timezone.utc)
    if args.get("notes"):
        pr.notes = args["notes"]

    db.commit()
    db.refresh(pr)

    return json_response({
        "success": True,
        "message": f"Verified requirement {pr.requirement_id}",
        "part_requirement": {
            "id": pr.id,
            "requirement_id": pr.requirement_id,
            "status": pr.status,
            "verified_at": pr.verified_at.isoformat(),
        },
    })


# ============ BOM TOOLS ============


async def _get_bom(db, args: dict) -> list[TextContent]:
    """Get BOM for an assembly."""
    part = db.query(Part).filter(
        Part.id == args["assembly_id"],
        Part.deleted_at.is_(None),
    ).first()

    if not part:
        return json_response({"error": f"Part {args['assembly_id']} not found"})

    lines = db.query(BOMLine).filter(BOMLine.assembly_id == args["assembly_id"]).all()

    return json_response({
        "assembly_id": part.id,
        "assembly_name": part.name,
        "count": len(lines),
        "components": [
            {
                "id": line.id,
                "component_id": line.component_id,
                "component_name": line.component.name,
                "component_external_pn": line.component.external_pn,
                "quantity": line.quantity,
                "reference_designator": line.reference_designator,
            }
            for line in lines
        ],
    })


async def _add_component(db, args: dict) -> list[TextContent]:
    """Add a component to an assembly's BOM."""
    assembly = db.query(Part).filter(
        Part.id == args["assembly_id"],
        Part.deleted_at.is_(None),
    ).first()

    if not assembly:
        return json_response({"error": f"Assembly part {args['assembly_id']} not found"})

    component = db.query(Part).filter(
        Part.id == args["component_id"],
        Part.deleted_at.is_(None),
    ).first()

    if not component:
        return json_response({"error": f"Component part {args['component_id']} not found"})

    if args["assembly_id"] == args["component_id"]:
        return json_response({"error": "A part cannot be a component of itself"})

    # Check if already exists
    existing = db.query(BOMLine).filter(
        BOMLine.assembly_id == args["assembly_id"],
        BOMLine.component_id == args["component_id"],
    ).first()

    if existing:
        return json_response({"error": f"Component {args['component_id']} already in assembly {args['assembly_id']} BOM"})

    line = BOMLine(
        assembly_id=args["assembly_id"],
        component_id=args["component_id"],
        quantity=args.get("quantity", 1),
        reference_designator=args.get("reference_designator"),
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    return json_response({
        "success": True,
        "message": f"Added '{component.name}' to '{assembly.name}' BOM",
        "bom_line": {
            "id": line.id,
            "assembly_id": line.assembly_id,
            "component_id": line.component_id,
            "quantity": line.quantity,
        },
    })


async def _remove_component(db, args: dict) -> list[TextContent]:
    """Remove a component from an assembly's BOM."""
    line = db.query(BOMLine).filter(BOMLine.id == args["bom_line_id"]).first()

    if not line:
        return json_response({"error": f"BOM line {args['bom_line_id']} not found"})

    component_name = line.component.name
    assembly_name = line.assembly.name

    db.delete(line)
    db.commit()

    return json_response({
        "success": True,
        "message": f"Removed '{component_name}' from '{assembly_name}' BOM",
    })


# ============ SERVER ENTRY POINT ============


async def run_server():
    """Run the MCP server."""
    print("OPAL MCP Server started", file=sys.stderr)
    print(f"Database: {get_active_settings().database_url}", file=sys.stderr)

    project = get_active_project()
    if project:
        print(f"Project: {project.name}", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
