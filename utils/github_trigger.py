import aiohttp
import logging
from config.settings import GITHUB_TOKEN, GITHUB_REPO

logger = logging.getLogger(__name__)

async def trigger_tracker_force_update():
    """
    Trigger the Daily Uma Tracker Update GitHub Action workflow with force flag enabled
    using Repository Dispatch.
    """
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN is not configured. Cannot trigger GitHub Action force update.")
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
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 204:
                    logger.info("Successfully triggered GitHub Action force update repository dispatch.")
                    return True
                else:
                    text = await response.text()
                    logger.error(f"Failed to trigger GitHub Action: Status {response.status}, Response: {text}")
                    return False
    except Exception as e:
        logger.error(f"Exception while triggering GitHub Action: {e}")
        return False
