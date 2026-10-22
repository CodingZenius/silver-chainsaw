"""
TeKivy Script Cache Manager
Handles session caching, binary metadata serialization, and local restoration
of procedural world states across Android Activity lifecycle changes.
"""

import os
import json
import time
from typing import Dict, Any, Optional


class SessionScriptCache:
    """
    Manages session-persisted scene graphs and compiled geometry buffers
    cached to the user's local device storage.
    """

    def __init__(self, cache_root: Optional[str] = None):
        self.cache_root = cache_root or ""
        self.meta_file = "cache_manifest.json"

    def set_cache_directory(self, path: str) -> None:
        self.cache_root = path
        os.makedirs(self.cache_root, exist_ok=True)

    def write_cache(self, filename: str, payload: Dict[str, Any]) -> str:
        """
        Dumps active scene state into a compressed-format JSON session file.
        """
        if not self.cache_root:
            raise RuntimeError("Cache directory has not been initialized.")

        target_path = os.path.join(self.cache_root, filename)
        meta_path = os.path.join(self.cache_root, self.meta_file)

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

        # Maintain manifest with timestamp and node count
        manifest = {
            "cached_file": filename,
            "timestamp": time.time(),
            "node_count": len(payload.get("nodes", {})),
            "infinite_loop": payload.get("infinite_loop", False)
        }
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        return target_path

    def read_cache(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Reads back cached procedural node data for OpenGL ES buffer streaming.
        """
        if not self.cache_root:
            return None

        target_path = os.path.join(self.cache_root, filename)
        if not os.path.exists(target_path):
            return None

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def invalidate_cache(self) -> None:
        """
        Deletes all session files when the app exits or resets.
        """
        if not self.cache_root or not os.path.exists(self.cache_root):
            return

        for item in os.listdir(self.cache_root):
            full_path = os.path.join(self.cache_root, item)
            if os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except OSError:
                    pass


# Singleton cache controller
script_cache = SessionScriptCache()
