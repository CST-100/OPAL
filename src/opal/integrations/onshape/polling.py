"""Background polling task for automatic Onshape sync."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def onshape_polling_loop(interval_minutes: int) -> None:
    """Background task that periodically pulls from Onshape.

    Runs pull_sync for every document with auto_sync=True.
    Automatically triggers a push for any newly created parts.

    Args:
        interval_minutes: Minutes between poll cycles.
    """
    from opal.config import get_active_project, get_active_settings
    from opal.db.base import SessionLocal
    from opal.integrations.onshape.client import OnshapeClient
    from opal.integrations.onshape.sync import pull_sync

    logger.info("Onshape polling started (interval=%d min)", interval_minutes)

    while True:
        await asyncio.sleep(interval_minutes * 60)

        try:
            settings = get_active_settings()
            if not settings.onshape_enabled:
                logger.debug("Onshape not enabled, skipping poll")
                continue

            project = get_active_project()
            if not project or not project.onshape.documents:
                logger.debug("No Onshape documents configured, skipping poll")
                continue

            client = OnshapeClient(
                access_key=settings.onshape_access_key,
                secret_key=settings.onshape_secret_key,
                base_url=settings.onshape_base_url,
            )

            for doc_ref in project.onshape.documents:
                if not doc_ref.auto_sync:
                    continue

                logger.info("Polling Onshape document: %s", doc_ref.name)
                db = SessionLocal()
                try:
                    # Pull sync (auto-pushes PNs for new parts internally)
                    await asyncio.to_thread(
                        pull_sync, db, client, doc_ref, None, "poll"
                    )
                finally:
                    db.close()

            client.close()

        except asyncio.CancelledError:
            logger.info("Onshape polling cancelled")
            raise
        except Exception:
            logger.exception("Onshape polling cycle failed")
