# -*- coding: utf-8 -*-
# Input: gloss list (JSON array). Output: timeline JSON (ordered clips with start_time, duration, bvh path).
# Usage: python gloss_to_timeline.py [path_to_gloss.json] [--output timeline.json]
from __future__ import annotations

import argparse
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))


def _bvh_duration(bvh_path: str) -> float:
    if not os.path.isfile(bvh_path):
        return 0.0
    with open(bvh_path, "r", encoding="utf-8", errors="ignore") as f:
        head = f.read()
    frames_match = re.search(r"Frames:\s*(\d+)", head, re.I)
    frame_time_match = re.search(r"Frame\s+Time:\s*([\d.]+)", head, re.I)
    if not frames_match or not frame_time_match:
        return 0.0
    n = int(frames_match.group(1))
    t = float(frame_time_match.group(1))
    return n * t


def _gloss_to_bvh_path(gloss: str, mapping: dict) -> str | None:
    fbx_name = mapping.get(gloss)
    if not fbx_name:
        return None
    base = os.path.splitext(fbx_name)[0]
    return os.path.join(SCRIPT_DIR, base + ".bvh")


def build_timeline(gloss_list: list[str], mapping_path: str | None = None) -> list[dict]:
    mapping_path = mapping_path or os.path.join(SCRIPT_DIR, "mapping.json")
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    timeline = []
    t_start = 0.0
    for i, gloss in enumerate(gloss_list):
        bvh_path = _gloss_to_bvh_path(gloss, mapping)
        if bvh_path is None:
            duration = 0.0
            bvh_rel = None
        else:
            duration = _bvh_duration(bvh_path)
            bvh_rel = os.path.relpath(bvh_path, SCRIPT_DIR) if os.path.isfile(bvh_path) else bvh_path

        timeline.append({
            "index": i,
            "gloss": gloss,
            "bvh": bvh_rel,
            "path_abs": bvh_path if bvh_path and os.path.isfile(bvh_path) else None,
            "start_time": round(t_start, 4),
            "duration": round(duration, 4),
        })
        t_start += duration
    return timeline


def main():
    parser = argparse.ArgumentParser(description="Gloss list -> timeline JSON")
    parser.add_argument("gloss_json", nargs="?", default=os.path.join(SCRIPT_DIR, "..", "..", "mock.json"),
                        help="Path to JSON array of glosses (default: ../../mock.json)")
    parser.add_argument("-o", "--output", default=None, help="Write timeline to file; default stdout")
    args = parser.parse_args()

    gloss_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.gloss_json)) if not os.path.isabs(args.gloss_json) else args.gloss_json
    with open(gloss_path, "r", encoding="utf-8") as f:
        gloss_list = json.load(f)

    timeline = build_timeline(gloss_list)
    out = {"gloss_list": gloss_list, "timeline": timeline, "total_duration": round(sum(c["duration"] for c in timeline), 4)}
    s = json.dumps(out, ensure_ascii=False, indent=2)

    if args.output:
        out_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.output)) if not os.path.isabs(args.output) else args.output
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(s)
        print("Wrote", out_path)
    else:
        print(s)


if __name__ == "__main__":
    main()
