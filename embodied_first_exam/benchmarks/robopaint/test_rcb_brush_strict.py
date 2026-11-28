"""Offline test of rcb_brush_strict.apply_rules' stroke cap (numpy + scipy only, no scene, no rendering).

Calligraphy (the rule has the counted-stroke keys stroke_gap_mm, mark_min_width_mm, max_stroke_path_mm) counts strokes as they
are written: an inked contact too light to leave a mark is no stroke. The picture rule (rcb_brush_score.is_success) has its own
cap on the inked contacts (stroke_count_ok); with counted strokes that cap must not fail the run, the counted one decides.
Lettering (no counted-stroke keys) keeps the contact cap.

  python3 embodied_first_exam/benchmarks/robopaint/test_rcb_brush_strict.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_brush_strict as S  # noqa: E402

PICTURE = {"iou": 0.8, "boundary_f": 0.8, "min_stroke_coverage": 0.8, "max_stray_frac": 0.05, "max_strokes": 2,
           "max_path_mm": 810.0, "min_mark_width_mm": 1.37, "register_mm": 3.0}
GLYPH = {**PICTURE, "stroke_gap_mm": 5.0, "mark_min_width_mm": 0.1, "max_stroke_path_mm": 720.0,
         "max_scribble": 12.0, "max_scribble_share": 0.1, "scribble_min_mm": 10.0}
LETTERS = dict(PICTURE)


def contact(x0_mm, width_mm, n=41, length_mm=40.0):
    """One straight inked contact on the main sheet: samples (n, 9), column 3 = the mark's width (m)."""
    P = np.zeros((n, 9))
    P[:, 0] = (x0_mm + np.linspace(0.0, length_mm, n)) / 1000.0
    P[:, 3] = width_mm / 1000.0
    return {"sheet": "main", "inked": True, "samples": P, "mask": np.full((4, 4), 255, np.uint8)}


# two written strokes and one touch too light to ink (its mark 0.05 mm < mark_min_width_mm): 3 inked contacts, 2 strokes
STROKES = [contact(0, 2.0), contact(100, 0.05, n=3, length_mm=1.0), contact(200, 2.0)]


def picture_metrics(cfg, n_contacts):
    """The picture rule's metrics as rcb_brush_score.score_ink leaves them: the picture matches, the contact cap as counted."""
    import rcb_brush_score as G
    m = {"iou": 0.9, "boundary_f": 0.9, "min_stroke_coverage": 0.9, "stray_frac": 0.0, "n_strokes": float(n_contacts),
         "max_strokes": float(cfg["max_strokes"]), "stroke_count_ok": float(n_contacts <= cfg["max_strokes"])}
    m["success"] = float(G.is_success(m, cfg))
    m["final_reward"] = G.final_reward(m)
    return m


def rules(cfg, m):
    return S.apply_rules(m, S.stroke_stats(STROKES, None, 0.01), cfg, pieces=S.piece_stats(STROKES, None, cfg))


class StrokeCap(unittest.TestCase):
    def test_calligraphy_counts_marks_not_contacts(self):
        m = picture_metrics(GLYPH, 3)
        self.assertEqual(m["stroke_count_ok"], 0.0)            # 3 inked contacts > 2
        out = rules(GLYPH, m)
        self.assertEqual(out["n_strokes_counted"], 2.0)
        self.assertEqual(out["strokes_counted_ok"], 1.0)
        self.assertEqual(out["image_success"], 1.0)
        self.assertEqual(out["success"], 1.0)

    def test_calligraphy_counted_cap_still_binds(self):
        cfg = {**GLYPH, "max_strokes": 1}
        out = rules(cfg, picture_metrics(cfg, 3))
        self.assertEqual(out["strokes_counted_ok"], 0.0)
        self.assertEqual(out["success"], 0.0)

    def test_calligraphy_picture_rule_still_binds(self):
        m = picture_metrics(GLYPH, 3)
        m["iou"] = 0.5
        out = rules(GLYPH, m)
        self.assertEqual(out["image_success"], 0.0)
        self.assertEqual(out["success"], 0.0)

    def test_lettering_keeps_the_contact_cap(self):
        out = rules(LETTERS, picture_metrics(LETTERS, 3))
        self.assertNotIn("n_strokes_counted", out)
        self.assertEqual(out["image_success"], 0.0)
        self.assertEqual(out["success"], 0.0)
        out = rules(LETTERS, picture_metrics(LETTERS, 2))
        self.assertEqual(out["success"], 1.0)


if __name__ == "__main__":
    unittest.main()
