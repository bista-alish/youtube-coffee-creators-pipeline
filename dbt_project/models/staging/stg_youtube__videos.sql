with

snapshots as (
    select * from {{ ref('stg_youtube__video_snapshots') }}
),

latest as (
    select *
    from snapshots
    where true
    qualify row_number() over (partition by video_id order by _extracted_at desc) = 1
)

select * from latest