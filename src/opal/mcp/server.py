"""OPAL MCP Server implementation."""

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from sqlalchemy import func

from opal.config import get_active_project, get_active_settings
from opal.core.audit import get_model_dict, log_create, log_delete, log_update
from opal.core.designators import generate_issue_number, generate_risk_number
from opal.db.base import SessionLocal
from opal.db.models import (
    BOMLine,
    Issue,
    Kit,
    MasterProcedure,
    Part,
    PartRequirement,
    ProcedureOutput,
    ProcedureStep,
    ProcedureVersion,
    Risk,
    StepDependency,
    StepKit,
)
from opal.db.models.issue import IssuePriority, IssueStatus, IssueType
from opal.db.models.procedure import ProcedureStatus, ProcedureType, UsageType
from opal.db.models.risk import RiskStatus

logger = logging.getLogger(__name__)

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
            description=(
                "Create a new master procedure template in draft status. "
                "procedure_type is 'op' (work order, no output) or 'build' "
                "(produces an assembly via ProcedureOutput). Status is always "
                "'draft' until published via the web UI / publish endpoint."
            ),
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
                    "procedure_type": {
                        "type": "string",
                        "enum": ["op", "build"],
                        "description": (
                            "'op' = work order with no part output (default); "
                            "'build' = produces an assembly. Outputs are configured "
                            "separately via the web UI / API."
                        ),
                        "default": "op",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="add_procedure_step",
            description=(
                "Add a step (OP) to a draft procedure. Without parent_step_id, "
                "creates a top-level OP numbered 1, 2, 3... (or C1, C2, C3... if "
                "is_contingency=true). With parent_step_id, creates a sub-step "
                "numbered <parent>.<N> that inherits is_contingency from its "
                "parent. step_number, level, and order are calculated server-side "
                "and cannot be overridden."
            ),
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
                    "parent_step_id": {
                        "type": "integer",
                        "description": (
                            "Parent OP ID. Omit for a top-level OP; set to create "
                            "a sub-step (level=1) under the given OP."
                        ),
                    },
                    "is_contingency": {
                        "type": "boolean",
                        "description": (
                            "Top-level only: mark as a contingency OP (numbered "
                            "C1, C2...) that runs only when an NC is logged. "
                            "Ignored for sub-steps — they inherit from their parent."
                        ),
                        "default": False,
                    },
                    "requires_signoff": {
                        "type": "boolean",
                        "description": "Step requires sign-off to complete (default false)",
                        "default": False,
                    },
                    "estimated_duration_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Estimated duration in minutes (optional)",
                    },
                    "required_data_schema": {
                        "type": "object",
                        "description": (
                            "JSON schema describing data to capture at this step "
                            "(measurements, readings, etc). Optional."
                        ),
                    },
                },
                "required": ["procedure_id", "title"],
            },
        ),
        Tool(
            name="get_procedure",
            description=(
                "Get a procedure with its full hierarchical step tree, kit, "
                "outputs, dependencies, and current version pointer."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer", "description": "The procedure ID"},
                },
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="update_procedure",
            description=(
                "Update a procedure's metadata: name, description, status "
                "(draft/active/deprecated), or procedure_type (op/build). "
                "Note: published versions are immutable; this only edits the "
                "master template."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "enum": ["draft", "active", "deprecated"]},
                    "procedure_type": {"type": "string", "enum": ["op", "build"]},
                },
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="delete_procedure",
            description="Soft-delete a procedure (sets deleted_at). Audit-logged.",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                },
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="update_step",
            description=(
                "Update a step's title, instructions, is_contingency, "
                "requires_signoff, estimated_duration_minutes, or "
                "required_data_schema. Step_number, level, parent, and order "
                "are not editable here — use reorder_steps for ordering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "instructions": {"type": "string"},
                    "is_contingency": {"type": "boolean"},
                    "requires_signoff": {"type": "boolean"},
                    "estimated_duration_minutes": {"type": "integer", "minimum": 1},
                    "required_data_schema": {"type": "object"},
                },
                "required": ["procedure_id", "step_id"],
            },
        ),
        Tool(
            name="delete_step",
            description=(
                "Hard-delete a step (and its sub-steps via cascade). Renumbers "
                "remaining steps so step_numbers stay contiguous (1, 2, 3..., "
                "C1, C2..., <parent>.N)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer"},
                },
                "required": ["procedure_id", "step_id"],
            },
        ),
        Tool(
            name="reorder_steps",
            description=(
                "Reorder every step in the procedure. step_ids must be the "
                "exact set of all current step IDs (including sub-steps) in "
                "the new global order. step_number labels are recomputed to "
                "match the new ordering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "All step IDs of the procedure, in the new order.",
                    },
                },
                "required": ["procedure_id", "step_ids"],
            },
        ),
        Tool(
            name="list_step_dependencies",
            description=(
                "List all op-level prerequisite edges in a procedure as "
                "{step_id, depends_on_step_id} pairs. Dependencies only apply "
                "to top-level OPs (sub-steps inherit their parent's gating)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                },
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="set_step_dependencies",
            description=(
                "Replace the full prerequisite list for a top-level OP. "
                "Validates same-procedure scope, op-level only (no sub-steps "
                "on either side), no self-loops, and no cycles. Pass an empty "
                "depends_on to clear all prereqs for the step."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer", "description": "The dependent (gated) OP"},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Step IDs that must complete before step_id can start.",
                    },
                },
                "required": ["procedure_id", "step_id", "depends_on"],
            },
        ),
        Tool(
            name="get_kit",
            description=(
                "Get the procedure-level Kit (Bill of Materials of parts that "
                "will be consumed by an execution of this procedure)."
            ),
            inputSchema={
                "type": "object",
                "properties": {"procedure_id": {"type": "integer"}},
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="add_kit_item",
            description=(
                "Add a part to the procedure-level Kit. Fails if the part is "
                "already on the kit (use update_kit_item to change quantity)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                    "quantity_required": {"type": "number", "exclusiveMinimum": 0},
                },
                "required": ["procedure_id", "part_id", "quantity_required"],
            },
        ),
        Tool(
            name="update_kit_item",
            description="Update a Kit item's required quantity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "kit_id": {"type": "integer"},
                    "quantity_required": {"type": "number", "exclusiveMinimum": 0},
                },
                "required": ["procedure_id", "kit_id", "quantity_required"],
            },
        ),
        Tool(
            name="remove_kit_item",
            description="Remove a part from the procedure-level Kit (by part_id).",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                },
                "required": ["procedure_id", "part_id"],
            },
        ),
        Tool(
            name="get_outputs",
            description=(
                "Get the output parts a build-type procedure produces. "
                "Returns [] for op-type procedures."
            ),
            inputSchema={
                "type": "object",
                "properties": {"procedure_id": {"type": "integer"}},
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="add_output",
            description=(
                "Add an output part (assembly produced) to a build-type "
                "procedure. Note: the canonical add-output handler also "
                "auto-populates the Kit from the part's BOMLine children; "
                "this tool does the same to stay consistent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                    "quantity_produced": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "default": 1,
                    },
                },
                "required": ["procedure_id", "part_id"],
            },
        ),
        Tool(
            name="update_output",
            description="Update the quantity_produced for an output part (by part_id).",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                    "quantity_produced": {"type": "number", "exclusiveMinimum": 0},
                },
                "required": ["procedure_id", "part_id", "quantity_produced"],
            },
        ),
        Tool(
            name="remove_output",
            description="Remove an output part from a procedure (by part_id).",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                },
                "required": ["procedure_id", "part_id"],
            },
        ),
        Tool(
            name="get_step_kit",
            description=(
                "Get the parts required at a specific step (StepKit). Each "
                "item has a usage_type: 'consume' (inventory decremented at "
                "step completion) or 'tooling' (GSE/fixtures, returned)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer"},
                },
                "required": ["procedure_id", "step_id"],
            },
        ),
        Tool(
            name="add_step_kit_item",
            description="Add a part to a step's kit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                    "quantity_required": {"type": "number", "exclusiveMinimum": 0},
                    "usage_type": {
                        "type": "string",
                        "enum": ["consume", "tooling"],
                        "default": "consume",
                    },
                    "notes": {"type": "string"},
                },
                "required": ["procedure_id", "step_id", "part_id", "quantity_required"],
            },
        ),
        Tool(
            name="update_step_kit_item",
            description="Update a step kit item's quantity, usage_type, or notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer"},
                    "step_kit_id": {"type": "integer"},
                    "quantity_required": {"type": "number", "exclusiveMinimum": 0},
                    "usage_type": {"type": "string", "enum": ["consume", "tooling"]},
                    "notes": {"type": "string"},
                },
                "required": ["procedure_id", "step_id", "step_kit_id"],
            },
        ),
        Tool(
            name="remove_step_kit_item",
            description="Remove a part from a step's kit (by part_id).",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "step_id": {"type": "integer"},
                    "part_id": {"type": "integer"},
                },
                "required": ["procedure_id", "step_id", "part_id"],
            },
        ),
        Tool(
            name="publish_version",
            description=(
                "Publish the current draft as a new immutable ProcedureVersion "
                "snapshot. Bumps current_version_id and flips status to "
                "'active'. Fails if the procedure has no steps. Snapshot "
                "includes steps (with hierarchy), step kits, dependencies "
                "(emitted as prereq `order` values for execution lookup), "
                "procedure kit, and outputs."
            ),
            inputSchema={
                "type": "object",
                "properties": {"procedure_id": {"type": "integer"}},
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="list_versions",
            description="List all published versions of a procedure (newest first).",
            inputSchema={
                "type": "object",
                "properties": {"procedure_id": {"type": "integer"}},
                "required": ["procedure_id"],
            },
        ),
        Tool(
            name="clone_procedure",
            description=(
                "Clone a procedure into a new draft. Copies all steps "
                "(hierarchy preserved). Step kits, procedure kit, and outputs "
                "are copied conditionally. The clone starts at version 0 in "
                "draft status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_id": {"type": "integer"},
                    "new_name": {
                        "type": "string",
                        "description": "Optional new name (default: 'Copy of <source name>')",
                    },
                    "copy_kit": {"type": "boolean", "default": True},
                    "copy_outputs": {"type": "boolean", "default": True},
                },
                "required": ["procedure_id"],
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
                        "description": "Filter by status: open, investigating, disposition_pending, disposition_approved, closed",
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
        elif name == "get_procedure":
            return await _get_procedure(db, arguments)
        elif name == "create_procedure":
            return await _create_procedure(db, arguments)
        elif name == "update_procedure":
            return await _update_procedure(db, arguments)
        elif name == "delete_procedure":
            return await _delete_procedure(db, arguments)
        elif name == "add_procedure_step":
            return await _add_procedure_step(db, arguments)
        elif name == "update_step":
            return await _update_step(db, arguments)
        elif name == "delete_step":
            return await _delete_step(db, arguments)
        elif name == "reorder_steps":
            return await _reorder_steps(db, arguments)
        elif name == "list_step_dependencies":
            return await _list_step_dependencies(db, arguments)
        elif name == "set_step_dependencies":
            return await _set_step_dependencies(db, arguments)
        elif name == "get_kit":
            return await _get_kit(db, arguments)
        elif name == "add_kit_item":
            return await _add_kit_item(db, arguments)
        elif name == "update_kit_item":
            return await _update_kit_item(db, arguments)
        elif name == "remove_kit_item":
            return await _remove_kit_item(db, arguments)
        elif name == "get_outputs":
            return await _get_outputs(db, arguments)
        elif name == "add_output":
            return await _add_output(db, arguments)
        elif name == "update_output":
            return await _update_output(db, arguments)
        elif name == "remove_output":
            return await _remove_output(db, arguments)
        elif name == "get_step_kit":
            return await _get_step_kit(db, arguments)
        elif name == "add_step_kit_item":
            return await _add_step_kit_item(db, arguments)
        elif name == "update_step_kit_item":
            return await _update_step_kit_item(db, arguments)
        elif name == "remove_step_kit_item":
            return await _remove_step_kit_item(db, arguments)
        elif name == "publish_version":
            return await _publish_version(db, arguments)
        elif name == "list_versions":
            return await _list_versions(db, arguments)
        elif name == "clone_procedure":
            return await _clone_procedure(db, arguments)

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
            (Part.name.ilike(search))
            | (Part.internal_pn.ilike(search))
            | (Part.external_pn.ilike(search))
        )

    limit = args.get("limit", 50)
    parts = query.order_by(Part.id.desc()).limit(limit).all()

    return json_response(
        {
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
        }
    )


async def _get_part(db, args: dict) -> list[TextContent]:
    """Get a specific part by ID."""
    from opal.db.models import InventoryConsumption, InventoryRecord

    part = (
        db.query(Part)
        .filter(
            Part.id == args["part_id"],
            Part.deleted_at.is_(None),
        )
        .first()
    )

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
    consumptions = (
        db.query(InventoryConsumption)
        .join(InventoryRecord, InventoryConsumption.inventory_record_id == InventoryRecord.id)
        .filter(InventoryRecord.part_id == part.id)
        .order_by(InventoryConsumption.created_at.desc())
        .limit(10)
        .all()
    )

    return json_response(
        {
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
                {"id": c.id, "internal_pn": c.internal_pn, "name": c.name} for c in children
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
        }
    )


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
    db.flush()
    log_create(db, part)
    db.commit()
    db.refresh(part)

    return json_response(
        {
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
        }
    )


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
                _build_part_tree(db, child, depth, current_depth + 1) for child in children
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
        tree = {"top_level_parts": [_build_part_tree(db, p, depth) for p in top_level]}

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
    consumptions = (
        db.query(InventoryConsumption, InventoryRecord, ProcedureInstance, StepExecution)
        .join(InventoryRecord, InventoryConsumption.inventory_record_id == InventoryRecord.id)
        .outerjoin(
            ProcedureInstance, InventoryConsumption.procedure_instance_id == ProcedureInstance.id
        )
        .outerjoin(StepExecution, InventoryConsumption.step_execution_id == StepExecution.id)
        .filter(InventoryRecord.part_id == args["part_id"])
        .order_by(InventoryConsumption.created_at.desc())
        .limit(limit)
        .all()
    )

    history = []
    for consumption, inv_record, proc_instance, step_exec in consumptions:
        entry = {
            "consumption_id": consumption.id,
            "quantity": float(consumption.quantity),
            "usage_type": consumption.usage_type.value
            if hasattr(consumption.usage_type, "value")
            else consumption.usage_type,
            "consumed_at": consumption.created_at.isoformat(),
            "opal_number": inv_record.opal_number,
            "notes": consumption.notes,
        }
        if proc_instance:
            entry["procedure_instance"] = {
                "id": proc_instance.id,
                "procedure_id": proc_instance.procedure_id,
                "work_order_number": proc_instance.work_order_number,
                "status": proc_instance.status.value
                if hasattr(proc_instance.status, "value")
                else proc_instance.status,
            }
        if step_exec:
            entry["step"] = {
                "id": step_exec.id,
                "step_number": step_exec.step_number_str,
            }
        history.append(entry)

    return json_response(
        {
            "part_id": part.id,
            "internal_pn": part.internal_pn,
            "part_name": part.name,
            "total_consumptions": len(history),
            "history": history,
        }
    )


async def _list_procedures(db, args: dict) -> list[TextContent]:
    """List procedures with optional filtering."""
    query = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None))

    if args.get("status"):
        query = query.filter(MasterProcedure.status == args["status"])

    if args.get("search"):
        search = f"%{args['search']}%"
        query = query.filter(MasterProcedure.name.ilike(search))

    procedures = query.order_by(MasterProcedure.id.desc()).limit(50).all()

    return json_response(
        {
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
        }
    )


async def _create_procedure(db, args: dict) -> list[TextContent]:
    """Create a new master procedure template (draft status)."""
    raw_type = args.get("procedure_type", "op")
    try:
        procedure_type = ProcedureType(raw_type)
    except ValueError:
        return json_response(
            {"error": f"Invalid procedure_type {raw_type!r}; expected 'op' or 'build'"}
        )

    procedure = MasterProcedure(
        name=args["name"],
        description=args.get("description"),
        procedure_type=procedure_type.value,
        status=ProcedureStatus.DRAFT.value,
    )
    db.add(procedure)
    db.flush()

    log_create(db, procedure)
    db.commit()
    db.refresh(procedure)

    return json_response(
        {
            "success": True,
            "message": f"Created procedure '{procedure.name}' with ID {procedure.id}",
            "procedure": {
                "id": procedure.id,
                "name": procedure.name,
                "description": procedure.description,
                "procedure_type": procedure_type.value,
                "status": ProcedureStatus.DRAFT.value,
            },
        }
    )


def _calculate_step_number(db, procedure_id: int, parent_step_id: int | None, is_contingency: bool):
    """Calculate the next step_number — mirrors the canonical API helper.

    Top-level normal ops: 1, 2, 3...
    Top-level contingency ops: C1, C2, C3...
    Sub-steps: <parent.step_number>.<N>
    """
    if parent_step_id:
        parent = db.query(ProcedureStep).filter(ProcedureStep.id == parent_step_id).first()
        if not parent:
            return None
        sub_count = (
            db.query(func.count(ProcedureStep.id))
            .filter(ProcedureStep.parent_step_id == parent_step_id)
            .scalar()
        )
        return f"{parent.step_number}.{sub_count + 1}"

    sibling_query = db.query(func.count(ProcedureStep.id)).filter(
        ProcedureStep.procedure_id == procedure_id,
        ProcedureStep.parent_step_id.is_(None),
        ProcedureStep.is_contingency.is_(is_contingency),
    )
    sibling_count = sibling_query.scalar()
    return f"C{sibling_count + 1}" if is_contingency else str(sibling_count + 1)


async def _add_procedure_step(db, args: dict) -> list[TextContent]:
    """Add an OP (top-level) or sub-step to a procedure."""
    procedure = (
        db.query(MasterProcedure)
        .filter(
            MasterProcedure.id == args["procedure_id"],
            MasterProcedure.deleted_at.is_(None),
        )
        .first()
    )

    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    parent_step_id = args.get("parent_step_id")
    if parent_step_id:
        parent = (
            db.query(ProcedureStep)
            .filter(
                ProcedureStep.id == parent_step_id,
                ProcedureStep.procedure_id == procedure.id,
            )
            .first()
        )
        if not parent:
            return json_response(
                {"error": f"Parent step {parent_step_id} not found in procedure {procedure.id}"}
            )
        # Sub-steps inherit contingency status from parent and are always level=1.
        is_contingency = parent.is_contingency
        level = 1
    else:
        is_contingency = bool(args.get("is_contingency", False))
        level = 0

    step_number = _calculate_step_number(db, procedure.id, parent_step_id, is_contingency)
    if step_number is None:
        return json_response({"error": f"Parent step {parent_step_id} not found"})

    max_order = (
        db.query(func.max(ProcedureStep.order))
        .filter(ProcedureStep.procedure_id == procedure.id)
        .scalar()
    )
    next_order = (max_order or 0) + 1

    step = ProcedureStep(
        procedure_id=procedure.id,
        parent_step_id=parent_step_id,
        order=next_order,
        step_number=step_number,
        level=level,
        title=args["title"],
        instructions=args.get("instructions"),
        required_data_schema=args.get("required_data_schema"),
        is_contingency=is_contingency,
        requires_signoff=bool(args.get("requires_signoff", False)),
        estimated_duration_minutes=args.get("estimated_duration_minutes"),
    )
    db.add(step)
    db.flush()

    log_create(db, step)
    db.commit()
    db.refresh(step)

    return json_response(
        {
            "success": True,
            "message": (
                f"Added {'sub-step' if level else 'OP'} {step.step_number} "
                f"'{step.title}' to procedure '{procedure.name}'"
            ),
            "step": {
                "id": step.id,
                "procedure_id": step.procedure_id,
                "parent_step_id": step.parent_step_id,
                "step_number": step.step_number,
                "level": step.level,
                "order": step.order,
                "title": step.title,
                "instructions": step.instructions,
                "is_contingency": step.is_contingency,
                "requires_signoff": step.requires_signoff,
                "estimated_duration_minutes": step.estimated_duration_minutes,
                "required_data_schema": step.required_data_schema,
            },
        }
    )


async def _list_issues(db, args: dict) -> list[TextContent]:
    """List issues with optional filtering."""
    query = db.query(Issue).filter(Issue.deleted_at.is_(None))

    if args.get("status"):
        query = query.filter(Issue.status == args["status"])

    if args.get("issue_type"):
        query = query.filter(Issue.issue_type == args["issue_type"])

    limit = args.get("limit", 50)
    issues = query.order_by(Issue.id.desc()).limit(limit).all()

    return json_response(
        {
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
        }
    )


async def _create_issue(db, args: dict) -> list[TextContent]:
    """Create a new issue."""
    issue_type = args.get("issue_type", "task")
    priority = args.get("priority", "medium")

    issue = Issue(
        issue_number=generate_issue_number(db),
        title=args["title"],
        description=args.get("description"),
        issue_type=IssueType(issue_type),
        status=IssueStatus.OPEN,
        priority=IssuePriority(priority),
    )
    db.add(issue)
    db.flush()
    log_create(db, issue)
    db.commit()
    db.refresh(issue)

    return json_response(
        {
            "success": True,
            "message": f"Created issue '{issue.title}' with ID {issue.id}",
            "issue": {
                "id": issue.id,
                "title": issue.title,
                "type": issue_type,
                "priority": priority,
            },
        }
    )


async def _list_risks(db, args: dict) -> list[TextContent]:
    """List risks with optional filtering."""
    query = db.query(Risk).filter(Risk.deleted_at.is_(None))

    if args.get("status"):
        query = query.filter(Risk.status == args["status"])

    risks = query.order_by(Risk.id.desc()).limit(50).all()

    # Filter by severity in Python (computed property)
    if args.get("severity"):
        risks = [r for r in risks if r.severity == args["severity"]]

    return json_response(
        {
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
        }
    )


async def _create_risk(db, args: dict) -> list[TextContent]:
    """Create a new risk."""
    risk = Risk(
        risk_number=generate_risk_number(db),
        title=args["title"],
        description=args.get("description"),
        probability=args["probability"],
        impact=args["impact"],
        mitigation_plan=args.get("mitigation_plan"),
        status=RiskStatus.IDENTIFIED,
    )
    db.add(risk)
    db.flush()
    log_create(db, risk)
    db.commit()
    db.refresh(risk)

    return json_response(
        {
            "success": True,
            "message": f"Created risk '{risk.title}' ({risk.risk_number}) with ID {risk.id}",
            "risk": {
                "id": risk.id,
                "risk_number": risk.risk_number,
                "title": risk.title,
                "probability": risk.probability,
                "impact": risk.impact,
                "severity": risk.severity,
            },
        }
    )


async def _get_project_info(db, args: dict) -> list[TextContent]:
    """Get project information."""
    project = get_active_project()
    settings = get_active_settings()

    # Get counts
    part_count = db.query(Part).filter(Part.deleted_at.is_(None)).count()
    procedure_count = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).count()
    open_issues = (
        db.query(Issue)
        .filter(
            Issue.deleted_at.is_(None),
            Issue.status.in_(["open", "investigating"]),
        )
        .count()
    )
    active_risks = (
        db.query(Risk)
        .filter(
            Risk.deleted_at.is_(None),
            Risk.status != "closed",
        )
        .count()
    )

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
        return json_response(
            {
                "part_number": part_number,
                "tier": tier,
                "tier_name": tier_config.name if tier_config else None,
                "sequence": sequence,
            }
        )
    except ValueError as e:
        return json_response({"error": str(e)})


# ============ REQUIREMENTS TOOLS ============


async def _list_requirements(db, args: dict) -> list[TextContent]:
    """List all project requirements."""
    project = get_active_project()
    if not project:
        return json_response({"error": "No project loaded", "requirements": []})

    return json_response(
        {
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
        }
    )


async def _list_part_requirements(db, args: dict) -> list[TextContent]:
    """List requirements assigned to a part."""
    part = (
        db.query(Part)
        .filter(
            Part.id == args["part_id"],
            Part.deleted_at.is_(None),
        )
        .first()
    )

    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    project = get_active_project()
    reqs = db.query(PartRequirement).filter(PartRequirement.part_id == args["part_id"]).all()

    return json_response(
        {
            "part_id": args["part_id"],
            "part_name": part.name,
            "count": len(reqs),
            "requirements": [
                {
                    "id": r.id,
                    "requirement_id": r.requirement_id,
                    "title": project.get_requirement(r.requirement_id).title
                    if project and project.get_requirement(r.requirement_id)
                    else None,
                    "status": r.status,
                    "notes": r.notes,
                    "verified_at": r.verified_at.isoformat() if r.verified_at else None,
                }
                for r in reqs
            ],
        }
    )


async def _assign_requirement(db, args: dict) -> list[TextContent]:
    """Assign a requirement to a part."""
    part = (
        db.query(Part)
        .filter(
            Part.id == args["part_id"],
            Part.deleted_at.is_(None),
        )
        .first()
    )

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
            return json_response(
                {"error": f"Requirement {args['requirement_id']} not found in project config"}
            )

    # Check if already assigned
    existing = (
        db.query(PartRequirement)
        .filter(
            PartRequirement.part_id == args["part_id"],
            PartRequirement.requirement_id == args["requirement_id"],
        )
        .first()
    )

    if existing:
        return json_response(
            {
                "error": f"Requirement {args['requirement_id']} already assigned to part {args['part_id']}"
            }
        )

    pr = PartRequirement(
        part_id=args["part_id"],
        requirement_id=args["requirement_id"],
        notes=args.get("notes"),
    )
    db.add(pr)
    db.flush()
    log_create(db, pr)
    db.commit()
    db.refresh(pr)

    return json_response(
        {
            "success": True,
            "message": f"Assigned requirement '{req_title or args['requirement_id']}' to part '{part.name}'",
            "part_requirement": {
                "id": pr.id,
                "part_id": pr.part_id,
                "requirement_id": pr.requirement_id,
                "status": pr.status,
            },
        }
    )


async def _verify_requirement(db, args: dict) -> list[TextContent]:
    """Verify a part requirement."""
    pr = db.query(PartRequirement).filter(PartRequirement.id == args["part_requirement_id"]).first()

    if not pr:
        return json_response({"error": f"Part requirement {args['part_requirement_id']} not found"})

    old_values = get_model_dict(pr)
    pr.status = "verified"
    pr.verified_at = datetime.now(UTC)
    if args.get("notes"):
        pr.notes = args["notes"]

    log_update(db, pr, old_values)
    db.commit()
    db.refresh(pr)

    return json_response(
        {
            "success": True,
            "message": f"Verified requirement {pr.requirement_id}",
            "part_requirement": {
                "id": pr.id,
                "requirement_id": pr.requirement_id,
                "status": pr.status,
                "verified_at": pr.verified_at.isoformat(),
            },
        }
    )


# ============ BOM TOOLS ============


async def _get_bom(db, args: dict) -> list[TextContent]:
    """Get BOM for an assembly."""
    part = (
        db.query(Part)
        .filter(
            Part.id == args["assembly_id"],
            Part.deleted_at.is_(None),
        )
        .first()
    )

    if not part:
        return json_response({"error": f"Part {args['assembly_id']} not found"})

    lines = db.query(BOMLine).filter(BOMLine.assembly_id == args["assembly_id"]).all()

    return json_response(
        {
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
        }
    )


async def _add_component(db, args: dict) -> list[TextContent]:
    """Add a component to an assembly's BOM."""
    assembly = (
        db.query(Part)
        .filter(
            Part.id == args["assembly_id"],
            Part.deleted_at.is_(None),
        )
        .first()
    )

    if not assembly:
        return json_response({"error": f"Assembly part {args['assembly_id']} not found"})

    component = (
        db.query(Part)
        .filter(
            Part.id == args["component_id"],
            Part.deleted_at.is_(None),
        )
        .first()
    )

    if not component:
        return json_response({"error": f"Component part {args['component_id']} not found"})

    if args["assembly_id"] == args["component_id"]:
        return json_response({"error": "A part cannot be a component of itself"})

    # Check if already exists
    existing = (
        db.query(BOMLine)
        .filter(
            BOMLine.assembly_id == args["assembly_id"],
            BOMLine.component_id == args["component_id"],
        )
        .first()
    )

    if existing:
        return json_response(
            {
                "error": f"Component {args['component_id']} already in assembly {args['assembly_id']} BOM"
            }
        )

    line = BOMLine(
        assembly_id=args["assembly_id"],
        component_id=args["component_id"],
        quantity=args.get("quantity", 1),
        reference_designator=args.get("reference_designator"),
    )
    db.add(line)
    db.flush()
    log_create(db, line)
    db.commit()
    db.refresh(line)

    return json_response(
        {
            "success": True,
            "message": f"Added '{component.name}' to '{assembly.name}' BOM",
            "bom_line": {
                "id": line.id,
                "assembly_id": line.assembly_id,
                "component_id": line.component_id,
                "quantity": line.quantity,
            },
        }
    )


async def _remove_component(db, args: dict) -> list[TextContent]:
    """Remove a component from an assembly's BOM."""
    line = db.query(BOMLine).filter(BOMLine.id == args["bom_line_id"]).first()

    if not line:
        return json_response({"error": f"BOM line {args['bom_line_id']} not found"})

    component_name = line.component.name
    assembly_name = line.assembly.name

    log_delete(db, line)
    db.delete(line)
    db.commit()

    return json_response(
        {
            "success": True,
            "message": f"Removed '{component_name}' from '{assembly_name}' BOM",
        }
    )


# ============ PROCEDURE: READ / UPDATE / DELETE / RENUMBER ============


def _serialize_step(step: ProcedureStep) -> dict:
    return {
        "id": step.id,
        "procedure_id": step.procedure_id,
        "parent_step_id": step.parent_step_id,
        "order": step.order,
        "step_number": step.step_number,
        "level": step.level,
        "title": step.title,
        "instructions": step.instructions,
        "required_data_schema": step.required_data_schema,
        "is_contingency": step.is_contingency,
        "requires_signoff": step.requires_signoff,
        "estimated_duration_minutes": step.estimated_duration_minutes,
        "workcenter_id": step.workcenter_id,
    }


def _build_step_tree(steps: list[ProcedureStep]) -> list[dict]:
    """Build the hierarchical step tree, mirroring the canonical helper."""
    children_map: dict[int | None, list[ProcedureStep]] = {}
    for s in steps:
        children_map.setdefault(s.parent_step_id, []).append(s)
    for kids in children_map.values():
        kids.sort(key=lambda s: s.order)

    def build(node: ProcedureStep) -> dict:
        d = _serialize_step(node)
        d["sub_steps"] = [build(c) for c in children_map.get(node.id, [])]
        return d

    return [build(s) for s in children_map.get(None, [])]


def _renumber_procedure_steps(steps: list[ProcedureStep]) -> None:
    """Recompute step_numbers from current `order` values.

    Mirrors src/opal/api/routes/procedures.py:_renumber_procedure_steps.
    Top-level normal -> 1, 2, 3...; top-level contingency -> C1, C2...;
    sub-steps -> <parent_step_number>.<N>.
    """
    top_level = sorted([s for s in steps if s.parent_step_id is None], key=lambda s: s.order)
    normal_idx = 0
    contingency_idx = 0
    for op in top_level:
        if op.is_contingency:
            contingency_idx += 1
            op.step_number = f"C{contingency_idx}"
        else:
            normal_idx += 1
            op.step_number = str(normal_idx)
    children: dict[int, list[ProcedureStep]] = {}
    for s in steps:
        if s.parent_step_id is not None:
            children.setdefault(s.parent_step_id, []).append(s)
    for parent_id, kids in children.items():
        parent = next((s for s in steps if s.id == parent_id), None)
        if parent is None:
            continue
        kids.sort(key=lambda s: s.order)
        for i, kid in enumerate(kids, start=1):
            kid.step_number = f"{parent.step_number}.{i}"


def _load_procedure(db, procedure_id: int) -> MasterProcedure | None:
    return (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )


async def _get_procedure(db, args: dict) -> list[TextContent]:
    """Return a procedure with its full hierarchical step tree, kit, outputs, and deps."""
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure.id)
        .order_by(ProcedureStep.order)
        .all()
    )
    deps = (
        db.query(StepDependency)
        .join(ProcedureStep, StepDependency.step_id == ProcedureStep.id)
        .filter(ProcedureStep.procedure_id == procedure.id)
        .all()
    )
    kit_items = db.query(Kit).filter(Kit.procedure_id == procedure.id).all()
    outputs = db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == procedure.id).all()

    return json_response(
        {
            "id": procedure.id,
            "name": procedure.name,
            "description": procedure.description,
            "procedure_type": procedure.procedure_type.value
            if hasattr(procedure.procedure_type, "value")
            else procedure.procedure_type,
            "status": procedure.status.value
            if hasattr(procedure.status, "value")
            else procedure.status,
            "current_version_id": procedure.current_version_id,
            "step_count": len(steps),
            "steps": _build_step_tree(steps),
            "dependencies": [
                {"step_id": d.step_id, "depends_on_step_id": d.depends_on_step_id} for d in deps
            ],
            "kit": [
                {
                    "id": k.id,
                    "part_id": k.part_id,
                    "part_name": k.part.name,
                    "quantity_required": float(k.quantity_required),
                }
                for k in kit_items
            ],
            "outputs": [
                {
                    "id": o.id,
                    "part_id": o.part_id,
                    "part_name": o.part.name,
                    "quantity_produced": float(o.quantity_produced),
                }
                for o in outputs
            ],
        }
    )


async def _update_procedure(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    old_values = get_model_dict(procedure)
    if "name" in args:
        procedure.name = args["name"]
    if "description" in args:
        procedure.description = args["description"]
    if "status" in args:
        try:
            procedure.status = ProcedureStatus(args["status"]).value
        except ValueError:
            return json_response({"error": f"Invalid status {args['status']!r}"})
    if "procedure_type" in args:
        try:
            procedure.procedure_type = ProcedureType(args["procedure_type"]).value
        except ValueError:
            return json_response({"error": f"Invalid procedure_type {args['procedure_type']!r}"})

    log_update(db, procedure, old_values)
    db.commit()
    db.refresh(procedure)

    return json_response(
        {
            "success": True,
            "message": f"Updated procedure {procedure.id}",
            "procedure": {
                "id": procedure.id,
                "name": procedure.name,
                "description": procedure.description,
                "procedure_type": procedure.procedure_type.value
                if hasattr(procedure.procedure_type, "value")
                else procedure.procedure_type,
                "status": procedure.status.value
                if hasattr(procedure.status, "value")
                else procedure.status,
            },
        }
    )


async def _delete_procedure(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    procedure.deleted_at = datetime.now(UTC)
    log_delete(db, procedure)
    db.commit()
    return json_response({"success": True, "message": f"Soft-deleted procedure {procedure.id}"})


async def _update_step(db, args: dict) -> list[TextContent]:
    step = (
        db.query(ProcedureStep)
        .filter(
            ProcedureStep.id == args["step_id"],
            ProcedureStep.procedure_id == args["procedure_id"],
        )
        .first()
    )
    if not step:
        return json_response(
            {"error": (f"Step {args['step_id']} not found in procedure {args['procedure_id']}")}
        )

    old_values = get_model_dict(step)
    if "title" in args:
        step.title = args["title"]
    if "instructions" in args:
        step.instructions = args["instructions"]
    if "is_contingency" in args:
        step.is_contingency = bool(args["is_contingency"])
    if "requires_signoff" in args:
        step.requires_signoff = bool(args["requires_signoff"])
    if "estimated_duration_minutes" in args:
        step.estimated_duration_minutes = args["estimated_duration_minutes"]
    if "required_data_schema" in args:
        step.required_data_schema = args["required_data_schema"]

    log_update(db, step, old_values)
    db.commit()
    db.refresh(step)

    return json_response(
        {"success": True, "message": f"Updated step {step.id}", "step": _serialize_step(step)}
    )


async def _delete_step(db, args: dict) -> list[TextContent]:
    step = (
        db.query(ProcedureStep)
        .filter(
            ProcedureStep.id == args["step_id"],
            ProcedureStep.procedure_id == args["procedure_id"],
        )
        .first()
    )
    if not step:
        return json_response({"error": f"Step {args['step_id']} not found"})

    deleted_order = step.order
    log_delete(db, step)
    db.delete(step)
    db.flush()

    # Pull remaining steps after the deleted-cascade flush and renumber.
    remaining = (
        db.query(ProcedureStep).filter(ProcedureStep.procedure_id == args["procedure_id"]).all()
    )
    for s in remaining:
        if s.order > deleted_order:
            s.order -= 1
    _renumber_procedure_steps(remaining)
    db.commit()

    return json_response(
        {
            "success": True,
            "message": f"Deleted step {args['step_id']} and renumbered remaining steps",
            "remaining_step_count": len(remaining),
        }
    )


async def _reorder_steps(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    steps = db.query(ProcedureStep).filter(ProcedureStep.procedure_id == procedure.id).all()
    step_map = {s.id: s for s in steps}
    requested = list(args["step_ids"])
    if set(requested) != set(step_map.keys()):
        return json_response(
            {
                "error": (
                    "step_ids must be the exact set of all step IDs in the procedure "
                    f"(got {len(requested)} ids, procedure has {len(step_map)} steps)"
                )
            }
        )

    for i, sid in enumerate(requested, start=1):
        step_map[sid].order = i
    _renumber_procedure_steps(steps)
    db.commit()

    ordered = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure.id)
        .order_by(ProcedureStep.order)
        .all()
    )
    return json_response(
        {
            "success": True,
            "message": f"Reordered {len(ordered)} steps",
            "steps": [_serialize_step(s) for s in ordered],
        }
    )


# ============ STEP DEPENDENCIES ============


async def _list_step_dependencies(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    rows = (
        db.query(StepDependency)
        .join(ProcedureStep, StepDependency.step_id == ProcedureStep.id)
        .filter(ProcedureStep.procedure_id == procedure.id)
        .all()
    )
    return json_response(
        {
            "procedure_id": procedure.id,
            "count": len(rows),
            "dependencies": [
                {"step_id": d.step_id, "depends_on_step_id": d.depends_on_step_id} for d in rows
            ],
        }
    )


async def _set_step_dependencies(db, args: dict) -> list[TextContent]:
    """Replace the prerequisite list for a top-level OP. Mirrors the canonical
    set_step_dependencies handler — same-procedure scope, op-level only, no
    self-loops, no cycles."""
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    target_id: int = args["step_id"]
    target = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == target_id, ProcedureStep.procedure_id == procedure.id)
        .first()
    )
    if not target:
        return json_response({"error": f"Step {target_id} not found in procedure {procedure.id}"})
    if target.parent_step_id is not None:
        return json_response({"error": "Dependencies are only allowed on top-level operations"})

    requested = list(dict.fromkeys(args["depends_on"]))
    if target_id in requested:
        return json_response({"error": "A step cannot depend on itself"})

    if requested:
        prereqs = db.query(ProcedureStep).filter(ProcedureStep.id.in_(requested)).all()
        prereq_map = {p.id: p for p in prereqs}
        for pid in requested:
            p = prereq_map.get(pid)
            if p is None or p.procedure_id != procedure.id:
                return json_response({"error": f"Step {pid} is not in this procedure"})
            if p.parent_step_id is not None:
                return json_response(
                    {"error": f"Step {pid} is a sub-step; only OPs can be prerequisites"}
                )

    existing = db.query(StepDependency).all()
    adj: dict[int, set[int]] = {}
    for d in existing:
        if d.step_id == target_id:
            continue
        adj.setdefault(d.depends_on_step_id, set()).add(d.step_id)
    for pid in requested:
        adj.setdefault(pid, set()).add(target_id)

    def reachable_from(start: int) -> set[int]:
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    downstream = reachable_from(target_id)
    cycle = downstream & set(requested)
    if cycle:
        return json_response(
            {
                "error": (
                    f"Cycle: step {target_id} already gates {sorted(cycle)}; cannot depend on them."
                )
            }
        )

    current = db.query(StepDependency).filter(StepDependency.step_id == target_id).all()
    for d in current:
        log_delete(db, d)
        db.delete(d)
    db.flush()
    for pid in requested:
        new_dep = StepDependency(step_id=target_id, depends_on_step_id=pid)
        db.add(new_dep)
        db.flush()
        log_create(db, new_dep)
    db.commit()
    return json_response(
        {
            "success": True,
            "message": (
                f"Set {len(requested)} prerequisite(s) for step {target_id}"
                if requested
                else f"Cleared prerequisites for step {target_id}"
            ),
            "step_id": target_id,
            "depends_on": requested,
        }
    )


# ============ KIT (procedure-level BOM) ============


async def _get_kit(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    items = (
        db.query(Kit).join(Part).filter(Kit.procedure_id == procedure.id).order_by(Part.name).all()
    )
    return json_response(
        {
            "procedure_id": procedure.id,
            "count": len(items),
            "kit": [
                {
                    "id": k.id,
                    "part_id": k.part_id,
                    "part_name": k.part.name,
                    "part_external_pn": k.part.external_pn,
                    "quantity_required": float(k.quantity_required),
                }
                for k in items
            ],
        }
    )


async def _add_kit_item(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    part = db.query(Part).filter(Part.id == args["part_id"], Part.deleted_at.is_(None)).first()
    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    existing = (
        db.query(Kit)
        .filter(Kit.procedure_id == procedure.id, Kit.part_id == args["part_id"])
        .first()
    )
    if existing:
        return json_response(
            {"error": f"Part {args['part_id']} already in kit (use update_kit_item)"}
        )

    item = Kit(
        procedure_id=procedure.id,
        part_id=args["part_id"],
        quantity_required=Decimal(str(args["quantity_required"])),
    )
    db.add(item)
    db.flush()
    log_create(db, item)
    db.commit()
    db.refresh(item)
    return json_response(
        {
            "success": True,
            "message": f"Added '{part.name}' to procedure {procedure.id} kit",
            "kit_item": {
                "id": item.id,
                "part_id": item.part_id,
                "quantity_required": float(item.quantity_required),
            },
        }
    )


async def _update_kit_item(db, args: dict) -> list[TextContent]:
    item = (
        db.query(Kit)
        .filter(Kit.id == args["kit_id"], Kit.procedure_id == args["procedure_id"])
        .first()
    )
    if not item:
        return json_response({"error": f"Kit item {args['kit_id']} not found"})

    old_values = get_model_dict(item)
    item.quantity_required = Decimal(str(args["quantity_required"]))
    log_update(db, item, old_values)
    db.commit()
    db.refresh(item)
    return json_response(
        {
            "success": True,
            "message": f"Updated kit item {item.id} quantity to {item.quantity_required}",
            "kit_item": {
                "id": item.id,
                "part_id": item.part_id,
                "quantity_required": float(item.quantity_required),
            },
        }
    )


async def _remove_kit_item(db, args: dict) -> list[TextContent]:
    item = (
        db.query(Kit)
        .filter(Kit.procedure_id == args["procedure_id"], Kit.part_id == args["part_id"])
        .first()
    )
    if not item:
        return json_response(
            {
                "error": (
                    f"Kit item for part {args['part_id']} not found in "
                    f"procedure {args['procedure_id']}"
                )
            }
        )

    log_delete(db, item)
    db.delete(item)
    db.commit()
    return json_response({"success": True, "message": f"Removed part {args['part_id']} from kit"})


# ============ PROCEDURE OUTPUTS (build-type) ============


async def _get_outputs(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    outputs = db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == procedure.id).all()
    return json_response(
        {
            "procedure_id": procedure.id,
            "procedure_type": procedure.procedure_type.value
            if hasattr(procedure.procedure_type, "value")
            else procedure.procedure_type,
            "count": len(outputs),
            "outputs": [
                {
                    "id": o.id,
                    "part_id": o.part_id,
                    "part_name": o.part.name,
                    "part_external_pn": o.part.external_pn,
                    "quantity_produced": float(o.quantity_produced),
                }
                for o in outputs
            ],
        }
    )


async def _add_output(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    part = db.query(Part).filter(Part.id == args["part_id"], Part.deleted_at.is_(None)).first()
    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    existing = (
        db.query(ProcedureOutput)
        .filter(
            ProcedureOutput.procedure_id == procedure.id,
            ProcedureOutput.part_id == args["part_id"],
        )
        .first()
    )
    if existing:
        return json_response(
            {"error": f"Part {args['part_id']} already in outputs (use update_output)"}
        )

    qty = Decimal(str(args.get("quantity_produced", 1)))
    output = ProcedureOutput(
        procedure_id=procedure.id, part_id=args["part_id"], quantity_produced=qty
    )
    db.add(output)
    db.flush()
    log_create(db, output)

    # Mirror canonical add_output: auto-populate the procedure kit from the
    # output part's direct BOM children (single-level).
    bom_lines = db.query(BOMLine).filter(BOMLine.assembly_id == args["part_id"]).all()
    auto_added = 0
    auto_bumped = 0
    for bom_line in bom_lines:
        kit_qty = Decimal(str(bom_line.quantity)) * qty
        existing_kit = (
            db.query(Kit)
            .filter(Kit.procedure_id == procedure.id, Kit.part_id == bom_line.component_id)
            .first()
        )
        if existing_kit:
            old_values = get_model_dict(existing_kit)
            existing_kit.quantity_required += kit_qty
            log_update(db, existing_kit, old_values)
            auto_bumped += 1
        else:
            new_kit = Kit(
                procedure_id=procedure.id,
                part_id=bom_line.component_id,
                quantity_required=kit_qty,
            )
            db.add(new_kit)
            db.flush()
            log_create(db, new_kit)
            auto_added += 1

    db.commit()
    db.refresh(output)
    return json_response(
        {
            "success": True,
            "message": (
                f"Added output '{part.name}' (qty {qty}) to procedure "
                f"{procedure.id}; auto-added {auto_added} kit item(s), bumped {auto_bumped}"
            ),
            "output": {
                "id": output.id,
                "part_id": output.part_id,
                "quantity_produced": float(output.quantity_produced),
            },
            "kit_auto_added": auto_added,
            "kit_auto_bumped": auto_bumped,
        }
    )


async def _update_output(db, args: dict) -> list[TextContent]:
    output = (
        db.query(ProcedureOutput)
        .filter(
            ProcedureOutput.procedure_id == args["procedure_id"],
            ProcedureOutput.part_id == args["part_id"],
        )
        .first()
    )
    if not output:
        return json_response(
            {
                "error": (
                    f"Output for part {args['part_id']} not found in procedure "
                    f"{args['procedure_id']}"
                )
            }
        )

    old_values = get_model_dict(output)
    output.quantity_produced = Decimal(str(args["quantity_produced"]))
    log_update(db, output, old_values)
    db.commit()
    db.refresh(output)
    return json_response(
        {
            "success": True,
            "message": f"Updated output quantity to {output.quantity_produced}",
            "output": {
                "id": output.id,
                "part_id": output.part_id,
                "quantity_produced": float(output.quantity_produced),
            },
        }
    )


async def _remove_output(db, args: dict) -> list[TextContent]:
    output = (
        db.query(ProcedureOutput)
        .filter(
            ProcedureOutput.procedure_id == args["procedure_id"],
            ProcedureOutput.part_id == args["part_id"],
        )
        .first()
    )
    if not output:
        return json_response(
            {
                "error": (
                    f"Output for part {args['part_id']} not found in procedure "
                    f"{args['procedure_id']}"
                )
            }
        )

    log_delete(db, output)
    db.delete(output)
    db.commit()
    return json_response({"success": True, "message": f"Removed output part {args['part_id']}"})


# ============ STEP KIT (step-level BOM) ============


async def _get_step_kit(db, args: dict) -> list[TextContent]:
    step = (
        db.query(ProcedureStep)
        .filter(
            ProcedureStep.id == args["step_id"],
            ProcedureStep.procedure_id == args["procedure_id"],
        )
        .first()
    )
    if not step:
        return json_response({"error": f"Step {args['step_id']} not found"})

    return json_response(
        {
            "procedure_id": step.procedure_id,
            "step_id": step.id,
            "step_number": step.step_number,
            "count": len(step.step_kits),
            "items": [
                {
                    "id": sk.id,
                    "part_id": sk.part_id,
                    "part_name": sk.part.name,
                    "part_external_pn": sk.part.external_pn,
                    "quantity_required": float(sk.quantity_required),
                    "usage_type": sk.usage_type.value
                    if hasattr(sk.usage_type, "value")
                    else sk.usage_type,
                    "notes": sk.notes,
                }
                for sk in step.step_kits
            ],
        }
    )


async def _add_step_kit_item(db, args: dict) -> list[TextContent]:
    step = (
        db.query(ProcedureStep)
        .filter(
            ProcedureStep.id == args["step_id"],
            ProcedureStep.procedure_id == args["procedure_id"],
        )
        .first()
    )
    if not step:
        return json_response({"error": f"Step {args['step_id']} not found"})

    part = db.query(Part).filter(Part.id == args["part_id"], Part.deleted_at.is_(None)).first()
    if not part:
        return json_response({"error": f"Part {args['part_id']} not found"})

    existing = (
        db.query(StepKit)
        .filter(StepKit.step_id == step.id, StepKit.part_id == args["part_id"])
        .first()
    )
    if existing:
        return json_response(
            {
                "error": (
                    f"Part {args['part_id']} already in step {step.id} kit "
                    "(use update_step_kit_item)"
                )
            }
        )

    try:
        usage = UsageType(args.get("usage_type", "consume"))
    except ValueError:
        return json_response({"error": f"Invalid usage_type {args.get('usage_type')!r}"})

    sk = StepKit(
        step_id=step.id,
        part_id=args["part_id"],
        quantity_required=Decimal(str(args["quantity_required"])),
        usage_type=usage,
        notes=args.get("notes"),
    )
    db.add(sk)
    db.flush()
    log_create(db, sk)
    db.commit()
    db.refresh(sk)
    return json_response(
        {
            "success": True,
            "message": (
                f"Added '{part.name}' ({usage.value}, qty "
                f"{sk.quantity_required}) to step {step.step_number}"
            ),
            "step_kit_item": {
                "id": sk.id,
                "step_id": sk.step_id,
                "part_id": sk.part_id,
                "quantity_required": float(sk.quantity_required),
                "usage_type": usage.value,
                "notes": sk.notes,
            },
        }
    )


async def _update_step_kit_item(db, args: dict) -> list[TextContent]:
    sk = (
        db.query(StepKit)
        .join(ProcedureStep)
        .filter(
            StepKit.id == args["step_kit_id"],
            StepKit.step_id == args["step_id"],
            ProcedureStep.procedure_id == args["procedure_id"],
        )
        .first()
    )
    if not sk:
        return json_response({"error": f"Step kit item {args['step_kit_id']} not found"})

    old_values = get_model_dict(sk)
    if "quantity_required" in args:
        sk.quantity_required = Decimal(str(args["quantity_required"]))
    if "usage_type" in args:
        try:
            sk.usage_type = UsageType(args["usage_type"])
        except ValueError:
            return json_response({"error": f"Invalid usage_type {args['usage_type']!r}"})
    if "notes" in args:
        sk.notes = args["notes"]

    log_update(db, sk, old_values)
    db.commit()
    db.refresh(sk)
    return json_response(
        {
            "success": True,
            "message": f"Updated step kit item {sk.id}",
            "step_kit_item": {
                "id": sk.id,
                "part_id": sk.part_id,
                "quantity_required": float(sk.quantity_required),
                "usage_type": sk.usage_type.value
                if hasattr(sk.usage_type, "value")
                else sk.usage_type,
                "notes": sk.notes,
            },
        }
    )


async def _remove_step_kit_item(db, args: dict) -> list[TextContent]:
    sk = (
        db.query(StepKit)
        .join(ProcedureStep)
        .filter(
            StepKit.step_id == args["step_id"],
            StepKit.part_id == args["part_id"],
            ProcedureStep.procedure_id == args["procedure_id"],
        )
        .first()
    )
    if not sk:
        return json_response(
            {
                "error": (
                    f"Step kit item for part {args['part_id']} not found on step {args['step_id']}"
                )
            }
        )

    log_delete(db, sk)
    db.delete(sk)
    db.commit()
    return json_response(
        {"success": True, "message": f"Removed part {args['part_id']} from step kit"}
    )


# ============ PUBLISH + VERSIONS + CLONE ============


async def _publish_version(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure.id)
        .order_by(ProcedureStep.order)
        .all()
    )
    if not steps:
        return json_response({"error": "Cannot publish procedure with no steps"})

    max_version = (
        db.query(func.max(ProcedureVersion.version_number))
        .filter(ProcedureVersion.procedure_id == procedure.id)
        .scalar()
    )
    next_version = (max_version or 0) + 1

    step_ids = [s.id for s in steps]
    all_step_kits = db.query(StepKit).filter(StepKit.step_id.in_(step_ids)).all()
    step_kit_map: dict[int, list[StepKit]] = {}
    for sk in all_step_kits:
        step_kit_map.setdefault(sk.step_id, []).append(sk)

    all_deps = db.query(StepDependency).filter(StepDependency.step_id.in_(step_ids)).all()
    step_id_to_order = {s.id: s.order for s in steps}
    depends_on_map: dict[int, list[int]] = {}
    for d in all_deps:
        prereq_order = step_id_to_order.get(d.depends_on_step_id)
        if prereq_order is not None:
            depends_on_map.setdefault(d.step_id, []).append(prereq_order)

    def step_to_dict(step: ProcedureStep) -> dict:
        return {
            "id": step.id,
            "order": step.order,
            "step_number": step.step_number,
            "level": step.level,
            "parent_step_id": step.parent_step_id,
            "title": step.title,
            "instructions": step.instructions,
            "required_data_schema": step.required_data_schema,
            "is_contingency": step.is_contingency,
            "requires_signoff": step.requires_signoff,
            "estimated_duration_minutes": step.estimated_duration_minutes,
            "workcenter_id": step.workcenter_id,
            "depends_on": sorted(depends_on_map.get(step.id, [])),
            "step_kit": [
                {
                    "part_id": sk.part_id,
                    "part_name": sk.part.name,
                    "quantity_required": float(sk.quantity_required),
                    "usage_type": sk.usage_type.value
                    if hasattr(sk.usage_type, "value")
                    else sk.usage_type,
                    "notes": sk.notes,
                }
                for sk in step_kit_map.get(step.id, [])
            ],
        }

    kit_items = db.query(Kit).filter(Kit.procedure_id == procedure.id).all()
    output_items = (
        db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == procedure.id).all()
    )

    content = {
        "procedure_name": procedure.name,
        "procedure_description": procedure.description,
        "steps": [step_to_dict(s) for s in steps],
        "kit_items": [
            {"part_id": k.part_id, "quantity_required": float(k.quantity_required)}
            for k in kit_items
        ],
        "output_items": [
            {"part_id": o.part_id, "quantity_produced": float(o.quantity_produced)}
            for o in output_items
        ],
    }

    version = ProcedureVersion(
        procedure_id=procedure.id,
        version_number=next_version,
        content=content,
        created_by_id=None,
    )
    db.add(version)
    db.flush()

    procedure.current_version_id = version.id
    procedure.status = ProcedureStatus.ACTIVE.value

    log_create(db, version)
    db.commit()
    db.refresh(version)

    return json_response(
        {
            "success": True,
            "message": (
                f"Published procedure {procedure.id} as v{next_version} (status -> active)"
            ),
            "version": {
                "id": version.id,
                "procedure_id": version.procedure_id,
                "version_number": version.version_number,
                "step_count": len(steps),
            },
        }
    )


async def _list_versions(db, args: dict) -> list[TextContent]:
    procedure = _load_procedure(db, args["procedure_id"])
    if not procedure:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    versions = (
        db.query(ProcedureVersion)
        .filter(ProcedureVersion.procedure_id == procedure.id)
        .order_by(ProcedureVersion.version_number.desc())
        .all()
    )
    return json_response(
        {
            "procedure_id": procedure.id,
            "current_version_id": procedure.current_version_id,
            "count": len(versions),
            "versions": [
                {
                    "id": v.id,
                    "version_number": v.version_number,
                    "created_at": v.created_at.isoformat(),
                    "created_by_id": v.created_by_id,
                    "is_current": v.id == procedure.current_version_id,
                }
                for v in versions
            ],
        }
    )


async def _clone_procedure(db, args: dict) -> list[TextContent]:
    source = _load_procedure(db, args["procedure_id"])
    if not source:
        return json_response({"error": f"Procedure {args['procedure_id']} not found"})

    clone_name = args.get("new_name") or f"Copy of {source.name}"
    new_procedure = MasterProcedure(
        name=clone_name,
        description=source.description,
        procedure_type=source.procedure_type.value
        if hasattr(source.procedure_type, "value")
        else source.procedure_type,
        status=ProcedureStatus.DRAFT.value,
        current_version_id=None,
    )
    db.add(new_procedure)
    db.flush()

    step_id_map: dict[int, int] = {}
    source_steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == source.id)
        .order_by(ProcedureStep.order)
        .all()
    )

    for s in source_steps:
        new_step = ProcedureStep(
            procedure_id=new_procedure.id,
            order=s.order,
            step_number=s.step_number,
            level=s.level,
            parent_step_id=None,
            title=s.title,
            instructions=s.instructions,
            required_data_schema=s.required_data_schema,
            is_contingency=s.is_contingency,
            requires_signoff=s.requires_signoff,
            estimated_duration_minutes=s.estimated_duration_minutes,
            workcenter_id=s.workcenter_id,
        )
        db.add(new_step)
        db.flush()
        step_id_map[s.id] = new_step.id

    for s in source_steps:
        if s.parent_step_id and s.parent_step_id in step_id_map:
            new_step = db.query(ProcedureStep).filter(ProcedureStep.id == step_id_map[s.id]).first()
            if new_step:
                new_step.parent_step_id = step_id_map[s.parent_step_id]

    copy_kit = bool(args.get("copy_kit", True))
    copy_outputs = bool(args.get("copy_outputs", True))

    if copy_kit:
        for s in source_steps:
            for sk in db.query(StepKit).filter(StepKit.step_id == s.id).all():
                db.add(
                    StepKit(
                        step_id=step_id_map[s.id],
                        part_id=sk.part_id,
                        quantity_required=sk.quantity_required,
                        usage_type=sk.usage_type,
                        notes=sk.notes,
                    )
                )
        for k in db.query(Kit).filter(Kit.procedure_id == source.id).all():
            db.add(
                Kit(
                    procedure_id=new_procedure.id,
                    part_id=k.part_id,
                    quantity_required=k.quantity_required,
                )
            )

    if copy_outputs:
        for o in db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == source.id).all():
            db.add(
                ProcedureOutput(
                    procedure_id=new_procedure.id,
                    part_id=o.part_id,
                    quantity_produced=o.quantity_produced,
                )
            )

    log_create(db, new_procedure)
    db.commit()
    db.refresh(new_procedure)

    return json_response(
        {
            "success": True,
            "message": (f"Cloned procedure {source.id} -> {new_procedure.id} ('{clone_name}')"),
            "procedure": {
                "id": new_procedure.id,
                "name": new_procedure.name,
                "procedure_type": new_procedure.procedure_type.value
                if hasattr(new_procedure.procedure_type, "value")
                else new_procedure.procedure_type,
                "status": "draft",
                "step_count": len(source_steps),
                "copied_kit": copy_kit,
                "copied_outputs": copy_outputs,
            },
        }
    )


# ============ SERVER ENTRY POINT ============


async def run_server():
    """Run the MCP server."""
    logger.info("OPAL MCP Server started")
    logger.info("Database: %s", get_active_settings().database_url)

    project = get_active_project()
    if project:
        logger.info("Project: %s", project.name)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
