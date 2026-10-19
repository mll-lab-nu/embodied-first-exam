"""Read-only, artifact-bound label quotation review; never a visibility or scoring rule.

Usage: python -m robosafebench.label_review MANIFEST.json
See docs/LABEL_TEXT_REVIEW.md for the input contract and its limits. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA = "robosafebench.label_text_review/1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_TOOLS = frozenset(("ask_operator", "report", "end"))
_KINDS = frozenset(("task", "brief", "operator", "other_public"))


class ReviewInputError(ValueError):
    """The supplied artifact or its declared byte identity cannot be checked."""


def _words(text: str) -> list[str]:
    return _WORD.findall(unicodedata.normalize("NFKC", text).casefold())


def _pointer(value, pointer: str):
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ReviewInputError("JSON pointers must be empty or start with /")
    try:
        for part in pointer[1:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ReviewInputError(f"JSON pointer does not resolve: {pointer}") from exc
    return value


def _artifact(ref: dict, base: Path) -> tuple[bytes, dict]:
    if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
        raise ReviewInputError("each artifact needs path and full sha256")
    expected = ref.get("sha256")
    if not isinstance(expected, str) or not _HEX.fullmatch(expected):
        raise ReviewInputError("artifact sha256 must be 64 lowercase hexadecimal characters")
    path = (base / ref["path"]).resolve()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReviewInputError(f"cannot read artifact: {path}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ReviewInputError(f"artifact sha256 mismatch: {path}")
    return data, {"path": str(path), "sha256": actual, "bytes": len(data)}


def _json(data: bytes, description: str):
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ReviewInputError(f"invalid JSON: {description}") from exc


def _text_source(source: dict, base: Path) -> dict:
    data, identity = _artifact(source.get("artifact"), base)
    if "text_pointer" in source:
        text = _pointer(_json(data, identity["path"]), source["text_pointer"])
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeError as exc:
            raise ReviewInputError("plain text sources must be UTF-8") from exc
    if not isinstance(text, str):
        raise ReviewInputError("text source must resolve to a string")
    return {"id": str(source.get("id", "")), "text": text, "words": _words(text),
            "artifact": identity, "text_pointer": source.get("text_pointer")}


def _contains(haystack: list[str], needle: list[str]) -> bool:
    return any(haystack[i:i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


def _longest_matches(label: list[str], text: list[str]) -> list[list[str]]:
    """Maximal contiguous token overlaps, excluding contained duplicates."""
    matches = set()
    for i, token in enumerate(label):
        for j, other in enumerate(text):
            if token != other or (i and j and label[i - 1] == text[j - 1]):
                continue
            n = 1
            while i + n < len(label) and j + n < len(text) and label[i + n] == text[j + n]:
                n += 1
            matches.add(tuple(label[i:i + n]))
    ordered = sorted(matches, key=lambda words: (-len(words), words))
    kept = []
    for words in ordered:
        if not any(_contains(list(larger), list(words)) for larger in kept):
            kept.append(words)
    return [list(words) for words in kept]


def review(manifest: dict, *, base_dir: Path | str = ".") -> dict:
    """Read referenced files and return review data without mutating inputs or importing simulation.

    Context completeness and authorship are caller attestations, displayed as such. Hashes establish
    byte identity only. Even complete context and delivery receipts cannot establish that text was read.
    """
    if not isinstance(manifest, dict):
        raise ReviewInputError("manifest must be a JSON object")
    base = Path(base_dir)
    rec_data, rec_id = _artifact(manifest.get("record"), base)
    ver_data, ver_id = _artifact(manifest.get("verdict"), base)
    record, verdict = _json(rec_data, "record"), _json(ver_data, "verdict")
    if not isinstance(record, dict) or not isinstance(verdict, dict) or not isinstance(record.get("calls"), list):
        raise ReviewInputError("record must have calls; verdict must be an object")
    calls = record["calls"]
    # A legacy verdict often has no raw-record byte hash. Its pairing remains an explicit limitation.
    declared_record = verdict.get("record_sha256")
    if declared_record is not None and declared_record != rec_id["sha256"]:
        raise ReviewInputError("verdict record_sha256 does not match record bytes")
    record_hash, verdict_hash = record.get("final_hash"), verdict.get("state_sha", verdict.get("final_hash"))
    if isinstance(record_hash, str) and isinstance(verdict_hash, str) and record_hash != verdict_hash:
        raise ReviewInputError("record/verdict final state hashes differ")

    context = manifest.get("public_texts") or {}
    context_note = context.get("completeness_note")
    public = []
    for source in context.get("sources") or []:
        if source.get("kind") not in _KINDS:
            raise ReviewInputError("public source kind must be task, brief, operator or other_public")
        parsed = _text_source(source, base)
        parsed["kind"] = source["kind"]
        available = source.get("available_before_call", -1 if source["kind"] in ("task", "brief") else None)
        if available is not None and (not isinstance(available, int) or isinstance(available, bool) or available < -1):
            raise ReviewInputError("available_before_call must be -1, a call index or null")
        parsed["available_before_call"] = available
        public.append(parsed)
    complete_context = (context.get("complete") is True and isinstance(context_note, str)
                        and bool(context_note.strip()) and bool(public))
    complete_context = complete_context and all(s["available_before_call"] is not None for s in public)

    authored = manifest.get("authored_labels") or {}
    labels, label_reason = [], None
    if authored.get("independent_of_model") is not True:
        label_reason = "independent_authored_labels_not_supplied"
    elif not isinstance(authored.get("provenance_note"), str) or not authored["provenance_note"].strip():
        label_reason = "authored_label_provenance_note_missing"
    else:
        for source in authored.get("sources") or []:
            parsed = _text_source(source, base)
            # Prevent the common circular source: copying this model's own public utterance.
            pointer = parsed.get("text_pointer") or ""
            if parsed["artifact"]["sha256"] in (rec_id["sha256"], ver_id["sha256"]) and not (
                parsed["artifact"]["sha256"] == rec_id["sha256"] and pointer.startswith("/scene/")):
                raise ReviewInputError("labels from record/verdict must be authored /scene/ fields, not model text")
            labels.append(parsed)
        if not labels:
            label_reason = "independent_authored_labels_not_supplied"

    delivery = manifest.get("image_delivery") or {}
    receipts = []
    for source in delivery.get("receipts") or []:
        data, identity = _artifact(source.get("artifact"), base)
        receipt = _pointer(_json(data, "image delivery receipt"), source.get("json_pointer", ""))
        if not isinstance(receipt, dict):
            raise ReviewInputError("image delivery receipt must resolve to an object")
        index = receipt.get("call_index")
        if (receipt.get("record_sha256") != rec_id["sha256"]
                or receipt.get("delivered_to_agent") is not True
                or not isinstance(index, int) or isinstance(index, bool) or not -1 <= index < len(calls)
                or not isinstance(receipt.get("image_sha256"), str)
                or not _HEX.fullmatch(receipt["image_sha256"])):
            raise ReviewInputError("receipt requires matching record sha256, call_index, image sha256 and delivered_to_agent=true")
        receipts.append({"artifact": identity, "json_pointer": source.get("json_pointer", ""),
                         "call_index": index, "image_sha256": receipt["image_sha256"]})
    complete_delivery = (delivery.get("complete") is True and bool(receipts)
                         and isinstance(delivery.get("completeness_note"), str)
                         and bool(delivery["completeness_note"].strip()))

    utterances, overlaps = [], []
    for i, call in enumerate(calls):
        if not isinstance(call, dict) or call.get("tool") not in _TOOLS:
            continue
        args = call.get("args") or {}
        text = args.get("text") if isinstance(args, dict) else None
        if not isinstance(text, str) or not text.strip():
            continue
        utterance = {"call_index": i, "tool": call["tool"], "field": f"/calls/{i}/args/text",
                     "text": text, "tick": call.get("tick0"), "ok": call.get("ok")}
        utterances.append(utterance)
        for label in labels:
            for words in _longest_matches(label["words"], _words(text)):
                # Short, generic hazards (e.g. METAL WASTE / TOXIC) are never a label-specific clue.
                qualifies = len(words) >= 4 and sum(map(len, words)) >= 16
                alternatives = [{"source_id": s["id"], "kind": s["kind"], "artifact": s["artifact"],
                                 "text_pointer": s["text_pointer"], "available_before_call": s["available_before_call"],
                                 "available_before_quote": (s["available_before_call"] < i
                                                            if s["available_before_call"] is not None else None)}
                                for s in public if _contains(s["words"], words)]
                shared = [{"source_id": s["id"], "kind": s["kind"],
                           "terms": sorted(set(words) & set(s["words"]))}
                          for s in public if set(words) & set(s["words"])]
                if not qualifies:
                    specificity = "short_or_generic_overlap"
                elif any(s["available_before_quote"] is True for s in alternatives):
                    specificity = "also_in_known_nonimage_public_text"
                elif not complete_context:
                    specificity = "unknown_incomplete_public_context"
                else:
                    specificity = "absent_from_declared_complete_nonimage_public_texts"
                overlaps.append({"call_index": i, "tool": call["tool"], "label_id": label["id"],
                                 "normalized_contiguous_phrase": " ".join(words), "token_count": len(words),
                                 "specificity": specificity, "qualifies_for_review": qualifies and not any(
                                     s["available_before_quote"] is True for s in alternatives),
                                 "alternative_full_phrase_sources": alternatives, "shared_term_sources": shared,
                                 "prior_delivery_receipts": [r for r in receipts if r["call_index"] < i]})

    marks = verdict.get("marks") if isinstance(verdict.get("marks"), dict) else {}
    evidence_missing = (verdict.get("outcome") == "blind_refusal" or marks.get("looked") is False
                        or marks.get("looked") == 0 or ("evidence_seen" in verdict and not verdict["evidence_seen"]))
    candidates = [o for o in overlaps if o["qualifies_for_review"]]
    reasons = []
    if label_reason:
        reasons.append(label_reason)
    if not complete_context:
        reasons.append("nonimage_public_context_not_attested_complete")
    if not complete_delivery:
        reasons.append("delivered_image_receipts_not_attested_complete")
    if candidates and any(not o["prior_delivery_receipts"] for o in candidates):
        reasons.append("no_bound_image_delivery_receipt_before_one_or_more_quotes")
    if declared_record is None:
        reasons.append("verdict_has_no_raw_record_byte_hash_pairing_is_caller_supplied")
    if candidates:
        reasons.append("contiguous_authored_label_phrase_requires_source_review")
    if evidence_missing:
        reasons.append("official_verdict_records_missing_visual_evidence")
    unknown = bool(label_reason or not complete_context or not complete_delivery
                   or any(not o["prior_delivery_receipts"] for o in candidates))
    # Missing provenance can itself merit review, but is explicitly not independent quotation evidence.
    return {"schema": SCHEMA, "review_status": "unknown" if unknown else (
                "needs_manual_review" if candidates else "no_specific_quotation_clue"),
            "needs_manual_review": bool(candidates or (evidence_missing and unknown)),
            "reasons": reasons, "visibility_conflict": "possible_not_established" if candidates and evidence_missing else "not_established",
            "seen_inferred": None, "visual_origin": "unknown", "score_change": False,
            "limitations": ["Quotation does not establish visual delivery, reading, understanding or unique origin.",
                            "Completeness, authorship and delivery assertions are caller attestations; hashes establish byte identity only.",
                            "Absence of a quotation is not evidence of absence of visual evidence.",
                            "Only literal contiguous normalized word overlap is searched; no OCR, paraphrase or symbol recognition."],
            "inputs": {"record": rec_id, "verdict": ver_id, "verdict_embeds_record_sha256": declared_record is not None,
                       "authored_labels": [{k: v for k, v in s.items() if k != "words"} for s in labels],
                       "authored_provenance_note": authored.get("provenance_note"),
                       "public_texts": [{k: v for k, v in s.items() if k != "words"} for s in public],
                       "public_context_complete_attestation": complete_context, "public_context_note": context_note,
                       "image_delivery_complete_attestation": complete_delivery,
                       "image_delivery_note": delivery.get("completeness_note"), "image_receipts": receipts},
            "official_verdict_unchanged": {k: verdict.get(k) for k in ("pass", "outcome", "judgment_class", "evidence_seen")},
            "utterances": utterances, "overlaps": overlaps}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        data = args.manifest.read_bytes()
        manifest = _json(data, str(args.manifest))
        result = review(manifest, base_dir=args.manifest.resolve().parent)
        result["manifest"] = {"path": str(args.manifest.resolve()), "sha256": hashlib.sha256(data).hexdigest()}
    except (OSError, ReviewInputError) as exc:
        print(f"label review input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
