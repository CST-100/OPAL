"""Seed data for Project Kestrel — LOX/ethanol pressure-fed sounding rocket."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from opal.core.designators import (
    generate_issue_number,
    generate_opal_number,
    generate_risk_number,
    generate_work_order_number,
)
from opal.db.models import (
    BOMLine,
    Issue,
    IssueComment,
    Kit,
    MasterProcedure,
    Part,
    PartRequirement,
    ProcedureInstance,
    ProcedureOutput,
    ProcedureStep,
    ProcedureVersion,
    Purchase,
    PurchaseLine,
    Risk,
    StepExecution,
    Supplier,
    TestTemplate,
    User,
    Workcenter,
)
from opal.db.models.execution import InstanceStatus, StepStatus
from opal.db.models.inventory import InventoryRecord, SourceType
from opal.db.models.issue import IssuePriority, IssueStatus, IssueType
from opal.db.models.procedure import ProcedureStatus, ProcedureType
from opal.db.models.purchase import PurchaseStatus
from opal.db.models.risk import RiskStatus


def seed_database(db: Session) -> None:
    """Populate database with Project Kestrel seed data."""
    _write_project_yaml()
    _seed_users(db)
    workcenters = _seed_workcenters(db)
    suppliers = _seed_suppliers(db)
    parts = _seed_parts(db)
    _seed_bom(db, parts)
    _seed_part_requirements(db, parts)
    _seed_inventory(db, parts)
    procedures = _seed_procedures(db, parts, workcenters)
    _seed_versions_and_executions(db, procedures)
    _seed_purchases(db, parts, suppliers)
    _seed_issues(db, parts, procedures)
    _seed_risks(db)
    _seed_test_templates(db, parts)
    db.commit()

    print(f"  {db.query(Workcenter).count()} workcenters")
    print(f"  {db.query(Supplier).count()} suppliers")
    print(f"  {db.query(Part).count()} parts")
    print(f"  {db.query(BOMLine).count()} BOM lines")
    print(f"  {db.query(PartRequirement).count()} part requirements")
    print(f"  {db.query(InventoryRecord).count()} inventory records")
    print(f"  {db.query(MasterProcedure).count()} procedures")
    print(f"  {db.query(ProcedureStep).count()} procedure steps")
    print(f"  {db.query(ProcedureVersion).count()} published versions")
    print(f"  {db.query(ProcedureInstance).count()} executions")
    print(f"  {db.query(Purchase).count()} purchase orders")
    print(f"  {db.query(PurchaseLine).count()} PO line items")
    print(f"  {db.query(Issue).count()} issues")
    print(f"  {db.query(IssueComment).count()} issue comments")
    print(f"  {db.query(Risk).count()} risks")
    print(f"  {db.query(TestTemplate).count()} test templates")


# ---------------------------------------------------------------------------
# Project YAML
# ---------------------------------------------------------------------------

_PROJECT_YAML = """\
name: Project Kestrel
description: LOX/ethanol pressure-fed sounding rocket — target altitude 10 km
tiers:
- level: 1
  name: FLIGHT
  code: F
  description: Flight-critical hardware — full traceability required
- level: 2
  name: GROUND
  code: G
  description: Ground support equipment — test stands, fill systems, launch rail
- level: 3
  name: DEV
  code: D
  description: Development hardware, prototypes, consumables
part_numbering:
  prefix: KST
  separator: '-'
  sequence_digits: 4
  format: '{prefix}{sep}{tier_code}{sep}{sequence}'
categories:
- Propulsion
- Structures
- Avionics
- Recovery
- Plumbing
- Fasteners
- GSE
- Raw Material
- Consumables
requirements:
- id: REQ-001
  title: Structural Loads
  description: All flight structures shall withstand 10g axial and 3g lateral load simultaneously with positive margin of safety.
- id: REQ-002
  title: Pressure Containment
  description: All pressure vessels and pressurized lines shall be proof tested to 1.5x MEOP before flight use.
- id: REQ-003
  title: LOX Compatibility
  description: All materials in contact with liquid oxygen shall be LOX-compatible per NASA MSFC-SPEC-106B.
- id: REQ-004
  title: Dual-Event Recovery
  description: Recovery system shall use dual-event deployment (drogue at apogee, main at low altitude) with redundant altimeters.
- id: REQ-005
  title: Flight Data Logging
  description: Flight computer shall log all sensor data (acceleration, rotation, pressure, GPS) at 50 Hz minimum.
- id: REQ-006
  title: Telemetry Link
  description: Telemetry downlink shall maintain 6 dB link margin to 10 km slant range.
- id: REQ-007
  title: Pyro Electrical Isolation
  description: Pyrotechnic firing circuits shall be electrically isolated from avionics power bus with independent arming switch.
- id: REQ-008
  title: Flight Hardware Traceability
  description: All flight components shall be traceable to lot number or serial number via OPAL inventory system.
cad_directories: []
"""


def _seed_users(db: Session) -> None:
    db.add(User(name="Build Lead", email="build@kestrel.local", is_admin=True))
    db.add(User(name="Test Engineer", email="test@kestrel.local", is_admin=False))
    db.add(User(name="QA Inspector", email="qa@kestrel.local", is_admin=False))
    db.flush()


def _write_project_yaml() -> None:
    """Write the Project Kestrel opal.project.yaml next to the running project."""
    from opal.project import find_project_config

    config_path = find_project_config()
    if config_path is None:
        config_path = Path.cwd() / "opal.project.yaml"

    config_path.write_text(_PROJECT_YAML)
    print(f"  Wrote {config_path}")


# ---------------------------------------------------------------------------
# Workcenters
# ---------------------------------------------------------------------------


def _seed_workcenters(db: Session) -> dict[str, Workcenter]:
    items = [
        Workcenter(
            code="SHOP", name="Machine Shop", description="Mill, lathe, welding, fabrication"
        ),
        Workcenter(code="CLEAN", name="Clean Room", description="Assembly bench, LOX-clean work"),
        Workcenter(code="PAD", name="Test Pad", description="Static fire stand and launch rail"),
        Workcenter(
            code="LAB",
            name="Electronics Lab",
            description="Soldering, programming, avionics assembly",
        ),
        Workcenter(code="STORE", name="Stockroom", description="Parts receiving and storage"),
    ]
    db.add_all(items)
    db.flush()
    return {w.code: w for w in items}


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


def _seed_suppliers(db: Session) -> dict[str, Supplier]:
    items = [
        Supplier(
            name="McMaster-Carr",
            email="",
            website="https://www.mcmaster.com",
            notes="Fasteners, plumbing, seals, raw stock. Next-day shipping.",
        ),
        Supplier(
            name="Swagelok",
            email="",
            website="https://www.swagelok.com",
            notes="High-pressure fittings, valves, regulators.",
        ),
        Supplier(
            name="Digi-Key",
            email="",
            website="https://www.digikey.com",
            notes="Electronics components, dev boards, connectors.",
        ),
        Supplier(
            name="Metal Supermarkets",
            email="",
            website="https://www.metalsupermarkets.com",
            notes="Cut-to-size aluminum, steel, stainless stock.",
        ),
        Supplier(
            name="Apogee Components",
            email="",
            website="https://www.apogeerockets.com",
            notes="Recovery hardware, parachutes, e-matches.",
        ),
        Supplier(
            name="Airgas",
            email="",
            website="https://www.airgas.com",
            notes="Industrial gases — LOX, nitrogen, helium.",
        ),
    ]
    db.add_all(items)
    db.flush()
    return {s.name: s for s in items}


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------


def _seed_parts(db: Session) -> dict[str, Part]:
    """Create ~50 parts. Returns dict keyed by short name for cross-referencing."""
    p: dict[str, Part] = {}

    def _add(
        key: str,
        ipn: str,
        name: str,
        *,
        category: str,
        tier: int = 1,
        tracking: str = "serialized",
        epn: str | None = None,
        desc: str | None = None,
        uom: str = "ea",
        parent_key: str | None = None,
        reorder: float | None = None,
        is_tooling: bool = False,
        cal_days: int | None = None,
    ) -> None:
        part = Part(
            internal_pn=ipn,
            external_pn=epn,
            name=name,
            description=desc,
            category=category,
            tier=tier,
            tracking_type=tracking,
            unit_of_measure=uom,
            parent_id=p[parent_key].id if parent_key else None,
            reorder_point=Decimal(str(reorder)) if reorder is not None else None,
            is_tooling=is_tooling,
            calibration_interval_days=cal_days,
        )
        db.add(part)
        db.flush()
        p[key] = part

    # ── Propulsion ──────────────────────────────────────────────
    _add(
        "engine_assy",
        "KST-F-0001",
        "Engine Assembly",
        category="Propulsion",
        desc="Complete engine: chamber, injector, nozzle, igniter",
    )
    _add(
        "chamber",
        "KST-F-0002",
        "Combustion Chamber",
        category="Propulsion",
        desc="6061-T6 aluminum chamber, 450 PSI MEOP",
        parent_key="engine_assy",
    )
    _add(
        "injector",
        "KST-F-0003",
        "Injector Plate",
        category="Propulsion",
        desc="304 SS, 32-element showerhead pattern",
        parent_key="engine_assy",
    )
    _add(
        "nozzle",
        "KST-F-0004",
        "Nozzle",
        category="Propulsion",
        desc="Copper-lined graphite, 4:1 expansion ratio",
        parent_key="engine_assy",
    )
    _add(
        "igniter",
        "KST-F-0005",
        "Igniter Assembly",
        category="Propulsion",
        desc="Pyrotechnic torch igniter with e-match",
        parent_key="engine_assy",
    )
    _add(
        "lox_tank",
        "KST-F-0006",
        "LOX Tank",
        category="Propulsion",
        desc="6061-T6 welded tank, 500 PSI MEOP, 2.5 gal capacity",
    )
    _add(
        "fuel_tank",
        "KST-F-0007",
        "Fuel Tank",
        category="Propulsion",
        desc="6061-T6 welded tank, 500 PSI MEOP, 3.0 gal capacity",
    )
    _add(
        "press_tank",
        "KST-F-0008",
        "Pressurant Tank (N2)",
        category="Propulsion",
        desc="COTS nitrogen bottle, 3000 PSI rated",
    )

    # ── Plumbing ────────────────────────────────────────────────
    _add(
        "lox_valve",
        "KST-F-0009",
        "Main LOX Valve",
        category="Plumbing",
        desc='Swagelok SS-63TS8 ball valve, 1/2" tube',
        epn="SS-63TS8",
    )
    _add(
        "fuel_valve",
        "KST-F-0010",
        "Main Fuel Valve",
        category="Plumbing",
        desc='Swagelok SS-63TS8 ball valve, 1/2" tube',
        epn="SS-63TS8",
    )
    _add(
        "check_valve",
        "KST-F-0011",
        'Check Valve, 1/4" SS',
        category="Plumbing",
        tracking="bulk",
        epn="4888K11",
        desc='McMaster 4888K11 — 1/4" tube, 3000 PSI, cracking pressure 1/3 PSI',
        reorder=4,
    )
    _add(
        "relief_valve",
        "KST-F-0012",
        "Pressure Relief Valve, 500 PSI",
        category="Plumbing",
        epn="48435K41",
        desc='McMaster 48435K41 — adjustable, 1/4" NPT, brass body',
    )
    _add(
        "tube_half",
        "KST-F-0013",
        'SS Tube, 1/2" OD x 0.035" Wall',
        category="Plumbing",
        tracking="bulk",
        uom="ft",
        epn="89895K427",
        desc="McMaster 89895K427 — 304 SS, seamless, ASTM A269",
        reorder=10,
    )
    _add(
        "tube_quarter",
        "KST-F-0014",
        'SS Tube, 1/4" OD x 0.035" Wall',
        category="Plumbing",
        tracking="bulk",
        uom="ft",
        epn="89895K217",
        desc="McMaster 89895K217 — 304 SS, seamless",
        reorder=10,
    )
    _add(
        "an_fitting_half",
        "KST-F-0015",
        'AN Flare Fitting, 1/2" Tube',
        category="Plumbing",
        tracking="bulk",
        epn="5182K18",
        desc="McMaster 5182K18 — 37° flare, 316 SS",
        reorder=8,
    )
    _add(
        "an_fitting_quarter",
        "KST-F-0016",
        'AN Flare Fitting, 1/4" Tube',
        category="Plumbing",
        tracking="bulk",
        epn="5182K14",
        desc="McMaster 5182K14 — 37° flare, 316 SS",
        reorder=8,
    )
    _add(
        "teflon_tape",
        "KST-D-0017",
        'Teflon Tape, 1/2" x 260"',
        category="Consumables",
        tier=3,
        tracking="bulk",
        epn="6802A13",
        desc="McMaster 6802A13 — PTFE thread seal tape",
        reorder=3,
    )

    # ── Structures ──────────────────────────────────────────────
    _add(
        "airframe",
        "KST-F-0018",
        'Airframe Tube, 6" OD x 48"',
        category="Structures",
        desc='6061-T6 drawn tube, 0.065" wall',
    )
    _add(
        "nosecone",
        "KST-F-0019",
        'Nose Cone, 6" 4:1 Ogive',
        category="Structures",
        desc='Fiberglass, 24" length, aluminum tip',
    )
    _add(
        "fin_set",
        "KST-F-0020",
        "Fin Set (3x)",
        category="Structures",
        desc='6061-T6 sheet, 0.125" thick, clipped delta planform',
    )
    _add(
        "bulkhead_fwd",
        "KST-F-0021",
        "Bulkhead, Forward",
        category="Structures",
        desc='6061-T6 plate, 6" OD, O-ring sealed, recovery harness attach',
    )
    _add(
        "bulkhead_aft",
        "KST-F-0022",
        "Bulkhead, Aft",
        category="Structures",
        desc='6061-T6 plate, 6" OD, engine mount interface, feedthrough ports',
    )
    _add(
        "coupler",
        "KST-F-0023",
        'Coupler Tube, 6" ID x 8"',
        category="Structures",
        desc="6061-T6, connects airframe sections, shear-pinned for separation",
    )
    _add(
        "rail_button",
        "KST-F-0024",
        "Rail Button, 1515",
        category="Structures",
        tracking="bulk",
        epn="97395A430",
        desc='McMaster 97395A430 — Delrin, 1/4"-20 thread',
        reorder=6,
    )

    # ── Avionics ────────────────────────────────────────────────
    _add(
        "fc",
        "KST-F-0025",
        "Flight Computer",
        category="Avionics",
        desc="Custom PCB — Teensy 4.1, data logging, dual pyro channels",
    )
    _add(
        "gps",
        "KST-F-0026",
        "GPS Module, u-blox MAX-M10S",
        category="Avionics",
        epn="MAX-M10S",
        desc="10 Hz update, SAW/LNA, active antenna connector",
    )
    _add(
        "imu",
        "KST-F-0027",
        "IMU, Bosch BNO055",
        category="Avionics",
        epn="BNO055",
        desc="9-DOF absolute orientation sensor, I2C, sensor fusion onboard",
    )
    _add(
        "altimeter",
        "KST-F-0028",
        "Barometric Altimeter, MS5611",
        category="Avionics",
        epn="MS5611",
        desc="24-bit ADC, 10 cm resolution, SPI/I2C",
    )
    _add(
        "radio",
        "KST-F-0029",
        "Telemetry Radio, RFM95W 915 MHz",
        category="Avionics",
        epn="RFM95W",
        desc="LoRa spread spectrum, +20 dBm, SPI interface",
    )
    _add(
        "lipo",
        "KST-F-0030",
        "Battery, LiPo 2S 1000 mAh",
        category="Avionics",
        tracking="bulk",
        desc="7.4V nominal, JST-XH balance connector, 20C discharge",
        reorder=2,
    )
    _add(
        "harness",
        "KST-F-0031",
        "Wiring Harness, Avionics Bay",
        category="Avionics",
        desc="Point-to-point harness: FC, sensors, pyro, antenna, battery",
    )
    _add(
        "pyro_board",
        "KST-F-0032",
        "Pyro Channel Board",
        category="Avionics",
        desc="Dual MOSFET e-match firing circuit, optoisolated, LED-armed indicator",
    )

    # ── Recovery ────────────────────────────────────────────────
    _add(
        "main_chute",
        "KST-F-0033",
        'Main Parachute, 48" Cruciform',
        category="Recovery",
        desc="Ripstop nylon, 12 lb max descent load, Vd ≈ 18 ft/s",
    )
    _add(
        "drogue",
        "KST-F-0034",
        'Drogue Parachute, 18" Hemispherical',
        category="Recovery",
        desc="Ripstop nylon, stabilizes descent to ~80 ft/s",
    )
    _add(
        "shock_cord",
        "KST-F-0035",
        'Shock Cord, 1/2" Tubular Nylon',
        category="Recovery",
        tracking="bulk",
        uom="ft",
        desc="1500 lb rated, 20 ft working length",
        reorder=25,
    )
    _add(
        "ubolt",
        "KST-F-0036",
        'U-Bolt, 1/4"-20 x 1-1/2" Span',
        category="Recovery",
        tracking="bulk",
        epn="3042T14",
        desc="McMaster 3042T14 — forged steel, zinc-plated",
        reorder=4,
    )
    _add(
        "shear_pin",
        "KST-F-0037",
        "Shear Pin, 2-56 Nylon",
        category="Recovery",
        tracking="bulk",
        epn="90207A004",
        desc="McMaster 90207A004 — nylon 6/6, calibrated shear for separation charge",
        reorder=50,
    )
    _add(
        "ematch",
        "KST-D-0038",
        "E-Match, J-Tek",
        category="Recovery",
        tier=3,
        tracking="bulk",
        desc="Electric match, 1A/1W no-fire, bridgewire igniter for ejection charges",
        reorder=10,
    )

    # ── Fasteners ───────────────────────────────────────────────
    _add(
        "shcs_quarter",
        "KST-D-0039",
        'SHCS 1/4"-20 x 1", 18-8 SS',
        category="Fasteners",
        tier=3,
        tracking="bulk",
        epn="91251A542",
        desc="McMaster 91251A542 — socket head cap screw, fully threaded",
        reorder=50,
    )
    _add(
        "shcs_10_32",
        "KST-D-0040",
        'SHCS 10-32 x 3/4", 18-8 SS',
        category="Fasteners",
        tier=3,
        tracking="bulk",
        epn="91251A320",
        desc="McMaster 91251A320 — socket head cap screw, fully threaded",
        reorder=50,
    )
    _add(
        "hex_nut_quarter",
        "KST-D-0041",
        'Hex Nut, 1/4"-20, 18-8 SS',
        category="Fasteners",
        tier=3,
        tracking="bulk",
        epn="91845A029",
        desc="McMaster 91845A029",
        reorder=50,
    )
    _add(
        "lock_washer_quarter",
        "KST-D-0042",
        'Lock Washer, 1/4", 18-8 SS',
        category="Fasteners",
        tier=3,
        tracking="bulk",
        epn="92146A029",
        desc="McMaster 92146A029 — split lock washer",
        reorder=50,
    )
    _add(
        "oring_012",
        "KST-D-0043",
        "O-Ring, -012 Buna-N, 70A",
        category="Fasteners",
        tier=3,
        tracking="bulk",
        epn="9452K113",
        desc='McMaster 9452K113 — AS568-012, 0.364" ID x 0.070" CS',
        reorder=20,
    )
    _add(
        "oring_016",
        "KST-D-0044",
        "O-Ring, -016 Buna-N, 70A",
        category="Fasteners",
        tier=3,
        tracking="bulk",
        epn="9452K117",
        desc='McMaster 9452K117 — AS568-016, 0.614" ID x 0.070" CS',
        reorder=20,
    )
    _add(
        "oring_116",
        "KST-F-0045",
        "O-Ring, -116 Viton, 75A",
        category="Fasteners",
        tracking="bulk",
        epn="9263K516",
        desc='McMaster 9263K516 — AS568-116, LOX-compatible fluoroelastomer, 0.614" ID x 0.103" CS',
        reorder=10,
    )

    # ── GSE ─────────────────────────────────────────────────────
    _add(
        "fill_valve",
        "KST-G-0001",
        "Fill/Drain Valve Assembly",
        category="GSE",
        tier=2,
        desc="Ground-side fill panel: ball valve, vent, burst disc",
    )
    _add(
        "umbilical_qd",
        "KST-G-0002",
        "Umbilical Quick-Disconnect",
        category="GSE",
        tier=2,
        desc="Swagelok QC4 series, auto-shutoff on disconnect",
        epn="SS-QC4-B-400",
    )
    _add(
        "ign_box",
        "KST-G-0003",
        "Ignition Control Box",
        category="GSE",
        tier=2,
        desc="Key-armed, dual-relay ignition circuit, 500 ft firing lead, continuity check",
    )
    _add(
        "launch_rail",
        "KST-G-0004",
        "Launch Rail, 20 ft 1515",
        category="GSE",
        tier=2,
        desc="80/20 1515 aluminum extrusion, guyed, 85° elevation angle",
    )
    _add(
        "proof_fixture",
        "KST-G-0005",
        "Pressure Test Fixture",
        category="GSE",
        tier=2,
        is_tooling=True,
        cal_days=365,
        desc="Hydrostatic proof test manifold: hand pump, gauge, relief valve, bleed",
    )
    _add(
        "ground_reg",
        "KST-G-0006",
        "Ground Regulator, N2",
        category="GSE",
        tier=2,
        desc="Swagelok KPR series, 0-800 PSI outlet, CGA-580 inlet",
        epn="KPR1FRA412A20000",
    )

    # ── Raw Material ────────────────────────────────────────────
    _add(
        "al_plate",
        "KST-D-0046",
        '6061-T6 Al Plate, 1/2" Thick',
        category="Raw Material",
        tier=3,
        tracking="bulk",
        uom="sq ft",
        epn="89015K28",
        desc="McMaster 89015K28 — mill finish, AMS-QQ-A-250/11",
    )
    _add(
        "ss_sheet",
        "KST-D-0047",
        '304 SS Sheet, 0.060" Thick',
        category="Raw Material",
        tier=3,
        tracking="bulk",
        uom="sq ft",
        epn="88885K58",
        desc="McMaster 88885K58 — #2B finish, ASTM A240",
    )
    _add(
        "al_round",
        "KST-D-0048",
        '6061-T6 Al Round Bar, 3" OD',
        category="Raw Material",
        tier=3,
        tracking="bulk",
        uom="ft",
        epn="8974K39",
        desc="McMaster 8974K39 — AMS 4150, turned and polished",
    )

    return p


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------


def _seed_bom(db: Session, p: dict[str, Part]) -> None:
    lines = [
        # Engine Assembly BOM
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["chamber"].id, quantity=1),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["injector"].id, quantity=1),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["nozzle"].id, quantity=1),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["igniter"].id, quantity=1),
        BOMLine(
            assembly_id=p["engine_assy"].id,
            component_id=p["shcs_quarter"].id,
            quantity=8,
            reference_designator="B1-B8",
            notes="Chamber-to-injector bolts",
        ),
        BOMLine(
            assembly_id=p["engine_assy"].id,
            component_id=p["hex_nut_quarter"].id,
            quantity=8,
            reference_designator="N1-N8",
        ),
        BOMLine(
            assembly_id=p["engine_assy"].id,
            component_id=p["lock_washer_quarter"].id,
            quantity=8,
            reference_designator="W1-W8",
        ),
        BOMLine(
            assembly_id=p["engine_assy"].id,
            component_id=p["oring_116"].id,
            quantity=2,
            notes="Injector face seal + nozzle throat seal",
        ),
        BOMLine(
            assembly_id=p["engine_assy"].id,
            component_id=p["shcs_10_32"].id,
            quantity=6,
            reference_designator="B9-B14",
            notes="Nozzle retainer ring",
        ),
    ]
    db.add_all(lines)
    db.flush()


# ---------------------------------------------------------------------------
# Part Requirements
# ---------------------------------------------------------------------------


def _seed_part_requirements(db: Session, p: dict[str, Part]) -> None:
    now = datetime.now(UTC)
    reqs: list[PartRequirement] = []

    # REQ-001 Structural Loads → structures
    for key in ["airframe", "nosecone", "fin_set", "bulkhead_fwd", "bulkhead_aft", "coupler"]:
        reqs.append(
            PartRequirement(
                part_id=p[key].id,
                requirement_id="REQ-001",
                status="open",
            )
        )

    # REQ-002 Pressure Containment → pressure vessels and engine
    for key in ["lox_tank", "fuel_tank", "press_tank", "chamber", "engine_assy"]:
        status = "verified" if key == "press_tank" else "open"
        reqs.append(
            PartRequirement(
                part_id=p[key].id,
                requirement_id="REQ-002",
                status=status,
                verified_at=now - timedelta(days=12) if status == "verified" else None,
                notes="COTS tank — vendor cert on file" if key == "press_tank" else None,
            )
        )

    # REQ-003 LOX Compatibility → wetted parts
    for key in [
        "lox_tank",
        "lox_valve",
        "check_valve",
        "relief_valve",
        "tube_half",
        "tube_quarter",
        "an_fitting_half",
        "an_fitting_quarter",
        "injector",
        "oring_116",
    ]:
        status = "verified" if key in ("tube_half", "tube_quarter") else "open"
        reqs.append(
            PartRequirement(
                part_id=p[key].id,
                requirement_id="REQ-003",
                status=status,
                verified_at=now - timedelta(days=20) if status == "verified" else None,
                notes="304 SS — per MSFC-SPEC-106B Table 1" if status == "verified" else None,
            )
        )

    # REQ-004 Recovery → recovery components and altimeter
    for key in ["main_chute", "drogue", "fc", "altimeter", "pyro_board"]:
        reqs.append(
            PartRequirement(
                part_id=p[key].id,
                requirement_id="REQ-004",
                status="open",
            )
        )

    # REQ-005 Data Logging → flight computer + sensors
    for key in ["fc", "imu", "altimeter", "gps"]:
        reqs.append(
            PartRequirement(
                part_id=p[key].id,
                requirement_id="REQ-005",
                status="open",
            )
        )

    # REQ-006 Telemetry Link → radio
    reqs.append(
        PartRequirement(
            part_id=p["radio"].id,
            requirement_id="REQ-006",
            status="open",
        )
    )

    # REQ-007 Pyro Isolation → pyro board
    reqs.append(
        PartRequirement(
            part_id=p["pyro_board"].id,
            requirement_id="REQ-007",
            status="verified",
            verified_at=now - timedelta(days=5),
            notes="Bench tested: >500V isolation between pyro and logic rails",
        )
    )

    # REQ-008 Traceability → all flight tier parts (sample)
    for key in [
        "engine_assy",
        "chamber",
        "injector",
        "nozzle",
        "lox_tank",
        "fuel_tank",
        "press_tank",
        "fc",
        "harness",
        "main_chute",
    ]:
        status = "open"
        if key in ("engine_assy", "chamber"):
            status = "waived"
        reqs.append(
            PartRequirement(
                part_id=p[key].id,
                requirement_id="REQ-008",
                status=status,
                notes="Waived — traceability deferred to post-assembly serial assignment"
                if status == "waived"
                else None,
            )
        )

    db.add_all(reqs)
    db.flush()


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def _seed_inventory(db: Session, p: dict[str, Part]) -> dict[str, InventoryRecord]:
    inv: dict[str, InventoryRecord] = {}

    def _add(key: str, part_key: str, qty: float, location: str, **kw: object) -> None:
        rec = InventoryRecord(
            part_id=p[part_key].id,
            opal_number=generate_opal_number(db),
            quantity=Decimal(str(qty)),
            location=location,
            source_type=SourceType.MANUAL,
            **kw,  # type: ignore[arg-type]
        )
        db.add(rec)
        db.flush()
        inv[key] = rec

    # Serialized flight hardware
    _add("chamber_1", "chamber", 1, "CLEAN-1")
    _add("injector_1", "injector", 1, "CLEAN-1")
    _add("nozzle_1", "nozzle", 1, "SHOP-BENCH")
    _add("igniter_1", "igniter", 1, "CLEAN-1")
    _add("lox_tank_1", "lox_tank", 1, "STORE-A1")
    _add("fuel_tank_1", "fuel_tank", 1, "STORE-A1")
    _add("press_tank_1", "press_tank", 1, "STORE-A2")
    _add("lox_valve_1", "lox_valve", 1, "STORE-B1")
    _add("fuel_valve_1", "fuel_valve", 1, "STORE-B1")
    _add("fc_1", "fc", 1, "LAB-BENCH")
    _add("gps_1", "gps", 1, "LAB-BENCH")
    _add("imu_1", "imu", 1, "LAB-BENCH")
    _add("radio_1", "radio", 1, "LAB-BENCH")
    _add("main_chute_1", "main_chute", 1, "STORE-C1")
    _add("drogue_1", "drogue", 1, "STORE-C1")
    _add("nosecone_1", "nosecone", 1, "STORE-A3")
    _add("airframe_1", "airframe", 1, "STORE-A3")

    # Bulk stock
    _add("tube_half_stock", "tube_half", 24, "STORE-B2", lot_number="LOT-2026-003")
    _add("tube_quarter_stock", "tube_quarter", 18, "STORE-B2", lot_number="LOT-2026-004")
    _add("an_half_stock", "an_fitting_half", 12, "STORE-B3")
    _add("an_quarter_stock", "an_fitting_quarter", 16, "STORE-B3")
    _add("shcs_quarter_stock", "shcs_quarter", 200, "STORE-D1", lot_number="LOT-2026-001")
    _add("shcs_10_32_stock", "shcs_10_32", 150, "STORE-D1", lot_number="LOT-2026-001")
    _add("hex_nut_stock", "hex_nut_quarter", 200, "STORE-D1")
    _add("lock_washer_stock", "lock_washer_quarter", 200, "STORE-D1")
    _add("oring_012_stock", "oring_012", 50, "STORE-D2")
    _add("oring_016_stock", "oring_016", 50, "STORE-D2")
    _add("oring_116_stock", "oring_116", 25, "STORE-D2")
    _add("shear_pin_stock", "shear_pin", 100, "STORE-D3")
    _add("ematch_stock", "ematch", 20, "STORE-D3")
    _add("rail_button_stock", "rail_button", 8, "STORE-D3")
    _add("shock_cord_stock", "shock_cord", 40, "STORE-C1")
    _add("ubolt_stock", "ubolt", 6, "STORE-C1")
    _add("lipo_stock", "lipo", 4, "LAB-SHELF")
    _add("teflon_stock", "teflon_tape", 5, "STORE-D4")

    # Raw material
    _add("al_plate_stock", "al_plate", 8, "STORE-E1", lot_number="LOT-MS-2026-A")
    _add("ss_sheet_stock", "ss_sheet", 4, "STORE-E1", lot_number="LOT-MS-2026-B")
    _add("al_round_stock", "al_round", 6, "STORE-E2", lot_number="LOT-MS-2026-C")

    # GSE
    _add("proof_fixture_1", "proof_fixture", 1, "PAD-CART")
    _add("ign_box_1", "ign_box", 1, "PAD-CART")
    _add("launch_rail_1", "launch_rail", 1, "PAD")
    _add("ground_reg_1", "ground_reg", 1, "PAD-CART")

    return inv


# ---------------------------------------------------------------------------
# Procedures
# ---------------------------------------------------------------------------


def _add_op_tree(
    db: Session,
    procedure_id: int,
    wc: dict[str, Workcenter],
    ops: list[dict[str, Any]],
) -> None:
    """Insert a list of top-level operations and their sub-steps.

    Each op dict supports: title, instructions, duration, workcenter, sub_steps.
    Each sub-step dict supports: title, instructions, duration, workcenter,
    requires_signoff, schema. Step numbers and parent_step_id are auto-computed.
    """
    order = 0
    for op_idx, op in enumerate(ops, start=1):
        order += 1
        parent = ProcedureStep(
            procedure_id=procedure_id,
            order=order,
            step_number=str(op_idx),
            level=0,
            title=op["title"],
            instructions=op.get("instructions"),
            estimated_duration_minutes=op.get("duration"),
            workcenter_id=wc[op["workcenter"]].id if op.get("workcenter") else None,
            requires_signoff=op.get("requires_signoff", False),
            required_data_schema=op.get("schema"),
        )
        db.add(parent)
        db.flush()
        for sub_idx, sub in enumerate(op.get("sub_steps", []), start=1):
            order += 1
            db.add(
                ProcedureStep(
                    procedure_id=procedure_id,
                    parent_step_id=parent.id,
                    order=order,
                    step_number=f"{op_idx}.{sub_idx}",
                    level=1,
                    title=sub["title"],
                    instructions=sub.get("instructions"),
                    estimated_duration_minutes=sub.get("duration"),
                    workcenter_id=wc[sub["workcenter"]].id if sub.get("workcenter") else None,
                    requires_signoff=sub.get("requires_signoff", False),
                    required_data_schema=sub.get("schema"),
                )
            )
    db.flush()


def _seed_procedures(
    db: Session,
    p: dict[str, Part],
    wc: dict[str, Workcenter],
) -> dict[str, MasterProcedure]:
    procs: dict[str, MasterProcedure] = {}

    # ── 1. Engine Assembly Build ────────────────────────────────
    eng_build = MasterProcedure(
        name="Engine Assembly Build",
        description="Assemble combustion chamber, injector plate, nozzle, and igniter into complete engine unit.",
        procedure_type=ProcedureType.BUILD,
        status=ProcedureStatus.ACTIVE,
    )
    db.add(eng_build)
    db.flush()
    procs["eng_build"] = eng_build

    # Kit (parts consumed by this procedure)
    for part_key, qty in [
        ("chamber", 1),
        ("injector", 1),
        ("nozzle", 1),
        ("igniter", 1),
        ("shcs_quarter", 8),
        ("hex_nut_quarter", 8),
        ("lock_washer_quarter", 8),
        ("oring_116", 2),
        ("shcs_10_32", 6),
    ]:
        db.add(
            Kit(
                procedure_id=eng_build.id,
                part_id=p[part_key].id,
                quantity_required=Decimal(str(qty)),
            )
        )
    db.add(
        ProcedureOutput(
            procedure_id=eng_build.id, part_id=p["engine_assy"].id, quantity_produced=Decimal("1")
        )
    )
    db.flush()

    _eng_build_ops: list[dict[str, Any]] = [
        {
            "title": "Component Prep and Inspection",
            "instructions": (
                "Inspect, clean, and stage all chamber, injector, nozzle, and igniter hardware "
                "before assembly begins."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Visual Component Inspection",
                    "instructions": (
                        "Inspect chamber bore, injector face, nozzle throat, and igniter housing "
                        "for nicks, machining swarf, or surface contamination."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Verify Dimensions Against Drawing",
                    "instructions": (
                        "Check chamber ID, injector face flatness, and nozzle throat diameter "
                        "with calipers. Confirm all dimensions are within tolerance per drawing."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Solvent-Clean All Mating Surfaces",
                    "instructions": (
                        "Wipe chamber flange, injector face, nozzle threads, and O-ring grooves "
                        "with isopropyl alcohol on a lint-free wipe. Blow dry with clean N2."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Stage Hardware Kit",
                    "instructions": (
                        "Verify kit contents against BOM: 8x 1/4-20 SHCS, 8x lock washers, "
                        "8x hex nuts, 6x 10-32 SHCS, 2x -116 O-rings. Record O-ring and "
                        "fastener lot numbers on traveler."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Injector to Chamber Mating",
            "instructions": "Loose-install the injector onto the chamber. No torque yet.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install Injector O-Ring",
                    "instructions": (
                        "Lubricate -116 O-ring with Krytox GPL-205 grease. Seat into injector "
                        "face groove. Verify O-ring sits flat with no twists or rolls."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Align Index Pin",
                    "instructions": (
                        "Rotate injector so the index dowel pin aligns with the chamber socket "
                        "at 0 degrees clock position."
                    ),
                    "duration": 3,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Lower Injector onto Chamber",
                    "instructions": (
                        "Slowly lower the injector flat onto the chamber flange. Verify the "
                        "O-ring engages evenly without pinching or extruding."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Injector Bolt Torquing",
            "instructions": "Install and final-torque the injector fasteners.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install Injector Fasteners",
                    "instructions": (
                        "Install 8x 1/4-20 SHCS with lock washers and hex nuts through the "
                        "injector flange. Tighten finger-tight in star pattern."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Torque to Spec in Star Pattern",
                    "instructions": (
                        "Torque 8x 1/4-20 SHCS to 120 in-lb in two passes: 60 in-lb first pass, "
                        "120 in-lb second pass. Follow star pattern."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                    "schema": {
                        "fields": [
                            {
                                "name": f"bolt{i}_torque",
                                "type": "number",
                                "label": f"Bolt {i} final torque (in-lb)",
                                "required": True,
                            }
                            for i in range(1, 9)
                        ]
                    },
                },
                {
                    "title": "Apply Witness Marks",
                    "instructions": (
                        "Apply yellow torque-seal across each bolt head and flange. Photograph "
                        "flange from two angles."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Nozzle Installation",
            "instructions": "Install nozzle and torque the retainer ring.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install Nozzle O-Ring",
                    "instructions": (
                        "Lubricate -116 O-ring with Krytox grease. Seat into nozzle throat "
                        "groove. Verify no twists."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Thread Nozzle into Chamber",
                    "instructions": (
                        "Thread nozzle into chamber aft end. Hand-tight plus 1/4 turn. "
                        "Verify nozzle seats fully against the O-ring."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Nozzle Retainer Ring",
                    "instructions": (
                        "Install retainer ring over nozzle. Insert 6x 10-32 SHCS and torque to "
                        "40 in-lb in alternating pattern."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                    "schema": {
                        "fields": [
                            {
                                "name": f"retainer_bolt{i}_torque",
                                "type": "number",
                                "label": f"Retainer bolt {i} torque (in-lb)",
                                "required": True,
                            }
                            for i in range(1, 7)
                        ]
                    },
                },
            ],
        },
        {
            "title": "Igniter Installation",
            "instructions": "Thread igniter into injector boss and verify continuity.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Thread Igniter into Injector Boss",
                    "instructions": (
                        "Apply thread sealant to igniter NPT threads. Thread into injector boss "
                        "hand-tight plus 1.5 turns. Torque to 25 ft-lb."
                    ),
                    "duration": 8,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Route E-Match Leads",
                    "instructions": (
                        "Route igniter leads up the chamber exterior, clear of the hot-gas "
                        "path. Tape leads to chamber wall with Kapton tape."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Igniter Continuity Check",
                    "instructions": (
                        "Measure resistance across e-match terminals with multimeter. Acceptable "
                        "range 1.0 to 3.0 ohms."
                    ),
                    "duration": 3,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "igniter_ohms",
                                "type": "number",
                                "label": "Igniter resistance (ohms)",
                                "required": True,
                            }
                        ]
                    },
                },
            ],
        },
        {
            "title": "Pneumatic Leak Check",
            "instructions": "Pressure-test all sealed joints with GN2 before closeout.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Cap Nozzle Exit",
                    "instructions": (
                        "Install machined test cap on nozzle exit with -012 O-ring. Verify cap "
                        "seats and is hand-tight."
                    ),
                    "duration": 3,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Pressurize to 50 PSI",
                    "instructions": (
                        "Connect GN2 supply via pressure test fixture (KST-G-0005). Slowly "
                        "pressurize chamber to 50 PSI. Hold 60 seconds."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Soap-Bubble All Joints",
                    "instructions": (
                        "Apply Snoop leak detector to injector flange, nozzle threads, igniter "
                        "boss, and cap seal. No bubbles permitted."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Depressurize and Remove Cap",
                    "instructions": (
                        "Slowly vent chamber to 0 PSI. Disconnect GN2 supply. Remove nozzle "
                        "exit cap."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Final Inspection and Documentation",
            "instructions": "Close out the build traveler and transfer engine to bonded storage.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Final Visual Inspection",
                    "instructions": (
                        "Confirm all fasteners are torque-sealed, no FOD inside chamber, no "
                        "swarf on injector face, no damage to igniter leads."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Photograph Assembly",
                    "instructions": (
                        "Take 4 photographs: fore (injector side), aft (nozzle side), left, "
                        "right. Include SN placard in each frame."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Record Assembly Data",
                    "instructions": (
                        "Log SNs of chamber, injector, nozzle, igniter. Record O-ring lot, "
                        "fastener lot, and thread sealant batch numbers."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Build Traveler Sign-Off",
                    "instructions": (
                        "Build lead and QA inspector both sign off that the engine is complete "
                        "and ready for hydrostatic proof test."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
            ],
        },
    ]
    _add_op_tree(db, eng_build.id, wc, _eng_build_ops)

    # ── 2. Hydrostatic Proof Test ───────────────────────────────
    hydro = MasterProcedure(
        name="Hydrostatic Proof Test",
        description="Proof test pressure vessel to 1.5x MEOP (675 PSI) with water. Verify no leaks or permanent deformation.",
        procedure_type=ProcedureType.OP,
        status=ProcedureStatus.ACTIVE,
    )
    db.add(hydro)
    db.flush()
    procs["hydro"] = hydro

    _hydro_ops: list[dict[str, Any]] = [
        {
            "title": "Test Setup",
            "instructions": (
                "Plumb the test article to the pressure fixture, fill with distilled water, "
                "and verify all instrumentation is reading nominal."
            ),
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Connect Test Fixture",
                    "instructions": (
                        "Connect pressure test fixture (KST-G-0005) to test article inlet via "
                        "1/4 inch SS tubing. Torque AN-4 fitting to 80 in-lb."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                },
                {
                    "title": "Fill with Distilled Water",
                    "instructions": (
                        "Fill test article with distilled water through fill port until water "
                        "weeps from highest vent. Close vent."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                },
                {
                    "title": "Bleed Air from Lines",
                    "instructions": (
                        "Open bleed valve and slowly stroke hand pump until water flows clear "
                        "with no entrained air. Close bleed valve."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Verify Instrumentation",
                    "instructions": (
                        "Confirm pressure gauge reads 0 to 2 PSI. Verify data-acquisition "
                        "system is logging. Verify pressure relief valve set point at 750 PSI."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Pressure Step — 100 PSI",
            "instructions": "First low-pressure hold. Verify gross leak integrity.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Pressurize to 100 PSI",
                    "instructions": (
                        "Slowly pressurize with hand pump at 10 PSI/sec. Stop at 100 PSI and "
                        "record reading."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "pressure_100_psi",
                                "type": "number",
                                "label": "Pressure at hold (PSI)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Hold and Inspect for Leaks",
                    "instructions": (
                        "Hold 60 seconds. Visually inspect all joints and weld lines. No "
                        "weeping or pressure decay permitted."
                    ),
                    "duration": 3,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Pressure Step — 300 PSI",
            "instructions": "Intermediate pressure hold.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Pressurize to 300 PSI",
                    "instructions": "Slowly pressurize to 300 PSI. Record reading.",
                    "duration": 5,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "pressure_300_psi",
                                "type": "number",
                                "label": "Pressure at hold (PSI)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Hold and Inspect",
                    "instructions": "Hold 60 seconds. Inspect for weeping or audible hiss.",
                    "duration": 3,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "MEOP Hold — 500 PSI",
            "instructions": "Maximum Expected Operating Pressure hold.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Pressurize to MEOP",
                    "instructions": "Slowly pressurize to 500 PSI. Record reading.",
                    "duration": 5,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "pressure_meop",
                                "type": "number",
                                "label": "Pressure at hold (PSI)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Hold 2 Minutes",
                    "instructions": (
                        "Hold 120 seconds. Monitor pressure gauge for decay. Decay shall not "
                        "exceed 2 PSI."
                    ),
                    "duration": 3,
                    "workcenter": "PAD",
                },
                {
                    "title": "Thorough Joint Inspection",
                    "instructions": (
                        "While at MEOP, inspect every weld seam, fitting, and seal with a "
                        "flashlight. Mark any suspect areas with chalk."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Proof Pressure Hold — 675 PSI",
            "instructions": "Proof test at 1.35x MEOP. Verify no yielding or weeping.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Pressurize to Proof",
                    "instructions": (
                        "Slowly pressurize to 675 PSI (1.35x MEOP). Approach proof pressure at "
                        "5 PSI/sec for the final 50 PSI."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                    "schema": {
                        "fields": [
                            {
                                "name": "proof_pressure",
                                "type": "number",
                                "label": "Peak proof pressure (PSI)",
                                "required": True,
                            },
                            {
                                "name": "hold_duration_s",
                                "type": "number",
                                "label": "Hold duration (seconds)",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "title": "Hold 5 Minutes",
                    "instructions": (
                        "Hold 300 seconds. Pressure decay shall not exceed 5 PSI. Log decay rate."
                    ),
                    "duration": 6,
                    "workcenter": "PAD",
                },
                {
                    "title": "Verify No Yielding or Weeping",
                    "instructions": (
                        "Final inspection at proof pressure. Any weeping, audible hiss, or "
                        "visible deformation is a failure."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Depressurization and Dimensional Check",
            "instructions": "Vent back to zero and verify no permanent deformation.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Slow Depressurize to 0 PSI",
                    "instructions": (
                        "Open bleed valve and vent slowly at 25 PSI/sec to atmosphere. "
                        "Disconnect supply once stable at 0."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Measure OD at 3 Stations",
                    "instructions": (
                        "Measure outside diameter with pi-tape at three stations along the "
                        "test article. Compare to baseline measurements taken pre-test."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "od_station_1",
                                "type": "number",
                                "label": "OD Station 1 (in)",
                            },
                            {
                                "name": "od_station_2",
                                "type": "number",
                                "label": "OD Station 2 (in)",
                            },
                            {
                                "name": "od_station_3",
                                "type": "number",
                                "label": "OD Station 3 (in)",
                            },
                        ]
                    },
                },
                {
                    "title": "Visual Inspection for Cracks or Bulging",
                    "instructions": (
                        "Inspect entire test article with bright light. Any visible cracks, "
                        "bulging, or surface distortion is a failure."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Test Closeout",
            "instructions": "Drain, dry, and record results.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Drain Test Article",
                    "instructions": (
                        "Open drain valve and tilt to fully empty water. Catch in graduated "
                        "container to verify fill volume."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Dry with N2 Purge",
                    "instructions": (
                        "Purge interior with dry GN2 for 5 minutes. Verify no residual moisture."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                },
                {
                    "title": "Record Pass or Fail",
                    "instructions": (
                        "Test director records pass/fail in traveler. Attach pressure trace "
                        "and OD measurements to test report."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
    ]
    _add_op_tree(db, hydro.id, wc, _hydro_ops)

    # ── 3. Hot Fire Test ────────────────────────────────────────
    hotfire = MasterProcedure(
        name="Static Hot Fire Test",
        description="Ground test of assembled engine on test stand. 5-second burn at full thrust. Record chamber pressure, thrust, and burn time.",
        procedure_type=ProcedureType.OP,
        status=ProcedureStatus.ACTIVE,
    )
    db.add(hotfire)
    db.flush()
    procs["hotfire"] = hotfire

    _hotfire_ops: list[dict[str, Any]] = [
        {
            "title": "Pre-Test Planning",
            "instructions": "Confirm plan, range, and weather before any propellant handling.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Review Test Plan and Abort Criteria",
                    "instructions": (
                        "Walk through test card with all crew. Confirm each station knows "
                        "their role and the abort triggers."
                    ),
                    "duration": 15,
                    "workcenter": "PAD",
                },
                {
                    "title": "Range Clear Confirmation",
                    "instructions": (
                        "Range safety officer sweeps test area and confirms all non-essential "
                        "personnel are clear of the 500 ft exclusion zone."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
                {
                    "title": "Weather Check",
                    "instructions": (
                        "Verify winds under 20 kts, no lightning within 25 nm, visibility "
                        "greater than 3 nm. Document conditions."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Engine Stand Installation",
            "instructions": "Mount engine to the thrust stand and verify alignment.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Mount Engine to Adapter Plate",
                    "instructions": (
                        "Lift engine onto thrust stand adapter plate. Engage 4x 3/8-16 mount "
                        "bolts finger-tight."
                    ),
                    "duration": 15,
                    "workcenter": "PAD",
                },
                {
                    "title": "Torque Mount Bolts",
                    "instructions": (
                        "Torque 4x 3/8-16 mount bolts to 240 in-lb in star pattern. Apply "
                        "Loctite 242."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                    "schema": {
                        "fields": [
                            {
                                "name": f"bolt{i}_torque",
                                "type": "number",
                                "label": f"Mount bolt {i} torque (in-lb)",
                                "required": True,
                            }
                            for i in range(1, 5)
                        ]
                    },
                },
                {
                    "title": "Verify Engine Alignment",
                    "instructions": (
                        "Check that nozzle axis is parallel to thrust stand load axis within "
                        "0.5 degrees. Adjust shims if needed."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Propellant Plumbing",
            "instructions": "Connect propellant and pressurant feedlines to the engine.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Connect LOX Feed Line",
                    "instructions": (
                        "Connect 1/2 inch SS LOX line to engine LOX inlet. Torque AN-8 fitting "
                        "to 180 in-lb."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                },
                {
                    "title": "Connect Fuel Feed Line",
                    "instructions": (
                        "Connect 1/2 inch SS ethanol line to engine fuel inlet. Torque AN-8 "
                        "fitting to 180 in-lb."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                },
                {
                    "title": "Connect Pressurant Lines",
                    "instructions": (
                        "Connect 1/4 inch GN2 pressurant lines to LOX and fuel tank ullage "
                        "ports. Torque AN-4 to 80 in-lb."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Instrumentation Hookup",
            "instructions": "Connect all transducers and verify DAQ is capturing.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Connect Thrust Load Cell",
                    "instructions": "Attach load cell cable to DAQ channel 1. Verify excitation voltage.",
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Connect Chamber Pressure Transducer",
                    "instructions": (
                        "Install Pc transducer in injector boss tap. Torque 1/8 NPT to 80 "
                        "in-lb with thread sealant. Connect to DAQ channel 2."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                },
                {
                    "title": "Connect Thermocouples",
                    "instructions": (
                        "Install Type K thermocouples on chamber wall, nozzle throat, and "
                        "injector body. Route leads to DAQ channels 3 to 5."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                },
                {
                    "title": "Verify Data Acquisition Capture",
                    "instructions": (
                        "Run DAQ self-test. Tap each transducer and verify signal appears on "
                        "the trace. Confirm sample rate at 1 kHz."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Pneumatic Leak Check",
            "instructions": "Pressure-test propellant lines with GN2 before loading.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Cap Engine Inlets",
                    "instructions": "Install test caps on engine LOX and fuel inlets.",
                    "duration": 3,
                    "workcenter": "PAD",
                },
                {
                    "title": "Pressurize Lines to 50 PSI",
                    "instructions": (
                        "Apply GN2 to both propellant lines at 50 PSI. Hold 60 seconds."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Soap-Bubble All Joints",
                    "instructions": (
                        "Apply Snoop to every AN fitting, NPT joint, and valve body. No "
                        "bubbles permitted."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
                {
                    "title": "Depressurize and Remove Caps",
                    "instructions": "Vent lines to 0 PSI. Remove test caps from engine inlets.",
                    "duration": 5,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Propellant Loading",
            "instructions": "Load LOX and ethanol. Loading crew only on pad.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Clear Pad Area",
                    "instructions": (
                        "All personnel except loading crew (2 max) clear to 100 ft. Loading "
                        "crew in PPE: face shield, cryo gloves, leather apron."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Fill LOX Tank",
                    "instructions": (
                        "Slowly fill LOX tank from dewar through fill port. Target 2.5 gal. "
                        "Vent ullage to atmosphere during fill."
                    ),
                    "duration": 15,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "lox_fill_level",
                                "type": "number",
                                "label": "LOX fill level (gal)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Fill Ethanol Tank",
                    "instructions": "Fill ethanol tank from supply jug. Target 3.0 gal.",
                    "duration": 10,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "fuel_fill_level",
                                "type": "number",
                                "label": "Fuel fill level (gal)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Verify Fill Levels and Crack Vent",
                    "instructions": (
                        "Confirm both tank sight glasses show target volume. Crack vent valves "
                        "to relieve pressure during fill cooldown."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Tank Pressurization",
            "instructions": "Bring tanks to 450 PSI pressurant.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Connect N2 Supply",
                    "instructions": "Open main N2 K-bottle valve. Verify supply pressure on regulator inlet.",
                    "duration": 3,
                    "workcenter": "PAD",
                },
                {
                    "title": "Regulate to 450 PSI",
                    "instructions": (
                        "Adjust ground regulator to deliver 450 PSI. Slowly open isolation "
                        "valves to tank ullage ports."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Verify Tank Pressures",
                    "instructions": "Read LOX and fuel tank ullage pressure. Both must be 440 to 460 PSI.",
                    "duration": 3,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "lox_tank_psi",
                                "type": "number",
                                "label": "LOX tank pressure (PSI)",
                                "required": True,
                            },
                            {
                                "name": "fuel_tank_psi",
                                "type": "number",
                                "label": "Fuel tank pressure (PSI)",
                                "required": True,
                            },
                        ]
                    },
                },
            ],
        },
        {
            "title": "Arm and Go/No-Go",
            "instructions": "All personnel to bunker. Final arming and poll.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Clear All Personnel to Bunker",
                    "instructions": "Loading crew clears pad to bunker. Confirm all stations report clear.",
                    "duration": 3,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
                {
                    "title": "Arm Ignition System",
                    "instructions": (
                        "Turn igniter arm key from SAFE to ARMED. Verify ARMED indicator LED "
                        "is lit and continuity is shown."
                    ),
                    "duration": 2,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
                {
                    "title": "Final Station Poll Go/No-Go",
                    "instructions": (
                        "Test director polls each station by callsign: PROPS, DAQ, RANGE, "
                        "MED. Record GO from all before proceeding."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Fire Sequence",
            "instructions": "Execute ignition and main-stage burn.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Countdown from 5",
                    "instructions": "Test director calls 5-4-3-2-1 over comms. DAQ trigger armed at T-2.",
                    "duration": 1,
                    "workcenter": "PAD",
                },
                {
                    "title": "Igniter Command",
                    "instructions": (
                        "At T-0 fire igniter. Verify pre-burner light through pad camera "
                        "within 200 ms."
                    ),
                    "duration": 1,
                    "workcenter": "PAD",
                },
                {
                    "title": "Main Valve Open Command",
                    "instructions": (
                        "T+0.5s: open main LOX and fuel valves simultaneously. Run 5 seconds. "
                        "Monitor chamber pressure trace live."
                    ),
                    "duration": 1,
                    "workcenter": "PAD",
                },
                {
                    "title": "Engine Shutdown",
                    "instructions": "T+5.5s: close both main valves. Engine should extinguish within 100 ms.",
                    "duration": 1,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Safe-State",
            "instructions": "Vent system and disarm before any pad approach.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Close Main Valves",
                    "instructions": "Confirm LOX and fuel main valves indicate CLOSED on control panel.",
                    "duration": 2,
                    "workcenter": "PAD",
                },
                {
                    "title": "Vent Tank Ullage",
                    "instructions": (
                        "Open tank vent valves and bleed ullage pressure to 0 PSI. Monitor "
                        "tank pressure gauges."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Safe Ignition System",
                    "instructions": "Turn igniter key to SAFE and remove. Confirm ARMED LED off.",
                    "duration": 2,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
                {
                    "title": "Approach and Inspect for Residual Fire",
                    "instructions": (
                        "Wait 5 minutes after shutdown before approach. RSO leads team to "
                        "pad with extinguisher. Verify no residual fire or smoldering."
                    ),
                    "duration": 8,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Data Capture and Post-Fire Inspection",
            "instructions": "Pull DAQ files and inspect engine hardware.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Download DAQ Files",
                    "instructions": (
                        "Download thrust, Pc, and temperature traces from DAQ. Verify file "
                        "integrity. Record peak values."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                    "schema": {
                        "fields": [
                            {
                                "name": "peak_chamber_psi",
                                "type": "number",
                                "label": "Peak Pc (PSI)",
                                "required": True,
                            },
                            {
                                "name": "peak_thrust_lbf",
                                "type": "number",
                                "label": "Peak thrust (lbf)",
                                "required": True,
                            },
                            {
                                "name": "burn_time_s",
                                "type": "number",
                                "label": "Burn time (seconds)",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "title": "Inspect Nozzle Throat",
                    "instructions": (
                        "Visual inspection of nozzle throat. Check for erosion, cracks, or "
                        "ablative loss. Photograph."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Inspect Injector Face",
                    "instructions": (
                        "Borescope injector face. Check for orifice erosion, soot patterns, "
                        "or hot spots. Photograph."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
                {
                    "title": "Inspect Chamber Walls",
                    "instructions": (
                        "Borescope chamber walls. Check for erosion, hot streaks, or "
                        "discoloration. Photograph."
                    ),
                    "duration": 5,
                    "workcenter": "PAD",
                },
            ],
        },
        {
            "title": "Stand Removal and Debrief",
            "instructions": "Disconnect, remove engine, and review data.",
            "duration": 5,
            "workcenter": "PAD",
            "sub_steps": [
                {
                    "title": "Disconnect Lines and Instrumentation",
                    "instructions": (
                        "Disconnect all propellant lines, pressurant lines, and instrumentation "
                        "cables. Cap engine ports."
                    ),
                    "duration": 15,
                    "workcenter": "PAD",
                },
                {
                    "title": "Remove Engine from Stand",
                    "instructions": (
                        "Break 4x mount bolts. Lift engine off adapter plate. Transfer to "
                        "transport cart."
                    ),
                    "duration": 10,
                    "workcenter": "PAD",
                },
                {
                    "title": "Data Review vs Predictions",
                    "instructions": (
                        "Compare measured Pc, thrust, and burn time against predicted values. "
                        "Note any deviations greater than 10%."
                    ),
                    "duration": 20,
                    "workcenter": "PAD",
                },
                {
                    "title": "Test Debrief and Sign-Off",
                    "instructions": (
                        "Whole team debrief: lessons learned, anomalies, action items. Test "
                        "director signs off on test report."
                    ),
                    "duration": 15,
                    "workcenter": "PAD",
                    "requires_signoff": True,
                },
            ],
        },
    ]
    _add_op_tree(db, hotfire.id, wc, _hotfire_ops)

    # ── 4. Avionics Integration ─────────────────────────────────
    avi = MasterProcedure(
        name="Avionics Bay Integration",
        description="Assemble flight computer, sensors, radio, pyro board, and battery onto avionics sled. Build and test wiring harness.",
        procedure_type=ProcedureType.BUILD,
        status=ProcedureStatus.DRAFT,
    )
    db.add(avi)
    db.flush()
    procs["avi"] = avi

    for part_key, qty in [
        ("fc", 1),
        ("gps", 1),
        ("imu", 1),
        ("altimeter", 1),
        ("radio", 1),
        ("lipo", 1),
        ("pyro_board", 1),
    ]:
        db.add(
            Kit(procedure_id=avi.id, part_id=p[part_key].id, quantity_required=Decimal(str(qty)))
        )
    db.add(
        ProcedureOutput(
            procedure_id=avi.id, part_id=p["harness"].id, quantity_produced=Decimal("1")
        )
    )
    db.flush()

    _avi_ops: list[dict[str, Any]] = [
        {
            "title": "Sled Preparation",
            "instructions": "Clean sled and install all standoffs before any components touch the board.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Clean Sled",
                    "instructions": (
                        "Wipe avionics sled with isopropyl alcohol on a lint-free cloth. "
                        "Blow off with clean N2."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Install Standoffs",
                    "instructions": (
                        "Install M3 brass standoffs at flight computer, pyro board, GPS, and "
                        "radio mounting locations per assembly drawing."
                    ),
                    "duration": 10,
                    "workcenter": "LAB",
                },
                {
                    "title": "Verify Mounting Hole Pattern",
                    "instructions": (
                        "Test-fit each board on its standoffs. Confirm no hole misalignment "
                        "before applying torque."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
            ],
        },
        {
            "title": "Flight Computer Mount",
            "instructions": "Mount Teensy 4.1 and verify USB access.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Position FC on Standoffs",
                    "instructions": "Place Teensy 4.1 onto its standoffs with USB port facing the access window.",
                    "duration": 3,
                    "workcenter": "LAB",
                },
                {
                    "title": "Secure with M3 Screws",
                    "instructions": "Secure with 4x M3x6 screws. Torque to 4 in-lb. Do not over-tighten.",
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Verify USB Port Accessibility",
                    "instructions": (
                        "Confirm USB-C cable seats and disconnects without binding through the "
                        "access window."
                    ),
                    "duration": 2,
                    "workcenter": "LAB",
                },
                {
                    "title": "Bench Continuity Check",
                    "instructions": "Connect FC to bench supply at 5V. Verify board enumerates over USB.",
                    "duration": 5,
                    "workcenter": "LAB",
                },
            ],
        },
        {
            "title": "Sensor Installation",
            "instructions": "Mount IMU, altimeter, GPS and connect data buses.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Install BNO055 IMU",
                    "instructions": (
                        "Mount BNO055 breakout on standoffs with X-axis aligned to vehicle "
                        "roll axis per drawing. Secure with M3 screws."
                    ),
                    "duration": 8,
                    "workcenter": "LAB",
                },
                {
                    "title": "Install MS5611 Altimeter",
                    "instructions": (
                        "Mount MS5611 breakout. Verify barometric port is unblocked and faces "
                        "the bay vent."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Install MAX-M10S GPS",
                    "instructions": (
                        "Mount GPS module with antenna patch facing the airframe outer wall "
                        "for sky visibility."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Connect Sensor I2C and UART Cables",
                    "instructions": (
                        "Connect IMU and altimeter to I2C bus pins. Connect GPS UART to FC "
                        "Serial1. Verify pin assignments against wiring diagram."
                    ),
                    "duration": 10,
                    "workcenter": "LAB",
                },
            ],
        },
        {
            "title": "Pyro Board Installation",
            "instructions": "Install and verify the pyro channel board.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Install Pyro Channel Board on Standoffs",
                    "instructions": "Mount pyro board with screw terminals facing the bulkhead penetration.",
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Connect Optoisolator Ribbon to FC",
                    "instructions": (
                        "Connect 10-conductor ribbon from pyro board to FC pyro control "
                        "header. Verify ribbon orientation by red stripe on pin 1."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Continuity Check Both Channels",
                    "instructions": (
                        "With pyro board unpowered, verify continuity between FC pyro pins "
                        "and screw terminals using multimeter."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                    "schema": {
                        "fields": [
                            {
                                "name": "drogue_channel_ohms",
                                "type": "number",
                                "label": "Drogue channel continuity (ohms)",
                                "required": True,
                            },
                            {
                                "name": "main_channel_ohms",
                                "type": "number",
                                "label": "Main channel continuity (ohms)",
                                "required": True,
                            },
                        ]
                    },
                },
            ],
        },
        {
            "title": "Radio and Antenna",
            "instructions": "Install telemetry radio and route antenna feed.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Install RFM95W Module",
                    "instructions": "Mount RFM95W on its standoffs. Connect SPI ribbon to FC.",
                    "duration": 8,
                    "workcenter": "LAB",
                },
                {
                    "title": "Route Antenna Coax",
                    "instructions": (
                        "Route 50 ohm coax from RFM95W u.FL to airframe bulkhead. Avoid sharp "
                        "bends (minimum 1 inch radius)."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Install SMA Bulkhead Connector",
                    "instructions": "Install SMA bulkhead through coupler. Torque SMA to 5 in-lb.",
                    "duration": 5,
                    "workcenter": "LAB",
                },
            ],
        },
        {
            "title": "Wiring Harness Build",
            "instructions": "Build the harness on the sled per harness drawing.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Cut and Strip Wires per Drawing",
                    "instructions": (
                        "Cut each wire to length and strip 5 mm per harness drawing. Label "
                        "both ends with shrink-wrap tags."
                    ),
                    "duration": 20,
                    "workcenter": "LAB",
                },
                {
                    "title": "Terminate Connectors",
                    "instructions": (
                        "Crimp Molex SL connectors on each terminated wire. Pull-test each "
                        "crimp at 5 lbf."
                    ),
                    "duration": 25,
                    "workcenter": "LAB",
                },
                {
                    "title": "Lace Harness with Waxed Cord",
                    "instructions": "Lace harness bundle with waxed cord every 25 mm. Tie off neatly.",
                    "duration": 15,
                    "workcenter": "LAB",
                },
                {
                    "title": "Continuity Check Each Wire",
                    "instructions": (
                        "Beep out every wire end-to-end with multimeter. Confirm no shorts "
                        "between adjacent pins."
                    ),
                    "duration": 15,
                    "workcenter": "LAB",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Power-On Test and Closeout",
            "instructions": "Power up and verify all subsystems before final inspection.",
            "duration": 5,
            "workcenter": "LAB",
            "sub_steps": [
                {
                    "title": "Install LiPo Battery",
                    "instructions": (
                        "Install 2S 1500 mAh LiPo in battery holder. Confirm polarity. "
                        "Connect with XT30."
                    ),
                    "duration": 3,
                    "workcenter": "LAB",
                },
                {
                    "title": "Verify Boot Sequence",
                    "instructions": (
                        "Power FC. Watch USB serial for boot banner. Verify firmware version "
                        "matches build manifest."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                    "requires_signoff": True,
                },
                {
                    "title": "Verify Sensor Responses",
                    "instructions": (
                        "Issue self-test command. Confirm IMU returns valid quaternion, GPS "
                        "acquires fix within 90 s, altimeter reads ground pressure."
                    ),
                    "duration": 8,
                    "workcenter": "LAB",
                    "schema": {
                        "fields": [
                            {
                                "name": "imu_status",
                                "type": "string",
                                "label": "IMU self-test result",
                                "required": True,
                            },
                            {
                                "name": "gps_fix_count",
                                "type": "number",
                                "label": "GPS satellites locked",
                                "required": True,
                            },
                            {
                                "name": "altimeter_ground_psi",
                                "type": "number",
                                "label": "Ground pressure (mbar)",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "title": "Verify Radio TX Test Packet",
                    "instructions": (
                        "Trigger test packet TX. Confirm ground station receives at RSSI "
                        "greater than -90 dBm at 10 m range."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Photograph Completed Assembly",
                    "instructions": (
                        "Take 4 photos: top, bottom, both ends. Include build SN placard "
                        "in each frame."
                    ),
                    "duration": 5,
                    "workcenter": "LAB",
                },
                {
                    "title": "Final Sign-Off",
                    "instructions": (
                        "Verify connector seating, wire routing, and chafe protection. "
                        "Avionics lead signs off."
                    ),
                    "duration": 10,
                    "workcenter": "LAB",
                    "requires_signoff": True,
                },
            ],
        },
    ]
    _add_op_tree(db, avi.id, wc, _avi_ops)

    # ── 5. Recovery System Pack ─────────────────────────────────
    rec = MasterProcedure(
        name="Recovery System Pack",
        description="Fold and pack main and drogue parachutes, install ejection charges, and verify continuity.",
        procedure_type=ProcedureType.OP,
        status=ProcedureStatus.ACTIVE,
    )
    db.add(rec)
    db.flush()
    procs["recovery"] = rec

    _rec_ops: list[dict[str, Any]] = [
        {
            "title": "Parachute Inspection",
            "instructions": "Inspect both canopies and lines before any folding.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Unfold Drogue",
                    "instructions": "Lay drogue (KST-F-0034) flat on clean inspection table. Spread canopy fully.",
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Unfold Main",
                    "instructions": "Lay main canopy (KST-F-0033) flat on clean inspection table adjacent to drogue.",
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Inspect Canopies for Tears or Burn-Through",
                    "instructions": (
                        "Inspect both canopies under bright light. No tears, burn marks, "
                        "fabric weakness, or seam separation."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Inspect Shroud Lines for Fraying",
                    "instructions": (
                        "Run gloved hand along every shroud line. No fraying, knots, or "
                        "abrasion. Verify all lines uniform length."
                    ),
                    "duration": 8,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Drogue Pack",
            "instructions": "Z-fold and bag the drogue.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Z-Fold Drogue Canopy",
                    "instructions": (
                        "Z-fold drogue canopy into 6 inch wide bundle per packing card. "
                        "Maintain symmetry."
                    ),
                    "duration": 8,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Bundle Shroud Lines",
                    "instructions": (
                        "Daisy-chain shroud lines into a loose bundle on top of folded canopy. "
                        "Do not knot."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Insert in Deployment Bag and Close",
                    "instructions": (
                        "Insert bundle into deployment bag. Pull rubber band closure. Verify "
                        "bridle exits cleanly."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Main Pack",
            "instructions": "Accordion-fold and bag the main chute.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Accordion-Fold Main Canopy",
                    "instructions": (
                        "Accordion-fold main canopy per packing card into 8 inch wide bundle. "
                        "Compress to deployment bag width."
                    ),
                    "duration": 12,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Bundle Main Shroud Lines",
                    "instructions": "Daisy-chain shroud lines on top of folded canopy. Avoid twists.",
                    "duration": 6,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Insert in Deployment Bag and Close",
                    "instructions": (
                        "Slide bundle into deployment bag. Close with bungee. Confirm pilot "
                        "chute attached."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Ejection Charge Loading",
            "instructions": "Load black powder charges. PYRO CREW ONLY in the area.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Clear Area to Pyro Crew Only",
                    "instructions": (
                        "All non-pyro personnel clear the room. Pyro crew dons PPE: safety "
                        "glasses, anti-static wrist strap."
                    ),
                    "duration": 3,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Measure and Load Drogue Charge",
                    "instructions": (
                        "Weigh 2.5 g FFFFg black powder on anti-static scale. Load into drogue "
                        "charge well. Record actual mass."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "drogue_charge_g",
                                "type": "number",
                                "label": "Drogue charge (grams)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Measure and Load Main Charge",
                    "instructions": (
                        "Weigh 4.0 g FFFFg black powder. Load into main charge well. Record "
                        "actual mass."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "main_charge_g",
                                "type": "number",
                                "label": "Main charge (grams)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Install E-Matches in Charge Wells",
                    "instructions": (
                        "Bed e-matches (KST-D-0038) in each charge well. Tape leads outboard "
                        "along bay wall."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Continuity Verification",
            "instructions": "Confirm both pyro channels show in-spec resistance.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Connect Multimeter to Drogue Circuit",
                    "instructions": "Connect multimeter across drogue pyro terminals. Set to 200 ohm range.",
                    "duration": 2,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Record Drogue Circuit Resistance",
                    "instructions": "Read and record drogue circuit. Acceptable range 1.0 to 3.5 ohms.",
                    "duration": 2,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "drogue_ohms",
                                "type": "number",
                                "label": "Drogue circuit (ohms)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Record Main Circuit Resistance",
                    "instructions": "Connect across main pyro terminals. Read and record. Same acceptable range.",
                    "duration": 2,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "main_ohms",
                                "type": "number",
                                "label": "Main circuit (ohms)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Verify Both Channels in Spec",
                    "instructions": (
                        "Pyro lead confirms both circuits are in spec and signs off before "
                        "closeout."
                    ),
                    "duration": 3,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Shear Pin Installation",
            "instructions": "Install separation-joint shear pins and verify coupler engagement.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install Drogue Joint Shear Pins",
                    "instructions": (
                        "Install 3x nylon shear pins (KST-F-0037) at 120 degree spacing through "
                        "drogue separation joint. Pins flush with airframe."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Main Joint Shear Pins",
                    "instructions": (
                        "Install 3x nylon shear pins at 120 degree spacing through main "
                        "separation joint. Pins flush with airframe."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Verify Coupler Alignment",
                    "instructions": (
                        "Visually verify both couplers are fully engaged with no gaps. Run "
                        "straight edge across each joint."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
            ],
        },
    ]
    _add_op_tree(db, rec.id, wc, _rec_ops)

    # ── 6. Final Vehicle Integration ────────────────────────────
    fvi = MasterProcedure(
        name="Final Vehicle Integration",
        description=(
            "Stack all flight subsystems into complete vehicle. Uses operation/step "
            "hierarchy: each operation groups related steps for loose install, final "
            "install, alignment, safety wire, and closeout."
        ),
        procedure_type=ProcedureType.BUILD,
        status=ProcedureStatus.DRAFT,
    )
    db.add(fvi)
    db.flush()
    procs["fvi"] = fvi

    _fvi_ops: list[dict[str, Any]] = [
        {
            "title": "Preparation and Staging",
            "instructions": (
                "Set up clean work area. Gather and verify all subassemblies, hardware, "
                "and tooling required for integration."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Clean Work Surface",
                    "instructions": (
                        "Wipe down integration bench with isopropyl alcohol. Lay out clean "
                        "ESD-safe mat."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Stage Subassemblies",
                    "instructions": (
                        "Place the following on bench: engine assembly (KST-F-0001), LOX tank "
                        "(KST-F-0006), fuel tank (KST-F-0007), avionics sled, recovery bay, "
                        "forward bulkhead (KST-F-0021), aft bulkhead (KST-F-0022), airframe "
                        "tube (KST-F-0018), nose cone (KST-F-0019), fin set (KST-F-0020), "
                        "coupler tubes (KST-F-0023)."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Verify Subassembly Serial Numbers",
                    "instructions": (
                        "Record serial numbers of all flight subassemblies. Cross-reference "
                        "against traveler. Confirm all items have passed incoming inspection "
                        "or prior build procedures."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Inventory Hardware Kit",
                    "instructions": (
                        "Verify kit contents against BOM: 1/4 inch-20 SHCS (qty 16), 10-32 "
                        "SHCS (qty 12), 1/4 inch-20 hex nuts (qty 16), lock washers (qty 16), "
                        "rail buttons (qty 2), shear pins (qty 6), U-bolts (qty 4), O-rings "
                        "-012 (qty 4), O-rings -016 (qty 2). Mark checklist."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Aft Section — Loose Install",
            "instructions": (
                "Loose-fit aft bulkhead, engine assembly, and thrust structure into the aft "
                "end of the airframe. All fasteners finger-tight only."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Loose-Install Aft Bulkhead",
                    "instructions": (
                        "Insert aft bulkhead (KST-F-0022) into airframe tube. Align "
                        "feedthrough ports to 0 degree clock position. Install retaining "
                        "ring finger-tight."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Loose-Install Engine Assembly",
                    "instructions": (
                        "Slide engine assembly into aft section. Engage mount flange bolts "
                        "(4x 1/4 inch-20 SHCS with lock washers) through bulkhead, "
                        "finger-tight only."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Check Clearances",
                    "instructions": (
                        "Verify igniter leads, nozzle exit, and propellant feed ports are "
                        "not fouled. Minimum 0.125 inch clearance to airframe ID."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Aft Section — Final Install and Torque",
            "instructions": "Final-torque all aft section fasteners. Apply witness marks.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Torque Aft Bulkhead Retaining Ring",
                    "instructions": (
                        "Torque retaining ring to 60 in-lb using spanner wrench. Verify even "
                        "contact around full circumference."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Apply Witness Marks",
                    "instructions": (
                        "Apply torque-seal (yellow) to all aft section fastener heads. "
                        "Photograph from two angles."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Torque Engine Mount Bolts",
                    "instructions": (
                        "Torque 4x 1/4 inch-20 engine mount bolts in star pattern to 120 "
                        "in-lb. Apply Loctite 242 per drawing."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                    "schema": {
                        "fields": [
                            {
                                "name": f"bolt{i}_torque",
                                "type": "number",
                                "label": f"Bolt {i} torque (in-lb)",
                                "required": True,
                            }
                            for i in range(1, 5)
                        ]
                    },
                },
            ],
        },
        {
            "title": "Propellant Tank Installation",
            "instructions": (
                "Install LOX and fuel tanks onto thrust structure. Connect feedlines and "
                "vent lines."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install LOX Tank",
                    "instructions": (
                        "Lower LOX tank (KST-F-0006) onto thrust structure standoffs. Orient "
                        "fill port to 0 degree clock position. Install 4x 10-32 SHCS "
                        "finger-tight."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Fuel Tank",
                    "instructions": (
                        "Stack fuel tank (KST-F-0007) above LOX tank on spacer ring. Orient "
                        "fill port to 180 degree clock position. Install 4x 10-32 SHCS "
                        "finger-tight."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Torque Tank Mount Bolts",
                    "instructions": (
                        "Torque all 8x 10-32 tank mount SHCS to 40 in-lb in alternating pattern."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Connect Propellant Feedlines",
                    "instructions": (
                        "Connect 1/2 inch SS feedlines from tank outlets to engine inlets. "
                        "Install AN fittings (KST-F-0015). Torque AN-8 fittings to 180 in-lb."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                    "schema": {
                        "fields": [
                            {
                                "name": "lox_fitting_torque",
                                "type": "number",
                                "label": "LOX feed fitting torque (in-lb)",
                                "required": True,
                            },
                            {
                                "name": "fuel_fitting_torque",
                                "type": "number",
                                "label": "Fuel feed fitting torque (in-lb)",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "title": "Connect Vent Lines",
                    "instructions": (
                        "Route 1/4 inch vent lines from tank ullage ports to forward "
                        "bulkhead feedthroughs. Install AN-4 fittings. Torque to 80 in-lb."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Pneumatic Leak Check",
            "instructions": (
                "Pressure-test all propellant and pneumatic connections with GN2 before "
                "closing out the aft section."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Cap Open Ports",
                    "instructions": (
                        "Install test caps on engine inlet ports and vent line "
                        "terminations. Verify all caps are seated."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Pressurize to 50 PSI",
                    "instructions": (
                        "Connect GN2 supply via test fixture (KST-G-0005). Slowly pressurize "
                        "propellant circuit to 50 PSI. Hold 60 seconds."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Soap-Bubble Inspect All Joints",
                    "instructions": (
                        "Apply Snoop leak detector to every fitting, O-ring face, and "
                        "feedthrough. No bubbles permitted."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Depressurize and Remove Caps",
                    "instructions": (
                        "Slowly vent to 0 PSI. Remove all test caps. Disconnect GN2 supply."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Forward Bulkhead and Pressurant Routing",
            "instructions": (
                "Install forward bulkhead. Route recovery harness, vent lines, and "
                "pressurant feed through bulkhead penetrations."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install Forward Bulkhead O-Rings",
                    "instructions": (
                        "Lubricate 2x -016 O-rings with Krytox grease. Seat into forward "
                        "bulkhead (KST-F-0021) grooves."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Seat Forward Bulkhead",
                    "instructions": (
                        "Insert forward bulkhead into airframe tube. Align wire feedthrough "
                        "to 90 degree clock position. Press until O-rings engage."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Route Vent Lines Through Bulkhead",
                    "instructions": (
                        "Pass LOX and fuel vent lines through bulkhead AN fittings. Tighten "
                        "to 80 in-lb."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Bulkhead Retaining Ring",
                    "instructions": "Install and torque forward bulkhead retaining ring to 60 in-lb.",
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Route Recovery Harness",
                    "instructions": (
                        "Thread shock cord (KST-F-0035) through center feedthrough. Leave "
                        "24 inches of slack on recovery bay side."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Avionics Bay Integration",
            "instructions": "Install avionics sled into coupler section. Make all electrical connections.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Slide Avionics Sled into Coupler",
                    "instructions": (
                        "Insert avionics sled assembly into coupler tube (KST-F-0023). "
                        "Align mounting rails. Secure with 4x 10-32 SHCS."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Connect Pyro Leads",
                    "instructions": (
                        "Attach drogue pyro channel leads to forward separation joint "
                        "e-match terminals. Attach main pyro channel leads to aft separation "
                        "joint e-match terminals. Verify correct polarity per wiring diagram."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Connect Telemetry Antenna",
                    "instructions": (
                        "Route antenna coax from RFM95W to SMA bulkhead on coupler. Torque "
                        "SMA connector to 5 in-lb."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Connect Umbilical",
                    "instructions": (
                        "Route external umbilical connector (arming plug, charge cable) "
                        "through coupler access port. Verify connector seats fully."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Power-On Verification",
                    "instructions": (
                        "Connect battery (KST-F-0030). Verify flight computer boots, GPS "
                        "acquires, IMU initializes, telemetry transmits test packet to ground "
                        "station. Verify both pyro channels show continuity."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Power Off and Safe",
                    "instructions": (
                        "Power down flight computer. Disconnect battery. Install arming plug "
                        "safety cap."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Recovery Bay Pack",
            "instructions": "Pack parachutes into recovery section. Install ejection charges. Connect shock cords.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Attach Shock Cord to Forward U-Bolts",
                    "instructions": (
                        "Tie shock cord to 2x U-bolts (KST-F-0036) on forward bulkhead using "
                        "double-bowline knot. Apply 50 lbf pull test to each attachment."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Pack Drogue Parachute",
                    "instructions": (
                        "Place folded drogue (KST-F-0034) in deployment bag. Attach "
                        "deployment bag to shock cord with lark's head knot. Position drogue "
                        "at aft end of recovery bay."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Pack Main Parachute",
                    "instructions": (
                        "Place folded main chute (KST-F-0033) in deployment bag. Attach to "
                        "shock cord forward of drogue. Tuck deployment bag and shroud lines "
                        "neatly."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Ejection Charges",
                    "instructions": (
                        "Load 2.5g FFFFg black powder into drogue charge well. Load 4.0g "
                        "into main charge well. Install e-matches (KST-D-0038) into each "
                        "well. Tape leads along shock cord."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Verify Charge Continuity",
                    "instructions": (
                        "Using multimeter, verify continuity on both e-match circuits "
                        "before final close-out."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
            ],
        },
        {
            "title": "Section Mating and Shear Pins",
            "instructions": "Mate all airframe sections. Install shear pins at separation joints.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Install Aft Separation Joint Shear Pins",
                    "instructions": (
                        "Install 3x nylon shear pins (KST-F-0037) at 120 degree spacing "
                        "through airframe and coupler at aft separation joint. Pins should "
                        "sit flush."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Forward Separation Joint Shear Pins",
                    "instructions": (
                        "Install 3x nylon shear pins at 120 degree spacing through recovery "
                        "tube and coupler at forward separation joint."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Install Nose Cone",
                    "instructions": (
                        "Seat nose cone (KST-F-0019) onto recovery tube shoulder. Secure "
                        "with 2x nylon shear pins."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Verify All Sections Seated",
                    "instructions": (
                        "Visually confirm all coupler joints are fully engaged. No gaps at "
                        "any joint. Run a straight edge along airframe to check alignment."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Mate Avionics Bay to Propulsion Section",
                    "instructions": (
                        "Slide coupler section into propulsion airframe tube. Align antenna "
                        "port to 270 degrees clock position. Engage coupler 4 inches into "
                        "tube."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Mate Recovery Bay to Avionics Section",
                    "instructions": (
                        "Slide recovery bay airframe onto upper coupler. Engage coupler 4 "
                        "inches into recovery tube."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Fin and Rail Button Installation",
            "instructions": "Bond fins to airframe. Install rail buttons at CG and CP stations.",
            "duration": 5,
            "workcenter": "SHOP",
            "sub_steps": [
                {
                    "title": "Mark Fin Locations",
                    "instructions": (
                        "Using fin alignment jig, mark 3x fin root locations at 120 degree "
                        "spacing on aft airframe tube. Mark leading and trailing edge "
                        "references."
                    ),
                    "duration": 10,
                    "workcenter": "SHOP",
                },
                {
                    "title": "Surface Prep for Bonding",
                    "instructions": (
                        "Sand fin root edges and airframe bonding areas with 220-grit. "
                        "Clean with acetone. Allow to dry 10 minutes."
                    ),
                    "duration": 15,
                    "workcenter": "SHOP",
                },
                {
                    "title": "Bond Fins",
                    "instructions": (
                        "Mix 30-minute epoxy per manufacturer instructions. Apply fillet to "
                        "fin root. Press fin onto airframe in jig. Repeat for all 3 fins. "
                        "Allow cure per epoxy data sheet (minimum 12 hours)."
                    ),
                    "duration": 20,
                    "workcenter": "SHOP",
                    "requires_signoff": True,
                },
                {
                    "title": "Apply Fin Fillets",
                    "instructions": (
                        "After initial cure, apply secondary epoxy fillets on both sides of "
                        "each fin root. Smooth with gloved finger. Allow full cure."
                    ),
                    "duration": 15,
                    "workcenter": "SHOP",
                },
                {
                    "title": "Install Rail Buttons",
                    "instructions": (
                        "Install 2x rail buttons (KST-F-0024) with 8-32 SHCS. Lower button "
                        "at predicted CG station. Upper button at predicted CP station. "
                        "Torque to 15 in-lb."
                    ),
                    "duration": 10,
                    "workcenter": "SHOP",
                },
            ],
        },
        {
            "title": "Safety Wire and Lockout",
            "instructions": "Install safety wire on all critical fasteners. Verify all locking features are in place.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Safety Wire AN Propellant Fittings",
                    "instructions": (
                        "Install safety wire on LOX and fuel AN feed fittings. Wire to "
                        "adjacent structure attach point."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Verify All Lock Washers Compressed",
                    "instructions": (
                        "Inspect every lock washer in aft section. All must show visible "
                        "compression (flat, no spring gap)."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Photograph Safety Wire",
                    "instructions": "Take close-up photos of all safety wire runs. Include in build traveler.",
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Safety Wire Engine Mount Bolts",
                    "instructions": (
                        "Install 0.032 inch MS20995C stainless safety wire on engine mount "
                        "bolt pairs in positive-lock direction. Verify 6 to 8 twists per inch."
                    ),
                    "duration": 15,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Final Mass Properties and Inspection",
            "instructions": (
                "Weigh completed vehicle. Measure CG. Verify stability margin. Perform "
                "final visual inspection."
            ),
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Weigh Vehicle",
                    "instructions": (
                        "Place completed vehicle on calibrated scale. Record dry mass. "
                        "Compare to predicted mass, must be within plus or minus 5%."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "dry_mass_lb",
                                "type": "number",
                                "label": "Dry mass (lb)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Measure CG Location",
                    "instructions": "Balance vehicle on knife-edge. Mark CG location. Measure from nose tip.",
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "schema": {
                        "fields": [
                            {
                                "name": "cg_from_nose_in",
                                "type": "number",
                                "label": "CG from nose tip (in)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "title": "Calculate Static Margin",
                    "instructions": (
                        "Static margin = (CP - CG) / body diameter. Must be at least 1.5 "
                        "calibers for flight acceptance."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Final Visual Inspection",
                    "instructions": (
                        "Inspect entire vehicle exterior: no dents, cracks, loose fins, "
                        "protruding fasteners, or FOD. Verify all access ports closed. Check "
                        "paint/markings per drawing."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Photograph Completed Vehicle",
                    "instructions": (
                        "Take 6 photographs: fore, aft, left, right, top (fins), detail of "
                        "nose cone. Include scale reference and SN placard in frame."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
            ],
        },
        {
            "title": "Closeout and Documentation",
            "instructions": "Complete all build records. Transfer vehicle to storage or launch prep.",
            "duration": 5,
            "workcenter": "CLEAN",
            "sub_steps": [
                {
                    "title": "Complete Build Traveler",
                    "instructions": (
                        "Fill in all remaining fields on build traveler. Attach all data "
                        "sheets, photos, and test records. Verify no open items."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Log All Serial Numbers",
                    "instructions": (
                        "Record serial/lot numbers for all installed components, O-rings, "
                        "fastener lots, and epoxy batch. Enter into OPAL inventory system."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
                {
                    "title": "Vehicle Acceptance Sign-Off",
                    "instructions": (
                        "Build lead and QA inspector sign off that vehicle is complete, all "
                        "steps passed, and vehicle is ready for launch operations."
                    ),
                    "duration": 5,
                    "workcenter": "CLEAN",
                    "requires_signoff": True,
                },
                {
                    "title": "Transfer to Storage",
                    "instructions": (
                        "Install protective nose cone cover and fin guards. Place vehicle "
                        "in padded transport case. Move to bonded storage area. Update OPAL "
                        "location."
                    ),
                    "duration": 10,
                    "workcenter": "CLEAN",
                },
            ],
        },
    ]
    _add_op_tree(db, fvi.id, wc, _fvi_ops)

    return procs


# ---------------------------------------------------------------------------
# Versions & Executions
# ---------------------------------------------------------------------------


def _seed_versions_and_executions(
    db: Session,
    procs: dict[str, MasterProcedure],
) -> None:
    now = datetime.now(UTC)

    # Publish versions for active procedures
    for proc_key in ("eng_build", "hydro", "hotfire", "recovery"):
        proc = procs[proc_key]
        steps = (
            db.query(ProcedureStep)
            .filter(
                ProcedureStep.procedure_id == proc.id,
            )
            .order_by(ProcedureStep.order)
            .all()
        )

        content = {
            "procedure_name": proc.name,
            "procedure_description": proc.description,
            "steps": [
                {
                    "id": s.id,
                    "order": s.order,
                    "step_number": s.step_number,
                    "level": s.level,
                    "parent_step_id": s.parent_step_id,
                    "title": s.title,
                    "instructions": s.instructions,
                    "required_data_schema": s.required_data_schema,
                    "is_contingency": s.is_contingency,
                    "requires_signoff": s.requires_signoff,
                    "estimated_duration_minutes": s.estimated_duration_minutes,
                    "workcenter_id": s.workcenter_id,
                    "depends_on": [],
                    "step_kit": [],
                }
                for s in steps
            ],
            "kit_items": [
                {"part_id": k.part_id, "quantity_required": float(k.quantity_required)}
                for k in db.query(Kit).filter(Kit.procedure_id == proc.id).all()
            ],
            "output_items": [
                {"part_id": o.part_id, "quantity_produced": float(o.quantity_produced)}
                for o in db.query(ProcedureOutput)
                .filter(ProcedureOutput.procedure_id == proc.id)
                .all()
            ],
        }

        version = ProcedureVersion(
            procedure_id=proc.id,
            version_number=1,
            content=content,
        )
        db.add(version)
        db.flush()
        proc.current_version_id = version.id

        # Create executions for hydro (completed) and hotfire (in-progress)
        if proc_key == "hydro":
            inst = ProcedureInstance(
                procedure_id=proc.id,
                version_id=version.id,
                work_order_number=generate_work_order_number(db),
                status=InstanceStatus.COMPLETED,
                started_at=now - timedelta(days=10, hours=3),
                completed_at=now - timedelta(days=10, hours=1),
            )
            db.add(inst)
            db.flush()

            # All steps completed
            for s in content["steps"]:
                se = StepExecution(
                    instance_id=inst.id,
                    step_number=s["order"],
                    step_number_str=s["step_number"],
                    level=s["level"],
                    status=StepStatus.SIGNED_OFF if s["requires_signoff"] else StepStatus.COMPLETED,
                    started_at=now
                    - timedelta(days=10, hours=3)
                    + timedelta(minutes=s["order"] * 8),
                    completed_at=now
                    - timedelta(days=10, hours=3)
                    + timedelta(minutes=s["order"] * 8 + 7),
                )
                if s["required_data_schema"] and s["step_number"] == "5.1":
                    se.data_captured = {"proof_pressure": 677, "hold_duration_s": 305}
                elif s["required_data_schema"] and s["step_number"] == "6.2":
                    se.data_captured = {
                        "od_station_1": 6.001,
                        "od_station_2": 6.000,
                        "od_station_3": 6.001,
                    }
                db.add(se)

        elif proc_key == "hotfire":
            inst = ProcedureInstance(
                procedure_id=proc.id,
                version_id=version.id,
                work_order_number=generate_work_order_number(db),
                status=InstanceStatus.IN_PROGRESS,
                started_at=now - timedelta(hours=2),
                priority=1,
            )
            db.add(inst)
            db.flush()

            # Pre-test planning, engine install, and plumbing complete (orders 1-12).
            # On instrumentation hookup (order 13).
            for s in content["steps"]:
                if s["order"] <= 12:
                    se = StepExecution(
                        instance_id=inst.id,
                        step_number=s["order"],
                        step_number_str=s["step_number"],
                        level=s["level"],
                        status=StepStatus.SIGNED_OFF
                        if s["requires_signoff"]
                        else StepStatus.COMPLETED,
                        started_at=now - timedelta(hours=2) + timedelta(minutes=s["order"] * 5),
                        completed_at=now
                        - timedelta(hours=2)
                        + timedelta(minutes=s["order"] * 5 + 4),
                    )
                    db.add(se)
                elif s["order"] == 13:
                    se = StepExecution(
                        instance_id=inst.id,
                        step_number=s["order"],
                        step_number_str=s["step_number"],
                        level=s["level"],
                        status=StepStatus.IN_PROGRESS,
                        started_at=now - timedelta(minutes=15),
                    )
                    db.add(se)
                else:
                    se = StepExecution(
                        instance_id=inst.id,
                        step_number=s["order"],
                        step_number_str=s["step_number"],
                        level=s["level"],
                        status=StepStatus.PENDING,
                    )
                    db.add(se)

    db.flush()


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------


def _seed_purchases(
    db: Session,
    p: dict[str, Part],
    suppliers: dict[str, Supplier],
) -> None:
    now = datetime.now(UTC)

    # PO-0001 McMaster — received
    po1 = Purchase(
        reference="PO-0001",
        supplier="McMaster-Carr",
        supplier_id=suppliers["McMaster-Carr"].id,
        status=PurchaseStatus.RECEIVED,
        ordered_at=now - timedelta(days=30),
        received_at=now - timedelta(days=27),
        destination="STORE",
        notes="Initial fastener and plumbing stock-up",
    )
    db.add(po1)
    db.flush()
    for part_key, qty, cost in [
        ("shcs_quarter", 200, Decimal("0.18")),
        ("shcs_10_32", 150, Decimal("0.14")),
        ("hex_nut_quarter", 200, Decimal("0.08")),
        ("lock_washer_quarter", 200, Decimal("0.06")),
        ("oring_012", 50, Decimal("0.45")),
        ("oring_016", 50, Decimal("0.52")),
        ("oring_116", 25, Decimal("1.85")),
        ("tube_half", 24, Decimal("8.50")),
        ("tube_quarter", 18, Decimal("5.20")),
        ("an_fitting_half", 12, Decimal("12.40")),
        ("an_fitting_quarter", 16, Decimal("8.90")),
        ("shear_pin", 100, Decimal("0.03")),
        ("rail_button", 8, Decimal("2.15")),
        ("ubolt", 6, Decimal("3.80")),
        ("teflon_tape", 5, Decimal("2.50")),
    ]:
        db.add(
            PurchaseLine(
                purchase_id=po1.id,
                part_id=p[part_key].id,
                qty_ordered=Decimal(str(qty)),
                qty_received=Decimal(str(qty)),
                unit_cost=cost,
            )
        )

    # PO-0002 Swagelok — partial (QD outstanding)
    po2 = Purchase(
        reference="PO-0002",
        supplier="Swagelok",
        supplier_id=suppliers["Swagelok"].id,
        status=PurchaseStatus.PARTIAL,
        ordered_at=now - timedelta(days=45),
        target_date=(now + timedelta(days=7)).date(),
        destination="STORE-B1",
        notes="Valves and fittings. QD on backorder.",
    )
    db.add(po2)
    db.flush()
    db.add(
        PurchaseLine(
            purchase_id=po2.id,
            part_id=p["lox_valve"].id,
            qty_ordered=Decimal("1"),
            qty_received=Decimal("1"),
            unit_cost=Decimal("245.00"),
        )
    )
    db.add(
        PurchaseLine(
            purchase_id=po2.id,
            part_id=p["fuel_valve"].id,
            qty_ordered=Decimal("1"),
            qty_received=Decimal("1"),
            unit_cost=Decimal("245.00"),
        )
    )
    db.add(
        PurchaseLine(
            purchase_id=po2.id,
            part_id=p["check_valve"].id,
            qty_ordered=Decimal("4"),
            qty_received=Decimal("4"),
            unit_cost=Decimal("68.00"),
        )
    )
    db.add(
        PurchaseLine(
            purchase_id=po2.id,
            part_id=p["umbilical_qd"].id,
            qty_ordered=Decimal("2"),
            qty_received=Decimal("0"),
            unit_cost=Decimal("185.00"),
            notes="Backordered — expected ship date 2026-03-28",
        )
    )
    db.add(
        PurchaseLine(
            purchase_id=po2.id,
            part_id=p["ground_reg"].id,
            qty_ordered=Decimal("1"),
            qty_received=Decimal("1"),
            unit_cost=Decimal("420.00"),
        )
    )

    # PO-0003 Digi-Key — received
    po3 = Purchase(
        reference="PO-0003",
        supplier="Digi-Key",
        supplier_id=suppliers["Digi-Key"].id,
        status=PurchaseStatus.RECEIVED,
        ordered_at=now - timedelta(days=21),
        received_at=now - timedelta(days=18),
        destination="LAB",
    )
    db.add(po3)
    db.flush()
    for part_key, qty, cost in [
        ("fc", 2, Decimal("32.95")),
        ("gps", 2, Decimal("18.50")),
        ("imu", 2, Decimal("28.00")),
        ("altimeter", 3, Decimal("12.40")),
        ("radio", 2, Decimal("15.95")),
        ("lipo", 4, Decimal("14.00")),
        ("pyro_board", 2, Decimal("8.50")),
    ]:
        db.add(
            PurchaseLine(
                purchase_id=po3.id,
                part_id=p[part_key].id,
                qty_ordered=Decimal(str(qty)),
                qty_received=Decimal(str(qty)),
                unit_cost=cost,
            )
        )

    # PO-0004 Metal Supermarkets — ordered, awaiting
    po4 = Purchase(
        reference="PO-0004",
        supplier="Metal Supermarkets",
        supplier_id=suppliers["Metal Supermarkets"].id,
        status=PurchaseStatus.ORDERED,
        ordered_at=now - timedelta(days=5),
        target_date=(now + timedelta(days=10)).date(),
        destination="STORE-E1",
        notes="Stock for tank and bulkhead fabrication",
    )
    db.add(po4)
    db.flush()
    db.add(
        PurchaseLine(
            purchase_id=po4.id,
            part_id=p["al_plate"].id,
            qty_ordered=Decimal("8"),
            qty_received=Decimal("0"),
            unit_cost=Decimal("45.00"),
        )
    )
    db.add(
        PurchaseLine(
            purchase_id=po4.id,
            part_id=p["ss_sheet"].id,
            qty_ordered=Decimal("4"),
            qty_received=Decimal("0"),
            unit_cost=Decimal("62.00"),
        )
    )
    db.add(
        PurchaseLine(
            purchase_id=po4.id,
            part_id=p["al_round"].id,
            qty_ordered=Decimal("6"),
            qty_received=Decimal("0"),
            unit_cost=Decimal("38.00"),
        )
    )

    db.flush()


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


def _seed_issues(
    db: Session,
    p: dict[str, Part],
    procs: dict[str, MasterProcedure],
) -> None:
    # ── Non-Conformances ────────────────────────────────────────

    nc1 = Issue(
        issue_number=generate_issue_number(db),
        title="Injector plate hole pattern out of tolerance",
        description='During QA inspection, bolt circle measured 0.005" outside tolerance.',
        issue_type=IssueType.NON_CONFORMANCE,
        status=IssueStatus.INVESTIGATING,
        priority=IssuePriority.HIGH,
        part_id=p["injector"].id,
        should_be='32x 0.040" holes on 1.500" bolt circle ±0.002"',
        is_condition='Holes measured at 1.505" bolt circle — 0.005" outside tolerance on 3 of 4 quadrants',
    )
    db.add(nc1)
    db.flush()

    nc2 = Issue(
        issue_number=generate_issue_number(db),
        title="LOX tank circumferential weld porosity",
        description="Radiographic inspection revealed pores in weld at station 14.",
        issue_type=IssueType.NON_CONFORMANCE,
        status=IssueStatus.DISPOSITION_PENDING,
        priority=IssuePriority.CRITICAL,
        part_id=p["lox_tank"].id,
        should_be="Full-penetration weld with no porosity per AWS D17.1 Class A",
        is_condition="Three pores detected: 0.8 mm, 0.6 mm, 0.5 mm in circumferential weld at station 14. Total aggregate porosity exceeds Class A limit.",
    )
    db.add(nc2)

    nc3 = Issue(
        issue_number=generate_issue_number(db),
        title="Aft bulkhead O-ring groove surface finish",
        description="Surface finish on aft bulkhead bore exceeds specification.",
        issue_type=IssueType.NON_CONFORMANCE,
        status=IssueStatus.OPEN,
        priority=IssuePriority.MEDIUM,
        part_id=p["bulkhead_aft"].id,
        should_be="16 µin Ra max per AS568 gland specification for static radial seal",
        is_condition="Profilometer measured 32 µin Ra on aft bulkhead bore — 2x allowable roughness",
    )
    db.add(nc3)

    nc4 = Issue(
        issue_number=generate_issue_number(db),
        title="Pressurant regulator external leak at set pressure",
        description="Bubble test shows leak at outlet fitting when regulator is at setpoint.",
        issue_type=IssueType.NON_CONFORMANCE,
        status=IssueStatus.OPEN,
        priority=IssuePriority.HIGH,
        part_id=p["ground_reg"].id,
        should_be="Regulate to 450 PSI ±10 PSI with zero external leakage",
        is_condition="Bubble test shows steady stream at outlet NPT fitting at 400 PSI. Leak rate ~5 cc/min.",
    )
    db.add(nc4)

    # ── Bugs ────────────────────────────────────────────────────

    bug1 = Issue(
        issue_number=generate_issue_number(db),
        title="Flight computer resets during pyro channel firing",
        description="FC reboots when e-match is fired on either pyro channel.",
        issue_type=IssueType.BUG,
        status=IssueStatus.INVESTIGATING,
        priority=IssuePriority.HIGH,
        part_id=p["fc"].id,
        steps_to_reproduce="1. Power on flight computer via LiPo\n2. Arm both pyro channels via software command\n3. Fire channel 1 e-match\n4. Observe FC status LED and telemetry stream",
        expected_behavior="FC maintains operation, logs firing event timestamp and channel ID, telemetry stream uninterrupted",
        actual_behavior="FC resets to boot screen immediately on firing. Telemetry drops for 3 seconds. No firing event logged. Behavior is 100% reproducible on both channels.",
    )
    db.add(bug1)
    db.flush()

    bug2 = Issue(
        issue_number=generate_issue_number(db),
        title="GPS cold lock exceeds 5 min in vertical orientation",
        description="GPS acquisition time dramatically worse when avionics sled is mounted vertically (flight orientation).",
        issue_type=IssueType.BUG,
        status=IssueStatus.OPEN,
        priority=IssuePriority.MEDIUM,
        part_id=p["gps"].id,
        steps_to_reproduce="1. Mount avionics sled in vertical orientation (flight config)\n2. Power on outdoors with clear sky view\n3. Monitor NMEA stream for fix quality indicator\n4. Record time to first 3D fix",
        expected_behavior="GPS 3D lock within 60 seconds (horizontal baseline with same antenna: 15 seconds typical)",
        actual_behavior="Lock takes 5-8 minutes in vertical orientation. Occasionally fails to acquire within 10-minute timeout. Suspect antenna ground plane effect.",
    )
    db.add(bug2)

    bug3 = Issue(
        issue_number=generate_issue_number(db),
        title="Telemetry packet CRC errors above 500 m range",
        description="Packet loss exceeds link budget prediction at relatively short range.",
        issue_type=IssueType.BUG,
        status=IssueStatus.OPEN,
        priority=IssuePriority.MEDIUM,
        part_id=p["radio"].id,
        steps_to_reproduce="1. Set up ground station at pad with directional antenna\n2. Mount flight transmitter on drone\n3. Fly drone to 500 m slant range, then 1 km\n4. Log packet reception rate and CRC error count",
        expected_behavior="<1% packet loss to 2 km slant range per link budget (SF7, BW125, +20 dBm, 6 dBi ground antenna)",
        actual_behavior="12% CRC errors at 500 m, 40% at 1 km. Ground station RSSI suggests adequate signal — likely interference or impedance mismatch at SMA bulkhead.",
    )
    db.add(bug3)

    # ── Tasks ───────────────────────────────────────────────────

    task1 = Issue(
        issue_number=generate_issue_number(db),
        title="Order replacement LOX-compatible O-rings (Viton -116)",
        description="Current Buna-N -116 O-rings are not LOX-compatible. Need Viton (fluoroelastomer) replacements for all LOX-wetted seals.",
        issue_type=IssueType.TASK,
        status=IssueStatus.OPEN,
        priority=IssuePriority.HIGH,
    )
    db.add(task1)

    task2 = Issue(
        issue_number=generate_issue_number(db),
        title="Machine new injector plate with corrected hole pattern",
        description='Remake injector from 304 SS stock with corrected bolt circle diameter (1.500" ±0.002"). Use CNC for hole pattern.',
        issue_type=IssueType.TASK,
        status=IssueStatus.OPEN,
        priority=IssuePriority.HIGH,
        part_id=p["injector"].id,
    )
    db.add(task2)

    task3 = Issue(
        issue_number=generate_issue_number(db),
        title="Write pre-launch checklist procedure",
        description="Create formal procedure covering all launch-day activities: range setup, vehicle prep, propellant loading, countdown, and safing.",
        issue_type=IssueType.TASK,
        status=IssueStatus.OPEN,
        priority=IssuePriority.MEDIUM,
    )
    db.add(task3)

    # ── Improvements ────────────────────────────────────────────

    imp1 = Issue(
        issue_number=generate_issue_number(db),
        title="Add redundant barometric altimeter for recovery",
        description="Single MS5611 is a single point of failure for apogee detection and recovery deployment.",
        issue_type=IssueType.IMPROVEMENT,
        status=IssueStatus.OPEN,
        priority=IssuePriority.MEDIUM,
        part_id=p["altimeter"].id,
        expected_benefit="Dual-sensor voting eliminates single-point failure for apogee detection. If primary altimeter fails, backup independently triggers recovery events. Required to meet REQ-004 (dual-event recovery with redundant altimeters).",
    )
    db.add(imp1)

    imp2 = Issue(
        issue_number=generate_issue_number(db),
        title="Replace e-match igniters with electronic igniters",
        description="E-matches require pyrotechnic handling during pad operations. Electronic (resistive) igniters would simplify pad procedures.",
        issue_type=IssueType.IMPROVEMENT,
        status=IssueStatus.OPEN,
        priority=IssuePriority.LOW,
        expected_benefit="Eliminates pyrotechnic handling during pad operations. Enables remote re-arm capability without approaching vehicle. Reduces hazmat paperwork for launch site operations.",
    )
    db.add(imp2)

    db.flush()

    # ── Issue Comments ──────────────────────────────────────────

    db.add(
        IssueComment(
            issue_id=nc1.id,
            body="Measured all 32 holes with pin gauges. Hole diameters are within spec — only the bolt circle is off. Likely a fixture alignment issue on the rotary table.",
        )
    )
    db.add(
        IssueComment(
            issue_id=nc1.id,
            body="Checked the G-code. Origin offset was set to X0.0025 Y0.0000 instead of X0.0000 Y0.0000. That explains the radial shift. CNC program has been corrected for the remake.",
        )
    )

    db.add(
        IssueComment(
            issue_id=bug1.id,
            body="Scope trace on Vcc rail shows a 1.2V dip lasting ~500 µs coincident with e-match firing. The MOSFET inrush is pulling the rail below the Teensy's brownout threshold (2.7V). Need a bigger bulk cap on the pyro board or separate battery for pyro.",
        )
    )
    db.add(
        IssueComment(
            issue_id=bug1.id,
            body="Added 2200 µF low-ESR cap to pyro board Vcc input. Dip reduced to 0.3V — FC stays up now. Will retest with both channels firing simultaneously before closing.",
        )
    )

    db.add(
        IssueComment(
            issue_id=nc2.id,
            body="Sent X-ray images to welding consultant. Recommendation: grind out affected area and re-weld, then re-inspect. Alternatively, could accept with stress analysis showing adequate margin at reduced section.",
        )
    )

    db.flush()


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


def _seed_risks(db: Session) -> None:
    risks = [
        Risk(
            risk_number=generate_risk_number(db),
            title="LOX compatibility failure",
            description="Material in LOX-wetted path ignites or degrades on contact with liquid oxygen, causing fire or contamination.",
            status=RiskStatus.MITIGATING,
            probability=3,
            impact=5,
            mitigation_plan="1. Review all wetted materials against MSFC-SPEC-106B.\n2. Replace any non-compatible materials (e.g., Buna-N O-rings → Viton).\n3. Oxygen-clean all LOX-side components per CGA G-4.1.\n4. Perform LOX drop-impact test on any questionable materials.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Recovery deployment failure",
            description="Parachute fails to deploy at apogee or main deploy altitude, resulting in ballistic impact.",
            status=RiskStatus.MONITORING,
            probability=2,
            impact=5,
            mitigation_plan="1. Dual-event recovery (drogue + main) with independent altimeters.\n2. Ground-test ejection charges with flight-weight hardware.\n3. Verify continuity before every flight.\n4. Redundant altimeter triggers both events independently.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Engine hard start / overpressure",
            description="Propellant accumulation in chamber before ignition causes deflagration-to-detonation event (hard start).",
            status=RiskStatus.MITIGATING,
            probability=2,
            impact=5,
            mitigation_plan="1. LOX-lead ignition sequence (oxidizer before fuel).\n2. Verified igniter reliability — 10/10 ground tests.\n3. Pressure relief valve on chamber (set to 1.5x MEOP).\n4. Remote operation with 500 ft minimum safe distance.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Avionics power loss during flight",
            description="LiPo battery failure or wiring fault causes total avionics blackout during flight.",
            status=RiskStatus.ANALYZING,
            probability=2,
            impact=4,
            mitigation_plan="1. Pre-flight voltage check under load.\n2. Strain-relieve all connectors.\n3. Consider adding independent backup battery for recovery altimeter.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Schedule slip past launch window",
            description="Delays in fabrication or testing cause the project to miss the target launch date and site reservation.",
            status=RiskStatus.IDENTIFIED,
            probability=4,
            impact=3,
            mitigation_plan="1. Identify critical path items (engine assembly, hot fire test).\n2. Order long-lead items early (Swagelok QD already on backorder).\n3. Maintain schedule buffer for re-work.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Propellant handling safety incident",
            description="Personnel injury during LOX or ethanol handling operations.",
            status=RiskStatus.MONITORING,
            probability=1,
            impact=5,
            mitigation_plan="1. Written propellant handling procedures with safety briefing.\n2. PPE: face shield, cryogenic gloves, long sleeves for LOX.\n3. Fire extinguisher and first aid kit at pad.\n4. Minimum 2 persons for any propellant operation.",
        ),
    ]
    db.add_all(risks)
    db.flush()


# ---------------------------------------------------------------------------
# Test Templates
# ---------------------------------------------------------------------------


def _seed_test_templates(db: Session, p: dict[str, Part]) -> None:
    templates = [
        TestTemplate(
            part_id=p["chamber"].id,
            name="Hydrostatic Proof Test",
            description="Pressurize to 1.5x MEOP (675 PSI) with water. Hold 5 min. No leaks or permanent deformation.",
            required=True,
            test_type="numeric",
            min_value=Decimal("675"),
            max_value=Decimal("750"),
            unit="PSI",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["lox_tank"].id,
            name="Hydrostatic Proof Test",
            description="Pressurize to 750 PSI (1.5x 500 PSI MEOP) with water. Hold 5 min.",
            required=True,
            test_type="numeric",
            min_value=Decimal("750"),
            max_value=Decimal("800"),
            unit="PSI",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["fuel_tank"].id,
            name="Hydrostatic Proof Test",
            description="Pressurize to 750 PSI (1.5x 500 PSI MEOP) with water. Hold 5 min.",
            required=True,
            test_type="numeric",
            min_value=Decimal("750"),
            max_value=Decimal("800"),
            unit="PSI",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["engine_assy"].id,
            name="Leak Check — Low Pressure",
            description="Pressurize assembled engine to 50 PSI with N2. Soap-bubble all joints. No bubbles for 60 seconds.",
            required=True,
            test_type="boolean",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["lox_valve"].id,
            name="Seat Leak Test",
            description="Pressurize upstream to 500 PSI with N2, valve closed. Measure downstream leak rate.",
            required=True,
            test_type="boolean",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["fuel_valve"].id,
            name="Seat Leak Test",
            description="Pressurize upstream to 500 PSI with N2, valve closed. Measure downstream leak rate.",
            required=True,
            test_type="boolean",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["ematch"].id,
            name="Continuity Check",
            description="Measure e-match bridgewire resistance. Must be within 0.5-5.0 Ω for reliable firing.",
            required=True,
            test_type="numeric",
            min_value=Decimal("0.5"),
            max_value=Decimal("5.0"),
            unit="Ω",
            sort_order=1,
        ),
        TestTemplate(
            part_id=p["pyro_board"].id,
            name="Isolation Test",
            description="Measure resistance between pyro power rail and logic power rail. Must exceed 10 MΩ.",
            required=True,
            test_type="numeric",
            min_value=Decimal("10000000"),
            max_value=None,
            unit="Ω",
            sort_order=1,
        ),
    ]
    db.add_all(templates)
    db.flush()
