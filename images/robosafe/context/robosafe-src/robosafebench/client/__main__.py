"""The `robot` command: one tool call per invocation.

    robot observe --save frames
    robot pick camera=front u=320 v=240 --save frames
    robot end reason=done text="The can is on the shelf."

Arguments are key=value; numbers are parsed as numbers. With --save DIR the images of the result are written there as
PNG files and their paths are printed in `image_files`. The JSON printed never contains image bytes.
"""
from __future__ import annotations

import json
import sys
import time

from . import connect


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    save = None
    if "--save" in argv:
        i = argv.index("--save")
        save = argv[i + 1]
        del argv[i:i + 2]
    tool, args = argv[0], {}
    for item in argv[1:]:
        if "=" not in item:
            print(json.dumps({"ok": False, "error": f"arguments are key=value, got {item!r}"}))
            return 2
        k, v = item.split("=", 1)
        try:
            args[k] = json.loads(v)
        except ValueError:
            args[k] = v
    robot = connect()
    if save is None:
        args.setdefault("images", False)
    out = robot.call(tool, **args)
    if save is not None and out.get("images"):
        out["image_files"] = robot.save_images(out, save, prefix=f"{int(time.time() * 1000) % 100000000:08d}")
    out.pop("images", None)
    out.pop("depth", None)
    print(json.dumps(out, indent=1))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
