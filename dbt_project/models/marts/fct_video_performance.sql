{{ config(cluster_by=['channel_id']) }}

with

videos as (
    select * from {{ ref('stg_youtube__videos') }}
    where live_broadcast_content = 'none'
),

channels as (
    select
        channel_id,
        title as channel_title
    from {{ ref('stg_youtube__channels') }}
),

final as (
    select
        videos.video_id,
        videos.channel_id,
        channels.channel_title,
        videos.title as video_title,
        videos.published_at_utc,
        format_timestamp('%A', videos.published_at_utc) as publish_day_utc,
        extract(dayofweek from videos.published_at_utc) as publish_day_num_utc,
        extract(hour from videos.published_at_utc) as publish_hour_utc,
        videos.duration_secs,
        {{ length_band('videos.duration_secs') }} as length_band,
        videos.duration_secs <= 180 as is_short_estimate,
        videos.view_count,
        videos.like_count,
        videos.comment_count,
        safe_divide(videos.like_count, videos.view_count) as like_rate,
        safe_divide(videos.comment_count, videos.view_count) as comment_rate,
        -- NULL when likes or comments are hidden, by design
        safe_divide(videos.like_count + videos.comment_count, videos.view_count) as engagement_rate,
        date_diff(videos.snapshot_date, date(videos.published_at_utc), day) as age_days,
        safe_divide(
            videos.view_count,
            greatest(date_diff(videos.snapshot_date, date(videos.published_at_utc), day), 1)
        ) as views_per_day_since_publish,
        videos.snapshot_date as as_of_date
    from videos
    left join channels
        on videos.channel_id = channels.channel_id
)

select * from final