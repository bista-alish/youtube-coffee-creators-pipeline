import os 
import sys
from datetime import datetime, timezone
import logging

import pandas as pd
import requests
from dotenv import load_dotenv
from google.cloud import bigquery
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential


from config import (
    BASE_URL, 
    CHANNEL_IDS, 
    REQUEST_TIMEOUT_SECS, 
    PAGE_SIZE, 
    MAX_VIDEOS_PER_CHANNEL,
    BQ_DATASET,
    CHANNEL_TABLE,
    VIDEO_TABLE,
)

load_dotenv()
API_KEY = os.environ["YOUTUBE_API_KEY"]

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}

logger = logging.getLogger(__name__)

def error_reason(error):
    try:
        return error.response.json()["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError):
        return "unknown"

def is_transient(error):
    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(error, requests.HTTPError):
        status = error.response.status_code
        return status in TRANSIENT_STATUSES or error_reason(error) in RATE_LIMIT_REASONS
    return False

@retry(
        stop = stop_after_attempt(5),
        wait = wait_exponential(multiplier=1, max=30),
        retry = retry_if_exception(is_transient),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise = True,
)
def get_json(endpoint, params):
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params=params,
        headers={"X-Goog-Api-Key": API_KEY},
        timeout=REQUEST_TIMEOUT_SECS,
    )
    response.raise_for_status()
    return response.json()


def get_channels(channel_ids):
    data = get_json("channels", {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(channel_ids),
    })
    channels = data.get("items", [])

    missing = set(channel_ids) - {channel["id"] for channel in channels}
    if missing:
        raise ValueError(f"Channel IDs not found: {sorted(missing)}")
    return channels


def get_video_ids(uploads_playlist_id):
    video_ids = []
    page_token = None

    while True:
        data = get_json("playlistItems", {
            "part":"contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": PAGE_SIZE,
            "pageToken": page_token,
        })

        video_ids += [item["contentDetails"]["videoId"] for item in data.get("items", [])]
        
        page_token = data.get("nextPageToken")
        if not page_token or len(video_ids) >= MAX_VIDEOS_PER_CHANNEL:
            break

    return video_ids[:MAX_VIDEOS_PER_CHANNEL]

def get_videos(video_ids):
    videos = []
    for start in range(0, len(video_ids), PAGE_SIZE):
        batch = video_ids[start:start + PAGE_SIZE]
        data = get_json("videos", {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),  
        })

        videos += data.get("items", [])
    return videos

def to_video_row(video):
    snippet = video["snippet"]
    stats = video["statistics"]
    return{
        "video_id": video["id"],
        "channel_id": snippet["channelId"],
        "title": snippet["title"],
        "published_at": snippet["publishedAt"],
        "duration": video["contentDetails"]["duration"],
        "view_count": stats.get("viewCount"),
        "like_count": stats.get("likeCount"),
        "comment_count": stats.get("commentCount"),
        "live_broadcast_content": snippet["liveBroadcastContent"],
    }

def to_channel_row(channel):
    stats = channel["statistics"]
    return {
        "channel_id": channel["id"],
        "title": channel["snippet"]["title"],
        "subscriber_count":stats.get("subscriberCount"),
        "video_count": stats.get("videoCount"),
        "view_count": stats.get("viewCount"),
    }

def load_rows(client, table_name, rows):
    df = pd.DataFrame(rows)
    schema = [
        bigquery.SchemaField(column, "TIMESTAMP" if column == "_extracted_at" else "STRING")
        for column in df.columns
    ]
    job_config = bigquery.LoadJobConfig(
        schema = schema,
        write_disposition = "WRITE_APPEND",
        clustering_fields = ["channel_id"],
    )
    table_id = f"{os.environ['BQ_PROJECT']}.{BQ_DATASET}.{table_name}"
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    return job.output_rows

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
            logger.warning("%s: %d videos not returned (private or deleted): %s", title, len(missing), sorted(missing))
        logger.info("%s: %d ids, %d videos", title, len(video_ids), len(rows))

    client = bigquery.Client(project=os.environ["BQ_PROJECT"])
    for table_name, rows in [(CHANNEL_TABLE, channel_rows), (VIDEO_TABLE, video_rows)]:
        loaded = load_rows(client, table_name, rows)
        if loaded != len(rows):
            raise RuntimeError(f"{table_name}: sent {len(rows)} rows but BigQuery loaded {loaded}")
        logger.info("%s: loaded %d rows", table_name, loaded)

if __name__=="__main__":
   logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
   try:
       main()
   except requests.HTTPError as error:
       reason = error_reason(error)
       if reason == "quotaExceeded":
           logger.error("Quota exhausted.")
       else:
           logger.error("API error %s: %s", error.response.status_code, reason)
       sys.exit(1)
   except requests.RequestException as error:
        logger.error("Network error after retries: %s", error)
        sys.exit(1)