def _check_success(self) -> torch.Tensor:
        """Check if task is successful: book resting on cup supports."""
        objs_info = self.collect_objs_info()

        ELEV_CLEARANCE = 0.005
        CONTACT_TOL = 0.035
        SUPPORT_HORIZ_TOL = 0.05
        FALL_BELOW_TOL = 0.05

        cup1 = objs_info.get("cup support 1")
        cup2 = objs_info.get("cup support 2")
        book = objs_info.get("heavy book")

        if cup1 is None or cup2 is None or book is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if cup1.get("bounds") is None or cup2.get("bounds") is None or book.get("bounds") is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def get_poly(obj):
            hull = obj.get("convex_hull_2d")
            if hull is not None and len(hull) >= 3:
                return [(float(p[0]), float(p[1])) for p in hull]
            b = obj.get("bounds")
            if b is None:
                return None
            xmin, ymin = b[0][0], b[0][1]
            xmax, ymax = b[1][0], b[1][1]
            return [
                (float(xmin), float(ymin)),
                (float(xmax), float(ymin)),
                (float(xmax), float(ymax)),
                (float(xmin), float(ymax)),
            ]

        def obj_center_xy(obj):
            p = obj.get("pos")
            if p is None:
                return None
            if len(p) < 2:
                return None
            return (float(p[0]), float(p[1]))

        def point_in_poly(pt, poly):
            if pt is None or poly is None or len(poly) < 3:
                return False
            x, y = pt
            inside = False
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 > y) != (y2 > y):
                    xinters = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
                    if x < xinters:
                        inside = not inside
            return inside

        def point_to_poly_dist(pt, poly):
            if pt is None or poly is None or len(poly) < 2:
                return float("inf")
            x, y = pt
            min_d = float("inf")
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                dx, dy = x2 - x1, y2 - y1
                seg_len2 = dx * dx + dy * dy
                if seg_len2 == 0:
                    d = math.hypot(x - x1, y - y1)
                else:
                    t = ((x - x1) * dx + (y - y1) * dy) / seg_len2
                    t = max(0.0, min(1.0, t))
                    projx = x1 + t * dx
                    projy = y1 + t * dy
                    d = math.hypot(x - projx, y - projy)
                if d < min_d:
                    min_d = d
            return min_d

        book_poly = get_poly(book)
        cup1_center = obj_center_xy(cup1)
        cup2_center = obj_center_xy(cup2)

        cup1_zmax = float(cup1["bounds"][1][2])
        cup2_zmax = float(cup2["bounds"][1][2])
        book_zmin = float(book["bounds"][0][2])

        for obj in (cup1, cup2, book):
            if float(obj["bounds"][0][2]) < (self.TABLE_Z - FALL_BELOW_TOL):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        if (book_zmin - self.TABLE_Z) <= ELEV_CLEARANCE:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_cup_under_book(cup_center, _book_poly=book_poly):
            if _book_poly is None or cup_center is None:
                return False
            if point_in_poly(cup_center, _book_poly):
                return True
            return point_to_poly_dist(cup_center, _book_poly) <= SUPPORT_HORIZ_TOL

        if not (is_cup_under_book(cup1_center) and is_cup_under_book(cup2_center)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_in_contact_vert(book_bottom, support_top):
            return abs(book_bottom - support_top) <= CONTACT_TOL and (book_bottom >= support_top - CONTACT_TOL)

        if not (is_in_contact_vert(book_zmin, cup1_zmax) and is_in_contact_vert(book_zmin, cup2_zmax)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if _utils.check_being_held(book, self._robot):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
