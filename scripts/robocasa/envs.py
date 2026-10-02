"""RoboCasa (v0.2) tasks of this benchmark: native environment -> PR #4 source task (frozen instance + reference).

The 29 environments whose official demonstration (robocasa/utils/dataset_registry.py at the pinned commit) gave a
reference that PR #4 validated; import_references.py re-verifies each one with this benchmark's tooling and grading.
"""

# environment name -> PR #4 task directory (under unlimited_tasks/robocasa/ of the PR #4 tree)
SOURCES = {
    "ArrangeVegetables": "robocasa-arrange-vegetables-unlimited60min-v3-i00",
    "CloseDoubleDoor": "robocasa-close-double-door-unlimited60min-v3-i00",
    "CloseDrawer": "robocasa-close-drawer-unlimited60min-v3-i00",
    "CloseSingleDoor": "robocasa-close-single-door-unlimited60min-v3-i00",
    "CoffeePressButton": "robocasa-coffee-press-button-unlimited60min-v3-i00",
    "CoffeeServeMug": "robocasa-coffee-serve-mug-unlimited60min-v3-i00",
    "CoffeeSetupMug": "robocasa-coffee-setup-mug-unlimited60min-v3-i00",
    "MicrowaveThawing": "robocasa-microwave-thawing-unlimited60min-v3-i00",
    "OpenDoubleDoor": "robocasa-open-double-door-unlimited60min-v3-i00",
    "OpenDrawer": "robocasa-open-drawer-unlimited60min-v3-i00",
    "OpenSingleDoor": "robocasa-open-single-door-unlimited60min-v3-i00",
    "PnPCabToCounter": "robocasa-pn-p-cab-to-counter-unlimited60min-v3-i00",
    "PnPCounterToCab": "robocasa-pn-p-counter-to-cab-unlimited60min-v3-i00",
    "PnPCounterToMicrowave": "robocasa-pn-p-counter-to-microwave-unlimited60min-v3-i00",
    "PnPCounterToSink": "robocasa-pn-p-counter-to-sink-unlimited60min-v3-i00",
    "PnPCounterToStove": "robocasa-pn-p-counter-to-stove-unlimited60min-v3-i00",
    "PnPMicrowaveToCounter": "robocasa-pn-p-microwave-to-counter-unlimited60min-v3-i00",
    "PnPSinkToCounter": "robocasa-pn-p-sink-to-counter-unlimited60min-v3-i00",
    "PnPStoveToCounter": "robocasa-pn-p-stove-to-counter-unlimited60min-v3-i00",
    "PreSoakPan": "robocasa-pre-soak-pan-unlimited60min-v3-i00",
    "PrepareCoffee": "robocasa-prepare-coffee-unlimited60min-v3-i00",
    "RestockPantry": "robocasa-restock-pantry-unlimited60min-v3-i00",
    "TurnOffMicrowave": "robocasa-turn-off-microwave-unlimited60min-v3-i00",
    "TurnOffSinkFaucet": "robocasa-turn-off-sink-faucet-unlimited60min-v3-i00",
    "TurnOffStove": "robocasa-turn-off-stove-unlimited60min-v3-i00",
    "TurnOnMicrowave": "robocasa-turn-on-microwave-unlimited60min-v3-i00",
    "TurnOnSinkFaucet": "robocasa-turn-on-sink-faucet-unlimited60min-v3-i00",
    "TurnOnStove": "robocasa-turn-on-stove-unlimited60min-v3-i00",
    "TurnSinkSpout": "robocasa-turn-sink-spout-unlimited60min-v3-i00",
}


def slug(env_name: str) -> str:
    """ArrangeVegetables -> arrange-vegetables, PnPCounterToCab -> pnp-counter-to-cab."""
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "-", env_name.replace("PnP", "Pnp")).lower()


# Native RoboCasa environments not in this benchmark, and why (docs/benchmarks/robocasa.md has the full list).
EXCLUDED = {
    "NavigateKitchen": "a navigation-only task with a different (3-D base) action interface; PR #4 has no reference trajectory for it",
    "AfterwashSorting": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ArrangeBreadBasket": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ArrangeTea": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "AssembleCookingArray": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "BeverageOrganization": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "BeverageSorting": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "BowlAndCup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "BreadAndCheese": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "BreadSelection": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "BreadSetupSlicing": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CandleCleanup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CerealAndBowl": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CheesyBread": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CleanMicrowave": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ClearClutter": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ClearingCleaningReceptacles": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ClearingTheCuttingBoard": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ColorfulSalsa": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CondimentCollection": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CountertopCleanup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "CupcakeCleanup": "the scene could not be frozen bit-exactly (reset not reproducible)",
    "DateNight": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DefrostByCategory": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DessertAssembly": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DessertUpgrade": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DrainVeggies": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DrawerUtensilSort": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DrinkwareConsolidation": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DryDishes": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "DryDrinkware": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "FillKettle": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "FoodCleanup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "FryingPanAdjustment": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "HeatMug": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "HeatMultipleWater": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "KettleBoiling": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "MakeFruitBowl": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "MakeLoadedPotato": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "MealPrepStaging": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "MeatTransfer": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "MultistepSteaming": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "OrganizeBakingIngredients": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "OrganizeCleaningSupplies": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "OrganizeVegetables": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PanTransfer": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PantryMishap": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PastryDisplay": "the scene could not be frozen bit-exactly (reset not reproducible)",
    "PlaceFoodInBowls": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PrepForSanitizing": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PrepForTenderizing": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PrepMarinatingMeat": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PrepareSoupServing": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PrepareToast": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PrewashFoodAssembly": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "PushUtensilsToSink": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "QuickThaw": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "RestockBowls": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SearingMeat": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SeasoningSpiceSetup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ServeSteak": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SetBowlsForSoup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SetupFrying": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SetupJuicing": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ShakerShuffle": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SimmeringSauce": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SizeSorting": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SnackSorting": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SortingCleanup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SpicyMarinade": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "StackBowlsInSink": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SteamInMicrowave": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SteamVegetables": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "StockingBreakfastFoods": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "SweetSavoryToastSetup": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "ThawInSink": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "VeggieBoil": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "VeggieDipPrep": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "WaffleReheat": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "WarmCroissant": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "WineServingPrep": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
    "YogurtDelightPrep": "no official demonstration in the pinned dataset registry, so no reference (oracle)",
}


# What each environment's `_check_success` requires (robocasa @ 756598a; robocasa/environments/kitchen/ and the fixture
# helpers it calls), in words: both instructions list these, so the agent need not guess a threshold or an implicit
# condition (letting go and moving away, a closed microwave door). Text only: the grader is the upstream check.
_FAR = "the gripper's grip site (between the fingertips) is more than 25 cm from {}: let go and move the hand away"
_INSIDE = (
    "entirely inside {} (all eight corners of its bounding box within the interior, with a 5 cm tolerance)"
)
_DOOR_SHUT = "at most 5% open (each hinge within 4.5° of closed; the check scales 0–90° to 0–100%)"
_DOOR_OPEN = "at least 90% open (each hinge at least 81° open; the check scales 0–90° to 0–100%)"
_DRAWER = "the drawer's travel is scaled to 0–100% over 0.55 × the drawer's depth"
_ON_PLATE = (
    "the object touches the {r} and its centre is within {d} of the {r}'s centre (horizontal distance)"
)
_RADIUS = "0.7 × the {}'s horizontal radius"
_COFFEE_SPOT = (
    "the mug's centre is within 4 cm (horizontally) and 10 cm (vertically) of the coffee machine's mug spot under "
    "the dispenser"
)
_COFFEE_ON = (
    "the coffee machine is on: it switches on the first time the gripper touches its start button and then stays on"
)
_MICRO_DOOR = (
    "the microwave only registers a button while its door is closed (at most 0.5% open), and opening the door "
    "switches it off"
)
_WATER_ON = (
    "the water is on: the faucet handle's angle (mod 360°) is between 0.40 rad (about 23°) and π from its off position"
)
_KNOB = "0.35 rad (about 20°)"

SUCCESS = {
    "ArrangeVegetables": [
        "each of the two vegetables touches the cutting board and its centre is within "
        + _RADIUS.format("board")
        + " of the board's centre (horizontal distance)",
        _FAR.format("the cutting board's centre"),
    ],
    "CloseDoubleDoor": ["both cabinet doors are " + _DOOR_SHUT],
    "CloseDrawer": ["the left drawer is at most 5% open (" + _DRAWER + ")"],
    "CloseSingleDoor": ["the microwave door is " + _DOOR_SHUT],
    "CoffeePressButton": [
        _COFFEE_ON,
        "the gripper's grip site is more than 15 cm from the start button: move the hand away after pressing",
    ],
    "CoffeeServeMug": [
        "the mug touches the counter by the coffee machine (standing on it)",
        _FAR.format("the mug's centre"),
    ],
    "CoffeeSetupMug": [_COFFEE_SPOT, _FAR.format("the mug's centre")],
    "MicrowaveThawing": [
        "the object is " + _INSIDE.format("the microwave"),
        "the microwave is on; " + _MICRO_DOOR + ": close the door fully, then press the start button",
        _FAR.format("the object's centre"),
    ],
    "OpenDoubleDoor": ["both cabinet doors are " + _DOOR_OPEN],
    "OpenDrawer": ["the right drawer is at least 95% open (" + _DRAWER + ")"],
    "OpenSingleDoor": ["the cabinet door is " + _DOOR_OPEN],
    "PnPCabToCounter": [
        "the object touches the counter below the cabinet",
        _FAR.format("the object's centre"),
    ],
    "PnPCounterToCab": ["the object is " + _INSIDE.format("the cabinet"), _FAR.format("the object's centre")],
    "PnPCounterToMicrowave": [
        "the object touches the plate inside the microwave, and that plate touches the microwave",
        _FAR.format("the object's centre"),
    ],
    "PnPCounterToSink": [
        "the object's centre is inside the sink basin",
        _FAR.format("the object's centre"),
    ],
    "PnPCounterToStove": [_ON_PLATE.format(r="pan", d="7 cm"), _FAR.format("the object's centre")],
    "PnPMicrowaveToCounter": [
        _ON_PLATE.format(r="plate", d=_RADIUS.format("plate")),
        _FAR.format("the object's centre"),
    ],
    "PnPSinkToCounter": [
        _ON_PLATE.format(r="plate", d=_RADIUS.format("plate")),
        "the plate touches the counter",
        _FAR.format("the object's centre"),
    ],
    "PnPStoveToCounter": [_ON_PLATE.format(r="plate", d="7 cm"), _FAR.format("the object's centre")],
    "PreSoakPan": [
        "the pan and the sponge are each " + _INSIDE.format("the sink basin"),
        _WATER_ON,
        _FAR.format("the pan's centre"),
    ],
    "PrepareCoffee": [
        _COFFEE_SPOT,
        _COFFEE_ON,
        _FAR.format("the mug's centre"),
        "the gripper's grip site is also more than 15 cm from the start button",
    ],
    "RestockPantry": [
        "both cans are " + _INSIDE.format("the cabinet"),
        "each of them is on the side of the can already in the cabinet: its distance to that can, times 2, is less "
        "than its distance to the other (non-can) item in the cabinet (centre to centre)",
        _FAR.format("each can's centre"),
    ],
    "TurnOffMicrowave": [
        "the microwave is off: touching its stop button with the gripper switches it off",
        "the gripper's grip site is more than 15 cm from the stop button: move the hand away after pressing",
    ],
    "TurnOffSinkFaucet": [
        "the water is off: the faucet handle's angle (mod 360°) is outside 0.40 rad (about 23°) to π from its off "
        "position, i.e. lowered back to below 0.40 rad"
    ],
    "TurnOffStove": ["the front right burner's knob is within " + _KNOB + " of its off position"],
    "TurnOnMicrowave": [
        "the microwave is on: touching its start button with the gripper switches it on; " + _MICRO_DOOR,
        "the gripper's grip site is more than 15 cm from the start button: move the hand away after pressing",
    ],
    "TurnOnSinkFaucet": [_WATER_ON],
    "TurnOnStove": [
        "the front left burner's knob is turned at least " + _KNOB + " away from its off position, either way "
        "(|angle| between 0.35 rad and 2π − 0.35 rad)"
    ],
    "TurnSinkSpout": [
        "the spout's joint angle (mod 360°) is between 30° and 180°, the range the check calls right: swing it at "
        "least 30° to the right of its middle position"
    ],
}
