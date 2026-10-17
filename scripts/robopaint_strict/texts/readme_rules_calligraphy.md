colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than {{MAX_PATH_MM}} mm ({{PATH_FACTOR}} × the reference
solution's {{REF_PATH_MM}} mm) made of marks narrower than {{MIN_MARK_WIDTH_MM}} mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; {{MARK_FACTOR}} × the reference's {{REF_MARK_WIDTH_MM}} mm). The cap counts strokes as written: a contact is cut where the brush moves more than {{STROKE_GAP_MM}} mm without a mark
{{MARK_MIN_WIDTH_MM}} mm wide, and a stroke longer than {{MAX_STROKE_PATH_MM}} mm ({{STROKE_PATH_FACTOR}} × the reference's
longest, {{REF_LONGEST_STROKE_MM}} mm) counts once per started {{MAX_STROKE_PATH_MM}} mm; at most {{SCRIBBLE_SHARE_PCT}} % of the
path in strokes longer than {{MAX_SCRIBBLE}} × their bounding box's diagonal (sweeps).
