import os
import sys
import json
import shutil
import zipfile
import traceback
from typing import Dict, Any, Optional, Callable


class TeKivyRuntime:
    """
    Main orchestrator bridged to the Kotlin Android AppShell.
    Manages the local device storage paths, active scripts, session cache,
    and forwards commands to the sandbox runner and world manager.
    """

    def __init__(self):
        self.storage_root: str = ""
        self.cache_dir: str = ""
        self.projects_dir: str = ""
        self.models_dir: str = ""
        self.active_project_name: str = "untitled.ki"
        self.scripts: Dict[str, str] = {}
        self.active_script_name: str = "procedural.py"
        self.is_world_ready: bool = False
        self.progress_callback: Optional[Callable[[int, str], None]] = None

    def initialize(self, android_files_dir: str, android_cache_dir: str) -> str:
        """
        Called by Kotlin MainActivity on startup.
        Sets up directory structure and clears stale session caches.
        """
        self.storage_root = android_files_dir
        self.cache_dir = os.path.join(android_cache_dir, "tekivy_session")
        self.projects_dir = os.path.join(self.storage_root, "user_projects")
        self.models_dir = os.path.join(self.projects_dir, "models")

        for folder in (self.cache_dir, self.projects_dir, self.models_dir):
            os.makedirs(folder, exist_ok=True)

        if self.projects_dir not in sys.path:
            sys.path.insert(0, self.projects_dir)

        self.clear_session_cache()

        # Load default starter script if no script is present
        default_script_path = os.path.join(self.projects_dir, "active_script.py")
        if os.path.exists(default_script_path):
            with open(default_script_path, "r", encoding="utf-8") as f:
                self.scripts["procedural.py"] = f.read()
        else:
            self.scripts["procedural.py"] = (
                "# TeKivy Procedural World Script\n"
                "def build(world):\n"
                "    world.set_infinite_loop(True, chunk_size=50.0)\n"
                "    world.add_ground(size=50.0, color=(0.18, 0.45, 0.22), finish='sanding_sealer')\n"
                "    world.add_box(name='pillar_1', pos=(0, 1.5, 0), scale=(1, 3, 1), color=(0.75, 0.55, 0.35))\n"
            )

        return json.dumps({
            "status": "initialized",
            "active_script": self.active_script_name,
            "scripts": list(self.scripts.keys())
        })

    def set_progress_callback(self, callback: Callable[[int, str], None]) -> None:
        """
        Allows the Kotlin UI to attach a listener for the blurred loading bar.
        """
        self.progress_callback = callback

    def report_progress(self, percent: int, message: str) -> None:
        """
        Sends progress updates (0-100) back to the Android UI thread.
        """
        if self.progress_callback is not None:
            try:
                self.progress_callback(int(percent), str(message))
            except Exception:
                pass

    def create_or_update_script(self, filename: str, code: str) -> str:
        """
        Saves or updates a .py script in the current project buffer (Blender-style text datablock).
        """
        if not filename.endswith(".py"):
            filename += ".py"

        self.scripts[filename] = code
        self.active_script_name = filename
        self.is_world_ready = False

        disk_path = os.path.join(self.projects_dir, filename)
        with open(disk_path, "w", encoding="utf-8") as f:
            f.write(code)

        return json.dumps({
            "status": "saved",
            "active_script": self.active_script_name,
            "all_scripts": list(self.scripts.keys())
        })

    def get_script_content(self, filename: str) -> str:
        """
        Returns the text content of a script buffer for the Kotlin code editor.
        """
        return self.scripts.get(filename, "")

    def execute_active_script(self, timeout_sec: float = 8.0) -> str:
        """
        Runs the active script inside SandboxRunner, builds the procedural world cache,
        and unlocks the 3D viewport tab only upon clean completion.
        """
        from .sandbox_runner import SandboxRunner
        from .world_manager import world_manager

        self.is_world_ready = False
        self.report_progress(10, f"Preparing {self.active_script_name}...")

        code = self.scripts.get(self.active_script_name, "")
        if not code.strip():
            return json.dumps({
                "status": "error",
                "viewport_unlocked": False,
                "error": "Script is empty."
            })

        try:
            self.report_progress(35, "Executing procedural generation...")
            runner = SandboxRunner(timeout=timeout_sec)
            result = runner.run_code(
                code=code,
                filename=self.active_script_name,
                world_manager=world_manager
            )

            if result["status"] != "ok":
                self.report_progress(0, "Execution failed.")
                return json.dumps({
                    "status": "error",
                    "viewport_unlocked": False,
                    "error": result.get("error", "Unknown script error.")
                })

            self.report_progress(75, "Caching procedural world to storage...")
            cache_file = os.path.join(self.cache_dir, "world_session_cache.json")
            world_manager.save_session_cache(cache_file)

            self.is_world_ready = True
            self.report_progress(100, "World ready.")

            return json.dumps({
                "status": "ok",
                "viewport_unlocked": True,
                "cache_path": cache_file,
                "has_controller": "control.py" in self.scripts,
                "controller_hint": (
                    "Tip: Add a control.py file to enable custom joystick navigation."
                    if "control.py" not in self.scripts else ""
                ),
                "node_count": len(world_manager.nodes)
            })

        except Exception as exc:
            return json.dumps({
                "status": "error",
                "viewport_unlocked": False,
                "error": f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()}"
            })

    def save_project_ki(self, project_name: str) -> str:
        """
        Packages all current .py scripts and metadata into a native TeKivy (.ki) archive.
        """
        if not project_name.endswith(".ki"):
            project_name += ".ki"

        ki_path = os.path.join(self.projects_dir, project_name)
        manifest = {
            "engine": "TeKivy",
            "version": "0.1.0-beta",
            "active_script": self.active_script_name,
            "scripts": list(self.scripts.keys())
        }

        with zipfile.ZipFile(ki_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for fname, content in self.scripts.items():
                zf.writestr(f"scripts/{fname}", content)

        self.active_project_name = project_name
        return json.dumps({"status": "saved_ki", "path": ki_path})

    def load_project_ki(self, ki_file_path: str) -> str:
        """
        Opens a .ki project archive and populates the script editor tabs.
        """
        if not os.path.exists(ki_file_path):
            return json.dumps({"status": "error", "error": "Project file not found."})

        self.scripts.clear()
        with zipfile.ZipFile(ki_file_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            for item in zf.namelist():
                if item.startswith("scripts/") and item.endswith(".py"):
                    script_name = os.path.basename(item)
                    self.scripts[script_name] = zf.read(item).decode("utf-8")

        self.active_script_name = manifest.get("active_script", next(iter(self.scripts), "text_1.py"))
        self.is_world_ready = False

        return json.dumps({
            "status": "loaded_ki",
            "active_script": self.active_script_name,
            "scripts": list(self.scripts.keys())
        })

    def clear_session_cache(self) -> None:
        """
        Wipes the temporary procedural world cache when the session ends or resets.
        """
        self.is_world_ready = False
        if os.path.exists(self.cache_dir):
            for entry in os.listdir(self.cache_dir):
                full_path = os.path.join(self.cache_dir, entry)
                if os.path.isfile(full_path):
                    os.remove(full_path)


# Global singleton instance accessed by Kotlin JNI / Chaquopy
runtime = TeKivyRuntime()


# Top-level helper functions for direct Kotlin invocation
def init_engine(files_dir: str, cache_dir: str) -> str:
    return runtime.initialize(files_dir, cache_dir)


def run_project_script(timeout_sec: float = 8.0) -> str:
    return runtime.execute_active_script(timeout_sec=timeout_sec)


def export_scene_glb(output_filename: str, selected_node_id: Optional[str] = None) -> str:
    from .world_manager import world_manager
    out_path = os.path.join(runtime.models_dir, output_filename)
    if not out_path.endswith(".glb"):
        out_path += ".glb"
    return world_manager.export_glb(out_path, selected_node_id=selected_node_id)
