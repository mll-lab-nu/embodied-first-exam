def _check_success(self) -> torch.Tensor:
        """Check if task is successful: box overlaps target by 80%."""
        objs_info = self.collect_objs_info()

        TABLE_BOUNDS = {"x_min": 0.21, "x_max": 1.00, "y_min": -0.69, "y_max": 0.69}
        EPS = 1e-6

        box_name = "tall cardboard box"
        target_name = "target area"
        if box_name not in objs_info or target_name not in objs_info:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        box = objs_info[box_name]
        tgt = objs_info[target_name]

        box_hull = box.get("convex_hull_2d", None)
        tgt_hull = tgt.get("convex_hull_2d", None)
        if box_hull is None or tgt_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def clean_polygon(poly: np.ndarray) -> np.ndarray:
            poly = np.asarray(poly, dtype=float).reshape(-1, 2)
            if len(poly) >= 2 and np.linalg.norm(poly[0] - poly[-1]) < 1e-9:
                poly = poly[:-1]
            if len(poly) > 1:
                dedup = [poly[0]]
                for p in poly[1:]:
                    if np.linalg.norm(p - dedup[-1]) > 1e-9:
                        dedup.append(p)
                poly = np.array(dedup)
            return poly

        box_hull = clean_polygon(box_hull)
        tgt_hull = clean_polygon(tgt_hull)
        if len(box_hull) < 3 or len(tgt_hull) < 3:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def poly_area(poly: np.ndarray) -> float:
            x = poly[:, 0]
            y = poly[:, 1]
            return 0.5 * float(np.abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))

        def signed_area(poly: np.ndarray) -> float:
            x = poly[:, 0]
            y = poly[:, 1]
            return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

        def ensure_ccw(poly: np.ndarray) -> np.ndarray:
            return poly if signed_area(poly) > 0 else poly[::-1].copy()

        def line_intersection(p1, p2, q1, q2):
            p1 = np.asarray(p1, float)
            p2 = np.asarray(p2, float)
            q1 = np.asarray(q1, float)
            q2 = np.asarray(q2, float)
            r = p2 - p1
            s = q2 - q1
            rxs = r[0] * s[1] + (-r[1]) * s[0]
            q_p = q1 - p1
            if abs(rxs) < 1e-12:
                return (p2 + q2) / 2.0
            t = (q_p[0] * s[1] - q_p[1] * s[0]) / rxs
            return p1 + t * r

        def suth_hodg_intersection(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
            output = subject.copy()
            clip = ensure_ccw(clip)
            if len(output) == 0:
                return output
            for i in range(len(clip)):
                A = clip[i]
                B = clip[(i + 1) % len(clip)]
                new_output = []
                if len(output) == 0:
                    return output
                S = output[-1]
                for E in output:

                    def is_inside(P, A=A, B=B):
                        return ((B[0] - A[0]) * (P[1] - A[1]) - (B[1] - A[1]) * (P[0] - A[0])) >= -1e-12

                    S_inside = is_inside(S)
                    E_inside = is_inside(E)
                    if E_inside:
                        if not S_inside:
                            inter_pt = line_intersection(S, E, A, B)
                            new_output.append(inter_pt)
                        new_output.append(E)
                    elif S_inside:
                        inter_pt = line_intersection(S, E, A, B)
                        new_output.append(inter_pt)
                    S = E
                output = np.array(new_output, dtype=float) if len(new_output) else np.zeros((0, 2), dtype=float)
            return output

        def hull_within_table(hull: np.ndarray) -> bool:
            if hull.size == 0:
                return False
            x_min, x_max = TABLE_BOUNDS["x_min"], TABLE_BOUNDS["x_max"]
            y_min, y_max = TABLE_BOUNDS["y_min"], TABLE_BOUNDS["y_max"]
            xs = hull[:, 0]
            ys = hull[:, 1]
            return (
                xs.min() >= x_min - 1e-3
                and xs.max() <= x_max + 1e-3
                and ys.min() >= y_min - 1e-3
                and ys.max() <= y_max + 1e-3
            )

        if not (hull_within_table(box_hull) and hull_within_table(tgt_hull)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        box_area = poly_area(box_hull)
        tgt_area = poly_area(tgt_hull)
        if box_area < EPS or tgt_area < EPS:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inter_poly = suth_hodg_intersection(ensure_ccw(box_hull), ensure_ccw(tgt_hull))
        inter_area = poly_area(inter_poly) if inter_poly is not None and len(inter_poly) >= 3 else 0.0

        coverage = inter_area / max(min(box_area, tgt_area), EPS)

        return torch.tensor([coverage > 0.6], dtype=torch.bool, device=self._device)
