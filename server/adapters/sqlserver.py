"""SQL Server source adapter."""

import os
from server.adapters.base import SourceAdapter


class SqlServerAdapter(SourceAdapter):
    def cdc_script_path(self) -> str:
        return os.path.join("src", "sqlserver_cdc.py")

    def full_load_script_path(self) -> str:
        return os.path.join("src", "sqlserver_full_load.py")

    def build_env(self, source_creds: dict, target_creds: dict, job: dict) -> dict:
        env = {
            "MSSQL_HOST": source_creds["host"],
            "MSSQL_PORT": str(source_creds["port"]),
            "MSSQL_USER": source_creds["username"],
            "MSSQL_PASS": source_creds["password"],
            "MSSQL_DB": source_creds.get("database_name") or "EnterpriseDW",
            "PG_HOST": target_creds["host"],
            "PG_PORT": str(target_creds["port"]),
            "PG_USER": target_creds["username"],
            "PG_PASS": target_creds["password"],
            "PG_DB": target_creds.get("database_name") or "enterprise_dw",
        }
        if target_creds.get("schema_name"):
            env["PG_TARGET_SCHEMA"] = target_creds["schema_name"]
        if job.get("table_list"):
            env["CDC_TABLES"] = ",".join(job["table_list"])
        # Per-job checkpoint isolation
        env["CDC_CHECKPOINT_DB"] = os.path.join("cdc-checkpoints", f"job_{job['id']}_ct_checkpoint.db")
        return env
