"""Assemble one shared frame axis with bounded temporary media storage."""
import math
import zlib
import numpy as np
from . import wire
from topogym.recording.sequence import FrameSequence


class Frames:
    def __init__(self, request, session):
        self.request, self.session = request, session
        self.samples = []
        self.start = session.control_steps
        self.media = FrameSequence(request.cameras,fps=request.fps,video=request.video in {"mp4","both"})

    def close(self):
        self.media.close()

    def capture(self, *, force=False):
        s,r = self.session,self.request
        if self.samples and self.samples[-1][0] == s.control_steps:
            return
        if not force and self.samples and (s.control_steps-self.start)*r.fps/s.spec["control_hz"] < len(self.samples)-1e-9:
            return
        frame=s.env.sensor_frame(depth=r.depth in {"frames","legacy"})
        self.media.append(frame,depth=r.depth in {"frames","legacy"})
        self.samples.append((s.control_steps,frame.sim_time_s,frame.camera_metadata,s.robot.measure()))

    def encode(self, meta):
        r=self.request
        self.capture(force=True)
        self.media.finish_video()
        parts=[wire.array("proprio",np.stack([p for _,_,_,p in self.samples])),
               wire.array("frame_step",np.array([s[0] for s in self.samples],dtype=np.int64)),
               wire.array("frame_time_s",np.array([s[0]/self.session.spec["control_hz"] for s in self.samples],dtype=np.float64))]
        last=self.session.env.sensor_frame(depth=r.depth != "none")
        cameras={}
        optional={}
        for name in r.cameras:
            if r.video in {"mp4","both"}:
                parts.append(wire.blob(f"video/{name}",(self.media.root/f"{name}.mp4").read_bytes(),kind="mp4",fps=r.fps,n=len(self.samples)))
            parts.append(wire.array(f"last/{name}",last.rgb[name]))
            extrinsics=np.array([c[name]["T_camera_cv_from_world"] for _,_,c,_ in self.samples],dtype=np.float64)[:,:3]
            parts.append(wire.array(f"extrinsic_cv/{name}",extrinsics))
            c=last.camera_metadata[name]
            cameras[name]=dict(intrinsic_cv=c["K_px"],extrinsic_cv=extrinsics[-1].tolist(),
                cam2world_gl=(np.array(c["T_world_from_camera_cv"]) @ np.diag([1.,-1.,-1.,1.])).tolist(),image_size=c["resolution_px"])
            if r.depth in {"last","frames"}:
                parts.append(wire.array(f"last_depth/{name}",last.depth[name]))
            shape=self.media.shapes[name]
            if r.video in {"frames","both"}:
                optional[f"frames/{name}"]=len(self.samples)*math.prod(shape)
            if r.depth == "legacy":
                optional[f"depth/{name}"]=len(self.samples)*math.prod(shape[:2])*2
            elif r.depth == "frames":
                compressor=zlib.compressobj()
                destination=self.media.root/f"{name}.depth.zlib"
                with destination.open("wb") as stream:
                    for i in range(len(self.samples)):
                        d=self.media.read("depth",name,i)
                        mm=np.rint(np.clip(d,0,65.535)*1000).astype("<u2")
                        stream.write(compressor.compress(mm.tobytes()))
                    stream.write(compressor.flush())
                optional[f"depth_frames/{name}"]=destination.stat().st_size
        degraded=[]
        for prefixes in (("depth_frames/","depth/"),("frames/",)):
            if sum(len(p["data"]) for p in parts)+sum(optional.values())+wire.MAX_HEADER > wire.MAX_RESPONSE:
                for key in list(optional):
                    if key.startswith(prefixes):
                        degraded.append(key)
                        del optional[key]
        for key in optional:
            kind,name=key.split("/",1)
            if kind == "depth_frames":
                shape=[len(self.samples),*self.media.shapes[name][:2]]
                parts.append(wire.blob(key,(self.media.root/f"{name}.depth.zlib").read_bytes(),codec="zlib",dtype="uint16",shape=shape,unit="mm"))
            else:
                parts.append(wire.array(key,self.media.array("rgb" if kind=="frames" else "depth",name,np.uint8 if kind=="frames" else np.float16)))
        meta.update(cameras=cameras,proprio=dict(layout=self.session.spec["proprio_layout"],now=self.samples[-1][3].tolist()),degraded=degraded)
        return wire.encode(meta,parts)
