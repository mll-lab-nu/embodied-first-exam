"""Harbor oracle on any seat: the sport's reference player (builtin_players:Reference, camera images and /spec only) over
HTTP through the core's client loop (ro_client.py = core/client.py)."""
import ro_client

ro_client.main(["builtin_players:Reference"])
