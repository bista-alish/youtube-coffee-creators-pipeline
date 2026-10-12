{{ config(cluster_by=['channel_id']) }}

with

snapshots as (
    select
        video_id,
        channel_id,
        snapshot_date,
        view_count
    from {{ ref('stg_youtube__video_snapshots') }}
    where live_broadcast_content = 'none'
),

final as (
    select
        video_id,
        channel_id,
        snapshot_date,
        view_count,
        view_count - lag(view_count) over (partition by video_id order by snapshot_date) as views_gained,
        date_diff(
            snapshot_date,
            lag(snapshot_date) over (partition by video_id order by snapshot_date),
            day
        ) as days_since_previous_snapshot
    from snapshots
)

select * from final