# OPAL TODO Issues

This document contains major features and improvements that need to be implemented in OPAL.

---

## High Priority - Core Features

### Issue 1: Parts Management UI
**Priority: HIGH**
**Labels: enhancement, ui, inventory**

**Description:**
Implement the complete Parts management web interface including:
- Parts list page with search, filtering by category/tier/parent
- Part detail page showing:
  - Basic information (internal/external PN, category, tier, description)
  - Total stock quantity across all locations
  - BOM structure (components)
  - Where-used analysis
  - Test templates management
  - Requirements tracking
- Part create/edit forms with tier-based PN auto-generation
- Bulk import capability for parts from CSV

**Acceptance Criteria:**
- [ ] Parts list page at `/parts` with data table
- [ ] Search and filter functionality working
- [ ] Part detail page at `/parts/{id}`
- [ ] Create new part form at `/parts/new`
- [ ] Edit part form at `/parts/{id}/edit`
- [ ] Delete part with confirmation
- [ ] Integration with existing Parts API (`/api/parts`)

**References:**
- API: `src/opal/api/routes/parts.py`
- Manual: `OPAL_manual.md` - Parts & Inventory Management section

---

### Issue 2: Inventory Record Management UI
**Priority: HIGH**
**Labels: enhancement, ui, inventory**

**Description:**
Complete the inventory management interface with full CRUD operations:
- Inventory list page showing all records with OPAL numbers
- Filter by part, location, lot number
- OPAL number detail page showing:
  - Complete history (created, adjusted, counted, transferred, consumed)
  - Test results and overall status
  - Transfer history
  - Consumption tracking
- Forms for:
  - Manual inventory entry
  - Quantity adjustments with reasons
  - Physical count recording
  - Location transfers (full and partial)
  - Test result entry

**Acceptance Criteria:**
- [ ] Inventory list page improvements at `/inventory`
- [ ] OPAL detail page fully functional at `/inventory/opal/{opal_number}`
- [ ] Create inventory form at `/inventory/new`
- [ ] Adjust quantity form
- [ ] Perform count form
- [ ] Transfer form with partial transfer support
- [ ] Test management interface

**References:**
- API: `src/opal/api/routes/inventory.py`
- Existing template: `src/opal/web/templates/inventory/opal_detail.html`

---

### Issue 3: Procedure Step Execution Interface
**Priority: HIGH**
**Labels: enhancement, ui, procedures, execution**

**Description:**
Build the interactive step-by-step execution interface for procedure instances:
- Real-time step execution view with collapsible hierarchy
- Step state visualization (pending/in_progress/completed/awaiting_signoff/signed_off/skipped)
- Data capture forms generated from step schemas
- File/image upload for steps
- Non-conformance logging from any step
- Sign-off workflow for parent OPs
- Progress tracking and duration timers
- Multi-user collaboration indicators

**Acceptance Criteria:**
- [ ] Interactive step execution UI on execution detail page
- [ ] Start/complete/skip step actions
- [ ] Dynamic form generation from required_data_schema
- [ ] File upload functionality per step
- [ ] NC logging modal with automatic issue creation
- [ ] Parent OP sign-off workflow
- [ ] Real-time progress indicators
- [ ] Duration tracking display

**References:**
- API: `src/opal/api/routes/execution.py`
- Existing: `src/opal/web/templates/executions/detail.html`
- Manual: OPAL_manual.md - Procedure Execution section

---

### Issue 4: Kit Management and Consumption UI
**Priority: HIGH**
**Labels: enhancement, ui, procedures, inventory**

**Description:**
Implement the kit availability checking and parts consumption interface:
- Kit availability view showing required vs available quantities
- Part selection for consumption with OPAL number lookup
- Procedure-level consumption interface
- Step-level consumption with tooling vs permanent distinction
- Consumption history view
- Visual indicators for kit readiness

**Acceptance Criteria:**
- [ ] Kit availability panel on execution detail page
- [ ] Consume parts form with inventory selection
- [ ] Step-level consumption forms
- [ ] Tooling vs permanent consumption toggle
- [ ] Consumption history display
- [ ] Real-time availability updates

**References:**
- API: `/api/procedure-instances/{id}/consume` endpoints
- Manual: Procedure Execution - Consuming Parts section

---

### Issue 5: Assembly Production and Genealogy Tracking
**Priority: HIGH**
**Labels: enhancement, ui, procedures, inventory, traceability**

**Description:**
Build the interface for producing assemblies and viewing genealogy:
- Production form for BUILD procedures
- Assembly output creation with OPAL number generation
- Forward genealogy view (what's in this assembly)
- Reverse genealogy view (where is this component used)
- Genealogy visualization/tree
- Production history per instance

**Acceptance Criteria:**
- [ ] Produce outputs form on BUILD execution detail page
- [ ] Production history view
- [ ] Forward genealogy display on assembly detail page
- [ ] Reverse genealogy display on component detail page
- [ ] Visual genealogy tree/diagram
- [ ] Complete traceability chain display

**References:**
- API: `/api/procedure-instances/{id}/produce`
- Core: `src/opal/core/genealogy.py`
- Manual: Procedures → Producing Assemblies, Traceability sections

---

### Issue 6: Dataset Graphing and Visualization
**Priority: MEDIUM**
**Labels: enhancement, ui, datasets, analytics**

**Description:**
Implement data visualization and graphing features for datasets:
- Time series graphs
- Scatter plots
- Histograms
- Graph configuration (axes, filters, date ranges)
- CSV export functionality
- Auto-capture from linked procedures display

**Acceptance Criteria:**
- [ ] Graph display on dataset detail page
- [ ] Graph type selection (time series/scatter/histogram)
- [ ] Axis configuration
- [ ] Date range and value filtering
- [ ] CSV export button
- [ ] Linked procedure data capture display

**References:**
- API: `/api/datasets/{id}/graph`
- Existing: `src/opal/web/templates/datasets/detail.html`

---

### Issue 7: Purchase Order Receiving Interface
**Priority: MEDIUM**
**Labels: enhancement, ui, procurement**

**Description:**
Complete the PO receiving workflow with automatic inventory creation:
- Receiving form per PO line item
- OPAL number auto-generation
- Partial receipt support
- Location assignment during receiving
- Lot number entry
- Automatic PO status updates
- Receipt history view

**Acceptance Criteria:**
- [ ] Receive items form on PO detail page
- [ ] Line-by-line receiving
- [ ] Automatic inventory record creation
- [ ] PO status auto-update (partial/received)
- [ ] Receipt history display
- [ ] Overdue PO highlighting

**References:**
- API: `/api/purchases/{id}/receive`
- Existing: `src/opal/web/templates/purchases/detail.html`

---

### Issue 8: Search Functionality
**Priority: MEDIUM**
**Labels: enhancement, ui, search**

**Description:**
Implement global search across all entities:
- Full-text search in command palette
- Search parts, procedures, issues, risks, inventory
- Search by OPAL numbers, WO numbers, IT numbers, RISK numbers
- Filter by status, date range, linked entities
- Recent items display
- Search history

**Acceptance Criteria:**
- [ ] Enhanced command palette search
- [ ] Global search endpoint
- [ ] Search results display
- [ ] Filter options
- [ ] Recent/frequent items
- [ ] Quick access shortcuts

**References:**
- Existing: Command palette in `base.html`
- Manual: User Interface Guide - Command Palette section

---

## Medium Priority - Enhancements

### Issue 9: BOM Management Interface
**Priority: MEDIUM**
**Labels: enhancement, ui, parts**

**Description:**
Build UI for managing bill of materials:
- BOM view showing hierarchical structure
- Add/edit/remove components
- Reference designator management
- Quantity per assembly
- Where-used analysis display
- BOM export to CSV

**Acceptance Criteria:**
- [ ] BOM tab on part detail page
- [ ] Add component form
- [ ] Edit component quantities and designators
- [ ] Remove component action
- [ ] Hierarchical BOM tree view
- [ ] Where-used tab display

**References:**
- API: `src/opal/api/routes/bom.py`

---

### Issue 10: Requirements Tracking Interface
**Priority: MEDIUM**
**Labels: enhancement, ui, quality**

**Description:**
Implement requirements tracking and verification:
- Link parts to requirements
- Requirement verification status tracking
- Requirements list per part
- Verification workflow
- Requirements matrix view

**Acceptance Criteria:**
- [ ] Requirements tab on part detail page
- [ ] Link requirement form
- [ ] Update verification status
- [ ] Requirements list display
- [ ] Status indicators (proposed/verified/not_met)

**References:**
- API: `src/opal/api/routes/requirements.py`

---

### Issue 11: Test Template and Results Management
**Priority: MEDIUM**
**Labels: enhancement, ui, quality, inventory**

**Description:**
Complete testing interface for inventory items:
- Test template creation per part
- Test template list and management
- Perform test form with type-specific inputs
- Test results history
- Overall pass/fail status calculation
- Required vs optional tests

**Acceptance Criteria:**
- [ ] Test templates tab on part detail page
- [ ] Create test template form
- [ ] Perform test form on inventory detail page
- [ ] Test results history display
- [ ] Overall status indicator
- [ ] Required test enforcement

**References:**
- API: `/api/parts/{id}/test-templates`, `/api/inventory/{id}/tests`

---

### Issue 12: Procedure Versioning UI
**Priority: MEDIUM**
**Labels: enhancement, ui, procedures**

**Description:**
Improve procedure version management interface:
- Version history display
- Version comparison view
- Publish version workflow with release notes
- Version detail view showing exact snapshot
- Active version indicator
- Clone procedure functionality

**Acceptance Criteria:**
- [ ] Versions tab on procedure detail page
- [ ] Publish version form with release notes
- [ ] Version history list
- [ ] Version detail page
- [ ] Version comparison view
- [ ] Clone procedure button

**References:**
- API: `/api/procedures/{id}/publish`, `/api/procedures/{id}/versions`
- Existing: `src/opal/web/templates/procedures/version_detail.html`

---

### Issue 13: Workcenter Management and Assignment
**Priority: LOW**
**Labels: enhancement, ui, manufacturing**

**Description:**
Enhance workcenter functionality:
- Workcenter list with active/inactive filters
- Workcenter detail showing assigned procedures/steps
- Assign workcenter to procedure/step
- Capacity planning view
- Workcenter utilization metrics

**Acceptance Criteria:**
- [ ] Workcenter list improvements
- [ ] Workcenter detail page enhancements
- [ ] Assignment UI on procedure/step forms
- [ ] Utilization dashboard

**References:**
- API: `src/opal/api/routes/workcenters.py`
- Existing: `src/opal/web/templates/workcenters/`

---

### Issue 14: Risk Matrix Visualization
**Priority: LOW**
**Labels: enhancement, ui, quality**

**Description:**
Improve risk matrix visualization:
- Interactive risk matrix grid
- Click risk to view details
- Color-coded severity levels
- Risk movement tracking over time
- Matrix filtering options

**Acceptance Criteria:**
- [ ] Interactive matrix grid
- [ ] Clickable risk cells
- [ ] Color coding by severity
- [ ] Filter controls
- [ ] Risk detail popup

**References:**
- API: `/api/risks/matrix`
- Existing: `src/opal/web/templates/risks/matrix.html`

---

### Issue 15: Reports and Analytics
**Priority: LOW**
**Labels: enhancement, ui, analytics**

**Description:**
Build reporting and analytics dashboard:
- Inventory valuation report
- Procedure execution metrics
- NC rate analysis
- Test pass/fail rates
- Supplier performance
- Traceability reports
- Export to PDF/CSV

**Acceptance Criteria:**
- [ ] Reports dashboard page
- [ ] Report type selection
- [ ] Configurable date ranges and filters
- [ ] PDF export
- [ ] CSV export
- [ ] Scheduled reports (future)

**References:**
- API: `src/opal/api/routes/reports.py`

---

## Low Priority - Polish

### Issue 16: Keyboard Shortcuts Documentation
**Priority: LOW**
**Labels: enhancement, ui, documentation**

**Description:**
Improve keyboard shortcuts:
- Visual keyboard shortcuts guide
- Shortcut hints in UI
- Customizable shortcuts
- Shortcuts help modal (accessible via `?`)

**Acceptance Criteria:**
- [ ] Keyboard shortcuts modal
- [ ] In-context shortcut hints
- [ ] Help modal with `?` key
- [ ] Consistent shortcuts across pages

---

### Issue 17: Real-Time Collaboration Indicators
**Priority: LOW**
**Labels: enhancement, ui, execution**

**Description:**
Enhance multi-user collaboration features:
- Active users list on execution page
- User presence indicators
- User actions feed
- Join/leave notifications
- SSE integration for real-time updates

**Acceptance Criteria:**
- [ ] Active users panel
- [ ] Real-time join/leave updates
- [ ] User action indicators
- [ ] SSE connection status

**References:**
- API: `src/opal/api/routes/events.py` (SSE)
- Core: `src/opal/core/events.py`

---

### Issue 18: Mobile-Responsive UI
**Priority: LOW**
**Labels: enhancement, ui, mobile**

**Description:**
Make UI responsive for mobile/tablet use:
- Responsive data tables
- Mobile navigation menu
- Touch-friendly buttons
- Readable on small screens
- Mobile-optimized forms

**Acceptance Criteria:**
- [ ] Responsive CSS breakpoints
- [ ] Mobile navigation
- [ ] Touch-friendly UI elements
- [ ] Readable typography on mobile

---

### Issue 19: Dark/Light Theme Support
**Priority: LOW**
**Labels: enhancement, ui, accessibility**

**Description:**
Add theme switching capability:
- Light mode color scheme
- Theme toggle in user dropdown
- Theme preference persistence
- System theme detection

**Acceptance Criteria:**
- [ ] Light theme CSS variables
- [ ] Theme toggle button
- [ ] localStorage persistence
- [ ] System preference detection

**References:**
- Existing: `src/opal/web/static/css/main.css` (dark theme only)

---

### Issue 20: Settings Page
**Priority: LOW**
**Labels: enhancement, ui**

**Description:**
Create user/system settings page:
- User preferences (theme, notifications, etc.)
- Project configuration editor
- Tier definitions
- Part number format customization
- System-wide settings

**Acceptance Criteria:**
- [ ] Settings page at `/settings`
- [ ] User preferences form
- [ ] Project configuration editor
- [ ] Settings persistence

**References:**
- User dropdown links to `/settings` (not yet implemented)

---

## Testing & Documentation

### Issue 21: End-to-End Testing
**Priority: MEDIUM**
**Labels: testing, quality**

**Description:**
Implement Playwright E2E tests for critical user flows:
- Parts creation and management
- Procedure execution workflow
- Purchase receiving
- Issue creation from NC
- Genealogy tracking

**Acceptance Criteria:**
- [ ] E2E test setup with Playwright
- [ ] Test fixtures for demo data
- [ ] Critical path tests
- [ ] CI integration

---

### Issue 22: API Documentation
**Priority: LOW**
**Labels: documentation**

**Description:**
Generate comprehensive API documentation:
- OpenAPI/Swagger spec
- Interactive API explorer
- Request/response examples
- Authentication documentation
- Rate limiting documentation

**Acceptance Criteria:**
- [ ] OpenAPI spec generation
- [ ] Swagger UI at `/api/docs`
- [ ] Example requests for all endpoints
- [ ] Published API docs

---

## Infrastructure

### Issue 23: User Authentication System
**Priority: FUTURE**
**Labels: enhancement, security, authentication**

**Description:**
Implement user authentication (marked as non-goal for now, but prepare for it):
- Login/logout flow
- Password hashing
- Session management
- Role-based access control (future)
- API key authentication for external integrations

**Note:** Currently a non-goal, but database already has user_id tracking in place.

---

### Issue 24: Backup and Restore Functionality
**Priority: LOW**
**Labels: enhancement, infrastructure**

**Description:**
Add database backup and restore features:
- Manual backup trigger
- Automated scheduled backups
- Backup file management
- Restore from backup
- Backup verification

**Acceptance Criteria:**
- [ ] Backup command
- [ ] Restore command
- [ ] Backup scheduling configuration
- [ ] Backup file browser

---

## Summary

**Total Issues: 24**
- High Priority: 8
- Medium Priority: 7
- Low Priority: 9

**Categories:**
- UI/UX: 15 issues
- Testing: 1 issue
- Documentation: 1 issue
- Infrastructure: 2 issues
- Future: 1 issue

These issues represent the major work items needed to bring OPAL to full production readiness with complete feature coverage as described in the user manual.
