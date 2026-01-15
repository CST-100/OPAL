# OPAL GitHub Issues Audit
**Generated: 2026-01-14**

## Overall Statistics
- **Total Issues**: 39
- **Open Issues**: 36 (92%)
- **Closed Issues**: 3 (8%)

---

## Critical Issues (MUST FIX)

### #30: Procedures system significantly broken [CRITICAL]
The procedures subsystem has multiple failures:
- **A**: ~~NEW PROCEDURE button doesn't work~~ (FIXED)
- **B**: ~~UI needs merging with SAVE DRAFT~~ (FIXED v0.4.3)
- **C**: ~~Procedures menu doesn't display existing procedures~~ (FIXED)
- **D**: Confusing URL routing (draft/master vs published versions) - OPEN
- **E**: ~~CRASH: Kitting parts throws 500 error~~ (FIXED)

### #36: "Add inventory" form fails [HIGH]
Adding inventory through the UI crashes completely. Blocks manual inventory entry workflows.

### #37: Inventory display empty [HIGH]
Inventory records exist in the database but don't display on part detail pages. Users can't see what stock is on hand.

### #41: Risk matrix colorless [LOW]
Missing color coding (green/yellow/red) on risk matrix visualization.

---

## High-Impact Design Issues (Need Architecture Decisions)

### #43: Ephemeral/intermediate parts and WIP inventory
Core manufacturing challenge: How to model parts that transform during production?
- Example: raw bar → machined bar → anodized part → installed in assembly
- Questions: Should intermediates get OPAL numbers? When consumed vs transformed?

### #40: Assembly part creation workflow
Need clear workflow for:
- Creating assemblies/sub-assemblies as parts
- Marking parts as buildable (produced via BUILD operations)
- Linking produced parts back to creating procedures

### #35: Tier-based OPAL number assignment [RELEASED v0.4.3]
- Default to SERIALIZED (individual OPAL per item)
- BULK for consumables (single OPAL per lot)

---

## Medium-Priority Features

| # | Title | Impact |
|---|-------|--------|
| #31 | Create parts via executions | Enable manufacturing output |
| #39 | BUILD operation marking UI | Backend exists, needs UI |
| #42 | Mark OPALs scrapped/destroyed | Track waste & non-conformances |
| #8 | Assembly genealogy tracking | Part lineage visibility |

---

## Core UI Features (Basic Functionality)

These represent foundational UI work still needed:
- **#4**: Parts Management UI
- **#5**: Inventory Record Management UI
- **#6**: Procedure Step Execution Interface
- **#7**: Kit Management & Consumption UI
- **#8**: Assembly Production & Genealogy Tracking
- **#10**: Purchase Order Receiving Interface

**Note**: Backend is ~80% complete; UI is ~30% complete.

---

## Infrastructure & Documentation
- **#33**: Docker Distribution, System Onboarding, Installation
- **#27**: Backup and Restore Functionality
- **#25**: API Documentation
- **#24**: End-to-End Testing

---

## Polish & Enhancement Features
#11 Search, #12 BOM, #13 Requirements Tracking, #14 Test Templates, #15 Procedure Versioning, #16 Workcenter Management, #17 Risk Visualization, #18 Analytics, #19 Keyboard Docs, #20 Collaboration, #21 Mobile UI, #22 Dark Mode, #23 Settings, #38 Parts Sorting, #26 Authentication

---

## Closed Issues
- **#32**: Can't manually add inventory (FIXED)
- **#29**: Use search, not dropdowns (FIXED v0.4.2)
- **#28**: Purchase orders fail on submission (FIXED v0.4.1)

---

## Recommended Priority for Initial Operating Capability

**Phase 1: Unblock Core Inventory**
1. Fix #36 - Add inventory form
2. Fix #37 - Inventory visibility on parts page

**Phase 2: Polish Core Experience**
3. Fix #41 - Risk matrix colors
4. Add #38 - Parts table sorting
5. Address #30D - Procedure URL clarity

**Phase 3: Manufacturing Features**
6. Design #43/#40 - Resolve architectural questions
7. Implement #31/#39 - BUILD operations & part creation
