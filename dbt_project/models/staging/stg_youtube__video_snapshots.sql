with

source as (
    select
        video_id,
        channel_id,
        title,
        published_at,
        duration,
        view_count,
        like_count,
        comment_count,
        live_broadcast_content,
        _extracted_at,
        _snapshot_id
    from {{ source('youtube', 'video_snapshots') }}
),

typed as (
    select
        video_id,
        channel_id,
        title,
        timestamp(published_at) as published_at_utc,
        duration as duration_iso,
        -- ISO 8601 duration, e.g. PT1H2M3S or P1DT2H for long streams
        case
            when duration is null then null
            else
                coalesce(cast(regexp_extract(duration, r'(\d+)D') as int64), 0) * 86400
                + coalesce(cast(regexp_extract(duration, r'(\d+)H') as int64), 0) * 3600
                + coalesce(cast(regexp_extract(duration, r'(\d+)M') as int64), 0) * 60
                + coalesce(cast(regexp_extract(duration, r'(\d+)S') as int64), 0)
        end as duration_secs,
        -- hidden likes and disabled comments arrive as NULL and stay NULL, never 0
        safe_cast(view_count as int64) as view_count,
        safe_cast(like_count as int64) as like_count,
        safe_cast(comment_count as int64) as comment_count,
        live_broadcast_content,
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
        partition by video_id, snapshot_date
        order by _extracted_at desc
    ) = 1
)

select * from deduplicated