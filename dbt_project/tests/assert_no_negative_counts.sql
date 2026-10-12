select
    video_id,
    view_count,
    like_count,
    comment_count
from {{ ref('fct_video_performance') }}
where view_count < 0
    or like_count < 0
    or comment_count < 0