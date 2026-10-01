"""RoboCasa GR1 tabletop tasks of this benchmark: native environment -> PR #4 source task (frozen instance + reference).

All 24 environments PR #4 validated (one instance each, i00): the GR1 tabletop pick-and-place tasks with an
official demonstration (robocasa-gr1-tabletop-tasks' dataset). import_references.py re-verifies each one with this
benchmark's tooling and grading.
"""

# environment name -> PR #4 task directory (under unlimited_tasks/robocasa-gr1/ of the PR #4 tree)
SOURCES = {
    "PnPBottleToCabinetClose": "robocasa-gr1-bottle-to-cabinet-close-unlimited60min-v3-i00",
    "PnPCupToDrawerClose": "robocasa-gr1-cup-to-drawer-close-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlateToPlateSplitA": "robocasa-gr1-plate-to-plate-unlimited60min-v3-i00",
    "PnPCanToDrawerClose": "robocasa-gr1-pn-p-can-to-drawer-close-unlimited60min-v3-i00",
    "PnPMilkToMicrowaveClose": "robocasa-gr1-pn-p-milk-to-microwave-close-unlimited60min-v3-i00",
    "PnPPotatoToMicrowaveClose": "robocasa-gr1-pn-p-potato-to-microwave-close-unlimited60min-v3-i00",
    "PnPWineToCabinetClose": "robocasa-gr1-pn-p-wine-to-cabinet-close-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromCuttingboardToBasketSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-cuttingboard-to-basket-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromCuttingboardToCardboardboxSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-cuttingboard-to-cardboardbox-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromCuttingboardToPanSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-cuttingboard-to-pan-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromCuttingboardToPotSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-cuttingboard-to-pot-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromCuttingboardToTieredbasketSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-cuttingboard-to-tieredbasket-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlacematToBasketSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-placemat-to-basket-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlacematToBowlSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-placemat-to-bowl-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlacematToPlateSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-placemat-to-plate-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlacematToTieredshelfSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-placemat-to-tieredshelf-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlateToBowlSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-plate-to-bowl-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlateToCardboardboxSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-plate-to-cardboardbox-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromPlateToPanSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-plate-to-pan-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromTrayToCardboardboxSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-tray-to-cardboardbox-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromTrayToPlateSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-tray-to-plate-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromTrayToPotSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-tray-to-pot-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromTrayToTieredbasketSplitA": "robocasa-gr1-posttrain-pn-p-novel-from-tray-to-tieredbasket-split-a-unlimited60min-v3-i00",
    "PosttrainPnPNovelFromTrayToTieredshelfSplitA": "robocasa-gr1-tray-to-tiered-shelf-unlimited60min-v3-i00",
}


def slug(env_name: str) -> str:
    """PnPBottleToCabinetClose -> bottle-to-cabinet-close, PosttrainPnPNovelFromPlateToBowlSplitA -> plate-to-bowl."""
    import re

    name = env_name.replace("PosttrainPnPNovelFrom", "").replace("PnP", "").replace("SplitA", "")
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


# Native environments not in this benchmark, and why.
EXCLUDED: dict[str, str] = {}
