"""Source database adapters."""

from server.adapters.sqlserver import SqlServerAdapter
from server.adapters.oracle import OracleAdapter

ADAPTERS = {
    "sqlserver": SqlServerAdapter(),
    "oracle": OracleAdapter(),
}


def get_adapter(db_type: str):
    adapter = ADAPTERS.get(db_type)
    if adapter is None:
        raise ValueError(f"No adapter for db_type: {db_type}")
    return adapter
