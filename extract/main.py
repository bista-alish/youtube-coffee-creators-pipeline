import logging
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from google.cloud import bigquery

from api import error_reason
from config import CHANNEL_IDS, CHANNEL_TABLE, VIDEO_TABLE
from load import load_rows
from youtube import get_channels, get_video_ids, get_videos, to_channel_row, to_video_row

logger = logging.getLogger(__name__)


def main():
    extracted_at = datetime.now(timezone.utc)
    metadata = {
        "_extracted_at": extracted_at,
        "_snapshot_id": extracted_at.strftime("%Y%m%dT%H%M%SZ"),
    }

    channels = get_channels(CHANNEL_IDS)
    channel_rows = [to_channel_row(channel) | metadata for channel in channels]

    video_rows = []
    for channel in channels:
        title = channel["snippet"]["title"]
        uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        video_ids = get_video_ids(uploads)
        rows = [to_video_row(video) | metadata for video in get_videos(video_ids)]
        video_rows += rows

        missing = set(video_ids) - {row["video_id"] for row in rows}
        if missing:
            logger.warning("%s: %d videos not returned (private or deleted?): %s",
                           title, len(missing), sorted(missing))
        logger.info("%s: %d ids, %d videos", title, len(video_ids), len(rows))

    client = bigquery.Client(project=os.environ["BQ_PROJECT"])
    for table_name, table_rows in [(CHANNEL_TABLE, channel_rows), (VIDEO_TABLE, video_rows)]:
        loaded = load_rows(client, table_name, table_rows)
        if loaded != len(table_rows):
            raise RuntimeError(f"{table_name}: sent {len(table_rows)} rows but BigQuery loaded {loaded}")
        logger.info("%s: loaded %d rows", table_name, loaded)


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        main()
    except requests.HTTPError as error:
        reason = error_reason(error)
        if reason == "quotaExceeded":
            logger.error("Daily quota exhausted. Stopping; rerun after midnight Pacific.")
        else:
            logger.error("API error %s: %s", error.response.status_code, reason)
        sys.exit(1)
    except requests.RequestException as error:
        logger.error("Network error after retries: %s", error)
        sys.exit(1)