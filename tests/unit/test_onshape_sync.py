"""Tests for Onshape pull and push sync engine, and document management."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from opal.db.models.onshape_link import OnshapeLink, OnshapeSyncLog
from opal.db.models.part import BOMLine, Part
from opal.integrations.onshape.client import OnshapeClient, parse_bom_item, resolve_header_value
from opal.integrations.onshape.models import (
    BOMParseWarning,
    OnshapeBOM,
    OnshapeBOMItem,
    OnshapeElement,
    OnshapePart,
)
from opal.integrations.onshape.sync import (
    ROOT_ASSEMBLY_MARKER,
    _compute_pull_hash,
    _compute_push_hash,
    _flatten_bom,
    _sync_bom_structure,
    pull_sync,
)
from opal.project import OnshapeConfig, OnshapeDocumentRef, ProjectConfig


@pytest.fixture
def doc_ref() -> OnshapeDocumentRef:
    """Create a test document reference."""
    return OnshapeDocumentRef(
        name="Test Assembly",
        document_id="doc123",
        workspace_id="ws456",
        element_id="elem789",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock OnshapeClient."""
    client = MagicMock()
    client.get_document.return_value = MagicMock(default_workspace_id="ws456")
    # Return empty metadata so auto-push after pull is a graceful no-op
    client.get_metadata.return_value = []
    return client


class TestHashFunctions:
    """Test change detection hash functions."""

    def test_pull_hash_deterministic(self) -> None:
        h1 = _compute_pull_hash("Bracket", "A bracket", "BRK-001")
        h2 = _compute_pull_hash("Bracket", "A bracket", "BRK-001")
        assert h1 == h2

    def test_pull_hash_changes_on_name(self) -> None:
        h1 = _compute_pull_hash("Bracket", None, None)
        h2 = _compute_pull_hash("Bracket v2", None, None)
        assert h1 != h2

    def test_push_hash_deterministic(self) -> None:
        h1 = _compute_push_hash("PN-001", "Mechanical", 1)
        h2 = _compute_push_hash("PN-001", "Mechanical", 1)
        assert h1 == h2

    def test_push_hash_changes_on_pn(self) -> None:
        h1 = _compute_push_hash("PN-001", None, 1)
        h2 = _compute_push_hash("PN-002", None, 1)
        assert h1 != h2


class TestPullSync:
    """Test pull_sync function."""

    def test_creates_new_parts(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync creates OPAL parts for new Onshape parts."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="Bracket",
                    part_number="BRK-001",
                    description="A mounting bracket",
                    quantity=1,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "p2"},
                    part_id="p2",
                    part_name="Bolt M5x20",
                    quantity=4,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 3  # root assembly + 2 children
        assert sync_log.direction == "pull"
        assert sync_log.trigger == "manual"

        # Verify OPAL parts were created
        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        part_names = {p.name for p in parts}
        assert "Bracket" in part_names
        assert "Bolt M5x20" in part_names
        assert "Test Assembly" in part_names  # root assembly

        # Verify external_pn is set from Onshape part number
        bracket = next(p for p in parts if p.name == "Bracket")
        assert bracket.external_pn == "BRK-001"
        assert bracket.description == "A mounting bracket"
        bolt = next(p for p in parts if p.name == "Bolt M5x20")
        assert bolt.external_pn is None  # No part_number provided
        assert bolt.description is None

        # Verify OnshapeLinks were created (root + 2 components)
        links = db_session.query(OnshapeLink).all()
        assert len(links) == 3

    def test_updates_existing_parts(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync updates CAD-owned fields on existing parts."""
        # Create an existing part + link
        part = Part(name="Old Name", internal_pn="PN-1-0001", tier=1)
        db_session.add(part)
        db_session.flush()

        link = OnshapeLink(
            part_id=part.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape="p1",
            onshape_name="Old Name",
            pull_hash="old-hash",
        )
        db_session.add(link)
        db_session.flush()

        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="New Name",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_updated == 1
        assert sync_log.parts_created == 1  # root assembly created

        # Verify name was updated
        db_session.refresh(part)
        assert part.name == "New Name"

        # Verify internal_pn was NOT changed (OPAL-owned)
        assert part.internal_pn == "PN-1-0001"

    def test_skips_unchanged_parts(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync skips parts whose Onshape data hasn't changed."""
        # Pre-create root assembly link so it isn't counted as new
        root = Part(name="Test Assembly", internal_pn="PN-1-0099", tier=1)
        db_session.add(root)
        db_session.flush()
        db_session.add(OnshapeLink(
            part_id=root.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape=ROOT_ASSEMBLY_MARKER,
            onshape_name="Test Assembly",
        ))
        db_session.flush()

        part = Part(name="Bracket", internal_pn="PN-1-0001", tier=1)
        db_session.add(part)
        db_session.flush()

        # Pre-compute the hash that the sync will generate
        expected_hash = _compute_pull_hash("Bracket", None, None)
        link = OnshapeLink(
            part_id=part.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape="p1",
            onshape_name="Bracket",
            pull_hash=expected_hash,
        )
        db_session.add(link)
        db_session.flush()

        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="Bracket",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_updated == 0
        assert sync_log.parts_created == 0

    def test_syncs_bom_structure(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync creates root assembly Part and BOM lines to children."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "child1"},
                    part_id="child1",
                    part_name="Bracket",
                    quantity=2,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "child2"},
                    part_id="child2",
                    part_name="Bolt",
                    quantity=4,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 3  # root assembly + 2 children
        assert sync_log.bom_lines_created == 2

        # Root assembly Part created from doc_ref.name
        root_link = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.part_id_onshape == ROOT_ASSEMBLY_MARKER)
            .first()
        )
        assert root_link is not None
        root_part = root_link.part
        assert root_part.name == "Test Assembly"

        # BOM lines should be children of the root assembly
        bom_lines = db_session.query(BOMLine).all()
        assert len(bom_lines) == 2
        for bl in bom_lines:
            assert bl.assembly_id == root_part.id

    def test_removes_bom_lines_for_removed_components(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync removes BOM lines when components are removed from Onshape BOM."""
        # Pre-create root assembly + 2 children with links and BOM lines
        root = Part(name="Test Assembly", internal_pn="PN-1-0001", tier=1)
        child1 = Part(name="Bracket", internal_pn="PN-1-0002", tier=1)
        child2 = Part(name="Bolt", internal_pn="PN-1-0003", tier=1)
        db_session.add_all([root, child1, child2])
        db_session.flush()

        # Create links (root uses marker, children have matching pull hashes)
        db_session.add(OnshapeLink(
            part_id=root.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape=ROOT_ASSEMBLY_MARKER,
            onshape_name="Test Assembly",
        ))
        for part, os_id in [(child1, "c1"), (child2, "c2")]:
            db_session.add(OnshapeLink(
                part_id=part.id,
                document_id="doc123",
                element_id="elem789",
                part_id_onshape=os_id,
                onshape_name=part.name,
                pull_hash=_compute_pull_hash(part.name, None, None),
            ))

        # Create BOM lines: root → child1, root → child2
        db_session.add(BOMLine(assembly_id=root.id, component_id=child1.id, quantity=2))
        db_session.add(BOMLine(assembly_id=root.id, component_id=child2.id, quantity=4))
        db_session.flush()

        # Return BOM without child2 — only child1 remains
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "c1"},
                    part_id="c1",
                    part_name="Bracket",
                    quantity=2,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.bom_lines_removed == 1
        assert sync_log.bom_lines_created == 0  # child1 BOM line already existed

        # child2's Part record should still exist (just BOM line removed)
        child2_still = db_session.query(Part).filter(Part.id == child2.id).first()
        assert child2_still is not None

    def test_handles_api_error(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync handles API errors gracefully."""
        from opal.integrations.onshape.client import OnshapeApiError

        mock_client.get_bom.side_effect = OnshapeApiError(500, "Internal server error")

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "error"
        assert sync_log.errors is not None

    def test_creates_sync_log(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync always creates a sync log entry."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.id is not None
        assert sync_log.started_at is not None
        assert sync_log.completed_at is not None

        # Verify it's in the database
        logs = db_session.query(OnshapeSyncLog).all()
        assert len(logs) == 1

    def test_auto_pushes_pns_for_new_parts(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync auto-pushes PNs to Onshape for newly created parts."""
        from opal.integrations.onshape.models import OnshapeMetadataProperty

        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="Bracket",
                    quantity=1,
                    children=[],
                ),
            ],
        )
        # Return metadata with a "Part Number" property so push can resolve it
        mock_client.get_metadata.return_value = [
            OnshapeMetadataProperty(
                name="Part Number", value="", property_id="prop-pn-id"
            ),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 2  # root assembly + bracket

        # Verify auto-push happened: set_metadata was called with the new PN
        mock_client.set_metadata.assert_called_once()
        call_kwargs = mock_client.set_metadata.call_args
        props = call_kwargs.kwargs.get("properties") or call_kwargs[1].get("properties", [])
        # The pushed property should have the resolved property ID and the new PN value
        assert any(p["propertyId"] == "prop-pn-id" for p in props)
        assert any(p["value"].startswith("PN-") for p in props)

        # Verify both pull and push sync logs exist
        logs = db_session.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id).all()
        assert len(logs) == 2
        assert logs[0].direction == "pull"
        assert logs[1].direction == "push"
        assert logs[1].trigger == "auto"

    def test_no_auto_push_when_no_new_parts(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync does NOT auto-push when only updating existing parts."""
        part = Part(name="Old Name", internal_pn="PN-1-0001", tier=1)
        db_session.add(part)
        db_session.flush()

        link = OnshapeLink(
            part_id=part.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape="p1",
            onshape_name="Old Name",
            pull_hash="old-hash",
        )
        db_session.add(link)
        db_session.flush()

        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="New Name",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_updated == 1
        assert sync_log.parts_created == 1  # root assembly created

        # No auto-push should have happened (root not in new_part_ids)
        mock_client.set_metadata.assert_not_called()
        logs = db_session.query(OnshapeSyncLog).all()
        assert len(logs) == 1  # Only the pull log

    def test_get_bom_called_with_generate_if_absent(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync passes generateIfAbsent=true to get_bom for assemblies."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[],
        )

        with patch("opal.config.get_active_project", return_value=None):
            pull_sync(db_session, mock_client, doc_ref, user_id=1)

        mock_client.get_bom.assert_called_once_with(
            document_id="doc123",
            workspace_id="ws456",
            element_id="elem789",
        )

    def test_skips_standard_content_items(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync skips standard content items (fasteners, bearings, etc.)."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="Custom Bracket",
                    quantity=1,
                    is_standard_content=False,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "p2"},
                    part_id="p2",
                    part_name="M5x20 Socket Head Cap Screw",
                    quantity=8,
                    is_standard_content=True,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "p3"},
                    part_id="p3",
                    part_name="608ZZ Bearing",
                    quantity=2,
                    is_standard_content=True,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 2  # root assembly + custom bracket

        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        assert len(parts) == 2
        part_names = {p.name for p in parts}
        assert "Custom Bracket" in part_names

        # Standard content items should NOT have OnshapeLinks
        links = db_session.query(OnshapeLink).all()
        assert len(links) == 2
        link_ids = {lnk.part_id_onshape for lnk in links}
        assert "p1" in link_ids
        assert ROOT_ASSEMBLY_MARKER in link_ids

    def test_syncs_nested_assembly_bom(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync handles nested assemblies: Root → [Bracket, Sub-Asm → [Gear]]."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "bracket"},
                    part_id="bracket",
                    part_name="Bracket",
                    quantity=1,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "subasm"},
                    part_id="subasm",
                    part_name="Sub-Assembly",
                    quantity=1,
                    children=[
                        OnshapeBOMItem(
                            item_source={"partId": "gear"},
                            part_id="gear",
                            part_name="Gear",
                            quantity=2,
                            children=[],
                        ),
                    ],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 4  # root + bracket + subasm + gear
        assert sync_log.bom_lines_created == 3  # root→bracket, root→subasm, subasm→gear

        # Verify root assembly
        root_link = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.part_id_onshape == ROOT_ASSEMBLY_MARKER)
            .first()
        )
        assert root_link is not None

        # Verify BOM structure
        bom_lines = db_session.query(BOMLine).all()
        assert len(bom_lines) == 3

        # Root should have 2 children (bracket, subasm)
        root_children = [bl for bl in bom_lines if bl.assembly_id == root_link.part_id]
        assert len(root_children) == 2

        # Sub-assembly should have 1 child (gear)
        subasm_link = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.part_id_onshape == "subasm")
            .first()
        )
        subasm_children = [bl for bl in bom_lines if bl.assembly_id == subasm_link.part_id]
        assert len(subasm_children) == 1

    def test_root_assembly_not_auto_pushed(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Root assembly Part is not included in auto-push after pull sync."""
        from opal.integrations.onshape.models import OnshapeMetadataProperty

        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="Bracket",
                    quantity=1,
                    children=[],
                ),
            ],
        )
        mock_client.get_metadata.return_value = [
            OnshapeMetadataProperty(
                name="Part Number", value="", property_id="prop-pn-id"
            ),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.parts_created == 2  # root + bracket

        # get_metadata should only be called for the component, not the root
        assert mock_client.get_metadata.call_count == 1
        call_kwargs = mock_client.get_metadata.call_args.kwargs
        assert call_kwargs["part_id"] == "p1"

    def test_name_dedup_creates_single_part(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Two items with same part_name but different composite keys create one OPAL Part."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "JFD", "elementId": "elemA"},
                    source_element_id="elemA",
                    part_id="JFD",
                    part_name="51205K289_Fitting",
                    quantity=1,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "JFH", "elementId": "elemB"},
                    source_element_id="elemB",
                    part_id="JFH",
                    part_name="51205K289_Fitting",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        # root assembly + 1 fitting (not 2)
        assert sync_log.parts_created == 2

        # Only one Part with that name
        fittings = (
            db_session.query(Part)
            .filter(Part.name == "51205K289_Fitting", Part.deleted_at.is_(None))
            .all()
        )
        assert len(fittings) == 1

        # Only one OnshapeLink for that part (first occurrence gets the link)
        links = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.part_id_onshape.in_(["JFD", "JFH"]))
            .all()
        )
        assert len(links) == 1

    def test_name_dedup_bom_qty_accumulation(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Same-name items from different coordinates produce 1 BOM line with accumulated qty."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "JFD", "elementId": "elemA"},
                    source_element_id="elemA",
                    part_id="JFD",
                    part_name="51205K289_Fitting",
                    quantity=1,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "JFH", "elementId": "elemB"},
                    source_element_id="elemB",
                    part_id="JFH",
                    part_name="51205K289_Fitting",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.bom_lines_created == 1  # One BOM line, not two

        bom_lines = db_session.query(BOMLine).all()
        fitting_lines = [bl for bl in bom_lines if bl.quantity == 2]
        assert len(fitting_lines) == 1  # qty=1+1=2

    def test_name_dedup_re_sync_stable(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Syncing twice with same-name items doesn't create duplicate Parts on second sync."""
        bom = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "JFD", "elementId": "elemA"},
                    source_element_id="elemA",
                    part_id="JFD",
                    part_name="51205K289_Fitting",
                    quantity=1,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "JFH", "elementId": "elemB"},
                    source_element_id="elemB",
                    part_id="JFH",
                    part_name="51205K289_Fitting",
                    quantity=1,
                    children=[],
                ),
            ],
        )
        mock_client.get_bom.return_value = bom

        with patch("opal.config.get_active_project", return_value=None):
            log1 = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert log1.status == "success"
        parts_after_first = (
            db_session.query(Part).filter(Part.deleted_at.is_(None)).count()
        )

        # Second sync — same BOM
        mock_client.get_bom.return_value = bom
        with patch("opal.config.get_active_project", return_value=None):
            log2 = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert log2.status == "success"
        assert log2.parts_created == 0  # No new parts on re-sync

        parts_after_second = (
            db_session.query(Part).filter(Part.deleted_at.is_(None)).count()
        )
        assert parts_after_second == parts_after_first


class TestPullSyncPartStudio:
    """Test pull_sync with part studio elements."""

    @pytest.fixture
    def ps_doc_ref(self) -> OnshapeDocumentRef:
        """Create a part studio document reference."""
        return OnshapeDocumentRef(
            name="Test Part Studio",
            document_id="doc123",
            workspace_id="ws456",
            element_id="elem789",
            element_type="part_studio",
        )

    def test_creates_parts_from_part_studio(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync creates OPAL parts from part studio, calls get_parts (not get_bom)."""
        mock_client.get_parts.return_value = [
            OnshapePart(part_id="p1", name="Bracket", part_number="BRK-001"),
            OnshapePart(part_id="p2", name="Spacer", part_number="SPC-001"),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 2

        # get_parts should be called, not get_bom
        mock_client.get_parts.assert_called_once_with(
            document_id="doc123", workspace_id="ws456", element_id="elem789",
        )
        mock_client.get_bom.assert_not_called()

        # No BOM lines for part studios (flat list, no hierarchy)
        assert sync_log.bom_lines_created == 0
        assert sync_log.bom_lines_updated == 0
        assert sync_log.bom_lines_removed == 0

        # Verify parts exist
        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        assert {p.name for p in parts} == {"Bracket", "Spacer"}

        # Verify links exist
        links = db_session.query(OnshapeLink).all()
        assert len(links) == 2

    def test_part_studio_updates_existing_parts(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """Part studio sync updates existing linked parts when hash changes."""
        # Create existing part + link
        part = Part(name="Old Bracket", internal_pn="PN-1-0001", tier=1)
        db_session.add(part)
        db_session.flush()

        link = OnshapeLink(
            part_id=part.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape="p1",
            onshape_name="Old Bracket",
            pull_hash="old-hash",
        )
        db_session.add(link)
        db_session.flush()

        mock_client.get_parts.return_value = [
            OnshapePart(part_id="p1", name="New Bracket", part_number="BRK-001"),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_updated == 1
        assert sync_log.parts_created == 0

        db_session.refresh(part)
        assert part.name == "New Bracket"
        assert part.internal_pn == "PN-1-0001"  # OPAL-owned, unchanged

    def test_empty_response_shows_diagnostics(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """When API returns 0 parts, summary includes diagnostic detail."""
        mock_client.get_parts.return_value = []

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 0
        assert "API returned 0 items" in sync_log.summary

    def test_unchanged_parts_shows_diagnostics(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """When all parts are unchanged, summary shows already-linked count."""
        # Create existing parts with matching hashes
        part1 = Part(name="Bracket", internal_pn="PN-1-0001", tier=1)
        part2 = Part(name="Spacer", internal_pn="PN-1-0002", tier=1)
        db_session.add_all([part1, part2])
        db_session.flush()

        for part, os_id, pn in [(part1, "p1", "BRK-001"), (part2, "p2", "SPC-001")]:
            db_session.add(OnshapeLink(
                part_id=part.id,
                document_id="doc123",
                element_id="elem789",
                part_id_onshape=os_id,
                onshape_name=part.name,
                pull_hash=_compute_pull_hash(part.name, None, pn),
            ))
        db_session.flush()

        mock_client.get_parts.return_value = [
            OnshapePart(part_id="p1", name="Bracket", part_number="BRK-001"),
            OnshapePart(part_id="p2", name="Spacer", part_number="SPC-001"),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 0
        assert sync_log.parts_updated == 0
        assert "2 parts already linked" in sync_log.summary
        # No API diagnostic when items were returned
        assert "API returned" not in sync_log.summary

    def test_restores_soft_deleted_parts(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync restores soft-deleted parts that are still in Onshape."""
        from datetime import UTC, datetime

        part = Part(
            name="Bracket", internal_pn="PN-1-0001", tier=1,
            deleted_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        db_session.add(part)
        db_session.flush()

        link = OnshapeLink(
            part_id=part.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape="p1",
            onshape_name="Bracket",
            pull_hash=_compute_pull_hash("Bracket", None, "BRK-001"),
        )
        db_session.add(link)
        db_session.flush()

        mock_client.get_parts.return_value = [
            OnshapePart(part_id="p1", name="Bracket", part_number="BRK-001"),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert "1 restored" in sync_log.summary

        # Part should no longer be soft-deleted
        db_session.refresh(part)
        assert part.deleted_at is None

    def test_creates_parts_with_description_and_material(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """Part studio sync populates Part.description and Part.metadata_ with material."""
        mock_client.get_parts.return_value = [
            OnshapePart(
                part_id="p1",
                name="Bracket",
                part_number="BRK-001",
                description="A mounting bracket",
                material="6061 Aluminum",
            ),
            OnshapePart(
                part_id="p2",
                name="Spacer",
                part_number="SPC-001",
                description=None,
                material=None,
            ),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 2

        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        bracket = next(p for p in parts if p.name == "Bracket")
        assert bracket.description == "A mounting bracket"
        assert bracket.metadata_ == {"material": "6061 Aluminum"}

        spacer = next(p for p in parts if p.name == "Spacer")
        assert spacer.description is None
        assert spacer.metadata_ is None

    def test_empty_part_studio_does_not_mark_links_stale(
        self, db_session: Session, mock_client: MagicMock, ps_doc_ref: OnshapeDocumentRef
    ) -> None:
        """Empty API response should NOT mark existing links as stale."""
        # Create an existing part + link for this element
        part = Part(name="Bracket", internal_pn="PN-1-0001", tier=1)
        db_session.add(part)
        db_session.flush()

        link = OnshapeLink(
            part_id=part.id,
            document_id="doc123",
            element_id="elem789",
            part_id_onshape="p1",
            onshape_name="Bracket",
            pull_hash=_compute_pull_hash("Bracket", None, "BRK-001"),
            stale=False,
        )
        db_session.add(link)
        db_session.flush()

        # API returns 0 parts
        mock_client.get_parts.return_value = []

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, ps_doc_ref, user_id=1)

        assert sync_log.status == "success"

        # Existing link should NOT be marked stale
        db_session.refresh(link)
        assert link.stale is False

    def test_assembly_still_calls_get_bom(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Default element_type='assembly' still uses get_bom, not get_parts."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[],
        )

        with patch("opal.config.get_active_project", return_value=None):
            pull_sync(db_session, mock_client, doc_ref, user_id=1)

        mock_client.get_bom.assert_called_once()
        mock_client.get_parts.assert_not_called()


class TestMultiElementSync:
    """Test that sync correctly scopes links by element_id."""

    def test_separate_links_per_element(
        self, db_session: Session, mock_client: MagicMock
    ) -> None:
        """Two part studios in the same document with colliding part IDs create separate parts."""
        doc_ref_a = OnshapeDocumentRef(
            name="Part Studio A",
            document_id="doc123",
            workspace_id="ws456",
            element_id="elemAAA",
            element_type="part_studio",
        )
        doc_ref_b = OnshapeDocumentRef(
            name="Part Studio B",
            document_id="doc123",
            workspace_id="ws456",
            element_id="elemBBB",
            element_type="part_studio",
        )

        # Both part studios return a part with the same Onshape part_id "JHD"
        mock_client.get_parts.return_value = [
            OnshapePart(part_id="JHD", name="Bracket A", part_number="BRK-A"),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            log_a = pull_sync(db_session, mock_client, doc_ref_a, user_id=1)

        assert log_a.status == "success"
        assert log_a.parts_created == 1

        # Second studio — same part_id "JHD" but different element
        mock_client.get_parts.return_value = [
            OnshapePart(part_id="JHD", name="Bracket B", part_number="BRK-B"),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            log_b = pull_sync(db_session, mock_client, doc_ref_b, user_id=1)

        assert log_b.status == "success"
        assert log_b.parts_created == 1  # Should create a NEW part, not skip

        # Verify two separate OnshapeLink records with different element_ids
        links = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.document_id == "doc123", OnshapeLink.part_id_onshape == "JHD")
            .all()
        )
        assert len(links) == 2
        element_ids = {link.element_id for link in links}
        assert element_ids == {"elemAAA", "elemBBB"}

        # Verify two distinct OPAL parts were created
        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        assert len(parts) == 2
        assert {p.name for p in parts} == {"Bracket A", "Bracket B"}

    def test_stale_marking_scoped_to_element(
        self, db_session: Session, mock_client: MagicMock
    ) -> None:
        """Syncing element B does not mark element A's links as stale."""
        # Create a part linked to element A
        part_a = Part(name="Part A", internal_pn="PN-1-0001", tier=1)
        db_session.add(part_a)
        db_session.flush()

        link_a = OnshapeLink(
            part_id=part_a.id,
            document_id="doc123",
            element_id="elemAAA",
            part_id_onshape="JHD",
            onshape_name="Part A",
            pull_hash=_compute_pull_hash("Part A", None, None),
            stale=False,
        )
        db_session.add(link_a)
        db_session.flush()

        # Sync element B (which has no part "JHD")
        doc_ref_b = OnshapeDocumentRef(
            name="Part Studio B",
            document_id="doc123",
            workspace_id="ws456",
            element_id="elemBBB",
            element_type="part_studio",
        )
        mock_client.get_parts.return_value = [
            OnshapePart(part_id="XYZ", name="Other Part", part_number=None),
        ]

        with patch("opal.config.get_active_project", return_value=None):
            pull_sync(db_session, mock_client, doc_ref_b, user_id=1)

        # Element A's link should NOT be marked stale
        db_session.refresh(link_a)
        assert link_a.stale is False


class TestDocumentManagementAPI:
    """Test add/remove document API endpoints."""

    def _make_project(self, tmp_path: "Path") -> ProjectConfig:
        """Create a minimal project config with a temp directory."""
        config = ProjectConfig(
            name="Test Project",
            onshape=OnshapeConfig(documents=[]),
        )
        config.project_dir = tmp_path
        return config

    def test_add_document_success(self, client, tmp_path: "Path") -> None:
        """POST /api/onshape/documents adds a document when URL is valid."""
        project = self._make_project(tmp_path)
        mock_elements = [
            OnshapeElement(id="elem789", name="Main Assembly", element_type="ASSEMBLY"),
            OnshapeElement(id="other", name="Part Studio 1", element_type="PARTSTUDIO"),
        ]

        with (
            patch("opal.config.get_active_settings") as mock_settings,
            patch("opal.config.get_active_project", return_value=project),
            patch("opal.integrations.onshape.client.OnshapeClient") as MockClient,
            patch("opal.project.save_project_config"),
        ):
            mock_settings.return_value = MagicMock(
                onshape_enabled=True,
                onshape_access_key="key",
                onshape_secret_key="secret",
                onshape_base_url="https://cad.onshape.com",
            )
            mock_inst = MockClient.return_value
            mock_inst.get_elements.return_value = mock_elements

            resp = client.post(
                "/api/onshape/documents",
                json={
                    "url": "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Main Assembly"
        assert data["document_id"] == "abc123"
        assert data["element_id"] == "elem789"
        assert data["element_type"] == "assembly"
        assert data["auto_sync"] is True

    def test_add_document_invalid_url(self, client, tmp_path: "Path") -> None:
        """POST /api/onshape/documents rejects invalid URLs."""
        project = self._make_project(tmp_path)

        with (
            patch("opal.config.get_active_settings") as mock_settings,
            patch("opal.config.get_active_project", return_value=project),
        ):
            mock_settings.return_value = MagicMock(onshape_enabled=True)

            resp = client.post(
                "/api/onshape/documents",
                json={"url": "https://example.com/not-onshape"},
            )

        assert resp.status_code == 422

    def test_add_document_duplicate(self, client, tmp_path: "Path") -> None:
        """POST /api/onshape/documents rejects duplicates."""
        project = self._make_project(tmp_path)
        project.onshape.documents.append(
            OnshapeDocumentRef(
                name="Existing",
                document_id="abc123",
                workspace_id="ws456",
                element_id="elem789",
            )
        )

        with (
            patch("opal.config.get_active_settings") as mock_settings,
            patch("opal.config.get_active_project", return_value=project),
        ):
            mock_settings.return_value = MagicMock(onshape_enabled=True)

            resp = client.post(
                "/api/onshape/documents",
                json={
                    "url": "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789",
                },
            )

        assert resp.status_code == 409

    def test_add_document_with_name_override(self, client, tmp_path: "Path") -> None:
        """POST /api/onshape/documents uses name override when provided."""
        project = self._make_project(tmp_path)
        mock_elements = [
            OnshapeElement(id="elem789", name="Auto Name", element_type="ASSEMBLY"),
        ]

        with (
            patch("opal.config.get_active_settings") as mock_settings,
            patch("opal.config.get_active_project", return_value=project),
            patch("opal.integrations.onshape.client.OnshapeClient") as MockClient,
            patch("opal.project.save_project_config"),
        ):
            mock_settings.return_value = MagicMock(
                onshape_enabled=True,
                onshape_access_key="key",
                onshape_secret_key="secret",
                onshape_base_url="https://cad.onshape.com",
            )
            mock_inst = MockClient.return_value
            mock_inst.get_elements.return_value = mock_elements

            resp = client.post(
                "/api/onshape/documents",
                json={
                    "url": "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789",
                    "name": "My Custom Name",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "My Custom Name"

    def test_remove_document_success(self, client, tmp_path: "Path") -> None:
        """DELETE /api/onshape/documents/{did}/{eid} removes a document."""
        project = self._make_project(tmp_path)
        project.onshape.documents.append(
            OnshapeDocumentRef(
                name="To Remove",
                document_id="abc123",
                workspace_id="ws456",
                element_id="elem789",
            )
        )

        with (
            patch("opal.config.get_active_project", return_value=project),
            patch("opal.project.save_project_config"),
        ):
            resp = client.delete("/api/onshape/documents/abc123/elem789")

        assert resp.status_code == 204
        assert len(project.onshape.documents) == 0

    def test_remove_document_not_found(self, client, tmp_path: "Path") -> None:
        """DELETE /api/onshape/documents/{did}/{eid} returns 404 for missing doc."""
        project = self._make_project(tmp_path)

        with patch("opal.config.get_active_project", return_value=project):
            resp = client.delete("/api/onshape/documents/nonexistent/elem")

        assert resp.status_code == 404

    def test_add_document_part_studio(self, client, tmp_path: "Path") -> None:
        """POST /api/onshape/documents correctly detects part_studio type."""
        project = self._make_project(tmp_path)
        mock_elements = [
            OnshapeElement(id="elem789", name="My Part Studio", element_type="PARTSTUDIO"),
        ]

        with (
            patch("opal.config.get_active_settings") as mock_settings,
            patch("opal.config.get_active_project", return_value=project),
            patch("opal.integrations.onshape.client.OnshapeClient") as MockClient,
            patch("opal.project.save_project_config"),
        ):
            mock_settings.return_value = MagicMock(
                onshape_enabled=True,
                onshape_access_key="key",
                onshape_secret_key="secret",
                onshape_base_url="https://cad.onshape.com",
            )
            mock_inst = MockClient.return_value
            mock_inst.get_elements.return_value = mock_elements

            resp = client.post(
                "/api/onshape/documents",
                json={
                    "url": "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["element_type"] == "part_studio"


class TestBomParsing:
    """Test BOM API response parsing at the client level.

    These tests instantiate a real OnshapeClient but mock _request() to return
    raw dicts, testing the actual parsing code path that was previously untested.
    """

    def _make_client(self) -> OnshapeClient:
        return OnshapeClient(access_key="fake", secret_key="fake")

    def test_parses_bom_items_standard_format(self) -> None:
        """get_bom correctly parses standard bomTable.items format."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "name": "Bracket",
                        "partNumber": "BRK-001",
                        "quantity": 2,
                        "children": [],
                    },
                    {
                        "itemSource": {"partId": "p2"},
                        "name": "Bolt",
                        "quantity": 8,
                        "isStandardContent": True,
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 2
        assert bom.items[0].part_id == "p1"
        assert bom.items[0].part_name == "Bracket"
        assert bom.items[0].part_number == "BRK-001"
        assert bom.items[0].quantity == 2
        assert bom.items[0].is_standard_content is False
        assert bom.items[1].part_id == "p2"
        assert bom.items[1].is_standard_content is True

    def test_parses_bom_rows_fallback(self) -> None:
        """get_bom falls back to bomTable.rows if items is missing."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "rows": [
                    {
                        "itemSource": {"partId": "r1"},
                        "name": "Gear",
                        "quantity": 1,
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 1
        assert bom.items[0].part_id == "r1"
        assert bom.items[0].part_name == "Gear"

    def test_parses_top_level_items_fallback(self) -> None:
        """get_bom falls back to top-level items if bomTable is missing."""
        client = self._make_client()
        raw_response = {
            "items": [
                {
                    "itemSource": {"partId": "t1"},
                    "name": "Plate",
                    "quantity": 1,
                    "children": [],
                },
            ],
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 1
        assert bom.items[0].part_id == "t1"
        assert bom.items[0].part_name == "Plate"

    def test_parses_nested_children(self) -> None:
        """get_bom correctly parses nested children within items."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "items": [
                    {
                        "itemSource": {"partId": "asm1"},
                        "name": "Sub-Assembly",
                        "quantity": 1,
                        "children": [
                            {
                                "itemSource": {"partId": "child1"},
                                "name": "Pin",
                                "quantity": 4,
                                "children": [],
                            },
                        ],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 1
        assert len(bom.items[0].children) == 1
        assert bom.items[0].children[0].part_id == "child1"
        assert bom.items[0].children[0].part_name == "Pin"
        assert bom.items[0].children[0].quantity == 4

    def test_parses_quantity_as_string(self) -> None:
        """get_bom handles quantity provided as string or float."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "name": "Part A",
                        "quantity": "3",
                        "children": [],
                    },
                    {
                        "itemSource": {"partId": "p2"},
                        "name": "Part B",
                        "quantity": 2.0,
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.items[0].quantity == 3
        assert bom.items[1].quantity == 2

    def test_part_id_fallback_to_top_level(self) -> None:
        """get_bom falls back to top-level partId when itemSource.partId is empty."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "items": [
                    {
                        "itemSource": {},
                        "partId": "fallback-id",
                        "name": "Widget",
                        "quantity": 1,
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.items[0].part_id == "fallback-id"

    def test_empty_bom_table(self) -> None:
        """get_bom returns empty items when response has no items anywhere."""
        client = self._make_client()
        raw_response = {"bomTable": {}}
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 0

    def test_parses_header_based_format(self) -> None:
        """get_bom correctly parses real Onshape header-based BOM format."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "hdr-name", "name": "Name", "propertyName": "name"},
                    {"id": "hdr-qty", "name": "Quantity", "propertyName": "quantity"},
                    {"id": "hdr-pn", "name": "Part number", "propertyName": "partNumber"},
                    {"id": "hdr-desc", "name": "Description", "propertyName": "description"},
                ],
                "items": [
                    {
                        "itemSource": {
                            "documentId": "doc1",
                            "elementId": "e1",
                            "partId": "abc123",
                            "wvmType": "w",
                            "wvmId": "ws1",
                        },
                        "headerIdToValue": {
                            "hdr-name": "Bracket",
                            "hdr-qty": "2",
                            "hdr-pn": "BRK-001",
                            "hdr-desc": "A bracket",
                        },
                        "isStandardContent": False,
                        "children": [],
                    },
                    {
                        "itemSource": {
                            "documentId": "doc1",
                            "elementId": "e2",
                            "partId": "def456",
                        },
                        "headerIdToValue": {
                            "hdr-name": "Spacer",
                            "hdr-qty": "4",
                            "hdr-pn": "",
                            "hdr-desc": "",
                        },
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 2

        assert bom.items[0].part_id == "abc123"
        assert bom.items[0].part_name == "Bracket"
        assert bom.items[0].part_number == "BRK-001"
        assert bom.items[0].description == "A bracket"
        assert bom.items[0].quantity == 2
        assert bom.items[0].is_standard_content is False

        assert bom.items[1].part_id == "def456"
        assert bom.items[1].part_name == "Spacer"
        assert bom.items[1].quantity == 4
        assert bom.items[1].part_number is None  # empty string → None
        assert bom.items[1].description is None  # empty string → None

    def test_parses_description_from_headers(self) -> None:
        """get_bom extracts description from headerIdToValue."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "h-name", "name": "Name", "propertyName": "name"},
                    {"id": "h-qty", "name": "Quantity", "propertyName": "quantity"},
                    {"id": "h-desc", "name": "Description", "propertyName": "description"},
                ],
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "headerIdToValue": {
                            "h-name": "Bracket",
                            "h-qty": "1",
                            "h-desc": "A mounting bracket",
                        },
                        "children": [],
                    },
                    {
                        "itemSource": {"partId": "p2"},
                        "headerIdToValue": {
                            "h-name": "Spacer",
                            "h-qty": "2",
                            "h-desc": "",
                        },
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.items[0].description == "A mounting bracket"
        assert bom.items[1].description is None  # empty string → None

    def test_subassembly_uses_element_id_as_part_id(self) -> None:
        """Sub-assemblies without partId fall back to elementId."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "h1", "name": "Name", "propertyName": "name"},
                    {"id": "h2", "name": "Quantity", "propertyName": "quantity"},
                ],
                "items": [
                    {
                        "itemSource": {
                            "documentId": "doc1",
                            "elementId": "subasm-elem-id",
                            # no partId — this is a sub-assembly
                        },
                        "headerIdToValue": {
                            "h1": "Drive Sub-Assembly",
                            "h2": "1",
                        },
                        "children": [
                            {
                                "itemSource": {"partId": "gear1"},
                                "headerIdToValue": {
                                    "h1": "Gear",
                                    "h2": "3",
                                },
                                "children": [],
                            },
                        ],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 1
        # Sub-assembly should use elementId as part_id
        assert bom.items[0].part_id == "subasm-elem-id"
        assert bom.items[0].part_name == "Drive Sub-Assembly"
        assert bom.items[0].quantity == 1

        # Child should still use partId normally
        assert len(bom.items[0].children) == 1
        assert bom.items[0].children[0].part_id == "gear1"
        assert bom.items[0].children[0].part_name == "Gear"
        assert bom.items[0].children[0].quantity == 3

    def test_parses_header_dict_values(self) -> None:
        """get_bom correctly unwraps dict-wrapped headerIdToValue entries."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "h-name", "name": "Name", "propertyName": "name"},
                    {"id": "h-qty", "name": "Quantity", "propertyName": "quantity"},
                    {"id": "h-pn", "name": "Part number", "propertyName": "partNumber"},
                    {"id": "h-desc", "name": "Description", "propertyName": "description"},
                ],
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "headerIdToValue": {
                            "h-name": {"value": "Bracket"},
                            "h-qty": {"value": "3"},
                            "h-pn": {"value": "BRK-001"},
                            "h-desc": {"value": "A mounting bracket"},
                        },
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 1
        assert bom.items[0].part_name == "Bracket"
        assert bom.items[0].part_number == "BRK-001"
        assert bom.items[0].description == "A mounting bracket"
        assert bom.items[0].quantity == 3

    def test_parses_header_mixed_value_types(self) -> None:
        """get_bom handles mixed string/int/float/dict values in the same BOM."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "h-name", "name": "Name", "propertyName": "name"},
                    {"id": "h-qty", "name": "Quantity", "propertyName": "quantity"},
                    {"id": "h-pn", "name": "Part number", "propertyName": "partNumber"},
                ],
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "headerIdToValue": {
                            "h-name": {"value": "Bracket"},
                            "h-qty": 5,
                            "h-pn": "BRK-001",
                        },
                        "children": [],
                    },
                    {
                        "itemSource": {"partId": "p2"},
                        "headerIdToValue": {
                            "h-name": "Spacer",
                            "h-qty": 2.0,
                            "h-pn": {"value": "SPC-001"},
                        },
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.items[0].part_name == "Bracket"
        assert bom.items[0].quantity == 5
        assert bom.items[0].part_number == "BRK-001"

        assert bom.items[1].part_name == "Spacer"
        assert bom.items[1].quantity == 2
        assert bom.items[1].part_number == "SPC-001"

    def test_unparseable_quantity_defaults_to_one(self) -> None:
        """Garbage quantity string defaults to 1 and logs a warning."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "h-name", "name": "Name", "propertyName": "name"},
                    {"id": "h-qty", "name": "Quantity", "propertyName": "quantity"},
                ],
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "headerIdToValue": {
                            "h-name": "Widget",
                            "h-qty": "not-a-number",
                        },
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.items[0].quantity == 1
        assert bom.items[0].part_name == "Widget"

    def test_parses_flat_indent_level_rows(self) -> None:
        """get_bom reconstructs hierarchy from flat rows with indentLevel (v6 API)."""
        client = self._make_client()
        raw_response = {
            "headers": [
                {"id": "h-name", "name": "Name", "propertyName": "name"},
                {"id": "h-qty", "name": "Quantity", "propertyName": "quantity"},
            ],
            "rows": [
                {
                    "indentLevel": 0,
                    "itemSource": {"elementId": "subasm-eid", "partId": ""},
                    "headerIdToValue": {"h-name": "Sub-Assembly", "h-qty": "1"},
                },
                {
                    "indentLevel": 1,
                    "itemSource": {"elementId": "ps1", "partId": "child1"},
                    "headerIdToValue": {"h-name": "Injector", "h-qty": "1"},
                },
                {
                    "indentLevel": 1,
                    "itemSource": {"elementId": "ps2", "partId": "child2"},
                    "headerIdToValue": {"h-name": "O-ring", "h-qty": "2"},
                },
                {
                    "indentLevel": 0,
                    "itemSource": {"elementId": "ps3", "partId": "chamber"},
                    "headerIdToValue": {"h-name": "Chamber", "h-qty": "1"},
                },
            ],
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        # Top level should have 2 items: Sub-Assembly and Chamber
        assert len(bom.items) == 2
        assert bom.items[0].part_name == "Sub-Assembly"
        assert bom.items[1].part_name == "Chamber"

        # Sub-Assembly should have 2 children
        assert len(bom.items[0].children) == 2
        assert bom.items[0].children[0].part_name == "Injector"
        assert bom.items[0].children[0].part_id == "child1"
        assert bom.items[0].children[1].part_name == "O-ring"
        assert bom.items[0].children[1].quantity == 2

        # Chamber should have no children
        assert len(bom.items[1].children) == 0

    def test_parses_deeply_nested_indent_levels(self) -> None:
        """get_bom handles 3+ levels of indentLevel nesting."""
        client = self._make_client()
        raw_response = {
            "rows": [
                {"indentLevel": 0, "itemSource": {"partId": "L0"}, "name": "Level 0"},
                {"indentLevel": 1, "itemSource": {"partId": "L1"}, "name": "Level 1"},
                {"indentLevel": 2, "itemSource": {"partId": "L2"}, "name": "Level 2"},
                {"indentLevel": 0, "itemSource": {"partId": "L0b"}, "name": "Level 0b"},
            ],
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert len(bom.items) == 2  # Two top-level items
        assert len(bom.items[0].children) == 1  # L0 has one child
        assert len(bom.items[0].children[0].children) == 1  # L1 has one child
        assert bom.items[0].children[0].children[0].part_id == "L2"

    def test_get_bom_populates_warnings_and_header_map(self) -> None:
        """get_bom returns warnings and header_map on the OnshapeBOM model."""
        client = self._make_client()
        raw_response = {
            "bomTable": {
                "headers": [
                    {"id": "h-name", "name": "Name", "propertyName": "name"},
                    {"id": "h-qty", "name": "Quantity", "propertyName": "quantity"},
                ],
                "items": [
                    {
                        "itemSource": {},
                        "headerIdToValue": {
                            "h-name": "Widget",
                            "h-qty": "1",
                        },
                        "children": [],
                    },
                ],
            },
        }
        with patch.object(client, "_request", return_value=raw_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.header_map == {"h-name": "name", "h-qty": "quantity"}
        # Item has empty part_id → should produce a warning
        assert len(bom.warnings) >= 1
        assert any(w.field == "part_id" for w in bom.warnings)


class TestResolveHeaderValue:
    """Test the extracted resolve_header_value function."""

    def test_simple_string_value(self) -> None:
        raw = {"headerIdToValue": {"hdr-1": "Bracket"}}
        header_map = {"hdr-1": "name"}
        assert resolve_header_value(raw, header_map, "name") == "Bracket"

    def test_dict_wrapped_value(self) -> None:
        raw = {"headerIdToValue": {"hdr-1": {"value": "Spacer"}}}
        header_map = {"hdr-1": "name"}
        assert resolve_header_value(raw, header_map, "name") == "Spacer"

    def test_no_header_id_to_value_returns_empty(self) -> None:
        raw = {"someOtherKey": "data"}
        header_map = {"hdr-1": "name"}
        assert resolve_header_value(raw, header_map, "name") == ""

    def test_unknown_prop_name_returns_empty(self) -> None:
        raw = {"headerIdToValue": {"hdr-1": "Bracket"}}
        header_map = {"hdr-1": "name"}
        assert resolve_header_value(raw, header_map, "nonexistent") == ""

    def test_numeric_value_converted_to_string(self) -> None:
        raw = {"headerIdToValue": {"hdr-1": 42}}
        header_map = {"hdr-1": "quantity"}
        assert resolve_header_value(raw, header_map, "quantity") == "42"

    def test_none_value_skipped(self) -> None:
        raw = {"headerIdToValue": {"hdr-1": None, "hdr-2": "fallback"}}
        header_map = {"hdr-1": "name", "hdr-2": "name"}
        assert resolve_header_value(raw, header_map, "name") == "fallback"


class TestParseBomItem:
    """Test the extracted parse_bom_item function."""

    def test_warns_on_empty_part_id(self) -> None:
        warnings: list[BOMParseWarning] = []
        raw = {"itemSource": {}, "children": []}
        parse_bom_item(raw, {}, warnings, item_index=0)
        assert any(w.field == "part_id" for w in warnings)

    def test_warns_on_empty_part_name_non_standard(self) -> None:
        warnings: list[BOMParseWarning] = []
        raw = {"itemSource": {"partId": "abc"}, "children": []}
        parse_bom_item(raw, {}, warnings, item_index=0)
        assert any(w.field == "part_name" for w in warnings)

    def test_no_warning_for_standard_content_empty_name(self) -> None:
        warnings: list[BOMParseWarning] = []
        raw = {
            "itemSource": {"partId": "abc"},
            "isStandardContent": True,
            "children": [],
        }
        parse_bom_item(raw, {}, warnings, item_index=0)
        assert not any(w.field == "part_name" for w in warnings)

    def test_part_number_with_space_in_property_name(self) -> None:
        """Header with propertyName 'Part Number' lowercases to 'part number'."""
        warnings: list[BOMParseWarning] = []
        header_map = {"hdr-pn": "part number", "hdr-name": "name"}
        raw = {
            "itemSource": {"partId": "p1"},
            "headerIdToValue": {
                "hdr-pn": "PN-123",
                "hdr-name": "Widget",
            },
            "children": [],
        }
        item = parse_bom_item(raw, header_map, warnings, item_index=0)
        assert item.part_number == "PN-123"
        assert item.part_name == "Widget"


class TestSyncBomStructure:
    """Test the extracted _sync_bom_structure function."""

    def test_cycle_detection(self, db_session: Session) -> None:
        """Cycle detection returns (0,0,0) when visited set already contains target."""
        # The function should short-circuit and return zeros
        created, updated, removed = _sync_bom_structure(
            db=db_session,
            bom_items=[],
            assembly_part_id=42,
            onshape_to_opal={},
            user_id=1,
            visited={42},
        )
        assert (created, updated, removed) == (0, 0, 0)

    def test_bom_line_deletion_creates_audit_log(
        self, db_session: Session,
    ) -> None:
        """BOM line deletion creates an audit log entry."""
        from opal.db.models.audit import AuditLog

        # Create assembly + component parts
        assembly = Part(name="Assembly", internal_pn="PN-1-0001", tier=1)
        component = Part(name="Old Part", internal_pn="PN-1-0002", tier=1)
        db_session.add_all([assembly, component])
        db_session.flush()

        # Create existing BOM line that should be removed
        bl = BOMLine(assembly_id=assembly.id, component_id=component.id, quantity=1)
        db_session.add(bl)
        db_session.flush()

        # Sync with empty bom_items → should remove the BOM line
        created, updated, removed = _sync_bom_structure(
            db=db_session,
            bom_items=[],
            assembly_part_id=assembly.id,
            onshape_to_opal={},
            user_id=1,
        )
        db_session.flush()

        assert removed == 1
        # Verify audit log was created for the deletion
        audit_entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "delete", AuditLog.table_name == "bom_lines")
            .all()
        )
        assert len(audit_entries) == 1


class TestBomParseWarningsInSync:
    """Test that BOM parse warnings surface in sync results."""

    def test_empty_names_produce_partial_status(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef,
    ) -> None:
        """Items with empty names produce status='partial' with error messages."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "p1"},
                    part_id="p1",
                    part_name="",  # Empty name
                    quantity=1,
                    children=[],
                ),
            ],
            warnings=[
                BOMParseWarning(
                    item_index=0, field="part_name",
                    message="Empty part_name for non-standard-content item (part_id='p1')",
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "partial"
        assert sync_log.errors is not None
        messages = sync_log.errors.get("messages", [])
        # Should have both the BOM parse warning and the empty name validation error
        assert any("part_name" in m for m in messages)
        assert any("Empty name" in m for m in messages)


class TestFlattenBom:
    """Test _flatten_bom deduplication with composite keys."""

    def test_dedup_by_composite_key(self) -> None:
        """Two items with same part_id but different source_element_id are both kept."""
        items = [
            OnshapeBOMItem(
                item_source={"partId": "JHD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JHD",
                part_name="Injector",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={"partId": "JHD", "elementId": "elemB"},
                source_element_id="elemB",
                part_id="JHD",
                part_name="Chamber",
                quantity=1,
            ),
        ]
        result = _flatten_bom(items)
        assert len(result) == 2
        assert {r.part_name for r in result} == {"Injector", "Chamber"}

    def test_dedup_same_element_same_part_id(self) -> None:
        """Two items with same source_element_id AND part_id are deduped to one."""
        items = [
            OnshapeBOMItem(
                item_source={"partId": "JHD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JHD",
                part_name="Injector",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={"partId": "JHD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JHD",
                part_name="Injector",
                quantity=2,
            ),
        ]
        result = _flatten_bom(items)
        assert len(result) == 1
        assert result[0].part_name == "Injector"

    def test_items_without_part_id_always_kept(self) -> None:
        """Items with empty part_id are always included (no dedup)."""
        items = [
            OnshapeBOMItem(
                item_source={},
                part_id="",
                part_name="Unknown A",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={},
                part_id="",
                part_name="Unknown B",
                quantity=1,
            ),
        ]
        result = _flatten_bom(items)
        assert len(result) == 2

    def test_flattens_nested_children(self) -> None:
        """Nested children are flattened with dedup across levels."""
        items = [
            OnshapeBOMItem(
                item_source={"partId": "asm", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="asm",
                part_name="Sub-Assembly",
                quantity=1,
                children=[
                    OnshapeBOMItem(
                        item_source={"partId": "child", "elementId": "elemB"},
                        source_element_id="elemB",
                        part_id="child",
                        part_name="Child Part",
                        quantity=2,
                    ),
                ],
            ),
        ]
        result = _flatten_bom(items)
        assert len(result) == 2
        assert {r.part_name for r in result} == {"Sub-Assembly", "Child Part"}


class TestSyncBomStructureDuplicateGuard:
    """Test that _sync_bom_structure prevents duplicate BOM lines."""

    def test_duplicate_component_guard(self, db_session: Session) -> None:
        """Two items mapping to same component_id produce one BOM line with accumulated qty."""
        assembly = Part(name="Assembly", internal_pn="PN-1-0001", tier=1)
        component = Part(name="Shared Part", internal_pn="PN-1-0002", tier=1)
        db_session.add_all([assembly, component])
        db_session.flush()

        # Two BOM items from different tree positions that resolve to the same OPAL Part
        bom_items = [
            OnshapeBOMItem(
                item_source={"partId": "JHD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JHD",
                part_name="Shared Part (ref 1)",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={"partId": "JHD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JHD",
                part_name="Shared Part (ref 2)",
                quantity=1,
            ),
        ]

        # Both map to the same OPAL part via composite key
        onshape_to_opal = {"elemA:JHD": component.id}

        created, updated, removed = _sync_bom_structure(
            db=db_session,
            bom_items=bom_items,
            assembly_part_id=assembly.id,
            onshape_to_opal=onshape_to_opal,
            user_id=1,
        )

        assert created == 1  # Only one BOM line created, not two
        bom_lines = (
            db_session.query(BOMLine)
            .filter(BOMLine.assembly_id == assembly.id)
            .all()
        )
        assert len(bom_lines) == 1
        assert bom_lines[0].quantity == 2  # Quantities accumulated (1 + 1)

    def test_bom_structure_accumulates_quantity(self, db_session: Session) -> None:
        """Two items with different composite keys mapping to same component_id → 1 BOM line, qty=2."""
        assembly = Part(name="Assembly", internal_pn="PN-1-0001", tier=1)
        component = Part(name="Fitting", internal_pn="PN-1-0002", tier=1)
        db_session.add_all([assembly, component])
        db_session.flush()

        bom_items = [
            OnshapeBOMItem(
                item_source={"partId": "JFD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JFD",
                part_name="Fitting",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={"partId": "JFH", "elementId": "elemB"},
                source_element_id="elemB",
                part_id="JFH",
                part_name="Fitting",
                quantity=1,
            ),
        ]

        # Both composite keys map to the same OPAL part
        onshape_to_opal = {
            "elemA:JFD": component.id,
            "elemB:JFH": component.id,
        }

        created, updated, removed = _sync_bom_structure(
            db=db_session,
            bom_items=bom_items,
            assembly_part_id=assembly.id,
            onshape_to_opal=onshape_to_opal,
            user_id=1,
        )

        assert created == 1
        bom_lines = (
            db_session.query(BOMLine)
            .filter(BOMLine.assembly_id == assembly.id)
            .all()
        )
        assert len(bom_lines) == 1
        assert bom_lines[0].quantity == 2

    def test_bom_structure_qty_update_on_resync(self, db_session: Session) -> None:
        """Existing BOM line with qty=2, new BOM has 3 references → updated to qty=3."""
        assembly = Part(name="Assembly", internal_pn="PN-1-0001", tier=1)
        component = Part(name="Fitting", internal_pn="PN-1-0002", tier=1)
        db_session.add_all([assembly, component])
        db_session.flush()

        # Pre-existing BOM line with qty=2
        bl = BOMLine(assembly_id=assembly.id, component_id=component.id, quantity=2)
        db_session.add(bl)
        db_session.flush()
        bl_id = bl.id

        # Three references in the new BOM
        bom_items = [
            OnshapeBOMItem(
                item_source={"partId": "JFD", "elementId": "elemA"},
                source_element_id="elemA",
                part_id="JFD",
                part_name="Fitting",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={"partId": "JFH", "elementId": "elemB"},
                source_element_id="elemB",
                part_id="JFH",
                part_name="Fitting",
                quantity=1,
            ),
            OnshapeBOMItem(
                item_source={"partId": "JFK", "elementId": "elemC"},
                source_element_id="elemC",
                part_id="JFK",
                part_name="Fitting",
                quantity=1,
            ),
        ]

        onshape_to_opal = {
            "elemA:JFD": component.id,
            "elemB:JFH": component.id,
            "elemC:JFK": component.id,
        }

        created, updated, removed = _sync_bom_structure(
            db=db_session,
            bom_items=bom_items,
            assembly_part_id=assembly.id,
            onshape_to_opal=onshape_to_opal,
            user_id=1,
        )

        assert created == 0
        assert updated == 1
        assert removed == 0

        # Query from DB to verify the update persisted
        db_session.flush()
        updated_bl = db_session.query(BOMLine).filter(BOMLine.id == bl_id).one()
        assert updated_bl.quantity == 3


class TestPullSyncCrossElementPartId:
    """Test assembly sync with parts from different Part Studios sharing partId."""

    def test_cross_element_part_id_collision(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef,
    ) -> None:
        """Assembly with two parts from different Part Studios sharing partId creates separate parts."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "JHD", "elementId": "elemA"},
                    source_element_id="elemA",
                    part_id="JHD",
                    part_name="Injector",
                    quantity=1,
                    children=[],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "JHD", "elementId": "elemB"},
                    source_element_id="elemB",
                    part_id="JHD",
                    part_name="Chamber",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 3  # root assembly + 2 distinct parts

        # Verify two distinct OPAL parts were created (not collapsed)
        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        part_names = {p.name for p in parts}
        assert "Injector" in part_names
        assert "Chamber" in part_names

        # Verify two separate OnshapeLinks with different element_ids
        links = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.part_id_onshape == "JHD")
            .all()
        )
        assert len(links) == 2
        element_ids = {lnk.element_id for lnk in links}
        assert element_ids == {"elemA", "elemB"}

        # Verify BOM lines — both should exist under root assembly
        assert sync_log.bom_lines_created == 2
