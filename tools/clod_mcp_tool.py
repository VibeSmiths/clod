"""
Clod MCP Filesystem Tool for Open-WebUI
========================================
Paste this entire file into Open-WebUI → Workspace → Tools → [+] New Tool.

Two modes (configure in the tool's Valves):

  shared_dir  — set to the container-side mount path (e.g. /workspace) when the
                directory is volume-mounted into Open-WebUI.  File I/O is done
                directly, no HTTP round-trip.  Fastest and works offline.

  mcp_url     — used when shared_dir is empty.  Calls clod's MCP HTTP server via
                host.docker.internal:8765 (requires clod running with MCP on).

docker-compose mount (add to open-webui volumes):
  - ${SHARED_DIR:-./shared}:/workspace:rw
Then set shared_dir = /workspace in the tool Valves.
"""

import os
import urllib.request
import urllib.error
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        shared_dir: str = Field(
            default="",
            description=(
                "Absolute container path to a volume-mounted shared directory "
                "(e.g. /workspace).  When set, files are accessed directly "
                "instead of via the MCP HTTP server."
            ),
        )
        mcp_url: str = Field(
            default="http://host.docker.internal:8765",
            description=(
                "Base URL of the clod MCP filesystem server.  "
                "Used only when shared_dir is empty."
            ),
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _use_direct(self) -> bool:
        return bool(self.valves.shared_dir.strip())

    def _safe_local(self, rel: str) -> str | None:
        """Resolve rel inside shared_dir; return None on path traversal."""
        root = os.path.realpath(self.valves.shared_dir)
        target = os.path.realpath(os.path.join(root, rel.lstrip("/")))
        return target if target.startswith(root) else None

    def _http(self, method: str, path: str = "", body: bytes | None = None) -> str:
        url = self.valves.mcp_url.rstrip("/")
        if path:
            url = f"{url}/{path.lstrip('/')}"
        req = urllib.request.Request(url, data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
        except urllib.error.URLError as e:
            return f"MCP unreachable ({e.reason}). Is clod running with MCP enabled?"

    # ── tool methods (called by the LLM) ─────────────────────────────────────

    def list_files(self, path: str = "") -> str:
        """
        List files in the clod MCP workspace.

        :param path: Sub-directory to list (default: workspace root).
        """
        if self._use_direct():
            target = self._safe_local(path)
            if target is None:
                return "Error: path traversal denied."
            if not os.path.isdir(target):
                return f"Not a directory: {path}"
            entries = os.listdir(target)
            return "\n".join(entries) if entries else "(empty)"
        return self._http("GET", "list")

    def read_file(self, path: str) -> str:
        """
        Read a file from the clod MCP workspace.

        :param path: Relative path, e.g. "notes.txt" or "src/main.py"
        """
        if self._use_direct():
            target = self._safe_local(path)
            if target is None:
                return "Error: path traversal denied."
            if not os.path.isfile(target):
                return f"File not found: {path}"
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        return self._http("GET", path)

    def write_file(self, path: str, content: str) -> str:
        """
        Write (create or overwrite) a file in the clod MCP workspace.

        :param path: Relative path, e.g. "notes.txt"
        :param content: Full text content to write.
        """
        if self._use_direct():
            target = self._safe_local(path)
            if target is None:
                return "Error: path traversal denied."
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written: {path}"
        return self._http("POST", path, body=content.encode("utf-8"))

    def delete_file(self, path: str) -> str:
        """
        Delete a file from the clod MCP workspace.

        :param path: Relative path, e.g. "old_notes.txt"
        """
        if self._use_direct():
            target = self._safe_local(path)
            if target is None:
                return "Error: path traversal denied."
            if not os.path.exists(target):
                return f"File not found: {path}"
            os.remove(target)
            return f"Deleted: {path}"
        return self._http("DELETE", path)
