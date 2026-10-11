import os 

import requests
from dotenv import load_dotenv

from config import BASE_URL, CHANNEL_IDS, REQUEST_TIMEOUT_SECS, PAGE_SIZE, MAX_VIDEOS_PER_CHANNEL

load_dotenv()
API_KEY = os.environ["YOUTUBE_API_KEY"]

def get_channels(channel_ids):
    response = requests.get(
        f"{BASE_URL}/channels",
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(channel_ids),
        },
        headers={"X-Goog-Api-Key": API_KEY},
        timeout=REQUEST_TIMEOUT_SECS,
    )
    response.raise_for_status()
    channels = response.json().get("items", [])

    missing = set(channel_ids) - {channel["id"] for channel in channels}
    if missing:
        raise ValueError(f"Channel IDs not found: {sorted(missing)}")
    return channels


def get_video_ids(uploads_playlist_id):
    video_ids = []
    page_token = None

    while True:
        response = requests.get(
            f"{BASE_URL}/playlistItems",
            params={
                "part":"contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": PAGE_SIZE,
                "pageToken": page_token,
            },
            headers={"X-Goog-Api-Key": API_KEY},
            timeout=REQUEST_TIMEOUT_SECS,
        )
        response.raise_for_status()
        data = response.json()

        video_ids += [item["contentDetails"]["videoId"] for item in data.get("items", [])]
        
        page_token = data.get("nextPageToken")
        if not page_token or len(video_ids) >= MAX_VIDEOS_PER_CHANNEL:
            break

    return video_ids[:MAX_VIDEOS_PER_CHANNEL]



if __name__=="__main__":
    for channel in get_channels(CHANNEL_IDS):
        title = channel["snippet"]["title"]
        uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        video_count = channel["statistics"]["videoCount"]
        video_ids = get_video_ids(uploads)
        print(f"{title}: {len(video_ids)} IDs fetched, videoCount says {video_count}")