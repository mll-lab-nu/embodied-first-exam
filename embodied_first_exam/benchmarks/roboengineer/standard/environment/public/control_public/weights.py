"""Bounded data-only policy ABI. No ONNX graph, Python, pickle, or external tensor paths in evaluation."""

import io, zipfile
from pathlib import Path
import numpy as np


def arrays(source, shapes):
    raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    if len(raw) > 8 * 1024**2:
        raise ValueError("Policy size")
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError("Invalid policy archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if len(infos) != len(shapes) or {i.filename for i in infos} != {k + ".npy" for k in shapes}:
            raise ValueError("Policy archive fields")
        if sum(i.file_size for i in infos) > 8 * 1024**2 or any(i.file_size > 4 * 1024**2 for i in infos):
            raise ValueError("Policy decompression limit")
        for entry in infos:
            with z.open(entry) as stream:
                version = np.lib.format.read_magic(stream)
                if version not in ((1, 0), (2, 0)):
                    raise ValueError("NPY version")
                reader = (
                    np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
                )
                shape, fortran, dtype = reader(stream)
                if shape != shapes[entry.filename[:-4]] or dtype.kind not in "fi" or dtype.itemsize not in (4, 8):
                    raise ValueError("Tensor header")

    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        result = {k: z[k].copy() for k in shapes}
    for k, v in result.items():
        # abs(min_signed_integer) overflows; compare in the original supported dtype.
        if (
            v.shape != shapes[k]
            or v.dtype.kind not in "fi"
            or not np.isfinite(v).all()
            or (v < -10000).any()
            or (v > 10000).any()
        ):
            raise ValueError("Invalid tensor " + k)
    if (result["std"] < 1e-5).any():
        raise ValueError("Invalid standard deviation")
    return result


def shapes(family):
    dims = [62, 256, 256, 16] if family == "linearbot" else [98, 512, 256, 128, 29]
    s = {"mean": (dims[0],), "std": (dims[0],)}
    for i, (a, b) in enumerate(zip(dims, dims[1:])):
        s.update({f"w{i}": (b, a), f"b{i}": (b,)})
    return s


class Network:
    def __init__(self, path, family):
        self.family = family
        self.a = arrays(path, shapes(family))

    def __call__(self, x):
        a = self.a
        y = (np.asarray(x, dtype=np.float32) - a["mean"]) / a["std"]
        n = (len(a) - 2) // 2
        for i in range(n):
            y = a[f"w{i}"] @ y + a[f"b{i}"]
            if i < n - 1:
                y = np.tanh(y) if self.family == "linearbot" else np.where(y > 0, y, np.expm1(np.minimum(y, 0)))
        if not np.isfinite(y).all():
            raise ValueError("Nonfinite actor")
        return np.clip(y, -1, 1) if self.family == "linearbot" else np.clip(y, -100, 100)


def convert_linearbot(source, dest):
    with np.load(source, allow_pickle=False) as z:
        a = {k: z[k] for k in shapes("linearbot")}
    np.savez_compressed(dest, **a)
    Network(dest, "linearbot")


def convert_g1(source, dest):
    import onnx
    from onnx import numpy_helper

    m = onnx.load(str(source))
    a = {t.name: numpy_helper.to_array(t) for t in m.graph.initializer}
    nodes = list(m.graph.node)
    if [n.op_type for n in nodes] != ["Sub", "Div", "Gemm", "Elu", "Gemm", "Elu", "Gemm", "Elu", "Gemm"]:
        raise ValueError("Unsupported actor architecture")
    values = {"mean": a[nodes[0].input[1]].reshape(98), "std": a[nodes[1].input[1]].reshape(98)}
    for i, node in enumerate(nodes[2::2]):
        values.update({f"w{i}": a[node.input[1]], f"b{i}": a[node.input[2]]})
    np.savez_compressed(dest, **values)
    Network(dest, "g1")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("family", choices=["linearbot", "g1"])
    p.add_argument("source")
    p.add_argument("dest")
    v = p.parse_args()
    (convert_linearbot if v.family == "linearbot" else convert_g1)(v.source, v.dest)
