"""Base adapter interface for source database types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    latency_ms: float | None = None


class SourceAdapter(ABC):
    """Abstract interface for a database source type."""

    @abstractmethod
    def cdc_script_path(self) -> str:
        """Relative path to the CDC daemon script (from project root)."""
        ...

    @abstractmethod
    def full_load_script_path(self) -> str:
        """Relative path to the full load script (from project root)."""
        ...

    @abstractmethod
    def build_env(self, source_creds: dict, target_creds: dict, job: dict) -> dict:
        """Build the environment variable dict for subprocess.Popen."""
        ...
