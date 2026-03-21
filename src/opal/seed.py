"""Seed data for Project Kestrel — LOX/ethanol pressure-fed sounding rocket."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
    StepKit,
    Supplier,
    TestTemplate,
    Workcenter,
)
from opal.db.models.execution import InstanceStatus, StepStatus
from opal.db.models.inventory import InventoryRecord, SourceType
from opal.db.models.issue import IssuePriority, IssueStatus, IssueType
from opal.db.models.procedure import ProcedureStatus, ProcedureType, UsageType
from opal.db.models.purchase import PurchaseStatus
from opal.db.models.risk import RiskStatus


def seed_database(db: Session) -> None:
    """Populate database with Project Kestrel seed data."""
    _write_project_yaml()
    workcenters = _seed_workcenters(db)
    suppliers = _seed_suppliers(db)
    parts = _seed_parts(db)
    _seed_bom(db, parts)
    _seed_part_requirements(db, parts)
    inventory = _seed_inventory(db, parts)
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
        Workcenter(code="SHOP", name="Machine Shop", description="Mill, lathe, welding, fabrication"),
        Workcenter(code="CLEAN", name="Clean Room", description="Assembly bench, LOX-clean work"),
        Workcenter(code="PAD", name="Test Pad", description="Static fire stand and launch rail"),
        Workcenter(code="LAB", name="Electronics Lab", description="Soldering, programming, avionics assembly"),
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
        key: str, ipn: str, name: str, *,
        category: str, tier: int = 1, tracking: str = "serialized",
        epn: str | None = None, desc: str | None = None,
        uom: str = "ea", parent_key: str | None = None,
        reorder: float | None = None, is_tooling: bool = False,
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
    _add("engine_assy", "KST-F-0001", "Engine Assembly",
         category="Propulsion", desc="Complete engine: chamber, injector, nozzle, igniter")
    _add("chamber", "KST-F-0002", "Combustion Chamber",
         category="Propulsion", desc="6061-T6 aluminum chamber, 450 PSI MEOP",
         parent_key="engine_assy")
    _add("injector", "KST-F-0003", "Injector Plate",
         category="Propulsion", desc="304 SS, 32-element showerhead pattern",
         parent_key="engine_assy")
    _add("nozzle", "KST-F-0004", "Nozzle",
         category="Propulsion", desc="Copper-lined graphite, 4:1 expansion ratio",
         parent_key="engine_assy")
    _add("igniter", "KST-F-0005", "Igniter Assembly",
         category="Propulsion", desc="Pyrotechnic torch igniter with e-match",
         parent_key="engine_assy")
    _add("lox_tank", "KST-F-0006", "LOX Tank",
         category="Propulsion", desc="6061-T6 welded tank, 500 PSI MEOP, 2.5 gal capacity")
    _add("fuel_tank", "KST-F-0007", "Fuel Tank",
         category="Propulsion", desc="6061-T6 welded tank, 500 PSI MEOP, 3.0 gal capacity")
    _add("press_tank", "KST-F-0008", "Pressurant Tank (N2)",
         category="Propulsion", desc="COTS nitrogen bottle, 3000 PSI rated")

    # ── Plumbing ────────────────────────────────────────────────
    _add("lox_valve", "KST-F-0009", "Main LOX Valve",
         category="Plumbing", desc="Swagelok SS-63TS8 ball valve, 1/2\" tube",
         epn="SS-63TS8")
    _add("fuel_valve", "KST-F-0010", "Main Fuel Valve",
         category="Plumbing", desc="Swagelok SS-63TS8 ball valve, 1/2\" tube",
         epn="SS-63TS8")
    _add("check_valve", "KST-F-0011", "Check Valve, 1/4\" SS",
         category="Plumbing", tracking="bulk", epn="4888K11",
         desc="McMaster 4888K11 — 1/4\" tube, 3000 PSI, cracking pressure 1/3 PSI",
         reorder=4)
    _add("relief_valve", "KST-F-0012", "Pressure Relief Valve, 500 PSI",
         category="Plumbing", epn="48435K41",
         desc="McMaster 48435K41 — adjustable, 1/4\" NPT, brass body")
    _add("tube_half", "KST-F-0013", "SS Tube, 1/2\" OD x 0.035\" Wall",
         category="Plumbing", tracking="bulk", uom="ft", epn="89895K427",
         desc="McMaster 89895K427 — 304 SS, seamless, ASTM A269",
         reorder=10)
    _add("tube_quarter", "KST-F-0014", "SS Tube, 1/4\" OD x 0.035\" Wall",
         category="Plumbing", tracking="bulk", uom="ft", epn="89895K217",
         desc="McMaster 89895K217 — 304 SS, seamless",
         reorder=10)
    _add("an_fitting_half", "KST-F-0015", "AN Flare Fitting, 1/2\" Tube",
         category="Plumbing", tracking="bulk", epn="5182K18",
         desc="McMaster 5182K18 — 37° flare, 316 SS",
         reorder=8)
    _add("an_fitting_quarter", "KST-F-0016", "AN Flare Fitting, 1/4\" Tube",
         category="Plumbing", tracking="bulk", epn="5182K14",
         desc="McMaster 5182K14 — 37° flare, 316 SS",
         reorder=8)
    _add("teflon_tape", "KST-D-0017", "Teflon Tape, 1/2\" x 260\"",
         category="Consumables", tier=3, tracking="bulk", epn="6802A13",
         desc="McMaster 6802A13 — PTFE thread seal tape",
         reorder=3)

    # ── Structures ──────────────────────────────────────────────
    _add("airframe", "KST-F-0018", "Airframe Tube, 6\" OD x 48\"",
         category="Structures", desc="6061-T6 drawn tube, 0.065\" wall")
    _add("nosecone", "KST-F-0019", "Nose Cone, 6\" 4:1 Ogive",
         category="Structures", desc="Fiberglass, 24\" length, aluminum tip")
    _add("fin_set", "KST-F-0020", "Fin Set (3x)",
         category="Structures", desc="6061-T6 sheet, 0.125\" thick, clipped delta planform")
    _add("bulkhead_fwd", "KST-F-0021", "Bulkhead, Forward",
         category="Structures", desc="6061-T6 plate, 6\" OD, O-ring sealed, recovery harness attach")
    _add("bulkhead_aft", "KST-F-0022", "Bulkhead, Aft",
         category="Structures", desc="6061-T6 plate, 6\" OD, engine mount interface, feedthrough ports")
    _add("coupler", "KST-F-0023", "Coupler Tube, 6\" ID x 8\"",
         category="Structures", desc="6061-T6, connects airframe sections, shear-pinned for separation")
    _add("rail_button", "KST-F-0024", "Rail Button, 1515",
         category="Structures", tracking="bulk", epn="97395A430",
         desc="McMaster 97395A430 — Delrin, 1/4\"-20 thread",
         reorder=6)

    # ── Avionics ────────────────────────────────────────────────
    _add("fc", "KST-F-0025", "Flight Computer",
         category="Avionics", desc="Custom PCB — Teensy 4.1, data logging, dual pyro channels")
    _add("gps", "KST-F-0026", "GPS Module, u-blox MAX-M10S",
         category="Avionics", epn="MAX-M10S",
         desc="10 Hz update, SAW/LNA, active antenna connector")
    _add("imu", "KST-F-0027", "IMU, Bosch BNO055",
         category="Avionics", epn="BNO055",
         desc="9-DOF absolute orientation sensor, I2C, sensor fusion onboard")
    _add("altimeter", "KST-F-0028", "Barometric Altimeter, MS5611",
         category="Avionics", epn="MS5611",
         desc="24-bit ADC, 10 cm resolution, SPI/I2C")
    _add("radio", "KST-F-0029", "Telemetry Radio, RFM95W 915 MHz",
         category="Avionics", epn="RFM95W",
         desc="LoRa spread spectrum, +20 dBm, SPI interface")
    _add("lipo", "KST-F-0030", "Battery, LiPo 2S 1000 mAh",
         category="Avionics", tracking="bulk",
         desc="7.4V nominal, JST-XH balance connector, 20C discharge",
         reorder=2)
    _add("harness", "KST-F-0031", "Wiring Harness, Avionics Bay",
         category="Avionics", desc="Point-to-point harness: FC, sensors, pyro, antenna, battery")
    _add("pyro_board", "KST-F-0032", "Pyro Channel Board",
         category="Avionics", desc="Dual MOSFET e-match firing circuit, optoisolated, LED-armed indicator")

    # ── Recovery ────────────────────────────────────────────────
    _add("main_chute", "KST-F-0033", "Main Parachute, 48\" Cruciform",
         category="Recovery", desc="Ripstop nylon, 12 lb max descent load, Vd ≈ 18 ft/s")
    _add("drogue", "KST-F-0034", "Drogue Parachute, 18\" Hemispherical",
         category="Recovery", desc="Ripstop nylon, stabilizes descent to ~80 ft/s")
    _add("shock_cord", "KST-F-0035", "Shock Cord, 1/2\" Tubular Nylon",
         category="Recovery", tracking="bulk", uom="ft",
         desc="1500 lb rated, 20 ft working length",
         reorder=25)
    _add("ubolt", "KST-F-0036", "U-Bolt, 1/4\"-20 x 1-1/2\" Span",
         category="Recovery", tracking="bulk", epn="3042T14",
         desc="McMaster 3042T14 — forged steel, zinc-plated",
         reorder=4)
    _add("shear_pin", "KST-F-0037", "Shear Pin, 2-56 Nylon",
         category="Recovery", tracking="bulk", epn="90207A004",
         desc="McMaster 90207A004 — nylon 6/6, calibrated shear for separation charge",
         reorder=50)
    _add("ematch", "KST-D-0038", "E-Match, J-Tek",
         category="Recovery", tier=3, tracking="bulk",
         desc="Electric match, 1A/1W no-fire, bridgewire igniter for ejection charges",
         reorder=10)

    # ── Fasteners ───────────────────────────────────────────────
    _add("shcs_quarter", "KST-D-0039", "SHCS 1/4\"-20 x 1\", 18-8 SS",
         category="Fasteners", tier=3, tracking="bulk", epn="91251A542",
         desc="McMaster 91251A542 — socket head cap screw, fully threaded",
         reorder=50)
    _add("shcs_10_32", "KST-D-0040", "SHCS 10-32 x 3/4\", 18-8 SS",
         category="Fasteners", tier=3, tracking="bulk", epn="91251A320",
         desc="McMaster 91251A320 — socket head cap screw, fully threaded",
         reorder=50)
    _add("hex_nut_quarter", "KST-D-0041", "Hex Nut, 1/4\"-20, 18-8 SS",
         category="Fasteners", tier=3, tracking="bulk", epn="91845A029",
         desc="McMaster 91845A029",
         reorder=50)
    _add("lock_washer_quarter", "KST-D-0042", "Lock Washer, 1/4\", 18-8 SS",
         category="Fasteners", tier=3, tracking="bulk", epn="92146A029",
         desc="McMaster 92146A029 — split lock washer",
         reorder=50)
    _add("oring_012", "KST-D-0043", "O-Ring, -012 Buna-N, 70A",
         category="Fasteners", tier=3, tracking="bulk", epn="9452K113",
         desc="McMaster 9452K113 — AS568-012, 0.364\" ID x 0.070\" CS",
         reorder=20)
    _add("oring_016", "KST-D-0044", "O-Ring, -016 Buna-N, 70A",
         category="Fasteners", tier=3, tracking="bulk", epn="9452K117",
         desc="McMaster 9452K117 — AS568-016, 0.614\" ID x 0.070\" CS",
         reorder=20)
    _add("oring_116", "KST-F-0045", "O-Ring, -116 Viton, 75A",
         category="Fasteners", tracking="bulk", epn="9263K516",
         desc="McMaster 9263K516 — AS568-116, LOX-compatible fluoroelastomer, 0.614\" ID x 0.103\" CS",
         reorder=10)

    # ── GSE ─────────────────────────────────────────────────────
    _add("fill_valve", "KST-G-0001", "Fill/Drain Valve Assembly",
         category="GSE", tier=2, desc="Ground-side fill panel: ball valve, vent, burst disc")
    _add("umbilical_qd", "KST-G-0002", "Umbilical Quick-Disconnect",
         category="GSE", tier=2, desc="Swagelok QC4 series, auto-shutoff on disconnect",
         epn="SS-QC4-B-400")
    _add("ign_box", "KST-G-0003", "Ignition Control Box",
         category="GSE", tier=2,
         desc="Key-armed, dual-relay ignition circuit, 500 ft firing lead, continuity check")
    _add("launch_rail", "KST-G-0004", "Launch Rail, 20 ft 1515",
         category="GSE", tier=2,
         desc="80/20 1515 aluminum extrusion, guyed, 85° elevation angle")
    _add("proof_fixture", "KST-G-0005", "Pressure Test Fixture",
         category="GSE", tier=2, is_tooling=True, cal_days=365,
         desc="Hydrostatic proof test manifold: hand pump, gauge, relief valve, bleed")
    _add("ground_reg", "KST-G-0006", "Ground Regulator, N2",
         category="GSE", tier=2,
         desc="Swagelok KPR series, 0-800 PSI outlet, CGA-580 inlet",
         epn="KPR1FRA412A20000")

    # ── Raw Material ────────────────────────────────────────────
    _add("al_plate", "KST-D-0046", "6061-T6 Al Plate, 1/2\" Thick",
         category="Raw Material", tier=3, tracking="bulk", uom="sq ft", epn="89015K28",
         desc="McMaster 89015K28 — mill finish, AMS-QQ-A-250/11")
    _add("ss_sheet", "KST-D-0047", "304 SS Sheet, 0.060\" Thick",
         category="Raw Material", tier=3, tracking="bulk", uom="sq ft", epn="88885K58",
         desc="McMaster 88885K58 — #2B finish, ASTM A240")
    _add("al_round", "KST-D-0048", "6061-T6 Al Round Bar, 3\" OD",
         category="Raw Material", tier=3, tracking="bulk", uom="ft", epn="8974K39",
         desc="McMaster 8974K39 — AMS 4150, turned and polished")

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
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["shcs_quarter"].id, quantity=8,
                reference_designator="B1-B8", notes="Chamber-to-injector bolts"),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["hex_nut_quarter"].id, quantity=8,
                reference_designator="N1-N8"),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["lock_washer_quarter"].id, quantity=8,
                reference_designator="W1-W8"),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["oring_116"].id, quantity=2,
                notes="Injector face seal + nozzle throat seal"),
        BOMLine(assembly_id=p["engine_assy"].id, component_id=p["shcs_10_32"].id, quantity=6,
                reference_designator="B9-B14", notes="Nozzle retainer ring"),
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
        reqs.append(PartRequirement(
            part_id=p[key].id, requirement_id="REQ-001", status="open",
        ))

    # REQ-002 Pressure Containment → pressure vessels and engine
    for key in ["lox_tank", "fuel_tank", "press_tank", "chamber", "engine_assy"]:
        status = "verified" if key == "press_tank" else "open"
        reqs.append(PartRequirement(
            part_id=p[key].id, requirement_id="REQ-002", status=status,
            verified_at=now - timedelta(days=12) if status == "verified" else None,
            notes="COTS tank — vendor cert on file" if key == "press_tank" else None,
        ))

    # REQ-003 LOX Compatibility → wetted parts
    for key in ["lox_tank", "lox_valve", "check_valve", "relief_valve",
                "tube_half", "tube_quarter", "an_fitting_half", "an_fitting_quarter",
                "injector", "oring_116"]:
        status = "verified" if key in ("tube_half", "tube_quarter") else "open"
        reqs.append(PartRequirement(
            part_id=p[key].id, requirement_id="REQ-003", status=status,
            verified_at=now - timedelta(days=20) if status == "verified" else None,
            notes="304 SS — per MSFC-SPEC-106B Table 1" if status == "verified" else None,
        ))

    # REQ-004 Recovery → recovery components and altimeter
    for key in ["main_chute", "drogue", "fc", "altimeter", "pyro_board"]:
        reqs.append(PartRequirement(
            part_id=p[key].id, requirement_id="REQ-004", status="open",
        ))

    # REQ-005 Data Logging → flight computer + sensors
    for key in ["fc", "imu", "altimeter", "gps"]:
        reqs.append(PartRequirement(
            part_id=p[key].id, requirement_id="REQ-005", status="open",
        ))

    # REQ-006 Telemetry Link → radio
    reqs.append(PartRequirement(
        part_id=p["radio"].id, requirement_id="REQ-006", status="open",
    ))

    # REQ-007 Pyro Isolation → pyro board
    reqs.append(PartRequirement(
        part_id=p["pyro_board"].id, requirement_id="REQ-007", status="verified",
        verified_at=now - timedelta(days=5),
        notes="Bench tested: >500V isolation between pyro and logic rails",
    ))

    # REQ-008 Traceability → all flight tier parts (sample)
    for key in ["engine_assy", "chamber", "injector", "nozzle", "lox_tank",
                "fuel_tank", "press_tank", "fc", "harness", "main_chute"]:
        status = "open"
        if key in ("engine_assy", "chamber"):
            status = "waived"
        reqs.append(PartRequirement(
            part_id=p[key].id, requirement_id="REQ-008", status=status,
            notes="Waived — traceability deferred to post-assembly serial assignment"
            if status == "waived" else None,
        ))

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

def _seed_procedures(
    db: Session, p: dict[str, Part], wc: dict[str, Workcenter],
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
        ("chamber", 1), ("injector", 1), ("nozzle", 1), ("igniter", 1),
        ("shcs_quarter", 8), ("hex_nut_quarter", 8), ("lock_washer_quarter", 8),
        ("oring_116", 2), ("shcs_10_32", 6),
    ]:
        db.add(Kit(procedure_id=eng_build.id, part_id=p[part_key].id,
                    quantity_required=Decimal(str(qty))))
    db.add(ProcedureOutput(procedure_id=eng_build.id, part_id=p["engine_assy"].id,
                           quantity_produced=Decimal("1")))
    db.flush()

    _eng_build_steps = [
        ("1", "Inspect Components", "Visually inspect chamber, injector, nozzle, and igniter for defects. Verify dimensions per drawing.", 15, "CLEAN", False),
        ("2", "Clean All Surfaces", "Solvent-clean all mating surfaces with isopropyl alcohol. Blow dry with clean N2.", 10, "CLEAN", False),
        ("3", "Install Injector O-Ring", "Lubricate -116 O-ring with Krytox grease. Seat into injector face groove.", 5, "CLEAN", False),
        ("4", "Mate Injector to Chamber", "Align index pin. Lower injector onto chamber flange.", 5, "CLEAN", False),
        ("5", "Torque Injector Bolts", "Install 8x 1/4\"-20 SHCS with lock washers. Torque in star pattern to 120 in-lb.", 15, "CLEAN", True),
        ("6", "Install Nozzle O-Ring", "Lubricate -116 O-ring. Seat into nozzle throat groove.", 5, "CLEAN", False),
        ("7", "Install Nozzle", "Thread nozzle into chamber aft end. Hand-tight plus 1/4 turn.", 5, "CLEAN", False),
        ("8", "Install Nozzle Retainer", "Install 6x 10-32 SHCS in retainer ring. Torque to 40 in-lb.", 10, "CLEAN", True),
        ("9", "Install Igniter", "Thread igniter into injector boss. Verify e-match leads routed clear of hot gas path.", 10, "CLEAN", False),
        ("10", "Leak Check — Low Pressure", "Cap nozzle exit. Pressurize to 50 PSI with N2. Soap-bubble all joints.", 15, "CLEAN", False),
        ("11", "Final Inspection", "Verify all fasteners torqued and marked. Photograph assembly from 4 angles.", 10, "CLEAN", True),
        ("12", "Record Assembly Data", "Log serial numbers of all components, lot numbers of O-rings and fasteners.", 5, "CLEAN", False),
    ]
    order = 0
    for sn, title, instructions, dur, wc_code, signoff in _eng_build_steps:
        order += 1
        db.add(ProcedureStep(
            procedure_id=eng_build.id, order=order, step_number=sn, level=0,
            title=title, instructions=instructions,
            estimated_duration_minutes=dur, workcenter_id=wc[wc_code].id,
            requires_signoff=signoff,
        ))
    db.flush()

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

    _hydro_steps = [
        ("1", "Setup Test Fixture", "Connect pressure test fixture to test article via 1/4\" fitting. Fill with distilled water, bleed air.", 20, "PAD", False, None),
        ("2", "Verify Instrumentation", "Confirm pressure gauge reads 0 ±2 PSI. Verify data acquisition running.", 5, "PAD", False, None),
        ("3", "Pressurize to 100 PSI", "Slowly pressurize to 100 PSI. Hold 60 seconds. Inspect for leaks.", 5, "PAD", False, {"fields": [{"name": "pressure_100_psi", "type": "number", "label": "Pressure at hold (PSI)", "required": True}]}),
        ("4", "Pressurize to 300 PSI", "Increase to 300 PSI. Hold 60 seconds. Inspect.", 5, "PAD", False, {"fields": [{"name": "pressure_300_psi", "type": "number", "label": "Pressure at hold (PSI)", "required": True}]}),
        ("5", "Pressurize to 500 PSI (MEOP)", "Increase to 500 PSI. Hold 2 minutes. Inspect thoroughly.", 5, "PAD", False, {"fields": [{"name": "pressure_meop", "type": "number", "label": "Pressure at hold (PSI)", "required": True}]}),
        ("6", "Pressurize to 675 PSI (Proof)", "Increase to 675 PSI (1.35x MEOP). Hold 5 minutes. No leaks or yielding.", 10, "PAD", True, {"fields": [{"name": "proof_pressure", "type": "number", "label": "Peak proof pressure (PSI)", "required": True}, {"name": "hold_duration_s", "type": "number", "label": "Hold duration (seconds)", "required": True}]}),
        ("7", "Depressurize and Inspect", "Slowly depressurize to 0. Inspect for permanent deformation — measure OD at 3 stations.", 10, "PAD", False, {"fields": [{"name": "od_station_1", "type": "number", "label": "OD Station 1 (in)"}, {"name": "od_station_2", "type": "number", "label": "OD Station 2 (in)"}, {"name": "od_station_3", "type": "number", "label": "OD Station 3 (in)"}]}),
        ("8", "Record Results", "Log pass/fail. Drain test article. Dry with N2.", 5, "PAD", True, None),
    ]
    order = 0
    for sn, title, instr, dur, wc_code, signoff, schema in _hydro_steps:
        order += 1
        db.add(ProcedureStep(
            procedure_id=hydro.id, order=order, step_number=sn, level=0,
            title=title, instructions=instr,
            estimated_duration_minutes=dur, workcenter_id=wc[wc_code].id,
            requires_signoff=signoff,
            required_data_schema=schema,
        ))
    db.flush()

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

    _hotfire_steps = [
        ("1", "Pre-Test Briefing", "Review test plan, abort criteria, and roles. Confirm range is clear.", 15, "PAD", False, None),
        ("2", "Install Engine on Stand", "Mount engine assembly to thrust stand adapter plate. Torque mount bolts.", 20, "PAD", False, None),
        ("3", "Connect Propellant Lines", "Connect LOX and fuel feed lines to engine inlets. Torque AN fittings.", 15, "PAD", False, None),
        ("4", "Connect Instrumentation", "Attach thrust load cell cable, chamber pressure transducer, thermocouples.", 10, "PAD", False, None),
        ("5", "Leak Check — Pneumatic", "Pressurize propellant lines to 50 PSI with N2. Verify zero leaks.", 10, "PAD", True, None),
        ("6", "Load Propellants", "Fill LOX tank (2.5 gal). Fill ethanol tank (3.0 gal). Verify levels.", 20, "PAD", True, {"fields": [{"name": "lox_fill_level", "type": "number", "label": "LOX fill level (gal)"}, {"name": "fuel_fill_level", "type": "number", "label": "Fuel fill level (gal)"}]}),
        ("7", "Pressurize Tanks", "Open N2 supply. Regulate to 450 PSI. Verify both tank pressures.", 5, "PAD", False, {"fields": [{"name": "lox_tank_psi", "type": "number", "label": "LOX tank pressure (PSI)"}, {"name": "fuel_tank_psi", "type": "number", "label": "Fuel tank pressure (PSI)"}]}),
        ("8", "Arm Ignition System", "Turn igniter arm key. Verify continuity LED.", 2, "PAD", True, None),
        ("9", "Final Poll — Go/No-Go", "Poll all stations. Record go/no-go.", 5, "PAD", True, None),
        ("10", "Countdown and Fire", "5-4-3-2-1-IGNITION. Open valves on command. Run 5 seconds.", 1, "PAD", False, None),
        ("11", "Engine Shutdown", "Close main valves. Vent tanks. Safe ignition system.", 2, "PAD", False, None),
        ("12", "Record Test Data", "Download thrust curve, chamber pressure trace, temperatures.", 10, "PAD", False, {"fields": [{"name": "peak_chamber_psi", "type": "number", "label": "Peak Pc (PSI)", "required": True}, {"name": "peak_thrust_lbf", "type": "number", "label": "Peak thrust (lbf)", "required": True}, {"name": "burn_time_s", "type": "number", "label": "Burn time (seconds)", "required": True}]}),
        ("13", "Post-Fire Inspection", "Inspect nozzle throat, injector face, chamber walls for erosion or damage.", 15, "PAD", False, None),
        ("14", "Disconnect and Remove", "Disconnect all lines and instrumentation. Remove engine from stand.", 20, "PAD", False, None),
        ("15", "Debrief and Report", "Review data. Compare Pc and thrust to predictions. Note anomalies.", 30, "PAD", False, None),
    ]
    order = 0
    for sn, title, instr, dur, wc_code, signoff, schema in _hotfire_steps:
        order += 1
        db.add(ProcedureStep(
            procedure_id=hotfire.id, order=order, step_number=sn, level=0,
            title=title, instructions=instr,
            estimated_duration_minutes=dur, workcenter_id=wc[wc_code].id,
            requires_signoff=signoff,
            required_data_schema=schema,
        ))
    db.flush()

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
        ("fc", 1), ("gps", 1), ("imu", 1), ("altimeter", 1),
        ("radio", 1), ("lipo", 1), ("pyro_board", 1),
    ]:
        db.add(Kit(procedure_id=avi.id, part_id=p[part_key].id,
                    quantity_required=Decimal(str(qty))))
    db.add(ProcedureOutput(procedure_id=avi.id, part_id=p["harness"].id,
                           quantity_produced=Decimal("1")))
    db.flush()

    _avi_steps = [
        ("1", "Prepare Avionics Sled", "Clean sled. Install standoffs for FC, pyro board, GPS.", 10, "LAB"),
        ("2", "Mount Flight Computer", "Secure Teensy 4.1 board to standoffs. Verify USB port accessible.", 5, "LAB"),
        ("3", "Mount Sensors", "Install BNO055 IMU, MS5611 altimeter, MAX-M10S GPS. Secure connectors.", 15, "LAB"),
        ("4", "Mount Pyro Board", "Install pyro channel board. Connect optoisolator ribbon cable to FC.", 10, "LAB"),
        ("5", "Mount Radio", "Install RFM95W module. Route antenna wire to external SMA bulkhead.", 10, "LAB"),
        ("6", "Build Wiring Harness", "Route and terminate all wires per harness drawing. Lace with waxed cord.", 30, "LAB"),
        ("7", "Power-On Test", "Connect LiPo. Verify FC boots, sensors respond, radio transmits test packet.", 15, "LAB"),
        ("8", "Final Inspection", "Verify all connectors seated. Check wire routing for chafe points. Photograph.", 10, "LAB"),
    ]
    order = 0
    for sn, title, instr, dur, wc_code in _avi_steps:
        order += 1
        db.add(ProcedureStep(
            procedure_id=avi.id, order=order, step_number=sn, level=0,
            title=title, instructions=instr,
            estimated_duration_minutes=dur, workcenter_id=wc[wc_code].id,
        ))
    db.flush()

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

    _rec_steps = [
        ("1", "Inspect Parachutes", "Unfold main and drogue. Inspect canopy for tears, shroud lines for fraying.", 10, "CLEAN", True, None),
        ("2", "Fold Drogue", "Z-fold drogue canopy. Bundle shroud lines. Wrap with deployment bag.", 10, "CLEAN", False, None),
        ("3", "Fold Main", "Accordion-fold main canopy per packing card. Bundle lines. Insert in deployment bag.", 15, "CLEAN", False, None),
        ("4", "Install Ejection Charges", "Load 2.5g black powder in drogue charge well. Load 4.0g in main charge well. Install e-matches.", 10, "CLEAN", True, {"fields": [{"name": "drogue_charge_g", "type": "number", "label": "Drogue charge (grams)", "required": True}, {"name": "main_charge_g", "type": "number", "label": "Main charge (grams)", "required": True}]}),
        ("5", "Continuity Check", "Verify continuity on both pyro channels. Record resistance.", 5, "CLEAN", True, {"fields": [{"name": "drogue_ohms", "type": "number", "label": "Drogue circuit (Ω)", "required": True}, {"name": "main_ohms", "type": "number", "label": "Main circuit (Ω)", "required": True}]}),
        ("6", "Install Shear Pins", "Install 3x nylon shear pins per separation joint. Verify coupler alignment.", 5, "CLEAN", False, None),
    ]
    order = 0
    for sn, title, instr, dur, wc_code, signoff, schema in _rec_steps:
        order += 1
        db.add(ProcedureStep(
            procedure_id=rec.id, order=order, step_number=sn, level=0,
            title=title, instructions=instr,
            estimated_duration_minutes=dur, workcenter_id=wc[wc_code].id,
            requires_signoff=signoff, required_data_schema=schema,
        ))
    db.flush()

    # ── 6. Final Vehicle Integration ────────────────────────────
    fvi = MasterProcedure(
        name="Final Vehicle Integration",
        description="Stack all subsystems: propulsion module, avionics bay, recovery bay, nose cone. Install fins and rail buttons.",
        procedure_type=ProcedureType.OP,
        status=ProcedureStatus.DRAFT,
    )
    db.add(fvi)
    db.flush()
    procs["fvi"] = fvi

    _fvi_steps = [
        ("1", "Stage Components", "Lay out all subassemblies on clean bench. Cross-check inventory.", 15, "CLEAN"),
        ("2", "Install Aft Bulkhead", "Insert aft bulkhead into airframe tube. Align feedthrough ports. Secure with retaining ring.", 10, "CLEAN"),
        ("3", "Install Engine", "Slide engine assembly into aft section. Mate to bulkhead flange. Torque mount bolts.", 15, "CLEAN"),
        ("4", "Install Tanks", "Stack LOX and fuel tanks on thrust structure. Connect feedlines.", 20, "CLEAN"),
        ("5", "Install Forward Bulkhead", "Seat forward bulkhead. Route recovery harness and vent lines through.", 10, "CLEAN"),
        ("6", "Mate Avionics Bay", "Slide avionics sled into coupler section. Connect pyro leads and antenna.", 15, "CLEAN"),
        ("7", "Install Recovery Bay", "Pack parachutes into recovery section. Connect shock cord to U-bolts.", 10, "CLEAN"),
        ("8", "Install Nose Cone", "Seat nose cone on coupler. Install shear pins.", 5, "CLEAN"),
        ("9", "Install Fins and Rail Buttons", "Epoxy 3x fins at 120° spacing. Install 2x rail buttons at CG and CP stations.", 20, "SHOP"),
        ("10", "Final Mass and CG", "Weigh vehicle. Measure CG location. Verify static margin ≥ 1.5 calibers.", 10, "CLEAN"),
    ]
    order = 0
    for sn, title, instr, dur, wc_code in _fvi_steps:
        order += 1
        db.add(ProcedureStep(
            procedure_id=fvi.id, order=order, step_number=sn, level=0,
            title=title, instructions=instr,
            estimated_duration_minutes=dur, workcenter_id=wc[wc_code].id,
        ))
    db.flush()

    return procs


# ---------------------------------------------------------------------------
# Versions & Executions
# ---------------------------------------------------------------------------

def _seed_versions_and_executions(
    db: Session, procs: dict[str, MasterProcedure],
) -> None:
    now = datetime.now(UTC)

    # Publish versions for active procedures
    for proc_key in ("eng_build", "hydro", "hotfire", "recovery"):
        proc = procs[proc_key]
        steps = db.query(ProcedureStep).filter(
            ProcedureStep.procedure_id == proc.id,
        ).order_by(ProcedureStep.order).all()

        content = {
            "steps": [
                {
                    "order": s.order,
                    "step_number": s.step_number,
                    "level": s.level,
                    "title": s.title,
                    "instructions": s.instructions,
                    "requires_signoff": s.requires_signoff,
                    "estimated_duration_minutes": s.estimated_duration_minutes,
                    "is_contingency": s.is_contingency,
                    "required_data_schema": s.required_data_schema,
                }
                for s in steps
            ]
        }

        version = ProcedureVersion(
            procedure_id=proc.id, version_number=1, content=content,
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
                    started_at=now - timedelta(days=10, hours=3) + timedelta(minutes=s["order"] * 8),
                    completed_at=now - timedelta(days=10, hours=3) + timedelta(minutes=s["order"] * 8 + 7),
                )
                # Add captured data for pressure steps
                if s["required_data_schema"] and s["step_number"] == "6":
                    se.data_captured = {"proof_pressure": 677, "hold_duration_s": 305}
                elif s["required_data_schema"] and s["step_number"] == "7":
                    se.data_captured = {"od_station_1": 6.001, "od_station_2": 6.000, "od_station_3": 6.001}
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

            # First 5 steps completed, step 6 in progress
            for s in content["steps"]:
                if s["order"] <= 5:
                    se = StepExecution(
                        instance_id=inst.id,
                        step_number=s["order"],
                        step_number_str=s["step_number"],
                        level=s["level"],
                        status=StepStatus.SIGNED_OFF if s["requires_signoff"] else StepStatus.COMPLETED,
                        started_at=now - timedelta(hours=2) + timedelta(minutes=s["order"] * 12),
                        completed_at=now - timedelta(hours=2) + timedelta(minutes=s["order"] * 12 + 10),
                    )
                    db.add(se)
                elif s["order"] == 6:
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
    db: Session, p: dict[str, Part], suppliers: dict[str, Supplier],
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
        db.add(PurchaseLine(
            purchase_id=po1.id, part_id=p[part_key].id,
            qty_ordered=Decimal(str(qty)), qty_received=Decimal(str(qty)),
            unit_cost=cost,
        ))

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
    db.add(PurchaseLine(
        purchase_id=po2.id, part_id=p["lox_valve"].id,
        qty_ordered=Decimal("1"), qty_received=Decimal("1"),
        unit_cost=Decimal("245.00"),
    ))
    db.add(PurchaseLine(
        purchase_id=po2.id, part_id=p["fuel_valve"].id,
        qty_ordered=Decimal("1"), qty_received=Decimal("1"),
        unit_cost=Decimal("245.00"),
    ))
    db.add(PurchaseLine(
        purchase_id=po2.id, part_id=p["check_valve"].id,
        qty_ordered=Decimal("4"), qty_received=Decimal("4"),
        unit_cost=Decimal("68.00"),
    ))
    db.add(PurchaseLine(
        purchase_id=po2.id, part_id=p["umbilical_qd"].id,
        qty_ordered=Decimal("2"), qty_received=Decimal("0"),
        unit_cost=Decimal("185.00"),
        notes="Backordered — expected ship date 2026-03-28",
    ))
    db.add(PurchaseLine(
        purchase_id=po2.id, part_id=p["ground_reg"].id,
        qty_ordered=Decimal("1"), qty_received=Decimal("1"),
        unit_cost=Decimal("420.00"),
    ))

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
        db.add(PurchaseLine(
            purchase_id=po3.id, part_id=p[part_key].id,
            qty_ordered=Decimal(str(qty)), qty_received=Decimal(str(qty)),
            unit_cost=cost,
        ))

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
    db.add(PurchaseLine(
        purchase_id=po4.id, part_id=p["al_plate"].id,
        qty_ordered=Decimal("8"), qty_received=Decimal("0"),
        unit_cost=Decimal("45.00"),
    ))
    db.add(PurchaseLine(
        purchase_id=po4.id, part_id=p["ss_sheet"].id,
        qty_ordered=Decimal("4"), qty_received=Decimal("0"),
        unit_cost=Decimal("62.00"),
    ))
    db.add(PurchaseLine(
        purchase_id=po4.id, part_id=p["al_round"].id,
        qty_ordered=Decimal("6"), qty_received=Decimal("0"),
        unit_cost=Decimal("38.00"),
    ))

    db.flush()


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def _seed_issues(
    db: Session, p: dict[str, Part], procs: dict[str, MasterProcedure],
) -> None:
    # ── Non-Conformances ────────────────────────────────────────

    nc1 = Issue(
        issue_number=generate_issue_number(db),
        title="Injector plate hole pattern out of tolerance",
        description="During QA inspection, bolt circle measured 0.005\" outside tolerance.",
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
        description="Remake injector from 304 SS stock with corrected bolt circle diameter (1.500\" ±0.002\"). Use CNC for hole pattern.",
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

    db.add(IssueComment(
        issue_id=nc1.id,
        body="Measured all 32 holes with pin gauges. Hole diameters are within spec — only the bolt circle is off. Likely a fixture alignment issue on the rotary table.",
    ))
    db.add(IssueComment(
        issue_id=nc1.id,
        body="Checked the G-code. Origin offset was set to X0.0025 Y0.0000 instead of X0.0000 Y0.0000. That explains the radial shift. CNC program has been corrected for the remake.",
    ))

    db.add(IssueComment(
        issue_id=bug1.id,
        body="Scope trace on Vcc rail shows a 1.2V dip lasting ~500 µs coincident with e-match firing. The MOSFET inrush is pulling the rail below the Teensy's brownout threshold (2.7V). Need a bigger bulk cap on the pyro board or separate battery for pyro.",
    ))
    db.add(IssueComment(
        issue_id=bug1.id,
        body="Added 2200 µF low-ESR cap to pyro board Vcc input. Dip reduced to 0.3V — FC stays up now. Will retest with both channels firing simultaneously before closing.",
    ))

    db.add(IssueComment(
        issue_id=nc2.id,
        body="Sent X-ray images to welding consultant. Recommendation: grind out affected area and re-weld, then re-inspect. Alternatively, could accept with stress analysis showing adequate margin at reduced section.",
    ))

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
            probability=3, impact=5,
            mitigation_plan="1. Review all wetted materials against MSFC-SPEC-106B.\n2. Replace any non-compatible materials (e.g., Buna-N O-rings → Viton).\n3. Oxygen-clean all LOX-side components per CGA G-4.1.\n4. Perform LOX drop-impact test on any questionable materials.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Recovery deployment failure",
            description="Parachute fails to deploy at apogee or main deploy altitude, resulting in ballistic impact.",
            status=RiskStatus.MONITORING,
            probability=2, impact=5,
            mitigation_plan="1. Dual-event recovery (drogue + main) with independent altimeters.\n2. Ground-test ejection charges with flight-weight hardware.\n3. Verify continuity before every flight.\n4. Redundant altimeter triggers both events independently.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Engine hard start / overpressure",
            description="Propellant accumulation in chamber before ignition causes deflagration-to-detonation event (hard start).",
            status=RiskStatus.MITIGATING,
            probability=2, impact=5,
            mitigation_plan="1. LOX-lead ignition sequence (oxidizer before fuel).\n2. Verified igniter reliability — 10/10 ground tests.\n3. Pressure relief valve on chamber (set to 1.5x MEOP).\n4. Remote operation with 500 ft minimum safe distance.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Avionics power loss during flight",
            description="LiPo battery failure or wiring fault causes total avionics blackout during flight.",
            status=RiskStatus.ANALYZING,
            probability=2, impact=4,
            mitigation_plan="1. Pre-flight voltage check under load.\n2. Strain-relieve all connectors.\n3. Consider adding independent backup battery for recovery altimeter.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Schedule slip past launch window",
            description="Delays in fabrication or testing cause the project to miss the target launch date and site reservation.",
            status=RiskStatus.IDENTIFIED,
            probability=4, impact=3,
            mitigation_plan="1. Identify critical path items (engine assembly, hot fire test).\n2. Order long-lead items early (Swagelok QD already on backorder).\n3. Maintain schedule buffer for re-work.",
        ),
        Risk(
            risk_number=generate_risk_number(db),
            title="Propellant handling safety incident",
            description="Personnel injury during LOX or ethanol handling operations.",
            status=RiskStatus.MONITORING,
            probability=1, impact=5,
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
