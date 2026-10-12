import aiohttp
import logging
from config.settings import GITHUB_TOKEN, GITHUB_REPO, TRACKER_WEBHOOK_URL

logger = logging.getLogger(__name__)

async def trigger_tracker_force_update():
    """
    Trigger tracker force update.
    Prioritizes local webhook (direct Docker network call),
    falling back to GitHub Action repository dispatch if local webhook is unavailable.
    """
    # 1. Attempt local webhook trigger first
    if TRACKER_WEBHOOK_URL:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(TRACKER_WEBHOOK_URL) as response:
                    if response.status in (200, 202):
                        logger.info("Successfully triggered tracker update via local webhook: %s", TRACKER_WEBHOOK_URL)
                        return True
                    else:
                        resp_text = await response.text()
                        logger.warning("Local tracker webhook returned status %s: %s. Attempting GitHub Action fallback...",
                                       response.status, resp_text)
        except Exception as err:
            logger.info("Local tracker webhook unavailable (%s). Attempting GitHub Action fallback...", err)

    # 2. Fallback to GitHub Action repository dispatch
    if not GITHUB_TOKEN:
        logger.warning("Neither local webhook succeeded nor GITHUB_TOKEN is configured. Cannot trigger tracker update.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {
        "event_type": "external-cron",
        "client_payload": {
            "force": True
        }
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 204:
                    logger.info("Successfully triggered GitHub Action force update repository dispatch.")
                    return True
                else:
                    text = await response.text()
                    logger.error("Failed to trigger GitHub Action: Status %s, Response: %s", response.status, text)
                    return False
    except Exception as e:
        logger.error("Exception while triggering GitHub Action: %s", e)
        return False
