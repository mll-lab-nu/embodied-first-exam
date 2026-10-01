def _check_success(self) -> torch.Tensor:
        """Check if task is successful: card overlaps target by 50%, resting on it, and not grasped."""

        objs_info = self.collect_objs_info()

        card_name = "bank card"
        target_name = "target area"
        if card_name not in objs_info or target_name not in objs_info:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        card = objs_info[card_name]
        target = objs_info[target_name]

        # Card must be resting on (or very near) the target surface, not floating above it
        TARGET_TOP_Z = 0.961  # top of target cube (pos z=0.96, half-size 0.001)
        RESTING_Z_TOL = 0.05
        card_z = float(card["pos"][2])
        if card_z > TARGET_TOP_Z + RESTING_Z_TOL:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Card must not be held by either gripper
        if check_being_held(card, self._robot):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def get_poly(obj):
            ch = obj.get("convex_hull_2d", None)
            try:
                if ch is not None and len(ch) >= 3:
                    return [(float(p[0]), float(p[1])) for p in ch]
            except Exception:
                pass
            b = obj.get("bounds", None)
            if b is None:
                return None
            try:
                (xmin, ymin, _), (xmax, ymax, _) = b
                return [
                    (float(xmin), float(ymin)),
                    (float(xmax), float(ymin)),
                    (float(xmax), float(ymax)),
                    (float(xmin), float(ymax)),
                ]
            except Exception:
                return None

        card_poly = get_poly(card)
        target_poly = get_poly(target)
        if card_poly is None or target_poly is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def poly_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            area = 0.0
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                area += x1 * y2 - x2 * y1
            return abs(area) * 0.5

        def signed_area(poly):
            s = 0.0
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                s += x1 * y2 - x2 * y1
            return 0.5 * s

        def line_intersection(p1, p2, p3, p4):
            x1, y1 = p1
            x2, y2 = p2
            x3, y3 = p3
            x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-12:
                return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
            det1 = x1 * y2 - y1 * x2
            det2 = x3 * y4 - y3 * x4
            px = (det1 * (x3 - x4) - (x1 - x2) * det2) / denom
            py = (det1 * (y3 - y4) - (y1 - y2) * det2) / denom
            return (px, py)

        def clip_polygon(subject, clip):
            if subject is None or clip is None or len(subject) < 3 or len(clip) < 3:
                return []
            ori_sign = 1.0 if signed_area(clip) >= 0.0 else -1.0

            def inside(pt, a, b):
                cross = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
                return ori_sign * cross >= -1e-9

            output = [(float(x), float(y)) for x, y in subject]
            cl = [(float(x), float(y)) for x, y in clip]
            for i in range(len(cl)):
                a = cl[i]
                b = cl[(i + 1) % len(cl)]
                input_list = output
                output = []
                if not input_list:
                    break
                s = input_list[-1]
                for e in input_list:
                    if inside(e, a, b):
                        if not inside(s, a, b):
                            output.append(line_intersection(s, e, a, b))
                        output.append(e)
                    elif inside(s, a, b):
                        output.append(line_intersection(s, e, a, b))
                    s = e
            return output

        inter_poly = clip_polygon(card_poly, target_poly)
        card_area = poly_area(card_poly)
        inter_area = poly_area(inter_poly)

        if card_area <= 0.0:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        overlap_ratio = inter_area / card_area
        return torch.tensor([overlap_ratio >= 0.5 - 1e-6], dtype=torch.bool, device=self._device)
