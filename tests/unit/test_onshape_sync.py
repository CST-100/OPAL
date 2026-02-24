"""Tests for Onshape pull and push sync engine."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from opal.db.models.onshape_link import OnshapeLink, OnshapeSyncLog
from opal.db.models.part import BOMLine, Part
from opal.integrations.onshape.models import OnshapeBOM, OnshapeBOMItem
from opal.integrations.onshape.sync import _compute_pull_hash, _compute_push_hash, pull_sync
from opal.project import OnshapeDocumentRef


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
        assert sync_log.parts_created == 2
        assert sync_log.direction == "pull"
        assert sync_log.trigger == "manual"

        # Verify OPAL parts were created
        parts = db_session.query(Part).filter(Part.deleted_at.is_(None)).all()
        part_names = {p.name for p in parts}
        assert "Bracket" in part_names
        assert "Bolt M5x20" in part_names

        # Verify OnshapeLinks were created
        links = db_session.query(OnshapeLink).all()
        assert len(links) == 2
        assert links[0].document_id == "doc123"

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
        assert sync_log.parts_created == 0

        # Verify name was updated
        db_session.refresh(part)
        assert part.name == "New Name"

        # Verify internal_pn was NOT changed (OPAL-owned)
        assert part.internal_pn == "PN-1-0001"

    def test_skips_unchanged_parts(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync skips parts whose Onshape data hasn't changed."""
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
        """Pull sync creates BOM lines matching Onshape assembly hierarchy."""
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "assembly"},
                    part_id="assembly",
                    part_name="Top Assembly",
                    quantity=1,
                    children=[
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
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.status == "success"
        assert sync_log.parts_created == 3  # assembly + 2 children
        assert sync_log.bom_lines_created == 2

        # Verify BOM structure
        bom_lines = db_session.query(BOMLine).all()
        assert len(bom_lines) == 2

        # Find the assembly part
        assembly_link = (
            db_session.query(OnshapeLink)
            .filter(OnshapeLink.part_id_onshape == "assembly")
            .first()
        )
        assert assembly_link is not None

        # BOM lines should be children of the assembly
        for bl in bom_lines:
            assert bl.assembly_id == assembly_link.part_id

    def test_removes_bom_lines_for_removed_components(
        self, db_session: Session, mock_client: MagicMock, doc_ref: OnshapeDocumentRef
    ) -> None:
        """Pull sync removes BOM lines when components are removed from Onshape BOM."""
        # Create existing parts and BOM structure
        assembly = Part(name="Assembly", internal_pn="PN-1-0001", tier=1)
        child1 = Part(name="Bracket", internal_pn="PN-1-0002", tier=1)
        child2 = Part(name="Bolt", internal_pn="PN-1-0003", tier=1)
        db_session.add_all([assembly, child1, child2])
        db_session.flush()

        # Create links
        for part, os_id in [(assembly, "asm"), (child1, "c1"), (child2, "c2")]:
            db_session.add(OnshapeLink(
                part_id=part.id,
                document_id="doc123",
                element_id="elem789",
                part_id_onshape=os_id,
                onshape_name=part.name,
                pull_hash="old-hash",
            ))

        # Create existing BOM line
        bom_line = BOMLine(assembly_id=assembly.id, component_id=child2.id, quantity=4)
        db_session.add(bom_line)
        db_session.flush()

        # Return BOM without child2 — only child1 remains
        mock_client.get_bom.return_value = OnshapeBOM(
            document_id="doc123",
            element_id="elem789",
            items=[
                OnshapeBOMItem(
                    item_source={"partId": "asm"},
                    part_id="asm",
                    part_name="Assembly",
                    quantity=1,
                    children=[
                        OnshapeBOMItem(
                            item_source={"partId": "c1"},
                            part_id="c1",
                            part_name="Bracket",
                            quantity=2,
                            children=[],
                        ),
                    ],
                ),
                OnshapeBOMItem(
                    item_source={"partId": "c2"},
                    part_id="c2",
                    part_name="Bolt",
                    quantity=1,
                    children=[],
                ),
            ],
        )

        with patch("opal.config.get_active_project", return_value=None):
            sync_log = pull_sync(db_session, mock_client, doc_ref, user_id=1)

        assert sync_log.bom_lines_removed == 1
        assert sync_log.bom_lines_created == 1  # Bracket added

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
