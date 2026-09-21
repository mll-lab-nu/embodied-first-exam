"""Dependency-free smoke task and a callback adapter for existing Genesis tasks."""
import io
import math
import struct
import zlib


def _png(width, height, rows):
    def chunk(kind, data):
        return struct.pack("!I", len(data))+kind+data+struct.pack("!I", zlib.crc32(kind+data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(b"\0"+r for r in rows))) + chunk(b"IEND", b""))


class CounterTask:
    """Move a marker to x=3. Protocol smoke task, never physics evidence."""
    def __init__(self, asset_dir=None):
        self.x = 0

    def describe(self):
        return dict(task_id="counter_smoke", objective="Move x to 3; |x| > 10 fails.",
                    cameras=["front", "top"], control_dt_s=.05, physics_qualified=False,
                    action_schema={"dx": "number in [-1, 1]"},
                    example_code='env.step({"dx": 1}, steps=3)')

    def validate_action(self, action):
        if set(action) != {"dx"} or type(action["dx"]) not in (int, float) or not -1 <= action["dx"] <= 1:
            raise ValueError("Expected only dx in [-1, 1]")

    def step(self, action):
        self.x += action["dx"]

    def observe(self):
        return {"x": self.x}

    def render(self):
        result = {}
        for camera in ("front", "top"):
            rows = []
            for y in range(80):
                row = bytearray()
                for x in range(240):
                    a, b = (x, y) if camera == "front" else (239-x, y)
                    color = (30, 42, 58)
                    if abs(a-156) < 3:
                        color = (78, 194, 137)
                    if abs(a-(120+12*self.x)) < 5 and abs(b-40) < 12:
                        color = (242, 177, 70)
                    row.extend(color)
                rows.append(bytes(row))
            result[camera] = _png(240, 80, rows)
        return result

    def evaluate(self):
        status = "succeeded" if abs(self.x-3) < 1e-9 else "failed" if abs(self.x) > 10 else "running"
        return dict(status=status)


class GenesisAdapter:
    """Wrap a built scene. All callbacks are trusted evaluator code.

    apply_action must only set control targets (no internal stepping); observe
    must expose only permitted sensors. evaluate must latch any failure.
    """
    def __init__(self, *, scene, cameras, description, validate_action, apply_action, observe, evaluate,
                 public_assets=None):
        self.scene, self.cameras = scene, cameras
        self.description = dict(description, cameras=list(cameras), control_dt_s=float(scene.dt))
        self.validate_action, self.apply_action = validate_action, apply_action
        self._observe, self.evaluate = observe, evaluate
        self.public_assets = public_assets or {}

    def observe(self):
        from .camera_info import pose_metadata
        # Session renders before observing, so attached poses match the saved RGB.
        return dict(self._observe(), camera_poses={name: pose_metadata(camera.transform)
                    for name, camera in self.cameras.items()})

    def describe(self):
        return self.description

    def step(self, action):
        self.apply_action(action)
        self.scene.step()

    def render(self):
        from PIL import Image
        from topogym.utils.recording import update_dynamic_camera
        result = {}
        for name, camera in self.cameras.items():
            update_dynamic_camera(camera)
            rgb = camera.render()[0]
            if hasattr(rgb, "detach"):
                rgb = rgb.detach().cpu().numpy()
            stream = io.BytesIO()
            Image.fromarray(rgb).save(stream, format="PNG")
            result[name] = stream.getvalue()
        return result


def finite_vector(value, size, name):
    if not isinstance(value, list) or len(value) != size or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in value
    ):
        raise ValueError(f"{name} must contain {size} finite numbers")
