import json
import math
from typing import Dict, Any, Optional
from .world_manager import world_manager
from .python_runtime import runtime


class InputBridge:
    """
    Translates native Android touch gestures from the Kotlin GLSurfaceView
    into Python camera transforms, infinite-world loop wrapping, and node picking.
    """

    def __init__(self):
        self.look_sensitivity: float = 0.25
        self.zoom_sensitivity: float = 0.08
        self.min_pitch: float = -85.0
        self.max_pitch: float = 85.0

    def on_drag(self, dx: float, dy: float) -> str:
        """
        Handles single-finger slide gesture to look around the 3D viewport.
        """
        world_manager.camera_yaw = (world_manager.camera_yaw + dx * self.look_sensitivity) % 360.0
        new_pitch = world_manager.camera_pitch - dy * self.look_sensitivity
        world_manager.camera_pitch = max(self.min_pitch, min(self.max_pitch, new_pitch))

        return json.dumps({
            "event": "camera_rotate",
            "yaw": world_manager.camera_yaw,
            "pitch": world_manager.camera_pitch,
            "pos": world_manager.camera_pos,
        })

    def on_pinch(self, scale_delta: float) -> str:
        """
        Handles two-finger pinch-in / pinch-out to move forward or backward
        along the camera's current forward vector, applying the infinite-loop
        grassland wrapping trick if enabled by the script.
        """
        yaw_rad = math.radians(world_manager.camera_yaw)
        pitch_rad = math.radians(world_manager.camera_pitch)

        forward_x = math.sin(yaw_rad) * math.cos(pitch_rad)
        forward_y = math.sin(pitch_rad)
        forward_z = -math.cos(yaw_rad) * math.cos(pitch_rad)

        step = scale_delta * self.zoom_sensitivity
        nx = world_manager.camera_pos[0] + forward_x * step
        ny = max(0.5, world_manager.camera_pos[1] + forward_y * step)
        nz = world_manager.camera_pos[2] + forward_z * step

        # Apply seamless loop wrapping on X and Z if infinite world mode is active
        world_manager.camera_pos = world_manager.wrap_position(nx, ny, nz)

        return json.dumps({
            "event": "camera_move",
            "pos": world_manager.camera_pos,
            "infinite_loop_active": world_manager.infinite_loop,
        })

    def on_tap_select(self, norm_x: float, norm_y: float) -> str:
        """
        Handles single-tap object selection in the 3D viewport.
        `norm_x` and `norm_y` are normalized screen coordinates in [-1.0, 1.0].
        If a node is hit, it becomes the active selection for single-object GLB export.
        If empty space is tapped, selection resets to None (full-scene GLB export).
        """
        yaw_rad = math.radians(world_manager.camera_yaw + norm_x * 30.0)
        pitch_rad = math.radians(world_manager.camera_pitch - norm_y * 20.0)

        ray_dir = (
            math.sin(yaw_rad) * math.cos(pitch_rad),
            math.sin(pitch_rad),
            -math.cos(yaw_rad) * math.cos(pitch_rad),
        )
        cam_x, cam_y, cam_z = world_manager.camera_pos

        closest_id: Optional[str] = None
        closest_dist: float = float("inf")

        for node_id, node in world_manager.nodes.items():
            if node_id == "ground_plane":
                continue

            px, py, pz = node["pos"]
            sx, sy, sz = node["scale"]
            radius = max(sx, sy, sz) * 0.65

            vx, vy, vz = px - cam_x, py - cam_y, pz - cam_z
            proj = vx * ray_dir[0] + vy * ray_dir[1] + vz * ray_dir[2]
            if proj <= 0.0:
                continue

            dist_sq = (vx * vx + vy * vy + vz * vz) - (proj * proj)
            if dist_sq <= (radius * radius) and proj < closest_dist:
                closest_dist = proj
                closest_id = node_id

        world_manager.select_node(closest_id)

        return json.dumps({
            "event": "node_selected",
            "selected_node": world_manager.selected_node_id,
            "export_scope": "single_object" if world_manager.selected_node_id else "full_scene",
        })

    def dispatch_custom_controller(self, action: str, value: float = 0.0) -> str:
        """
        If the user has created a `control.py` script in their project,
        forwards custom input actions to it; otherwise returns an advisory hint.
        """
        if "control.py" not in runtime.scripts:
            return json.dumps({
                "status": "no_controller",
                "hint": "Add a control.py script to your project to enable joystick movement.",
            })

        return json.dumps({
            "status": "controller_event",
            "action": action,
            "value": value,
        })


# Global singleton instance accessed by the Kotlin touch listener
input_bridge = InputBridge()


# Top-level helper functions for direct Kotlin JNI calls
def handle_touch_drag(dx: float, dy: float) -> str:
    return input_bridge.on_drag(dx, dy)


def handle_touch_pinch(scale_delta: float) -> str:
    return input_bridge.on_pinch(scale_delta)


def handle_tap_pick(norm_x: float, norm_y: float) -> str:
    return input_bridge.on_tap_select(norm_x, norm_y)
