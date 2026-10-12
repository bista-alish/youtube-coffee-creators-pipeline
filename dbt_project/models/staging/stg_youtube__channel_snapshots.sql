with

source as (
    select
        channel_id,
        title,
        subscriber_count,
        video_count,
        view_count,
        _extracted_at,
        _snapshot_id
    from {{ source('youtube', 'channel_snapshots') }}
),

typed as (
    select
        channel_id,
        title,
        -- public subscriber counts are rounded to 3 significant figures by YouTube
        safe_cast(subscriber_count as int64) as subscriber_count,
        safe_cast(video_count as int64) as video_count,
        safe_cast(view_count as int64) as view_count,
        _extracted_at,
        _snapshot_id,
        date(_extracted_at) as snapshot_date
    from source
),

deduplicated as (
    select *
    from typed
    where true
    qualify row_number() over (
        partition by channel_id, snapshot_date
        order by _extracted_at desc
    ) = 1
)

select * from deduplicated