"""Consistent presentation for task observations without changing mechanics."""

import xml.etree.ElementTree as ET


def child(parent, tag, **attributes):
    value = parent.find(tag)
    if value is None:
        value = ET.SubElement(parent, tag)
    value.attrib.update({key: str(item) for key, item in attributes.items()})
    return value


def configure(source):
    assets = source.find("asset")
    shell = assets.find("material[@name='silver']")
    if shell is not None:
        shell.attrib.update(rgba="0.90 0.92 0.92 1", specular="0.3", shininess="0.25",
                            metallic="0", roughness="0.28")
    pads = assets.find("material[@name='green']")
    if pads is not None:
        pads.attrib.update(rgba="0.16 0.24 0.20 1", specular="0.12", shininess="0.06",
                           metallic="0", roughness="0.7")
    visual = child(source, "visual")
    child(visual, "global", offwidth="1920", offheight="1080")
    child(visual, "quality", shadowsize="4096", offsamples="8", numslices="64", numstacks="32")
    child(visual, "headlight", ambient="0.16 0.16 0.16", diffuse="0.28 0.28 0.28", specular="0.1 0.1 0.1")
    child(visual, "rgba", haze="0.78 0.80 0.79 1")
    world = source.find("worldbody")
    table = world.find("geom[@name='table']")
    if table is not None:
        table.set("rgba", "0.72 0.74 0.72 1")
    for light in list(world.findall("light")):
        world.remove(light)
    for attributes in (
        dict(pos="0.3 -0.35 0.95", dir="-0.25 0.3 -0.8", diffuse="0.62 0.62 0.60", ambient="0.08 0.08 0.08", castshadow="true"),
        dict(pos="-0.35 0.25 0.70", dir="0.3 -0.2 -0.5", diffuse="0.32 0.34 0.36", castshadow="false"),
        dict(pos="0.1 0.4 0.9", dir="0 -0.3 -0.6", diffuse="0.25 0.27 0.25", castshadow="false"),
    ):
        ET.SubElement(world, "light", attributes)
