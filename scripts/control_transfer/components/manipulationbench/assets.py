from control_assets import ROOT, check

COMMIT = "0059d4335f8156206f63a35662313385f7ad6d74"
MODEL = ROOT / "yam/yam.xml"


def verify():
    return check("yam")
