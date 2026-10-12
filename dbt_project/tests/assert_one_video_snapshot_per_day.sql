select
    video_id,
    snapshot_date,
    count(*) as row_count
from {{ ref('stg_youtube__video_snapshots') }}
group by video_id, snapshot_date
having count(*) > 1