"""Oracle source adapter."""

import os
from server.adapters.base import SourceAdapter


class OracleAdapter(SourceAdapter):
    def cdc_script_path(self) -> str:
        return os.path.join("src", "oracle_cdc.py")

    def full_load_script_path(self) -> str:
        return os.path.join("src", "oracle_full_load.py")

    def build_env(self, source_creds: dict, target_creds: dict, job: dict) -> dict:
        env = {
            "ORACLE_USER": source_creds["username"],
            "ORACLE_PASS": source_creds["password"],
            "ORACLE_PDB_DSN": source_creds.get("oracle_dsn") or f"{source_creds['host']}:{source_creds['port']}/FREEPDB1",
            "ORACLE_SCHEMA": source_creds.get("schema_name") or "REPLTEST",
            "PG_HOST": target_creds["host"],
            "PG_PORT": str(target_creds["port"]),
            "PG_USER": target_creds["username"],
            "PG_PASS": target_creds["password"],
            "PG_DB": target_creds.get("database_name") or "enterprise_dw",
        }
        if source_creds.get("oracle_cdb_dsn"):
            env["ORACLE_CDB_DSN"] = source_creds["oracle_cdb_dsn"]
        if source_creds.get("oracle_sys_password"):
            env["ORACLE_SYS_PASS"] = source_creds["oracle_sys_password"]
        if target_creds.get("schema_name"):
            env["PG_TARGET_SCHEMA"] = target_creds["schema_name"]
        if job.get("table_list"):
            env["CDC_TABLES"] = ",".join(job["table_list"])
        # Per-job checkpoint isolation
        env["CDC_SCN_CHECKPOINT"] = os.path.join("cdc-checkpoints", f"job_{job['id']}_oracle_scn.txt")
        return env
