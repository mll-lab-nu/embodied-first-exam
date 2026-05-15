from __future__ import annotations

from topogym.world import build_common_room, default_common_room_spec


def main() -> None:
    room = build_common_room(default_common_room_spec(show_viewer=False))
    room.scene.step()

    oblique_rgb = room.read_rgb("oblique")
    topdown_rgb = room.read_rgb("topdown")

    print("Built common room with entities:", sorted(room.entities))
    print("Oblique RGB shape:", tuple(oblique_rgb.shape))
    print("Top-down RGB shape:", tuple(topdown_rgb.shape))


if __name__ == "__main__":
    main()

