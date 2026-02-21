# OPAL User Manual

**Version 0.3.2**

**Operations, Procedures, Assets, Logistics**

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Desktop App](#desktop-app)
4. [Core Concepts](#core-concepts)
5. [Parts & Inventory Management](#parts--inventory-management)
6. [Procedures & Execution](#procedures--execution)
7. [Procurement](#procurement)
8. [Quality Management](#quality-management)
9. [Data Analysis](#data-analysis)
10. [User Interface Guide](#user-interface-guide)
11. [Advanced Features](#advanced-features)
12. [Traceability & Compliance](#traceability--compliance)
13. [Troubleshooting](#troubleshooting)

---

## Introduction

### What is OPAL?

OPAL (Operations, Procedures, Assets, Logistics) is an enterprise resource planning (ERP) system specifically designed for small teams working on hardware projects that require rigorous traceability and quality control. Unlike traditional ERP systems that are complex, cloud-based, and expensive, OPAL is:

- **Local-first**: Runs entirely on a single computer (typically a laptop)
- **Network-accessible**: Other team members can access it on the local network
- **Simple yet rigorous**: Provides aerospace-level traceability without enterprise complexity
- **Hardware-focused**: Optimized for physical parts, assemblies, and manufacturing procedures
- **Audit-ready**: Every action is logged with full traceability

### Who Should Use OPAL?

OPAL is ideal for:

- Small hardware startups (2-20 people)
- Research labs building physical prototypes
- Hardware projects requiring documentation and traceability
- Teams that need to track parts, assemblies, and manufacturing procedures
- Projects with compliance requirements but limited budget
- Makerspaces and educational institutions teaching hardware development

### Key Features at a Glance

| Feature | Description |
|---------|-------------|
| **Parts Database** | Track components with internal and external part numbers |
| **Inventory Tracking** | Unique OPAL numbers for every physical item or batch |
| **Procedure Management** | Version-controlled step-by-step manufacturing procedures |
| **Execution Tracking** | Real-time procedure execution with data capture |
| **Traceability** | Complete genealogy from components to assemblies |
| **Quality Control** | Non-conformances, issues, risks, and testing |
| **Procurement** | Purchase order management with receiving workflow |
| **Audit Trail** | Every change tracked with user, timestamp, and details |

---

## Getting Started

### Installation

There are two ways to install OPAL:

1. **Standalone binary** (recommended for most users) — download a single file and run it
2. **From source** (for development) — clone the repo and install with `uv`

#### Option A: Standalone Binary

Download the binary for your platform from the [GitHub Releases](https://github.com/CST-100/OPAL/releases/latest) page:

| Platform | File |
|----------|------|
| macOS (Apple Silicon) | `opal-macos-arm64` |
| macOS (Intel) | `opal-macos-x86_64` |
| Linux (x86_64) | `opal-linux-x86_64` |
| Windows (x86_64) | `opal-windows-x86_64.exe` |

On macOS/Linux, make it executable and run:

```bash
chmod +x opal-macos-arm64
./opal-macos-arm64
```

On Windows, double-click `opal-windows-x86_64.exe`.

The launcher handles everything: database initialization, migrations, and server management. See [Desktop App](#desktop-app) for full details.

#### Option B: From Source (Development)

##### Prerequisites

- A computer running macOS, Linux, or Windows
- Python 3.11 or higher (installed automatically by uv)
- ~100 MB disk space for software
- Additional space for data and attachments

##### Step 1: Install uv

OPAL uses `uv` for Python dependency management. Install it:

```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

##### Step 2: Download OPAL

```bash
git clone https://github.com/CST-100/OPAL.git
cd OPAL
```

##### Step 3: Install Dependencies

```bash
uv sync
```

This installs all required Python packages.

##### Step 4: Initialize Database

```bash
uv run opal init
```

This creates the SQLite database at `./data/opal.db` and runs all migrations.

##### Step 5: Start the Server

```bash
uv run opal serve
```

By default, OPAL runs on `http://localhost:8080`. The server will print the URL when it starts.

##### Step 6: Access the Web Interface

Open your web browser and navigate to:

```
http://localhost:8080
```

You should see the OPAL dashboard.

### Initial Setup

#### Project Configuration

On first run, OPAL will prompt you to configure your project:

1. **Project Name**: Your organization or project name
2. **Tier Definitions**: Classification system for parts (default: Flight, Ground, Loose)
3. **Location Setup**: Physical storage locations (e.g., "Warehouse", "Lab Bench", "Cabinet A")

This creates a `opal.project.yaml` file with your settings.

#### Create Users

Navigate to **Users** and create user accounts for your team members. While OPAL doesn't have authentication yet, user tracking is essential for:

- Audit logs
- Procedure execution sign-offs
- Responsibility assignment

Create at least one user for yourself.

#### Select Your User

In the upper-right corner of the interface, click the user dropdown (shows "NO USER" initially) and select your username. This selection persists in your browser and is used for all actions.

### Optional: Seed Demo Data

To explore OPAL with sample data:

```bash
uv run opal seed
```

This creates example parts, procedures, and other entities.

---

## Desktop App

The OPAL desktop app is a standalone binary that bundles everything needed to run OPAL — no Python installation, no dependency management, no terminal commands. It provides a TUI (terminal user interface) launcher for managing the OPAL server.

### First Launch

On first launch the desktop app:

1. Creates the platform data directory (see [Data Directory](#data-directory) below)
2. Initializes the SQLite database and runs all migrations
3. Presents the launcher interface

No manual setup is required.

### Launcher Interface

The launcher displays:

- **Server Panel** — current server status (STOPPED / STARTING / RUNNING), port, URL, and data directory path
- **Controls** — Start, Stop, Restart, and Open in Browser buttons
- **Log** — timestamped output from the server process and launcher events
- **Footer** — version number, Check for Updates button, Quit button

### Keyboard Shortcuts

All launcher actions are accessible via keyboard:

| Key | Action |
|-----|--------|
| `s` | Start server |
| `x` | Stop server |
| `r` | Restart server |
| `o` | Open web UI in browser |
| `u` | Check for updates (or install pending update) |
| `q` | Quit (stops server first) |

### Data Directory

The standalone binary stores its database and attachments in a platform-specific data directory:

| Platform | Default Path |
|----------|-------------|
| macOS | `~/Library/Application Support/OPAL/` |
| Linux | `$XDG_DATA_HOME/opal/` (default `~/.local/share/opal/`) |
| Windows | `%LOCALAPPDATA%\OPAL\` |

To override the data directory, set the `OPAL_DATA_DIR` environment variable:

```bash
OPAL_DATA_DIR=/path/to/custom/data ./opal
```

The data directory contains:

- `opal.db` — SQLite database
- `attachments/` — uploaded files

### Updating

The launcher can check for updates from GitHub Releases:

1. Press `u` (or click **Check for Updates**)
2. If an update is available, the log shows the new version and release notes
3. For binary installs, press `u` again to download and install the update
4. Restart the app to apply the update

The updater detects the correct binary for your platform automatically.

### Running Headless (Server-Only)

The desktop app is not required for server operation. For CI, server deployments, or users who prefer the terminal:

```bash
# From source
uv run opal serve

# Or with the binary's Python (development install)
opal-app  # launches the TUI
opal serve  # runs the server directly
```

The web UI is fully functional without the launcher.

---

## Core Concepts

### The OPAL Philosophy

OPAL is built around several key principles:

1. **Unique Identifiers**: Every physical item gets a unique OPAL number that never changes
2. **Version Control**: Procedures are versioned; executions lock to specific versions
3. **Explicit State**: Everything has a clear status visible in the UI
4. **Complete History**: All changes are logged and queryable
5. **Simple but Rigorous**: Easy to use, but maintains compliance-grade traceability

### Key Terminology

| Term | Definition | Example |
|------|------------|---------|
| **Part** | A design-level definition of a component | "Li-Ion Battery 18650" |
| **Inventory Record** | A physical instance or batch of a part | OPAL-00042 (10 units of that battery) |
| **OPAL Number** | Unique identifier for inventory items | OPAL-00001, OPAL-00042 |
| **Internal PN** | OPAL-generated part number | FL/1-001, GR/2-012 |
| **External PN** | Manufacturer or supplier part number | NCR18650B |
| **Master Procedure** | Living template for a manufacturing process | "Battery Module Assembly v3" |
| **Procedure Version** | Immutable snapshot of a procedure | Version 2 (published 2024-01-15) |
| **Procedure Instance** | A single execution of a procedure version | WO-0023 |
| **Work Order (WO)** | Unique identifier for procedure instances | WO-0001, WO-0023 |
| **Step Execution** | Completion of one step in an instance | Step 3.2 in WO-0023 |
| **Kit** | Bill of materials for a procedure | "Requires 12× FL/1-001, 1× FL/1-002" |
| **Non-Conformance (NC)** | Deviation from procedure or specification | "Battery polarity reversed" |
| **Issue Ticket** | Tracked problem or task | IT-0005 |
| **Risk Ticket** | Identified risk requiring mitigation | RISK-0003 |
| **Tier** | Classification level for parts | Flight (1), Ground (2), Loose (3) |
| **Genealogy** | Parent-child relationships in assemblies | "Which batteries are in this module?" |

### Data Hierarchy

Understanding the data structure is key to using OPAL effectively:

```
Project
├── Parts (design-level)
│   ├── Inventory Records (physical items with OPAL numbers)
│   │   ├── Test Results
│   │   ├── Transfers
│   │   └── Consumptions
│   └── BOM (assembly structure)
│
├── Procedures
│   ├── Master Procedures (living documents)
│   │   ├── Steps (hierarchical)
│   │   ├── Kit (procedure-level parts)
│   │   └── Step Kits (step-level parts)
│   └── Versions (immutable snapshots)
│
├── Procedure Instances (executions with WO numbers)
│   ├── Step Executions
│   │   ├── Data Captured
│   │   ├── Attachments
│   │   └── Non-Conformances
│   ├── Consumptions (parts used)
│   └── Productions (assemblies created)
│
├── Purchases
│   ├── Purchase Lines
│   └── Inventory Records (created on receipt)
│
├── Issues (IT numbers)
│   └── References (links to OPAL/WO numbers)
│
└── Risks (RISK numbers)
    └── Linked Issues
```

---

## Parts & Inventory Management

### Parts Database

#### What is a Part?

A **Part** in OPAL represents a design-level component - the abstract definition of something you use in your project. It's **not** a physical item; it's the blueprint or specification.

**Example**:
- Part: "Samsung 18650 Li-Ion Battery, 3400mAh"
- Inventory: OPAL-00042 (10 of those batteries sitting on Shelf A)

#### Creating a Part

1. Navigate to **Inventory → Parts** in the navigation menu dropdown
2. Click **New Part**
3. Fill in the form:

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | Yes | Human-readable name (e.g., "Li-Ion Battery 18650") |
| **Internal PN** | Auto | Auto-generated based on tier (can override) |
| **External PN** | No | Manufacturer part number (e.g., "NCR18650B") |
| **Category** | No | Grouping (e.g., "Batteries", "Fasteners", "PCBs") |
| **Tier** | Yes | Classification level (Flight/Ground/Loose) |
| **Unit of Measure** | Yes | How it's counted (each, kg, m, L, etc.) |
| **Description** | No | Detailed specifications |
| **Parent Part** | No | For assemblies - what this is part of |
| **Tracking Type** | Yes | BULK (counted by quantity) or SERIALIZED (each item tracked) |
| **Metadata** | No | Custom JSON fields for extra data |

4. Click **Create Part**

#### Part Number Schemes

OPAL auto-generates internal part numbers in the format: `TIER_CODE/TIER_NUMBER-SEQUENCE`

**Default Tiers:**
- `FL/1-###`: Flight-critical parts (tier 1)
- `GR/2-###`: Ground support equipment (tier 2)
- `LO/3-###`: Loose parts / commercial off-the-shelf (tier 3)

These can be customized in `opal.project.yaml`.

**Why two part numbers?**
- **Internal PN**: Your numbering system, controlled by you
- **External PN**: Manufacturer's number for ordering and cross-referencing

#### Part Categories

Categories are free-form tags for grouping parts. Common examples:

- Batteries
- Fasteners (Bolts, Nuts, Washers)
- Electronics (ICs, Resistors, Capacitors)
- Mechanical (Brackets, Shafts, Bearings)
- PCBAs (Printed Circuit Board Assemblies)
- Consumables (Solder, Epoxy, Kapton Tape)
- Tools (Torque Wrenches, Calipers)

#### Tracking Types

**BULK**: Used for parts tracked by quantity only
- Example: Fasteners, resistors, consumables
- Inventory shows total count at each location
- Consumed by quantity

**SERIALIZED**: Used for parts where each individual item must be tracked
- Example: Expensive batteries, critical components, assemblies
- Each inventory record is one item with a unique OPAL number
- Consumed one at a time with full traceability

#### Searching and Filtering Parts

The parts list supports:

- **Text search**: Searches name, internal PN, external PN, description
- **Category filter**: Show only parts in specific category
- **Tier filter**: Show only Flight/Ground/Loose parts
- **Parent filter**: Show only top-level parts or sub-assemblies

### Inventory Records

#### What is an Inventory Record?

An **Inventory Record** represents physical items in your possession. Each record has:

- A unique **OPAL number** (never reused)
- A **quantity** (1 for serialized items, any number for bulk)
- A **location** (where it's physically stored)
- A **part reference** (what design it implements)
- A **source** (where it came from)

#### Creating Inventory Records

There are three ways to create inventory:

1. **Manual Entry** (for existing stock or donations)
2. **Purchase Receiving** (when POs arrive)
3. **Production** (when procedures create assemblies)

##### Method 1: Manual Entry

1. Navigate to **Inventory → Stock Levels**
2. Click **New Inventory Record**
3. Fill in:
   - **Part**: Select from dropdown
   - **Quantity**: How many units
   - **Location**: Where it's stored
   - **Lot Number**: Optional batch/lot code
   - **Notes**: Optional context

4. Click **Create**

The system auto-generates an OPAL number (e.g., OPAL-00001).

##### Method 2: Receiving a Purchase Order

(See [Procurement → Receiving](#receiving-purchases) for detailed workflow)

When you receive a PO, OPAL automatically creates inventory records with OPAL numbers linked to the purchase.

##### Method 3: Production

(See [Procedures → Production](#producing-assemblies) for detailed workflow)

When a BUILD procedure completes, it creates inventory records for the assembled products.

#### OPAL Numbers

OPAL numbers are the backbone of traceability:

- Format: `OPAL-#####` (e.g., OPAL-00001, OPAL-00234)
- Sequential, never reused
- Survive transfers, adjustments, and partial consumptions
- Can be printed as labels or barcodes

**Best Practice**: Print OPAL number labels and affix them to bins, bags, or individual items.

#### Locations

Locations are free-form text fields representing physical storage:

- Warehouse Shelf A
- Lab Bench 3
- Cabinet B, Drawer 2
- Cold Storage
- Receiving Area
- Scrap Bin

**Tip**: Use consistent naming and consider a hierarchical scheme:
- `BLDG-A > ROOM-101 > SHELF-3 > BIN-A`

#### Lot Numbers

Lot numbers (also called batch numbers) track groups of parts received together:

- Provided by supplier or manufacturer
- Important for tracking defects or recalls
- Optional but recommended for critical parts

**Example**: You receive 100 batteries from supplier with lot code "LOT-2024-Q1-003". If one fails, you can identify all parts from the same lot.

#### Adjusting Inventory

To change the quantity of an existing inventory record:

1. Go to the inventory record detail page
2. Click **Adjust Quantity**
3. Enter:
   - **New Quantity**: Target amount (not delta)
   - **Reason**: Why (e.g., "Found 2 more in drawer", "Damaged in handling")
4. Click **Adjust**

The system logs the old quantity, new quantity, reason, user, and timestamp.

#### Performing Physical Counts

Physical counts verify actual inventory matches system records:

1. Go to the inventory record detail page
2. Click **Perform Count**
3. Enter:
   - **Counted Quantity**: What you physically counted
   - **Notes**: Optional observations
4. Click **Record Count**

If the counted quantity differs from the system quantity, OPAL:
- Highlights the discrepancy
- Logs the variance
- Prompts you to adjust the quantity

**Best Practice**: Perform regular cycle counts (e.g., weekly) on critical items.

#### Transferring Between Locations

To move inventory:

1. Go to the inventory record detail page
2. Click **Transfer**
3. Enter:
   - **To Location**: Destination
   - **Quantity**: How much to move (or all)
   - **Reason**: Why (e.g., "Moving to workbench for assembly")
4. Click **Transfer**

For partial transfers, OPAL creates a new inventory record at the destination with a new OPAL number, and reduces the source quantity.

#### Viewing Inventory History

Every inventory record has a complete history showing:

- **Created**: When and how (manual/purchase/production)
- **Adjusted**: Quantity changes with reasons
- **Counted**: Physical count results
- **Transferred**: Movements between locations
- **Consumed**: When used in procedures
- **Tested**: Test results (pass/fail)

Access history on the inventory detail page.

### Bill of Materials (BOM)

#### Design-Level BOM

The BOM defines the design-level structure of assemblies:

**Example**:
```
Battery Module (FL/1-005)
├── 12× Li-Ion Cell 18650 (FL/1-001)
├── 1× BMS PCB (FL/1-002)
├── 1× Nickel Strip, 1m (LO/3-045)
└── 4× M3×10 Bolt (LO/3-001)
```

#### Creating a BOM

1. Navigate to the **assembly part** (parent)
2. Go to the **BOM** tab
3. Click **Add Component**
4. Select:
   - **Component Part**: Child part
   - **Quantity**: How many per assembly
   - **Reference Designators**: Optional (e.g., "U1, U2, U3" for ICs)
5. Click **Add**

#### Reference Designators

Reference designators identify specific instances of components in the assembly:

**Example**: A PCB assembly might have:
- Part: "0.1µF Capacitor"
- Quantity: 5
- Designators: "C1, C2, C3, C4, C5"

This is critical for troubleshooting: "Replace C3" is much clearer than "Replace one of the five capacitors."

#### Viewing Where-Used

The **Where-Used** query shows all assemblies that contain a given part:

1. Go to a part detail page
2. Click **Where-Used** tab

**Example**: For "M3×10 Bolt", you might see:
- Battery Module (4 per assembly)
- Avionics Enclosure (16 per assembly)
- Test Fixture (8 per assembly)

This is essential for impact analysis: "If we change this bolt, which assemblies are affected?"

### Inventory Testing

#### Test Templates

Test templates define quality checks that should be performed on inventory items:

**Types of Tests:**

1. **Boolean**: Pass/fail check
   - Example: "Visual inspection - no damage"

2. **Numeric**: Measured value with optional min/max limits
   - Example: "Voltage test: 3.6-3.8V expected"

3. **Text**: Free-form result
   - Example: "Serial number: _______"

#### Creating Test Templates

1. Go to a part detail page
2. Click **Test Templates** tab
3. Click **New Template**
4. Fill in:
   - **Name**: What is being tested
   - **Type**: Boolean / Numeric / Text
   - **Required**: Must this test pass for item to be usable?
   - **Min/Max**: For numeric tests, acceptable range
   - **Instructions**: How to perform the test
5. Click **Create**

#### Performing Tests

1. Go to an inventory record detail page
2. Click **Tests** tab
3. Click **Perform Test**
4. Select the test template
5. Enter the result:
   - Boolean: Pass / Fail
   - Numeric: Measured value (system auto-checks if in range)
   - Text: Free-form entry
6. Add notes if needed
7. Click **Record Test**

#### Viewing Test Status

Each inventory record shows its overall test status:

- **PASS**: All required tests passed
- **FAIL**: One or more required tests failed
- **PENDING**: Required tests not yet performed

Failed items should be quarantined and investigated.

---

## Procedures & Execution

### Master Procedures

#### What is a Master Procedure?

A **Master Procedure** is a living document that defines how to build or test something. It contains:

- Hierarchical steps with instructions
- Data capture requirements
- Part requirements (kit)
- Expected outputs
- Contingency steps

Master procedures are editable and evolve over time. When ready for production use, you **publish** them to create an immutable **version**.

#### Procedure Types

OPAL supports two types:

1. **OP (Operating Procedure)**: General procedures (assembly, testing, calibration)
2. **BUILD**: Procedures that produce trackable assemblies with OPAL numbers

#### Creating a Master Procedure

1. Navigate to **Manufacturing → Procedures**
2. Click **New Procedure**
3. Fill in:
   - **Name**: Clear, descriptive name
   - **Type**: OP or BUILD
   - **Description**: Overview and purpose
   - **Status**: DRAFT (initial), ACTIVE (ready for use), DEPRECATED (obsolete)
4. Click **Create**

You now have an empty procedure. Next, add steps.

#### Adding Steps

Steps can be flat or hierarchical:

**Flat Structure:**
```
1. Prepare workspace
2. Gather materials
3. Assemble parts
4. Perform quality check
5. Package and label
```

**Hierarchical Structure:**
```
1. Prepare workspace
   1.1. Clean bench
   1.2. Gather tools
   1.3. Put on ESD protection
2. Cell preparation
   2.1. Visual inspect cells
   2.2. Test voltage on each cell
   2.3. Mark polarity
3. Assembly
   3.1. Install cells in holder
   3.2. Connect BMS
   3.3. Apply insulation
```

##### Adding a Step

1. On the procedure detail page, click **Add Step**
2. Fill in:
   - **Parent Step**: Leave empty for top-level, or select parent for sub-step
   - **Title**: Short name
   - **Instructions**: Detailed markdown instructions
   - **Is Contingency**: Check if this is a contingency step (only required if an NC occurs)
   - **Required Data Schema**: JSON schema for data capture (see below)
3. Click **Add**

OPAL auto-numbers steps: 1, 2, 3 for top-level; 1.1, 1.2 for sub-steps; C1, C2 for contingencies.

##### Reordering Steps

Use the **Reorder Steps** button to drag-and-drop steps into the correct sequence.

#### Step Instructions (Markdown)

Instructions support **Markdown** formatting:

```markdown
## Cell Voltage Test

1. Use a calibrated multimeter (±0.01V accuracy)
2. Measure voltage across **positive and negative terminals**
3. Record value in data capture field below

**Acceptance Criteria:**
- Voltage must be between 3.6V and 3.8V
- If out of range, log NC and move to contingency step C1

![Measurement diagram](https://example.com/diagram.png)
```

Supported features:
- Headers, lists, bold, italic
- Links and images
- Code blocks
- Tables

#### Data Capture Schemas

Steps can require operators to capture data. Define what's needed using a JSON schema:

**Example: Numeric Measurement**
```json
{
  "type": "object",
  "properties": {
    "voltage": {
      "type": "number",
      "minimum": 3.6,
      "maximum": 3.8,
      "description": "Cell voltage in volts"
    }
  },
  "required": ["voltage"]
}
```

**Example: Multiple Fields**
```json
{
  "type": "object",
  "properties": {
    "visual_inspection": {
      "type": "boolean",
      "description": "No visible damage or defects"
    },
    "serial_number": {
      "type": "string",
      "description": "Cell serial number from label"
    },
    "notes": {
      "type": "string",
      "description": "Additional observations"
    }
  },
  "required": ["visual_inspection", "serial_number"]
}
```

During execution, OPAL auto-generates a form based on this schema.

#### Contingency Steps

Contingency steps handle non-conformances:

**Example**:
```
3. Test voltage
C1. [Contingency] Low voltage cell recovery
   C1.1. Charge cell at 0.1C for 1 hour
   C1.2. Re-test voltage
   C1.3. If still low, quarantine cell and log NC
```

Contingency steps:
- Are numbered C1, C2, C3...
- Only appear during execution if explicitly started
- Are required if started (cannot skip)
- Often created when an NC is logged

#### Procedure Kits

The **Kit** defines which parts are consumed by the procedure:

1. On the procedure detail page, click **Kit** tab
2. Click **Add Kit Item**
3. Select:
   - **Part**: Which part is consumed
   - **Quantity**: How many per execution
   - **Notes**: Optional context
4. Click **Add**

**Example Kit for "Battery Module Assembly":**
- 12× FL/1-001 (Li-Ion Cell 18650)
- 1× FL/1-002 (BMS PCB)
- 1× LO/3-045 (Nickel Strip, 1m)
- 4× LO/3-001 (M3×10 Bolt)

During execution, OPAL checks kit availability before allowing the procedure to proceed.

#### Step-Level Kits

Some parts are only needed at specific steps (e.g., tooling that's returned):

1. On the procedure detail page, expand a step
2. Click **Step Kit**
3. Add parts with quantities
4. Mark as **Tooling** if the part is reusable (not permanently consumed)

**Example**: Step "2.3. Apply epoxy" might require:
- 1× LO/3-067 (Syringe)
- 5× LO/3-068 (Mixing stick)

The syringe is tooling (returned after use), mixing sticks are consumed.

#### Procedure Outputs

For **BUILD** type procedures, define what assemblies are produced:

1. On the procedure detail page, click **Outputs** tab
2. Click **Add Output**
3. Select:
   - **Part**: Which assembly is produced (must be a part in your system)
   - **Quantity Per Execution**: How many are created each time
4. Click **Add**

**Example**: "Battery Module Assembly" produces:
- 1× FL/1-005 (Battery Module, 12S1P)

During execution, completing the procedure creates inventory records for the outputs with new OPAL numbers.

#### Publishing Versions

When a master procedure is ready for production:

1. Click **Publish Version**
2. Add **Release Notes** (what changed)
3. Click **Publish**

This creates an immutable **ProcedureVersion** snapshot containing:
- All step content at this moment
- Kit definitions
- Outputs
- Version number (auto-incremented)
- Publish timestamp and user

**Critical**: Once published, versions never change. If you need to update the procedure:
1. Edit the master procedure
2. Test the changes
3. Publish a new version

Existing procedure instances continue using their locked version.

#### Version History

View all published versions on the **Versions** tab:

| Version | Published | User | Status | Release Notes |
|---------|-----------|------|--------|---------------|
| v1 | 2024-01-15 | Alice | Superseded | Initial release |
| v2 | 2024-02-03 | Bob | Active | Added voltage test step |
| v3 | 2024-03-12 | Alice | Active | Updated epoxy curing time |

Click a version to see its exact content as it was published.

### Procedure Instances (Executions)

#### What is a Procedure Instance?

A **Procedure Instance** is a single execution of a specific procedure version. It has:

- A unique **Work Order (WO) number**
- A locked **version reference** (never changes)
- A **status** (PENDING → IN_PROGRESS → COMPLETED / ABORTED)
- **Step executions** (one for each step in the version)
- **Consumptions** (parts used)
- **Productions** (assemblies created)
- **Participants** (users involved)

#### Creating an Instance

1. Navigate to **Manufacturing → Executions**
2. Click **New Execution**
3. Select:
   - **Procedure**: Which master procedure
   - **Version**: Which published version to execute
   - **Work Order Number**: Auto-generated (WO-0001) or custom
   - **Scheduled Start**: Optional start date/time
   - **Target Completion**: Optional deadline
   - **Priority**: LOW / MEDIUM / HIGH / CRITICAL
4. Click **Create**

The system:
- Creates the instance with status PENDING
- Generates step executions for all steps in the version
- Checks kit availability
- Displays the execution detail page

#### The Execution Dashboard

The execution detail page shows:

**Header:**
- Work Order number
- Procedure name and version
- Status with color coding
- Progress bar (steps completed / total)

**Step List:**
```
☑ 1. Prepare workspace [SIGNED_OFF] - 00:05:23
  ☑ 1.1. Clean bench [COMPLETED] - 00:02:10
  ☑ 1.2. Gather tools [COMPLETED] - 00:03:13
☐ 2. Cell preparation [PENDING]
  ☐ 2.1. Visual inspect cells [PENDING]
  ☐ 2.2. Test voltage [PENDING]
  ☐ 2.3. Mark polarity [PENDING]
```

**Actions:**
- Start Next Step
- Log Non-Conformance
- View Kit Status
- Consume Parts
- Produce Outputs
- View History

#### Executing Steps

##### Basic Flow

1. **Start Step**: Click "Start" on the next pending step
   - Status changes to IN_PROGRESS
   - Timer begins
   - Instructions displayed

2. **Follow Instructions**: Read and perform the step

3. **Capture Data**: Fill in any required fields (measurements, checkboxes, etc.)

4. **Upload Attachments**: Add photos, documents as needed

5. **Complete Step**: Click "Complete"
   - Data is validated against schema
   - Status changes to COMPLETED
   - Timer stops
   - Duration recorded

##### Hierarchical Steps

For **parent OPs** (e.g., step 1 with sub-steps 1.1, 1.2):

1. Start the parent step (step 1)
2. Complete all sub-steps (1.1, 1.2)
3. Parent step status becomes AWAITING_SIGNOFF
4. Click **Sign Off** on the parent step
5. Parent step status becomes SIGNED_OFF

This workflow ensures proper review: the parent OP is checked before moving on.

##### Skipping Steps

Sometimes a step doesn't apply:

1. Click **Skip** on the step
2. Enter a **reason** (required)
3. Click **Confirm Skip**

Skipped steps show as SKIPPED with the reason logged.

**Note**: You cannot skip required steps if they have dependent logic.

#### Data Capture

When a step has a data capture schema, OPAL presents a form:

**Example: Voltage Test**
```
Step 2.2: Test voltage

Instructions:
- Use calibrated multimeter
- Measure voltage across terminals
- Record value below

[Form]
Voltage (V): [____] (must be 3.6-3.8)

[Photo of measurement]: [Upload]

Notes: [_______________]

[Complete Step]
```

Captured data is stored as structured JSON:
```json
{
  "voltage": 3.72,
  "notes": "Cell slightly warm to touch"
}
```

This data is queryable for analysis and reports.

#### Logging Non-Conformances

If something goes wrong:

1. Click **Log Non-Conformance** (available at any step)
2. Fill in:
   - **Step**: Where the NC occurred
   - **Description**: What went wrong
   - **Severity**: MINOR / MAJOR / CRITICAL
3. Click **Log NC**

OPAL automatically:
- Creates an **Issue** ticket (type: NON_CONFORMANCE)
- Links it to the instance and step
- Makes contingency steps available (if defined)

**Example**: "Battery voltage out of spec at step 2.2" creates issue IT-0012 linked to WO-0023, step 2.2.

The NC doesn't stop execution - you can continue or use contingency procedures.

#### Consuming Parts (Kit)

Before or during execution, consume the required parts:

##### Procedure-Level Consumption

1. Click **Consume Parts** (top-level action)
2. The kit list shows required parts with availability
3. For each part, select which inventory record to consume:
   - OPAL number
   - Location
   - Available quantity
4. Click **Consume**

OPAL:
- Reduces inventory quantities (or deletes if fully consumed)
- Records consumption with instance, part, OPAL number, user, timestamp
- Updates kit status

##### Step-Level Consumption

Some parts are consumed at specific steps:

1. Start the step
2. Click **Consume Step Kit**
3. Select inventory records
4. Mark if **Tooling** (reusable)
5. Click **Consume**

Tooling items:
- Are tracked but not permanently consumed
- Can be returned after the step
- Build genealogy (components → assembly) without being used up

**Example**: Using a test fixture:
- Consume: 1× Test Fixture (tooling) at step 3.1
- Complete step 3.1
- Fixture is still available for the next execution

#### Producing Assemblies

For **BUILD** procedures, create the output assemblies:

1. Click **Produce Outputs**
2. The system shows expected outputs from the procedure definition
3. For each output:
   - Confirm quantity
   - Enter location for storage
   - Add serial number or notes
4. Click **Produce**

OPAL:
- Creates new inventory records with new OPAL numbers
- Links to the procedure instance (WO number)
- Records genealogy (which components went into this assembly)
- Sets source as PRODUCTION

**Example**: Completing "Battery Module Assembly" (WO-0023) produces:
- OPAL-00145 (Battery Module, 12S1P) at "Lab Shelf A"

The genealogy links:
- OPAL-00145 (assembly) ← WO-0023 ← consumed parts (OPAL-00031 through OPAL-00042)

#### Viewing Genealogy

On the assembly's inventory detail page, see:

**Forward Genealogy** (what's in this assembly):
```
OPAL-00145 (Battery Module) contains:
- OPAL-00031 (Li-Ion Cell)
- OPAL-00032 (Li-Ion Cell)
- ...
- OPAL-00042 (Li-Ion Cell)
- OPAL-00043 (BMS PCB)
```

**Reverse Genealogy** (where is this component used):
```
OPAL-00031 (Li-Ion Cell) used in:
- OPAL-00145 (Battery Module) via WO-0023
```

This provides complete traceability: if a cell is defective, you know exactly which assemblies contain it.

#### Multi-User Collaboration

Multiple users can work on the same instance:

1. Open the instance detail page
2. Click **Join Execution**
3. Your user is added to participants list
4. Other participants see you as active (real-time via SSE)

**Use cases**:
- Two people working together on assembly
- Supervisor overseeing operator
- Inspector performing sign-offs

When done, click **Leave Execution**.

#### Completing an Instance

An instance is automatically marked COMPLETED when:
- All required steps are completed or signed off
- All contingency steps (if started) are completed
- No steps are IN_PROGRESS

You can also manually abort an instance:
1. Click **Abort Instance**
2. Enter reason
3. Confirm

Aborted instances are preserved for auditing.

---

## Procurement

### Suppliers

#### Creating Suppliers

1. Navigate to **Inventory → Suppliers**
2. Click **New Supplier**
3. Fill in:
   - **Name**: Company name
   - **Code**: Short identifier (e.g., "DIGI" for Digi-Key)
   - **Contact Info**: Phone, email, address
   - **Website**: URL
   - **Active**: Is this supplier currently used?
4. Click **Create**

Keep supplier records updated - you'll reference them when creating purchase orders.

### Purchase Orders

#### Creating a PO

1. Navigate to **Inventory → Purchases**
2. Click **New Purchase**
3. Fill in:
   - **Reference Number**: Auto-generated (PO-0001) or custom
   - **Supplier**: Select from dropdown
   - **Status**: DRAFT (not yet ordered)
   - **Order Date**: When you expect to place the order
   - **Target Delivery**: When you expect it to arrive
   - **Notes**: Any special instructions
4. Click **Create**

You now have an empty PO. Next, add line items.

#### Adding Line Items

1. On the PO detail page, click **Add Line**
2. Fill in:
   - **Part**: Select from parts list (or create new part first)
   - **Quantity Ordered**: How many you're ordering
   - **Unit Cost**: Price per unit
   - **Notes**: Optional (e.g., lead time, packaging)
3. Click **Add**

Repeat for all items in the order.

**Example PO**:
```
PO-0015 to Digi-Key
│
├── 100× FL/1-001 (Li-Ion Cell) @ $4.50 = $450.00
├── 10× FL/1-002 (BMS PCB) @ $12.00 = $120.00
└── 1× LO/3-045 (Nickel Strip, 10m roll) @ $25.00 = $25.00

Total: $595.00
```

#### PO Status Workflow

Purchase orders follow this lifecycle:

1. **DRAFT**: Being prepared, not yet sent to supplier
2. **ORDERED**: Sent to supplier, waiting for delivery
3. **PARTIAL**: Some items received, some still pending
4. **RECEIVED**: All items received and checked in
5. **CANCELLED**: Order cancelled
6. **ON_HOLD**: Temporarily paused

#### Placing an Order

When ready to order:

1. Review the PO and line items
2. Change status to **ORDERED**
3. Record the **Order Date**
4. Send the actual order to the supplier (outside OPAL)

OPAL doesn't send orders automatically - it tracks what you've ordered elsewhere.

### Receiving Purchases

#### Receiving Workflow

When items arrive:

1. Navigate to the PO detail page
2. Click **Receive Items**
3. For each line, enter:
   - **Quantity Received**: How many actually arrived (may differ from ordered)
   - **Location**: Where you're storing them
   - **Lot Number**: Batch code from packaging (if provided)
   - **Notes**: Condition, packaging, etc.
4. Click **Receive**

OPAL automatically:
- Creates inventory records with new OPAL numbers
- Links them to the PO and line item (full traceability)
- Updates quantities received on the line
- Marks lines as fully/partially received
- Updates PO status (PARTIAL or RECEIVED)
- Sets inventory source as PURCHASE

**Example**: Receiving line 1 (100× Li-Ion Cell):
- Creates OPAL-00150 (100 units) at "Receiving Area"
- Links OPAL-00150 → PO-0015, Line 1
- Updates line 1: Ordered 100, Received 100
- PO status: PARTIAL (other lines still pending)

#### Partial Receipts

You can receive multiple shipments for one PO:

**Shipment 1**:
- Receive 50× cells → creates OPAL-00150
- Line 1: Ordered 100, Received 50
- PO status: PARTIAL

**Shipment 2** (a week later):
- Receive 50× cells → creates OPAL-00151
- Line 1: Ordered 100, Received 100
- If all lines complete, PO status: RECEIVED

#### Overdue POs

OPAL flags POs as overdue if:
- Status is ORDERED or PARTIAL
- Target delivery date has passed

Overdue POs show in red on the list view.

---

## Quality Management

### Issues

#### What is an Issue?

An **Issue** represents a problem, task, or improvement to track. Issues have unique **IT numbers** (Issue Ticket).

**Types**:
- **NON_CONFORMANCE**: Deviation from specification (auto-created from NCs during execution)
- **BUG**: Software or hardware defect
- **TASK**: Work item to complete
- **IMPROVEMENT**: Enhancement suggestion

#### Creating an Issue

1. Navigate to **Quality → Issues**
2. Click **New Issue**
3. Fill in:
   - **Title**: Short description
   - **Type**: NON_CONFORMANCE / BUG / TASK / IMPROVEMENT
   - **Status**: OPEN / IN_PROGRESS / RESOLVED / CLOSED
   - **Priority**: LOW / MEDIUM / HIGH / CRITICAL
   - **Description**: Detailed explanation
   - **Assigned To**: User responsible
   - **Due Date**: Optional deadline
   - **Linked Part**: Optional part reference
   - **Linked Procedure**: Optional procedure reference
   - **Linked Instance**: Optional execution reference
   - **Linked Step**: Optional step reference
4. Click **Create**

#### Issue References

Link issues to specific OPAL or WO numbers for traceability:

1. On the issue detail page, click **Add Reference**
2. Select type: OPAL / WORK_ORDER
3. Enter the number (e.g., OPAL-00042 or WO-0023)
4. Add optional notes
5. Click **Add**

**Use case**: Issue IT-0045 "Battery cell out of spec" references OPAL-00042 (the specific cell).

#### Issue Workflow

Typical lifecycle:

1. **OPEN**: Issue reported, needs investigation
2. **IN_PROGRESS**: Someone is working on it
3. **RESOLVED**: Fix implemented, awaiting verification
4. **CLOSED**: Verified complete

Use the **Assigned To** field to track ownership.

### Risks

#### What is a Risk?

A **Risk** is a potential problem that hasn't happened yet. Risks have unique **RISK numbers**.

**Risk Assessment Matrix**:

| Probability | Impact | Severity |
|-------------|--------|----------|
| 1 (Rare) | 1 (Negligible) | LOW |
| 1 (Rare) | 5 (Catastrophic) | MEDIUM |
| 5 (Certain) | 1 (Negligible) | MEDIUM |
| 5 (Certain) | 5 (Catastrophic) | HIGH |

#### Creating a Risk

1. Navigate to **Quality → Risks**
2. Click **New Risk**
3. Fill in:
   - **Title**: What could go wrong
   - **Description**: Detailed scenario
   - **Probability**: 1 (rare) to 5 (certain)
   - **Impact**: 1 (negligible) to 5 (catastrophic)
   - **Mitigation Plan**: How to prevent or handle it
   - **Status**: IDENTIFIED / ANALYZING / MITIGATING / ACCEPTED / RESOLVED
   - **Linked Issue**: Optional issue for mitigation work
4. Click **Create**

OPAL auto-calculates:
- **Score**: probability × impact (1-25)
- **Severity**: LOW (1-4), MEDIUM (5-15), HIGH (16-25)

#### Risk Matrix Visualization

View all risks on a matrix:

1. Navigate to **Quality → Risks**
2. Click **Risk Matrix**

The matrix shows:
```
                    IMPACT →
         1      2      3      4      5
      ┌─────┬─────┬─────┬─────┬─────┐
    1 │     │     │ R3  │     │     │
P     ├─────┼─────┼─────┼─────┼─────┤
R   2 │     │ R1  │     │     │     │
O     ├─────┼─────┼─────┼─────┼─────┤
B   3 │     │     │     │ R2  │     │
A     ├─────┼─────┼─────┼─────┼─────┤
B   4 │     │     │     │     │     │
I     ├─────┼─────┼─────┼─────┼─────┤
L   5 │     │     │     │ R4  │     │
I     └─────┴─────┴─────┴─────┴─────┘
T
Y
```

Click any risk to view details.

#### Linking Risks to Issues

When mitigating a risk requires work:

1. Create an issue (type: TASK)
2. Describe the mitigation action
3. Link the issue to the risk

**Example**:
- **Risk**: RISK-0005 "Battery cell short circuit during assembly"
- **Mitigation**: "Add insulation step between cells"
- **Linked Issue**: IT-0067 "Update battery procedure to include insulation"

---

## Data Analysis

### Datasets

#### What is a Dataset?

A **Dataset** is a collection of structured data points for analysis. Datasets have:

- A **schema** defining the structure (like a database table)
- **Data points** collected over time
- Optional **link to a procedure** (auto-capture data during execution)
- Graphing and export capabilities

#### Creating a Dataset

1. Navigate to **Quality → Datasets**
2. Click **New Dataset**
3. Fill in:
   - **Name**: Descriptive name
   - **Description**: What this dataset tracks
   - **Schema**: JSON schema defining fields
   - **Linked Procedure**: Optional procedure to auto-capture from
4. Click **Create**

**Example Schema** (battery voltage tracking):
```json
{
  "type": "object",
  "properties": {
    "cell_id": {
      "type": "string",
      "description": "Which cell was tested"
    },
    "voltage": {
      "type": "number",
      "description": "Measured voltage in volts"
    },
    "temperature": {
      "type": "number",
      "description": "Ambient temperature in °C"
    },
    "pass": {
      "type": "boolean",
      "description": "Within specification?"
    }
  },
  "required": ["cell_id", "voltage", "pass"]
}
```

#### Adding Data Points

##### Manual Entry

1. On the dataset detail page, click **Add Data Point**
2. Fill in the form (auto-generated from schema)
3. Click **Add**

##### CSV Import

For bulk data:

1. Click **Import CSV**
2. Upload a CSV file matching the schema
3. Map columns to schema fields
4. Click **Import**

##### Auto-Capture from Procedures

If a dataset is linked to a procedure, data points are automatically created when steps are completed:

**Setup**:
1. Create dataset with schema matching step data capture
2. Link dataset to procedure
3. Ensure step data schemas match dataset schema

**During execution**:
1. Operator completes step with data capture
2. OPAL automatically creates a data point in the linked dataset
3. Links the data point to the step execution

This creates a queryable database of all measurements from all executions.

#### Graphing Data

OPAL supports basic visualization:

1. On the dataset detail page, click **Graph**
2. Select graph type:
   - **Time Series**: Plot a field over time
   - **Scatter**: Plot two fields against each other
   - **Histogram**: Distribution of a field
3. Configure:
   - **X-axis**: Time or field name
   - **Y-axis**: Field name
   - **Filters**: Date range, value range
4. Click **Generate Graph**

**Example**: Plot battery voltage over time to identify trends.

#### Exporting Data

Export to CSV for analysis in other tools:

1. Click **Export CSV**
2. Select fields to include
3. Set filters (date range, etc.)
4. Click **Export**

Open in Excel, Python pandas, R, etc. for advanced analysis.

---

## User Interface Guide

### Navigation

#### Header

The header contains:

**Left Side:**
- **OPAL**: Logo, click to return to dashboard
- **Version**: Current version number

**Center:**
- **INVENTORY** dropdown: Parts, Stock Levels, Purchases, Suppliers
- **MANUFACTURING** dropdown: Procedures, Executions, Workcenters
- **QUALITY** dropdown: Issues, Risks, Datasets
- **Command Palette** button (⌘K): Quick search and navigation

**Right Side:**
- **User Dropdown**: Select current user (hover to see menu with user list)

#### Using the Dropdown Menus

The navigation uses dropdown menus for organized access:

1. **Hover** over INVENTORY, MANUFACTURING, or QUALITY
2. A dropdown menu appears with related pages
3. Click any item to navigate
4. The active section and page are highlighted in blue

**INVENTORY Dropdown:**
- Parts
- Stock Levels
- Purchases
- Suppliers

**MANUFACTURING Dropdown:**
- Procedures
- Executions
- Workcenters

**QUALITY Dropdown:**
- Issues
- Risks
- Datasets

#### User Dropdown

In the upper-right corner:

1. **Hover** over the user button (shows current user or "NO USER")
2. Dropdown shows:
   - List of all users
   - "Clear Selection" option
3. Click a user to set as active
4. Your selection persists across sessions

#### Breadcrumbs

Below the header, breadcrumbs show your location:

```
HOME > INVENTORY > PARTS > FL/1-001 > EDIT
```

Click any breadcrumb to navigate back.

#### Keyboard Shortcuts

OPAL supports keyboard-driven navigation:

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` / `⌘K` | Open command palette |
| `Alt+H` | Go to home |
| `Alt+P` | Go to parts |
| `Alt+R` | Go to procedures |
| `Alt+E` | Go to executions |
| `Alt+I` | Go to issues |
| `Alt+K` | Go to risks |
| `Alt+D` | Go to datasets |
| `Alt+N` | Go to inventory |
| `Alt+U` | Go to purchases |
| `Alt+S` | Go to suppliers |
| `Alt+W` | Go to workcenters |
| `Esc` | Close modals/dialogs |

### Command Palette

The command palette provides quick access to any page or action:

1. Press `Ctrl+K` (or `⌘K` on Mac)
2. Type to search:
   - Page names: "parts", "procedures", "executions"
   - Actions: "new part", "new procedure", "new purchase"
3. Use arrow keys to navigate results
4. Press `Enter` to select

**Examples**:
- Type "parts" → "Go to Parts"
- Type "new po" → "New Purchase Order"
- Type "exec" → "Go to Executions"

### Dashboard

The dashboard shows:

**Stats Panel:**
- Total parts
- Active procedures
- Open issues
- Critical risks

**Recent Activity:**
- Latest executions
- Recent issues
- Recent purchases

**Quick Links:**
- New Part
- New Procedure
- New Execution
- New Issue

### Data Tables

OPAL uses dense data tables (not cards) for all list views:

**Features:**
- **Sortable columns**: Click headers to sort
- **Filters**: Dropdowns and search boxes above table
- **Pagination**: Footer shows page controls
- **Row actions**: Click rows to view details

**Example Parts Table:**

| ID | Internal PN | Name | Category | Tier | Stock | Actions |
|----|-------------|------|----------|------|-------|---------|
| 1 | FL/1-001 | Li-Ion Cell 18650 | Batteries | Flight | 245 | View |
| 2 | FL/1-002 | BMS PCB | Electronics | Flight | 12 | View |
| 3 | GR/2-005 | Test Fixture | Tooling | Ground | 3 | View |

### Forms

Forms follow consistent patterns:

**Field Types:**
- **Text input**: Single-line text
- **Text area**: Multi-line text (with Markdown preview for instructions)
- **Select dropdown**: Choose from predefined options
- **Number input**: Numeric values
- **Date/time picker**: Timestamps
- **Checkbox**: Boolean flags
- **File upload**: Attachments

**Required fields** are marked with an asterisk (*).

**Validation** happens on submit:
- Missing required fields highlighted in red
- Invalid formats shown with error messages
- Submission blocked until fixed

### Status Indicators

Status is always visible with color coding:

**Colors:**
- **Green**: OK, completed, active, pass
- **Blue**: In progress, pending
- **Yellow**: Warning, draft, awaiting
- **Red**: Error, critical, fail, aborted

**Status Badges:**
```
[COMPLETED]  [IN_PROGRESS]  [PENDING]  [FAILED]
```

These appear throughout the UI on tables, detail pages, and breadcrumbs.

### Timestamps

All timestamps are **ISO 8601** format:

```
2024-01-15T14:30:00Z
```

Never relative (no "2 hours ago"). This ensures clarity and reproducibility.

### Loading States

When data is loading:

```
[LOADING]
```

Appears inline. No spinners that hide content.

---

## Advanced Features

### Workcenters

#### What is a Workcenter?

A **Workcenter** represents a physical work location where procedures are executed:

- Assembly Bench 1
- Test Station A
- Clean Room 3
- Calibration Lab

#### Creating Workcenters

1. Navigate to **Manufacturing → Workcenters**
2. Click **New Workcenter**
3. Fill in:
   - **Name**: Full name
   - **Code**: Short identifier (e.g., "AB1", "TEST-A")
   - **Description**: What happens here
   - **Active**: Is this workcenter in use?
4. Click **Create**

#### Linking to Procedures

You can set default workcenters for:
- Entire procedures
- Specific steps

This helps with:
- Scheduling (knowing where work happens)
- Capacity planning (how many jobs can run in parallel)
- Equipment tracking (tools available at each location)

### Part Requirements

Link parts to project requirements for verification:

1. Go to a part detail page
2. Click **Requirements** tab
3. Click **Link Requirement**
4. Enter:
   - **Requirement ID**: External reference (e.g., "REQ-SYS-042")
   - **Description**: What requirement this satisfies
   - **Status**: PROPOSED / VERIFIED / NOT_MET
5. Click **Link**

**Use case**: Aerospace projects must verify each part meets specific requirements. Track verification status here.

### Project Configuration

Edit `opal.project.yaml` to customize:

**Tier Definitions:**
```yaml
tiers:
  - number: 1
    code: "FL"
    name: "Flight"
    description: "Flight-critical hardware"
  - number: 2
    code: "GR"
    name: "Ground"
    description: "Ground support equipment"
  - number: 3
    code: "LO"
    name: "Loose"
    description: "COTS / non-critical parts"
```

**Part Number Format:**
```yaml
part_number_format: "{tier_code}/{tier_number}-{sequence:03d}"
# Produces: FL/1-001, GR/2-023, etc.
```

**Work Order Format:**
```yaml
work_order_format: "WO-{sequence:04d}"
# Produces: WO-0001, WO-0023, etc.
```

### Cloning Procedures

To create a variant of an existing procedure:

1. Go to the procedure detail page
2. Click **Clone Procedure**
3. Enter:
   - **New Name**: Name for the clone
   - **Include Steps**: Copy steps? (usually yes)
   - **Include Kit**: Copy kit? (usually yes)
4. Click **Clone**

OPAL creates a complete copy as a new DRAFT procedure. Edit as needed, then publish.

**Use case**: You have "Battery Module 1S" and need "Battery Module 2S" - clone and modify.

### Audit Logs

Every create/update/delete is logged:

1. Navigate to **System → Audit Logs** (admin only, future feature)
2. Filter by:
   - **Entity Type**: Part / Procedure / Issue / etc.
   - **Entity ID**: Specific item
   - **User**: Who made changes
   - **Date Range**: When
3. View logs:

```
[2024-01-15T14:30:00Z] User: Alice
Action: UPDATE
Entity: Part #42 (FL/1-005)
Old: {"name": "Battery Module", "tier": 1}
New: {"name": "Battery Module 12S1P", "tier": 1}
```

Complete change history for compliance and troubleshooting.

---

## Traceability & Compliance

### Why Traceability Matters

For hardware projects, especially in aerospace, medical, or safety-critical domains, you must answer:

1. **What went into this assembly?** (Forward traceability)
2. **Where did this component end up?** (Reverse traceability)
3. **Who built it, when, and how?** (Process traceability)
4. **What tests were performed?** (Quality traceability)
5. **What problems occurred?** (Non-conformance traceability)

OPAL provides complete traceability through:
- OPAL numbers (unique IDs)
- Work Order numbers (execution tracking)
- Genealogy (component → assembly relationships)
- Audit logs (complete change history)

### Forward Traceability Example

**Question**: "What components are in Battery Module OPAL-00145?"

**Answer**:
```
OPAL-00145 (Battery Module 12S1P)
├── Built via: WO-0023 (Battery Module Assembly v2)
├── Built by: Alice on 2024-01-15T14:30:00Z
├── Contains components:
│   ├── OPAL-00031 (Li-Ion Cell) from PO-0012
│   ├── OPAL-00032 (Li-Ion Cell) from PO-0012
│   ├── ... (10 more cells)
│   ├── OPAL-00043 (BMS PCB) from PO-0015
│   └── OPAL-00044 (Nickel Strip) from stock
└── Tests performed:
    ├── Voltage Test: 12.6V [PASS]
    └── Short Circuit Test: No continuity [PASS]
```

### Reverse Traceability Example

**Question**: "Battery cell OPAL-00031 is defective. Which assemblies contain it?"

**Answer**:
```
OPAL-00031 (Li-Ion Cell)
├── Purchased via: PO-0012 from Supplier ABC
├── Lot Number: LOT-2024-Q1-003
└── Used in assemblies:
    └── OPAL-00145 (Battery Module 12S1P)
        ├── Built via: WO-0023
        ├── Currently located: Lab Shelf A
        └── Action: Quarantine and disassemble
```

### Process Traceability Example

**Question**: "How was Battery Module OPAL-00145 built?"

**Answer**:
```
OPAL-00145 (Battery Module 12S1P)
Built via: WO-0023 (Battery Module Assembly v2)

Procedure Steps Executed:
├── Step 1: Prepare workspace [COMPLETED]
│   └── Signed off by: Alice at 2024-01-15T13:05:00Z
├── Step 2: Cell preparation [COMPLETED]
│   ├── 2.1: Visual inspect [COMPLETED]
│   ├── 2.2: Test voltage [COMPLETED]
│   │   └── Data: {"voltage": 3.72, "pass": true}
│   └── 2.3: Mark polarity [COMPLETED]
├── Step 3: Assembly [COMPLETED]
│   ├── 3.1: Install cells [COMPLETED]
│   ├── 3.2: Connect BMS [COMPLETED]
│   │   └── Attachment: photo_bms_connections.jpg
│   └── 3.3: Apply insulation [COMPLETED]
└── Step 4: Final test [COMPLETED]
    └── Data: {"voltage": 12.6, "pass": true}

Total Duration: 01:23:45
No non-conformances logged
```

### Quality Traceability Example

**Question**: "What testing has been performed on OPAL-00145?"

**Answer**:
```
OPAL-00145 (Battery Module 12S1P)

Factory Tests (during WO-0023):
├── Voltage Test: 12.6V [PASS] - Step 4 at 2024-01-15T14:30:00Z
└── Visual Inspection: No defects [PASS] - Step 2.1

Post-Production Tests:
├── [2024-01-16] Capacity Test: 3350mAh [PASS]
├── [2024-01-17] Temperature Cycle: -20°C to +60°C [PASS]
└── [2024-01-18] Vibration Test: 5-2000Hz, 20G [PASS]

Overall Status: [PASS] - Cleared for flight
```

### Non-Conformance Traceability Example

**Question**: "What problems have occurred with Battery Modules?"

**Answer**:
```
Non-Conformances for Part: FL/1-005 (Battery Module 12S1P)

IT-0012: Battery voltage out of spec
├── Instance: WO-0023
├── Step: 2.2 (Test voltage)
├── Severity: MAJOR
├── Description: Cell voltage measured 3.45V (spec: 3.6-3.8V)
├── Resolution: Replaced cell (OPAL-00032 → OPAL-00055)
└── Status: CLOSED

IT-0034: BMS connection loose
├── Instance: WO-0067
├── Step: 3.2 (Connect BMS)
├── Severity: MINOR
├── Description: Wire came loose during insulation step
├── Resolution: Re-soldered connection, added strain relief
└── Status: CLOSED

Pattern Analysis:
- 2 NCs in 45 executions (4.4% NC rate)
- Most common issue: Component installation (50%)
- Recommended: Add connection verification step
```

### Compliance Reporting

For audits or certifications, OPAL can generate reports showing:

1. **Part Traceability Matrix**: Every part with sources and uses
2. **Procedure Compliance**: All executions with sign-offs
3. **Test Results Summary**: Pass/fail rates by part or procedure
4. **Change History**: Complete audit log for any date range
5. **Non-Conformance Log**: All issues with resolutions

**Export formats**:
- CSV for data analysis
- PDF for documentation packages (future)
- JSON for integration with other systems

### Best Practices for Traceability

1. **Always assign OPAL numbers**: Never use parts without inventory records
2. **Capture data at every step**: More data = better traceability
3. **Log all NCs immediately**: Don't wait until end of day
4. **Use lot numbers**: Especially for critical components
5. **Sign off parent OPs**: Ensures review happened
6. **Regular audits**: Spot-check traceability chains monthly
7. **Backup database**: OPAL is your compliance record - back up `data/opal.db` daily

---

## Troubleshooting

### Common Issues

#### Issue: "Kit not available" when starting execution

**Cause**: Required parts aren't in stock.

**Solution**:
1. Check kit requirements on procedure detail page
2. View current stock levels for each part
3. If stock exists but at wrong location, transfer it
4. If out of stock, create a purchase order
5. Alternatively, consume from other OPAL numbers if acceptable

#### Issue: Cannot complete step - "Data validation failed"

**Cause**: Captured data doesn't match the required schema.

**Solution**:
1. Check the step's required data schema
2. Ensure all required fields are filled
3. Ensure numeric values are within min/max ranges
4. Ensure correct data types (number vs text)
5. If schema is wrong, update the master procedure and publish a new version (future executions will use the fix)

#### Issue: OPAL number not found

**Cause**: Typo or the inventory record was deleted.

**Solution**:
1. Check the exact OPAL number format (OPAL-00001, not OPAL-1)
2. Search inventory by part instead
3. Check audit logs to see if it was deleted or consumed
4. If consumed, view consumption record to see which execution used it

#### Issue: Version content doesn't match master procedure

**Cause**: Editing the master doesn't affect published versions.

**Solution**:
This is intentional! Published versions are immutable. To update:
1. Edit the master procedure
2. Publish a new version
3. New executions will use the new version
4. Old executions continue using their locked version (preserving traceability)

#### Issue: Server won't start - "Database locked"

**Cause**: Another OPAL process is running, or a previous process didn't shut down cleanly.

**Solution**:
1. Check for other `opal serve` processes: `ps aux | grep opal`
2. Kill any hung processes: `kill <PID>`
3. If persists, check file permissions on `data/opal.db`
4. Worst case: restart your computer

#### Issue: Changes not showing up in UI

**Cause**: Browser cache or HTMX not refreshing.

**Solution**:
1. Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
2. Clear browser cache
3. Check browser console for errors (F12 → Console tab)

#### Issue: Dropdown menus not working

**Cause**: CSS not loaded or JavaScript disabled.

**Solution**:
1. Hard refresh the page
2. Check that `/static/css/main.css` is loading (Network tab in browser dev tools)
3. Ensure browser has CSS hover support
4. Try a different browser

### Getting Help

#### Documentation

- **This manual**: Comprehensive user guide
- **CLAUDE.md**: Technical architecture and development guide
- **README.md**: Quick start and installation
- **In-app help**: (future) Context-sensitive help buttons

#### Bug Reports

File issues on GitHub: https://github.com/CST-100/OPAL/issues

Include:
- OPAL version (`v0.3.2` shown in header)
- Operating system
- Steps to reproduce
- Screenshots if applicable
- Any error messages

#### Feature Requests

Also on GitHub issues, tagged as "enhancement".

Describe:
- Use case (what are you trying to accomplish)
- Current workaround (if any)
- Expected behavior
- Why this matters for your project

---

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| **Assembly** | A part composed of other parts, tracked via genealogy |
| **Audit Log** | Automatic record of all system changes |
| **BOM (Bill of Materials)** | List of components required for an assembly |
| **BUILD Procedure** | Procedure that produces trackable assemblies |
| **Bulk Tracking** | Inventory tracked by quantity only |
| **Contingency Step** | Optional step performed only if NC occurs |
| **Data Capture** | Structured data collected during step execution |
| **External PN** | Manufacturer or supplier part number |
| **Forward Traceability** | Following components into assemblies |
| **Genealogy** | Parent-child relationships in assemblies |
| **Instance** | Single execution of a procedure version |
| **Internal PN** | OPAL-generated part number |
| **Issue Ticket (IT)** | Tracked problem or task |
| **Kit** | Bill of materials for a procedure |
| **Lot Number** | Batch identifier from supplier |
| **Master Procedure** | Living template for a process |
| **NC (Non-Conformance)** | Deviation from specification |
| **OP (Operating Procedure)** | General procedure type |
| **OPAL Number** | Unique inventory identifier |
| **Part** | Design-level component definition |
| **Procedure Version** | Immutable snapshot of a master procedure |
| **Production** | Creating assemblies via BUILD procedures |
| **Reference Designator** | Specific instance identifier (e.g., "R1", "U3") |
| **Reverse Traceability** | Finding which assemblies contain a component |
| **Risk Ticket (RISK)** | Potential problem requiring mitigation |
| **Serialized Tracking** | Inventory tracked individually by OPAL number |
| **Sign-off** | Formal approval of completed parent OP |
| **Step Execution** | Completion of one step in an instance |
| **Supplier** | Vendor providing parts |
| **Test Template** | Definition of a quality test |
| **Tier** | Classification level for parts |
| **Tooling** | Reusable equipment used but not consumed |
| **Work Order (WO)** | Unique identifier for procedure instance |
| **Workcenter** | Physical location where work is performed |

### Database Schema Reference

For developers or advanced users, the complete schema is defined in:

- `/src/opal/db/models/*.py` - SQLAlchemy model definitions
- `/migrations/*.py` - Alembic migration history

Key tables:
- `parts`, `inventory_records`, `bom_lines`
- `master_procedures`, `procedure_steps`, `procedure_versions`
- `procedure_instances`, `step_executions`
- `purchases`, `purchase_lines`, `suppliers`
- `issues`, `risks`, `datasets`, `data_points`
- `users`, `workcenters`, `audit_logs`

### API Reference

OPAL exposes a REST API (future: full API docs):

Base URL: `http://localhost:8080/api`

All endpoints accept optional `X-User-Id` header for user tracking.

**Common Patterns:**
- `GET /api/{resource}` - List resources
- `POST /api/{resource}` - Create resource
- `GET /api/{resource}/{id}` - Get specific resource
- `PATCH /api/{resource}/{id}` - Update resource
- `DELETE /api/{resource}/{id}` - Delete resource

See `/src/opal/api/*.py` for full endpoint documentation.

### File Locations

**Configuration:**
- `opal.project.yaml` - Project settings (created by `opal init`)

**Data:**
- `data/opal.db` - SQLite database (all structured data)
- `data/attachments/` - Uploaded files (photos, documents)

**Logs:**
- `data/opal.log` - Application log (future)

**Backups:**
- Backup `data/` directory daily for safety
- SQLite supports online backups: `.backup data/opal_backup.db`

### Version History

- **v0.1.0** (2024-01-01): Initial release - Parts, Inventory, basic Procedures
- **v0.2.0** (2024-02-01): Added Execution tracking, Issues, Genealogy
- **v0.3.0** (2024-03-01): Added Risks, Datasets, improved UI
- **v0.3.2** (2024-03-15): Added dropdown navigation, user dropdown

### License

OPAL is open-source software. See LICENSE file for details.

---

**End of Manual**

For the latest version of this manual and OPAL updates, visit:
https://github.com/CST-100/OPAL
