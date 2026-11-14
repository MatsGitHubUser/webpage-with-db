"""Comment storage in Azure Table Storage.

The storage account is given by the AZURE_STORAGE_CONNECTION_STRING environment
variable: locally it points at the Azurite emulator (see compose.yaml), in Azure
at the storage account Terraform creates (see infra/main.tf).

All comments share one partition. The RowKey counts down with time, so the
table's natural sort order (by PartitionKey, then RowKey) is newest first.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice

from azure.data.tables import TableClient, TableServiceClient

MAX_NAME = 50
MAX_BODY = 1000

PARTITION = "comments"
# Microseconds since 1970 stay below this until the year 2286.
_ROW_KEY_CEILING = 10**16


@dataclass(frozen=True)
class Comment:
    id: str
    author: str
    body: str
    created_at: datetime


def open_table() -> TableClient:
    """Connect to the comments table, creating it if needed."""
    service = TableServiceClient.from_connection_string(
        os.environ["AZURE_STORAGE_CONNECTION_STRING"],
        # Fail within seconds when storage is unreachable instead of retrying
        # for minutes, so the page can show an error.
        retry_total=2,
        connection_timeout=5,
        read_timeout=10,
    )
    return service.create_table_if_not_exists(os.environ.get("COMMENTS_TABLE", "comments"))


def clean(value: str, limit: int, what: str) -> str:
    """Trim user input and check it fits the limits."""
    value = (value or "").replace("\x00", "").strip()
    if not value:
        raise ValueError(f"{what} cannot be empty.")
    if len(value) > limit:
        raise ValueError(f"{what} can be at most {limit} characters.")
    return value


def _new_row_key(now: datetime) -> str:
    micros = int(now.timestamp() * 1_000_000)
    # The random tail keeps two comments in the same microsecond apart.
    return f"{_ROW_KEY_CEILING - micros:016d}-{uuid.uuid4().hex[:8]}"


def add_comment(table: TableClient, author: str, body: str) -> Comment:
    author = clean(author, MAX_NAME, "Name")
    body = clean(body, MAX_BODY, "Comment")
    now = datetime.now(timezone.utc)
    comment = Comment(id=_new_row_key(now), author=author, body=body, created_at=now)
    table.create_entity(
        {
            "PartitionKey": PARTITION,
            "RowKey": comment.id,
            "author": comment.author,
            "body": comment.body,
            "created_at": comment.created_at,
        }
    )
    return comment


def list_comments(table: TableClient, limit: int = 100) -> list[Comment]:
    """Newest first."""
    entities = table.query_entities(
        "PartitionKey eq @pk",
        parameters={"pk": PARTITION},
        select=["RowKey", "author", "body", "created_at"],
        results_per_page=limit,
    )
    return [
        Comment(id=e["RowKey"], author=e["author"], body=e["body"], created_at=e["created_at"])
        for e in islice(entities, limit)
    ]
