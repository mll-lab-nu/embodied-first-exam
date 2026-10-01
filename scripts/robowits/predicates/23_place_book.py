def _check_success(self) -> torch.Tensor:
        """Check if task is successful: book on mat, block undisturbed."""
        objs_info = self.collect_objs_info()

        BOOK_ON_MAT_RATIO = 0.95
        BOOK_HB_NO_OVERLAP_RATIO = 0.02
        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        def get_hull_xy(bounds, hull_2d):
            if hull_2d is not None and len(hull_2d) >= 3:
                return [(float(p[0]), float(p[1])) for p in hull_2d]
            if bounds is None:
                return None
            xmin, ymin = float(bounds[0][0]), float(bounds[0][1])
            xmax, ymax = float(bounds[1][0]), float(bounds[1][1])
            return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]

        def is_within_table_bounds(poly):
            if poly is None:
                return False
            for x, y in poly:
                if x < TABLE_X_MIN - 1e-3 or x > TABLE_X_MAX + 1e-3:
                    return False
                if y < TABLE_Y_MIN - 1e-3 or y > TABLE_Y_MAX + 1e-3:
                    return False
            return True

        def polygon_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            n = len(poly)
            area = 0.0
            for i in range(n):
                j = (i + 1) % n
                area += poly[i][0] * poly[j][1]
                area -= poly[j][0] * poly[i][1]
            return abs(area) / 2.0

        def compute_overlap_ratio(poly_a, poly_b):
            inter_area = _utils.intersection_area(poly_a, poly_b)
            a_area = polygon_area(poly_a)
            if a_area <= 1e-9:
                return 0.0
            return inter_area / a_area

        hb = objs_info.get("heavy block")
        book = objs_info.get("thin book")
        mat = objs_info.get("blue target mat")

        if hb is None or book is None or mat is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        hb_hull = get_hull_xy(hb.get("bounds"), hb.get("convex_hull_2d"))
        book_hull = get_hull_xy(book.get("bounds"), book.get("convex_hull_2d"))
        mat_hull = get_hull_xy(mat.get("bounds"), mat.get("convex_hull_2d"))

        if hb_hull is None or book_hull is None or mat_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not is_within_table_bounds(hb_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not is_within_table_bounds(book_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not is_within_table_bounds(mat_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        euler = hb.get("euler")
        if euler is not None:
            roll_deg = abs(float(euler[0])) * 180.0 / np.pi
            pitch_deg = abs(float(euler[1])) * 180.0 / np.pi
            roll_ok = roll_deg <= 15.0
            pitch_ok = pitch_deg <= 15.0
            if not (roll_ok and pitch_ok):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        book_area = polygon_area(book_hull)
        if book_area <= 1e-5:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inter_b_hb = compute_overlap_ratio(book_hull, hb_hull) * book_area
        free_of_block = inter_b_hb <= max(1e-5, BOOK_HB_NO_OVERLAP_RATIO * book_area)

        inter_b_m = compute_overlap_ratio(book_hull, mat_hull)
        on_mat = inter_b_m >= BOOK_ON_MAT_RATIO

        return torch.tensor([free_of_block and on_mat], dtype=torch.bool, device=self._device)
