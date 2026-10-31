"""Taxim polynomial look-up-table renderer: height map (mm) -> GelSight RGB image.

This is a port of the GPU Taxim implementation (torch backend) released under
the MIT licence by CMURoboTouch; see ``LICENSE_TAXIM_MIT.txt`` next to this
file. Reference:

  Si & Yuan (2022). Taxim: An example-based simulation model for GelSight
  tactile sensors. IEEE RA-L 7(2), 2361-2368. https://arxiv.org/abs/2109.04027

The maths is unchanged. The only implementation differences are:

* ``torch_scatter.scatter_min`` is replaced by ``torch.Tensor.scatter_reduce_``
  with ``reduce="amin"`` (same result, no extra dependency);
* ``torchvision.transforms.functional.resize`` (bilinear, antialiased) is
  replaced by ``torch.nn.functional.interpolate`` with the same settings;
* the simulator parameters are read from ``params.json`` with a small helper
  instead of a dataclass with ``__getattr__`` magic.

Height-map convention (``render``): values are distances in mm from the
undeformed gel surface, positive away from the camera. A taxel in contact has
``height < 0`` after the press-depth shift (see :meth:`TaximRenderer.render`).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import torch
import torch.nn.functional as F

__all__ = ["TaximRenderer", "default_calib_dir"]


def default_calib_dir() -> Path:
    """Directory of the GelSight Mini calibration files shipped with the package."""
    return Path(__file__).resolve().parent / "calib" / "gsmini"


# --------------------------------------------------------------------------- helpers


def _resize_bilinear(img: torch.Tensor, shape: Sequence[int]) -> torch.Tensor:
    """Bilinear resize of a ``(C, H, W)`` or ``(N, C, H, W)`` float tensor.

    Matches ``torchvision.transforms.functional.resize`` with
    ``InterpolationMode.BILINEAR`` (``align_corners=False``, ``antialias=True``).
    """
    shape = [int(shape[0]), int(shape[1])]
    if tuple(img.shape[-2:]) == tuple(shape):
        return img
    squeeze = img.dim() == 3
    x = img.unsqueeze(0) if squeeze else img
    y = F.interpolate(x, size=shape, mode="bilinear", align_corners=False, antialias=True)
    return y.squeeze(0) if squeeze else y


def _fast_conv2d(inp: torch.Tensor, kernel: torch.Tensor) -> torch.Tensor:
    """FFT-based 2D cross-correlation of ``(..., C, H, W)`` with a ``(KH, KW)`` kernel.

    Returns the "valid" part: ``(..., C, H - KH + 1, W - KW + 1)``.
    """
    assert all(e % 2 == 1 for e in kernel.shape[-2:])
    kpy = inp.shape[-2] - kernel.shape[-2]
    kpx = inp.shape[-1] - kernel.shape[-1]
    kernel_padded = F.pad(kernel, (0, kpx, 0, kpy), mode="constant", value=0.0)
    input_ft = torch.fft.fft2(inp)
    kernel_ft = torch.fft.fft2(kernel_padded[None])
    output = torch.real(torch.fft.ifft2(input_ft * torch.conj(kernel_ft)))
    return output[..., : inp.shape[-2] - (kernel.shape[-2] - 1), : inp.shape[-1] - (kernel.shape[-1] - 1)]


def _gaussian_kernel1d(sigma: float, kernel_size: int) -> torch.Tensor:
    x = torch.linspace(-(kernel_size - 1) * 0.5, (kernel_size - 1) * 0.5, steps=kernel_size)
    pdf = torch.exp(-0.5 * (x / sigma).pow(2))
    return pdf / pdf.sum()


def _gaussian_kernel2d(sigma: Sequence[float], kernel_size: Sequence[int], dtype, device) -> torch.Tensor:
    kx = _gaussian_kernel1d(sigma[0], kernel_size[0]).to(device, dtype=dtype)
    ky = _gaussian_kernel1d(sigma[1], kernel_size[1]).to(device, dtype=dtype)
    return torch.mm(ky[:, None], kx[None, :])


def _gaussian_blur(
    img: torch.Tensor, sigma: Sequence[float], kernel_size: Optional[Sequence[int]] = None
) -> torch.Tensor:
    """Gaussian blur of a ``(..., C, H, W)`` tensor with ``sigma = (sigma_x, sigma_y)`` in pixels.

    The kernel size (odd) is chosen so that the outermost weight is below 1e-5.
    Reflect padding, FFT convolution.
    """
    if kernel_size is None:
        eps = 1e-5
        sigma_np = np.array(sigma)
        kernel_size = (
            np.round(np.sqrt(-2 * np.log(eps * np.sqrt(2 * np.pi) * sigma_np)) * sigma_np).astype(np.int_) // 2 * 2 + 1
        ).tolist()
    kernel = _gaussian_kernel2d(sigma, kernel_size, dtype=torch.float, device=img.device)
    p = (np.array(kernel_size) - 1) // 2
    img_padded = F.pad(img, (int(p[0]), int(p[0]), int(p[1]), int(p[1])), mode="reflect")
    return _fast_conv2d(img_padded, kernel)


class _SimParams:
    """Simulator parameters from ``params.json``.

    Every ``*_rel`` entry is relative to the image size: ``sim.name(shape)`` with
    ``shape = (H, W)`` returns ``(value_w * W, value_h * H)`` (tuples element-wise).
    """

    def __init__(self, d: dict):
        self._d = dict(d)
        self.diff_threshold = d["diff_threshold"]
        self.frame_mixing_percentage = d["frame_mixing_percentage"]
        self.contact_scale = d["contact_scale"]
        self.height_precision = d["height_precision"]
        self.discretize_precision = d["discretize_precision"]
        self.fan_angle = d["fan_angle"]
        self.fan_precision = d["fan_precision"]

    def __getattr__(self, item):
        rel = f"{item}_rel"
        d = self.__dict__.get("_d", {})
        if not item.endswith("_rel") and rel in d:
            value = d[rel]

            def scaled(shape):
                assert len(shape) == 2
                w_val, h_val = value[0], value[1]
                w_val = tuple(e * shape[1] for e in w_val) if isinstance(w_val, (list, tuple)) else w_val * shape[1]
                h_val = tuple(e * shape[0] for e in h_val) if isinstance(h_val, (list, tuple)) else h_val * shape[0]
                return w_val, h_val

            return scaled
        raise AttributeError(item)


# --------------------------------------------------------------------------- renderer


def _load_shadow_calib(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """``(shadowDirections, shadowTable)`` of a Taxim shadow calibration file.

    ``shadowTable`` is a ``(3, 63, 24)`` object array of float lists. The packaged file stores it without pickle: the flat
    float64 array ``shadowTable_values`` cut into cells (C order) by the int64 ``shadowTable_offsets``, and
    ``shadowTable_shape``. The pickled ``shadowTable`` array of the original calibration set is read as well.
    """
    data = np.load(str(path), allow_pickle=True)
    directions = data["shadowDirections"]
    if "shadowTable" in data.files:
        return directions, data["shadowTable"]
    values, offsets = data["shadowTable_values"], data["shadowTable_offsets"]
    table = np.empty(tuple(int(n) for n in data["shadowTable_shape"]), dtype=object)
    cells = table.reshape(-1)
    for i in range(cells.size):
        cells[i] = values[offsets[i] : offsets[i + 1]].tolist()
    return directions, table


class TaximRenderer:
    """Taxim renderer for a flat GelSight-type sensor (torch backend).

    Args:
        calib_dir: folder with ``polycalib.npz``, ``gelmap.npy``, ``dataPack.npz``,
            ``shadowTable.npz`` and ``params.json``. ``None`` selects the GelSight
            Mini calibration shipped with the package.
        with_shadow: render the shadow pass (slower, more realistic).
        out_hw: output image size ``(H, W)``; the height map is resized to it first.
        device: torch device.
    """

    def __init__(
        self,
        calib_dir: Optional[str | Path] = None,
        with_shadow: bool = True,
        out_hw: Sequence[int] = (240, 320),
        device: str | torch.device = "cuda",
    ):
        calib_dir = Path(calib_dir) if calib_dir is not None else default_calib_dir()
        if not calib_dir.is_dir():
            raise FileNotFoundError(f"Taxim calibration folder not found: {calib_dir}")
        self.calib_dir = calib_dir
        self.with_shadow = bool(with_shadow)
        self.out_hw = (int(out_hw[0]), int(out_hw[1]))
        self.device = torch.device(device)
        if self.device.type == "cuda" and self.device.index is None:
            self.device = torch.device("cuda", torch.cuda.current_device())

        with (calib_dir / "params.json").open() as f:
            params = json.load(f)
        self.sim = _SimParams(params["simulator"])
        sensor = params["sensor"]
        self.pixmm = float(sensor["pixmm"])
        self.num_bins = int(sensor["num_bins"])
        # Calibration image size; the polynomial features and gradient scaling refer to it.
        self.width = int(sensor["w"])
        self.height = int(sensor["h"])

        with torch.no_grad():
            self._load(calib_dir)
        self._gel_map_cache: dict = {}
        self._features_cache: dict = {}
        self._bg_cache: dict = {}
        self._no_contact: Optional[torch.Tensor] = None

    # ------------------------------------------------------------------ loading

    def _load(self, calib_dir: Path) -> None:
        dev = self.device
        data = np.load(str(calib_dir / "polycalib.npz"))
        # In the calibration file grad_b and grad_r are switched (BGR order).
        self._poly_grad = (
            torch.from_numpy(np.stack([data["grad_b"], data["grad_g"], data["grad_r"]], axis=0) / 255).float().to(dev)
        )

        gel_map = self._np_img_to_torch(np.load(str(calib_dir / "gelmap.npy")), has_channels=False)
        gel_map = _gaussian_blur(gel_map, self.sim.deform_final_sigma(gel_map.shape[1:]))[0] * self.pixmm
        # Normalise the gel map to have a maximum of 0.
        self._gel_map_shift = gel_map.max().item()
        self._gel_map_full_res = gel_map - self._gel_map_shift

        data_file = np.load(str(calib_dir / "dataPack.npz"), allow_pickle=True)
        f0 = self._bgr_to_rgb(self._np_img_to_torch(data_file["f0"] / 255))
        self._bg_proc = self._process_initial_frame(f0)

        # Shadow calibration.
        self._shadow_depth_0 = 0.4
        shadow_directions, shadow_table = _load_shadow_calib(calib_dir / "shadowTable.npz")
        direction = torch.from_numpy(shadow_directions).float().to(dev)
        fan_angle = self.sim.fan_angle
        num_fan_rays = int(fan_angle * 2 / self.sim.fan_precision)
        self._shadow_direction_fan_angles = direction.unsqueeze(-1) + torch.linspace(
            -fan_angle, fan_angle, num_fan_rays, device=dev
        )
        # Append an extra empty entry for heights outside the range; flip BGR -> RGB.
        shadow_table = np.concatenate(
            [np.flip(shadow_table, axis=0), [[[]] * shadow_table.shape[1]] * shadow_table.shape[0]],
            axis=2,
        )
        max_len = max(map(len, shadow_table.reshape((-1,))))
        self._shadow_table_padded = (
            torch.tensor(
                [list(e) + [np.inf] * (max_len - len(e)) for e in shadow_table.reshape((-1,))],
                device=dev,
                dtype=torch.float,
            ).reshape(shadow_table.shape + (-1,))
            / 255
        )

    # ------------------------------------------------------------------ public API

    @torch.no_grad()
    def render(self, height_map_mm: torch.Tensor, press_depth_mm: torch.Tensor) -> torch.Tensor:
        """Render tactile images from a batch of height maps.

        Args:
            height_map_mm: ``(E, H, W)`` object height map in mm (any ``H, W``; it is
                resized bilinearly to ``out_hw``). ``base - penetration`` style maps
                are expected: flat where nothing touches, lower where the object
                presses in.
            press_depth_mm: ``(E,)`` pressing depth in mm. Each map is shifted so that
                its minimum sits ``press_depth`` below the gel surface, i.e.
                ``hm <- hm - min(hm) - press_depth``; taxels with ``hm < 0`` are in
                contact. With ``hm = base - penetration`` and ``press_depth =
                max(penetration)`` the shifted map equals ``-penetration``.

        Returns:
            ``(E, out_h, out_w, 3)`` uint8 RGB tensor on :attr:`device`.
        """
        hm = torch.as_tensor(height_map_mm, dtype=torch.float32, device=self.device)
        if hm.dim() == 2:
            hm = hm.unsqueeze(0)
        press = torch.as_tensor(press_depth_mm, dtype=torch.float32, device=self.device).reshape(-1)
        if press.numel() != hm.shape[0]:
            raise ValueError(f"press_depth_mm has {press.numel()} entries for {hm.shape[0]} height maps")
        hm = _resize_bilinear(hm.unsqueeze(1), self.out_hw).squeeze(1)
        hm = self._shifted_height_map(press, hm)
        img = self._render(hm, shadow=self.with_shadow)  # (E, 3, H, W) in [0, 1]
        return (img.movedim(1, 3) * 255).clamp(0, 255).to(torch.uint8)

    @torch.no_grad()
    def background(self, num: int = 1) -> torch.Tensor:
        """Calibration background image (processed ``f0``), ``(num, out_h, out_w, 3)`` uint8.

        Note that rendering a flat height map does not reproduce this image exactly:
        the polynomial LUT adds a small offset at zero gradient. Use
        :meth:`no_contact_image` for the frame the pipeline produces when nothing touches.
        """
        bg = self._background_img(self.out_hw)  # (3, H, W) in [0, 1]
        bg = (bg.movedim(0, 2) * 255).clamp(0, 255).to(torch.uint8)
        return bg.unsqueeze(0).expand(int(num), -1, -1, -1).contiguous()

    @torch.no_grad()
    def no_contact_image(self, num: int = 1) -> torch.Tensor:
        """Rendered frame of a flat height map (press depth 0), ``(num, out_h, out_w, 3)`` uint8, cached."""
        if getattr(self, "_no_contact", None) is None:
            flat = torch.zeros((1,) + self.out_hw, dtype=torch.float32, device=self.device)
            self._no_contact = self.render(flat, torch.zeros(1, device=self.device))[0]
        return self._no_contact.unsqueeze(0).expand(int(num), -1, -1, -1).contiguous()

    # ------------------------------------------------------------------ cached tables

    def _background_img(self, shape) -> torch.Tensor:
        key = tuple(int(s) for s in shape)
        if key not in self._bg_cache:
            self._bg_cache[key] = _resize_bilinear(self._bg_proc, key)
        return self._bg_cache[key]

    def _gel_map(self, shape) -> torch.Tensor:
        key = tuple(int(s) for s in shape)
        if key not in self._gel_map_cache:
            self._gel_map_cache[key] = _resize_bilinear(self._gel_map_full_res[None], key)[0]
        return self._gel_map_cache[key]

    def _precomputed_features(self, shape) -> torch.Tensor:
        key = tuple(int(s) for s in shape)
        if key not in self._features_cache:
            yy, xx = torch.meshgrid(
                torch.linspace(0, self.height, key[0] + 1, device=self.device)[:-1],
                torch.linspace(0, self.width, key[1] + 1, device=self.device)[:-1],
                indexing="ij",
            )
            xf = xx.flatten()
            yf = yy.flatten()
            self._features_cache[key] = torch.stack(
                [xf * xf, yf * yf, xf * yf, xf, yf, torch.ones(key[0] * key[1], device=self.device)], dim=-1
            )
        return self._features_cache[key]

    # ------------------------------------------------------------------ core

    def _render(self, height_map: torch.Tensor, shadow: bool) -> torch.Tensor:
        """Simulate the tactile image of a shifted height map ``(E, H, W)`` in mm.

        Returns ``(E, 3, H, W)`` RGB in ``[0, 1]``.
        """
        shape = height_map.shape[1:]
        height, width = shape

        deformed_gel, contact_mask = self._gel_pad_deformation(height_map)

        # Gradients of the deformed gel (in pixels).
        deformed_gel_px = deformed_gel / self.pixmm
        grad_mag, grad_dir = self._generate_normals(-deformed_gel_px)

        # Discretise the gradient grid and look the polynomial coefficients up.
        x_binr = 0.5 * torch.pi / (self.num_bins - 1)  # magnitude in [0, pi/2]
        y_binr = 2 * torch.pi / (self.num_bins - 1)  # direction in [-pi, pi]
        idx_mag = torch.floor(grad_mag / x_binr).long()
        idx_dir = torch.floor((grad_dir + torch.pi) / y_binr).long()

        params = self._poly_grad[:, idx_mag, idx_dir].transpose(0, 1)  # (E, 3, H, W, 6)
        params_flat = torch.flatten(params, start_dim=-3, end_dim=-2)  # (E, 3, H*W, 6)
        sim_img_flat = (self._precomputed_features(shape).unsqueeze(0) * params_flat).sum(-1)
        sim_img_r = torch.unflatten(sim_img_flat, dim=-1, sizes=(height, width))  # (E, 3, H, W)

        if not shadow:
            return torch.clip(sim_img_r + self._background_img(shape), 0, 1)

        # Shadow attachment area: dilate the contact mask and keep its rim.
        kernel_size_float = np.array(self.sim.shadow_attachment_kernel_size(shape))
        kernel_size_total = np.round(kernel_size_float * 2).astype(np.int_)
        first_round = kernel_size_total // 2
        rounds = [first_round, kernel_size_total - first_round]
        dilated_mask = contact_mask[..., None, :, :].float()
        for ks in rounds:
            kernel = torch.ones((1, 1, *np.flip(np.maximum(1, ks))), device=self.device)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                dilated_mask = F.conv2d(dilated_mask, kernel, padding="same")
        enlarged_mask = dilated_mask[..., 0, :, :] != 0
        boundary_contact_mask = enlarged_mask & ~contact_mask

        # Normal index into the shadow table.
        norm_map = grad_dir[boundary_contact_mask] + np.pi
        norm_idx = torch.floor(norm_map / self.sim.discretize_precision).long()

        # Height index into the shadow table.
        contact_height = self._gel_map(shape) - deformed_gel
        contact_height_px = contact_height / self.pixmm
        contact_map = contact_height_px[boundary_contact_mask]
        height_idx = torch.floor((contact_map * self.pixmm - self._shadow_depth_0) / self.sim.height_precision).long()
        height_idx_shifted = height_idx + 6
        max_height_idx = self._shadow_table_padded.shape[2] - 1
        height_idx_shifted[(height_idx_shifted < 0) | (height_idx_shifted >= max_height_idx)] = max_height_idx

        shadow_table_sel = self._shadow_table_padded[:, norm_idx, height_idx_shifted]  # (3, K, S)
        thetas = self._shadow_direction_fan_angles[norm_idx]  # (K, F)
        steps = torch.arange(shadow_table_sel.shape[-1], device=self.device)

        batch_idx, y_coord, x_coord = torch.where(boundary_contact_mask)
        x_coord_r = x_coord.reshape((-1, 1, 1))
        y_coord_r = y_coord.reshape((-1, 1, 1))
        shadow_step = self.sim.shadow_step(shape)

        shadow_coords_x = (
            x_coord_r + shadow_step[1] * (steps.reshape((1, 1, -1)) + 1) * torch.cos(thetas).unsqueeze(-1)
        ).long()
        shadow_coords_y = (
            y_coord_r + shadow_step[0] * (steps.reshape((1, 1, -1)) + 1) * torch.sin(thetas).unsqueeze(-1)
        ).long()
        sc_x_clipped = torch.clip(shadow_coords_x, 0, width - 1)
        sc_y_clipped = torch.clip(shadow_coords_y, 0, height - 1)
        sc_valid = (
            (shadow_coords_x >= 0)
            & (shadow_coords_x < width)
            & (shadow_coords_y >= 0)
            & (shadow_coords_y < height)
            & (
                deformed_gel_px[batch_idx[..., None, None], y_coord_r, x_coord_r]
                < deformed_gel_px[batch_idx[..., None, None], sc_y_clipped, sc_x_clipped]
            )
        )
        valid_sc_x = shadow_coords_x[sc_valid]
        valid_sc_y = shadow_coords_y[sc_valid]
        valid_sc_batch = torch.broadcast_to(batch_idx[:, None, None], sc_valid.shape)[sc_valid]
        sc_valid_idx_coord, _, sc_valid_idx_shadow_coord = torch.where(sc_valid)
        valid_values = shadow_table_sel[:, sc_valid_idx_coord, sc_valid_idx_shadow_coord]  # (3, V)
        valid_flat = (valid_sc_batch * height + valid_sc_y) * width + valid_sc_x  # (V,)

        bs = sim_img_r.shape[0]
        shadow_img_flat = torch.full((3, bs * width * height), np.inf, device=self.device)
        # scatter-min of the shadow intensities onto the image (same as scatter_min with an inf-initialised output)
        shadow_img_flat.scatter_reduce_(1, valid_flat.unsqueeze(0).expand_as(valid_values), valid_values, reduce="amin")
        shadow_img = shadow_img_flat.reshape((3, bs, height, width)).transpose(0, 1)
        sim_img_r = torch.minimum(sim_img_r, shadow_img)

        shadow_sim = _gaussian_blur(sim_img_r, self.sim.shadow_blur_sigma(shape))
        shadow_sim_img = shadow_sim + self._background_img(shape)
        shadow_sim_img_blurred = _gaussian_blur(shadow_sim_img, self.sim.deform_final_sigma(shape))
        return torch.clip(shadow_sim_img_blurred, 0, 1)

    def _np_img_to_torch(self, img: np.ndarray, has_channels: bool = True) -> torch.Tensor:
        t = torch.from_numpy(np.ascontiguousarray(img)).to(self.device).float()
        if has_channels:
            b_dims = len(t.shape[:-3])
            return t.permute(*range(b_dims), -1, -3, -2)
        return t[..., None, :, :]

    @staticmethod
    def _bgr_to_rgb(img: torch.Tensor) -> torch.Tensor:
        return torch.flip(img, dims=(-3,))

    def _process_initial_frame(self, f0: torch.Tensor) -> torch.Tensor:
        """Blend the calibration background with a blurred copy where they differ little."""
        f0_blurred = _gaussian_blur(f0, self.sim.initial_frame_sigma(f0.shape[1:]))
        d_i = torch.mean(f0_blurred - f0, dim=0)
        fmp = self.sim.frame_mixing_percentage
        thresh = self.sim.diff_threshold
        return torch.where((d_i < thresh).unsqueeze(0), fmp * f0_blurred + (1 - fmp) * f0, f0)

    @staticmethod
    def _shifted_height_map(press_depth_mm: torch.Tensor, height_map: torch.Tensor) -> torch.Tensor:
        """Shift each map so that its minimum is ``press_depth`` below the gel surface."""
        return height_map - height_map.amin(-1, keepdim=True).amin(-2, keepdim=True) - press_depth_mm.view(-1, 1, 1)

    def _gel_pad_deformation(self, height_map: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Approximate the gel deformation with a Gaussian pyramid; return (deformed gel, contact mask)."""
        pressing_depth_mm = -height_map.amin(-1).amin(-1)
        contact_mask = height_map < 0
        gel = self._gel_map(height_map.shape[1:])
        joined = torch.minimum(height_map, gel)
        # Contact mask slightly smaller than the real one.
        mask = torch.logical_and(
            joined - gel < -pressing_depth_mm[..., None, None] * self.sim.contact_scale, contact_mask
        )
        blurred = joined
        for sigma in zip(*self.sim.deform_pyramid_sigma(height_map.shape[1:])):
            blurred = _gaussian_blur(blurred.unsqueeze(0), sigma)[0]
            blurred[mask] = joined[mask]
        blurred = _gaussian_blur(blurred.unsqueeze(0), self.sim.deform_final_sigma(height_map.shape[1:]))[0]
        return blurred, mask

    def _generate_normals(self, height_map: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Gradient magnitude (as an angle) and direction of ``(E, H, W)`` height maps."""
        h, w = height_map.shape[-2:]
        top = height_map[..., 0 : h - 2, 1 : w - 1]
        bot = height_map[..., 2:h, 1 : w - 1]
        left = height_map[..., 1 : h - 1, 0 : w - 2]
        right = height_map[..., 1 : h - 1, 2:w]
        dzdx = (bot - top) / 2.0
        dzdy = (right - left) / 2.0
        dzdx_norm = dzdx * height_map.shape[1] / self.height
        dzdy_norm = dzdy * height_map.shape[2] / self.width
        mag_tan = torch.sqrt(dzdx_norm**2 + dzdy_norm**2)
        grad_mag = torch.arctan(mag_tan)
        valid = mag_tan != 0
        grad_dir = torch.zeros(mag_tan.shape[:-2] + (h - 2, w - 2), device=self.device)
        grad_dir[valid] = torch.arctan2(dzdx_norm[valid] / mag_tan[valid], dzdy_norm[valid] / mag_tan[valid])
        grad_mag = F.pad(grad_mag, (1, 1, 1, 1), "replicate")
        grad_dir = F.pad(grad_dir, (1, 1, 1, 1), "replicate")
        return grad_mag, grad_dir
