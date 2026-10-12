import os

import pandas as pd
from google.cloud import bigquery

from config import BQ_DATASET


def load_rows(client, table_name, rows):
    df = pd.DataFrame(rows)
    schema = [
        bigquery.SchemaField(column, "TIMESTAMP" if column == "_extracted_at" else "STRING")
        for column in df.columns
    ]
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_APPEND",
        clustering_fields=["channel_id"],
    )
    table_id = f"{os.environ['BQ_PROJECT']}.{BQ_DATASET}.{table_name}"
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    return job.output_rows