"""
TeKivy - Mobile Game Engine & Procedural World Studio
Entry point invoked by Android AppShell / Chaquopy runtime.
"""

import sys
import os
import json

from core_engine.python_runtime import runtime, init_engine, run_project_script, export_scene_glb
from core_engine.world_manager import world_manager
from core_engine.input_bridge import input_bridge
from user_projects.script_cache import script_cache


def bootstrap(files_dir: str, cache_dir: str) -> str:
    """
    Initializes engine storage directories, session caches, and registers paths.
    """
    script_cache.set_cache_directory(os.path.join(cache_dir, "tekivy_session"))
    return init_engine(files_dir, cache_dir)


def execute_current() -> str:
    """
    Runs the current active script, enforces sandbox safety limits,
    and returns JSON execution status to the Kotlin UI thread.
    """
    return run_project_script(timeout_sec=8.0)


def export_glb(filename: str = "scene_export.glb", selected_node: str = None) -> str:
    """
    Exports the current scene or selected node to GLB format.
    If selected_node is None or empty, exports the entire scene.
    """
    node_id = selected_node if (selected_node and selected_node.strip()) else None
    return export_scene_glb(filename, selected_node_id=node_id)


def select_scene_node(node_id: str = None) -> str:
    """
    Selects or clears the active target node for viewport inspection or single-object export.
    """
    target = node_id if (node_id and node_id.strip()) else None
    return world_manager.select_node(target)


def handle_gesture(gesture_type: str, *args) -> str:
    """
    Routes touch events from the Android GLSurfaceView to the input bridge.
    Supported types: 'drag' (dx, dy), 'pinch' (delta), 'tap' (norm_x, norm_y).
    """
    try:
        if gesture_type == "drag" and len(args) >= 2:
            return input_bridge.on_drag(float(args[0]), float(args[1]))
        elif gesture_type == "pinch" and len(args) >= 1:
            return input_bridge.on_pinch(float(args[0]))
        elif gesture_type == "tap" and len(args) >= 2:
            return input_bridge.on_tap_select(float(args[0]), float(args[1]))
        else:
            return json.dumps({"status": "ignored", "reason": "unrecognized gesture"})
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)})


if __name__ == "__main__":
    # Local terminal testing fallback
    local_dir = os.path.dirname(os.path.abspath(__file__))
    res = bootstrap(
        files_dir=os.path.join(local_dir, "sandbox_files"),
        cache_dir=os.path.join(local_dir, "sandbox_cache"),
    )
    print("Bootstrap result:", res)
    exec_res = execute_current()
    print("Execution result:", exec_res)
