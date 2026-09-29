"""Exact-frame observation clips, backed by disk and the shared video writer."""
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from .encoding import VideoWriter


class FrameSequence:
    def __init__(self, cameras, *, fps, video=False):
        self.temporary = TemporaryDirectory(prefix="topogym-observation-")
        self.root = Path(self.temporary.name)
        self.cameras = cameras
        self.writers = {c:VideoWriter(self.root/f"{c}.mp4",fps) for c in cameras} if video else {}
        self.count = 0
        self.shapes = {}

    def append(self, frame, *, depth=False):
        for camera in self.cameras:
            rgb = frame.rgb[camera]
            self.shapes[camera] = rgb.shape
            np.save(self.root/f"rgb-{camera}-{self.count}.npy",rgb,allow_pickle=False)
            if camera in self.writers:
                self.writers[camera].append_data(rgb)
            if depth:
                np.save(self.root/f"depth-{camera}-{self.count}.npy",frame.depth[camera],allow_pickle=False)
        self.count += 1

    def read(self, kind, camera, index):
        return np.load(self.root/f"{kind}-{camera}-{index}.npy",allow_pickle=False)

    def array(self, kind, camera, dtype):
        first = self.read(kind,camera,0)
        output = np.lib.format.open_memmap(self.root/f"array-{kind}-{camera}.npy",mode="w+",dtype=dtype,shape=(self.count,*first.shape))
        for index in range(self.count):
            output[index] = self.read(kind,camera,index)
        return output

    def finish_video(self):
        for writer in self.writers.values():
            writer.close()
        self.writers.clear()

    def close(self):
        for writer in self.writers.values():
            writer.close(commit=False)
        self.writers.clear()
        self.temporary.cleanup()
