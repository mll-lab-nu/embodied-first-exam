"""RoboCasa365 tasks of this benchmark: native environment -> PR #4 source task (frozen instance + reference).

Selected by select_instances.py's rule from the 256 families PR #4 accepted: 12 atomic + 38 composite slots
(shared in proportion to the 63 atomic and 193 composite families), families in SHA-256-of-name order within
each group, skipping any whose reference does not verify (import_references.py). See docs/benchmarks/robocasa365.md.
"""

# environment name -> PR #4 task directory (under unlimited_tasks/robocasa365/ of the PR #4 tree)
SOURCES = {
    "PickPlaceSinkToCounter": "robocasa365-pick-place-sink-to-counter-unlimited60min-v3-i00",
    "PickPlaceCabinetToCounter": "robocasa365-pick-place-cabinet-to-counter-unlimited60min-v3-i00",
    "CloseDrawer": "robocasa365-close-drawer-unlimited60min-v3-i00",
    "TurnOnMicrowave": "robocasa365-turn-on-microwave-unlimited60min-v3-i00",
    "CloseOven": "robocasa365-close-oven-unlimited60min-v3-i00",
    "TurnOnStove": "robocasa365-turn-on-stove-unlimited60min-v3-i00",
    "TurnOnToasterOven": "robocasa365-turn-on-toaster-oven-unlimited60min-v3-i00",
    "OpenDishwasher": "robocasa365-open-dishwasher-unlimited60min-v3-i00",
    "TurnOffMicrowave": "robocasa365-turn-off-microwave-unlimited60min-v3-i00",
    "PackDessert": "robocasa365-pack-dessert-unlimited60min-v3-i00",
    "TurnOnSinkFaucet": "robocasa365-turn-on-sink-faucet-unlimited60min-v3-i00",
    "CloseStandMixerHead": "robocasa365-close-stand-mixer-head-unlimited60min-v3-i00",
    "RetrieveMeat": "robocasa365-retrieve-meat-unlimited60min-v3-i00",
    "DrainVeggies": "robocasa365-drain-veggies-unlimited60min-v3-i00",
    "SanitizePrepCuttingBoard": "robocasa365-sanitize-prep-cutting-board-unlimited60min-v3-i00",
    "AssembleCookingArray": "robocasa365-assemble-cooking-array-unlimited60min-v3-i00",
    "ClearSink": "robocasa365-clear-sink-unlimited60min-v3-i00",
    "CookieDoughPrep": "robocasa365-cookie-dough-prep-unlimited60min-v3-i00",
    "DisplayMeatVariety": "robocasa365-display-meat-variety-unlimited60min-v3-i00",
    "CandleCleanup": "robocasa365-candle-cleanup-unlimited60min-v3-i00",
    "DivideBasins": "robocasa365-divide-basins-unlimited60min-v3-i00",
    "BeverageSorting": "robocasa365-beverage-sorting-unlimited60min-v3-i00",
    "StockingBreakfastFoods": "robocasa365-stocking-breakfast-foods-unlimited60min-v3-i00",
    "BreadAndCheese": "robocasa365-bread-and-cheese-unlimited60min-v3-i00",
    "DeliverBrewedCoffee": "robocasa365-deliver-brewed-coffee-unlimited60min-v3-i00",
    "PortionInTupperware": "robocasa365-portion-in-tupperware-unlimited60min-v3-i00",
    "OvenBroilFish": "robocasa365-oven-broil-fish-unlimited60min-v3-i00",
    "MakeIceLemonade": "robocasa365-make-ice-lemonade-unlimited60min-v3-i00",
    "TongBuffetSetup": "robocasa365-tong-buffet-setup-unlimited60min-v3-i00",
    "AddLemonToFish": "robocasa365-add-lemon-to-fish-unlimited60min-v3-i00",
    "MicrowaveDefrostMeat": "robocasa365-microwave-defrost-meat-unlimited60min-v3-i00",
    "MealPrepStaging": "robocasa365-meal-prep-staging-unlimited60min-v3-i00",
    "MakeLoadedPotato": "robocasa365-make-loaded-potato-unlimited60min-v3-i00",
    "PrepForSanitizing": "robocasa365-prep-for-sanitizing-unlimited60min-v3-i00",
    "SeasoningSpiceSetup": "robocasa365-seasoning-spice-setup-unlimited60min-v3-i00",
    "PrepMarinatingMeat": "robocasa365-prep-marinating-meat-unlimited60min-v3-i00",
    "PreRinseStation": "robocasa365-pre-rinse-station-unlimited60min-v3-i00",
    "SetUpCuttingStation": "robocasa365-set-up-cutting-station-unlimited60min-v3-i00",
    "DessertUpgrade": "robocasa365-dessert-upgrade-unlimited60min-v3-i00",
    "SweetenCoffee": "robocasa365-sweeten-coffee-unlimited60min-v3-i00",
    "CerealAndBowl": "robocasa365-cereal-and-bowl-unlimited60min-v3-i00",
    "SearingMeat": "robocasa365-searing-meat-unlimited60min-v3-i00",
    "ThawInSink": "robocasa365-thaw-in-sink-unlimited60min-v3-i00",
    "ScrubBowl": "robocasa365-scrub-bowl-unlimited60min-v3-i00",
    "PlateSteakMeal": "robocasa365-plate-steak-meal-unlimited60min-v3-i00",
    "DrinkwareConsolidation": "robocasa365-drinkware-consolidation-unlimited60min-v3-i00",
    "ReheatMeal": "robocasa365-reheat-meal-unlimited60min-v3-i00",
    "ClearFoodWaste": "robocasa365-clear-food-waste-unlimited60min-v3-i00",
    "ChooseMeasuringCup": "robocasa365-choose-measuring-cup-unlimited60min-v3-i00",
    "OrganizeCoffeeCondiments": "robocasa365-organize-coffee-condiments-unlimited60min-v3-i00",
}

# atomic | composite (the module the environment class is defined in)
GROUP = {
    "PickPlaceSinkToCounter": "atomic",
    "PickPlaceCabinetToCounter": "atomic",
    "CloseDrawer": "atomic",
    "TurnOnMicrowave": "atomic",
    "CloseOven": "atomic",
    "TurnOnStove": "atomic",
    "TurnOnToasterOven": "atomic",
    "OpenDishwasher": "atomic",
    "TurnOffMicrowave": "atomic",
    "PackDessert": "atomic",
    "TurnOnSinkFaucet": "atomic",
    "CloseStandMixerHead": "atomic",
    "RetrieveMeat": "composite",
    "DrainVeggies": "composite",
    "SanitizePrepCuttingBoard": "composite",
    "AssembleCookingArray": "composite",
    "ClearSink": "composite",
    "CookieDoughPrep": "composite",
    "DisplayMeatVariety": "composite",
    "CandleCleanup": "composite",
    "DivideBasins": "composite",
    "BeverageSorting": "composite",
    "StockingBreakfastFoods": "composite",
    "BreadAndCheese": "composite",
    "DeliverBrewedCoffee": "composite",
    "PortionInTupperware": "composite",
    "OvenBroilFish": "composite",
    "MakeIceLemonade": "composite",
    "TongBuffetSetup": "composite",
    "AddLemonToFish": "composite",
    "MicrowaveDefrostMeat": "composite",
    "MealPrepStaging": "composite",
    "MakeLoadedPotato": "composite",
    "PrepForSanitizing": "composite",
    "SeasoningSpiceSetup": "composite",
    "PrepMarinatingMeat": "composite",
    "PreRinseStation": "composite",
    "SetUpCuttingStation": "composite",
    "DessertUpgrade": "composite",
    "SweetenCoffee": "composite",
    "CerealAndBowl": "composite",
    "SearingMeat": "composite",
    "ThawInSink": "composite",
    "ScrubBowl": "composite",
    "PlateSteakMeal": "composite",
    "DrinkwareConsolidation": "composite",
    "ReheatMeal": "composite",
    "ClearFoodWaste": "composite",
    "ChooseMeasuringCup": "composite",
    "OrganizeCoffeeCondiments": "composite",
}


def slug(env_name: str) -> str:
    """CloseDrawer -> close-drawer, PnPCounterToCab -> pnp-counter-to-cab."""
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "-", env_name.replace("PnP", "Pnp")).lower()


# Candidates in rule order that are not in this benchmark, and why.
EXCLUDED = {
    "OrganizeMugsByHandle": "its reference does not reach success when replayed with MuJoCo's mesh cache off (every build cold); PR #4 had accepted it with the cache on",
}

# What each environment's `_check_success` (robocasa @ 4f8a298) requires, in words, for the instructions: conditions
# the task's sentence leaves out (letting go and moving the gripper away, thresholds, timers). The terms "on / in",
# "touches", "inside" and "the gripper ends more than d m from" are defined once in generate.py (SUCCESS_TERMS).
# The sink's faucet handle has two hinges at one pivot (RoboCasa's sink model, read from the frozen scenes of
# turn-on-sink-faucet, thaw-in-sink and drain-veggies): `<sink>_handle_joint`, the water on / off, range 0-0.5 rad about
# the sink's front-to-back axis, and `<sink>_handle_temp_joint`, the temperature, +-0.785 rad about its left-right axis
# (board 0086: every standard run moved the temperature hinge and never got water).
_HANDLE = ("The handle turns on two hinges at one pivot: the on / off hinge, whose range is 0 to 0.5 rad (so the water "
           "is on only over the last fifth of its travel), turns about the sink's front-to-back axis, so the handle "
           "swings sideways; the temperature hinge (about ±0.79 rad) tilts the handle toward or away from you and never "
           "turns the water on or off.")
SUCCESS = {
    "PickPlaceSinkToCounter": "the egg is on the plate, the plate touches the counter next to the sink, and the "
    "gripper ends more than 0.25 m from the egg.",
    "PickPlaceCabinetToCounter": "the ice cube touches the counter nearest the cabinet, and the gripper ends more than "
    "0.25 m from it.",
    "CloseDrawer": "every joint of the drawer is at most 5% open (normalised: 0 closed, 1 fully open).",
    "TurnOnMicrowave": "the microwave is on (it turns on when the gripper touches the start button while the door is "
    "not open), and the gripper ends more than 0.15 m from the start button.",
    "CloseOven": "the oven door is fully closed: at most 0.5% open (normalised: 0 closed, 1 fully open).",
    "TurnOnStove": "the rear left burner's knob is on: its angle from off, in absolute value, is between 0.35 rad and "
    "2π − 0.35 rad.",
    "TurnOnToasterOven": "the timer knob is at 0.1 or more of its range (normalised) at the end; a set timer slowly "
    "runs down.",
    "OpenDishwasher": "the dishwasher door is at least 90% open (normalised: 0 closed, 1 fully open).",
    "TurnOffMicrowave": "the microwave is off (it turns off when the gripper touches the stop button), and the gripper "
    "ends more than 0.15 m from the stop button.",
    "PackDessert": "the hot dog and the marshmallow are both in the tupperware, and the gripper ends more than 0.25 m "
    "from the marshmallow.",
    "TurnOnSinkFaucet": "the faucet handle is in its water-on range (its on / off hinge between 0.40 rad and π rad). "
    + _HANDLE,
    "CloseStandMixerHead": "the mixer head is closed: less than 1% open (normalised: 0 closed, 1 fully open).",
    "RetrieveMeat": "the fish is on the cutting board, and the gripper ends more than 0.25 m from the fish.",
    "DrainVeggies": "the lettuce has been washed: inside the sink with the water on for more than 10 consecutive "
    "checks (the check runs twice per control step: at least 6 control steps; once washed it stays washed); at the "
    "end the lettuce is in the pot and the water is off (the water is on while the faucet handle's on / off hinge is "
    "between 0.40 rad and π rad). " + _HANDLE,
    "SanitizePrepCuttingBoard": "the spray bottle and the dish brush each touch a counter with their centres at most "
    "0.35 m (horizontally) from the cutting board's, the board touches a counter, and the gripper ends more than "
    "0.25 m from the spray bottle and from the brush.",
    "AssembleCookingArray": "the shrimp is in the pan (touching it, centres within 0.07 m horizontally); the syrup "
    "bottle and the broccoli touch the counter next to the stove (where the plate is); the gripper ends more than "
    "0.25 m from all three.",
    "ClearSink": "the corn and the carrot are not inside the sink, the bowl and the cup are inside it, and the gripper "
    "ends more than 0.25 m from all four.",
    "CookieDoughPrep": "the egg and the butter each touch a counter with their centres within the bowl's horizontal "
    "radius + 0.25 m (horizontally) of the bowl's, and the gripper ends more than 0.15 m from both.",
    "DisplayMeatVariety": "the drumstick, the shrimp and the steak are all on the serving tray, the tray touches the "
    "dining counter, and the gripper ends more than 0.25 m from all three.",
    "CandleCleanup": "the candle and the jar are both inside the cabinet, and the cabinet is closed (every door at "
    "most 0.5% open, normalised).",
    "DivideBasins": "the item that was in the left basin is in the right basin, the cup is in the left basin, and the "
    "gripper ends more than 0.25 m from both.",
    "BeverageSorting": "both alcoholic drinks are inside one of the two cabinets and both non-alcoholic drinks inside "
    "the other, and the gripper ends more than 0.25 m from all four.",
    "StockingBreakfastFoods": "each item is inside the cabinet the task assigns to it (the one closest to it), and the "
    "gripper ends more than 0.25 m from both.",
    "BreadAndCheese": "the bread and the cheese are both on the cutting board, and the gripper ends more than 0.25 m "
    "from the bread.",
    "DeliverBrewedCoffee": "the coffee and the breakfast plate both touch the dining counter with their centres at "
    "most 0.3 m apart (horizontally), and the gripper ends more than 0.25 m from the coffee.",
    "PortionInTupperware": "each tupperware holds exactly one of the two cooked foods and exactly one of the two "
    "vegetables, and the gripper ends more than 0.25 m from all four.",
    "OvenBroilFish": "the fish touches the rack the task names and the oven door is fully closed (at most 0.5% open, "
    "normalised) for 10 consecutive checks (5 control steps); from then on the check stays true.",
    "MakeIceLemonade": "the lemon wedge and at least one ice cube are in the glass (touching it, centres within 0.5 m "
    "horizontally), and the gripper ends more than 0.15 m from the lemon wedge and from both ice cubes.",
    "TongBuffetSetup": "the tongs and the tray both touch the dining counter with their centres at most 0.5 m apart "
    "(horizontally), and the gripper ends more than 0.15 m from both.",
    "AddLemonToFish": "the lemon wedge and the fish are both on the plate, the plate touches the dining counter, and "
    "the gripper ends more than 0.25 m from the lemon wedge.",
    "MicrowaveDefrostMeat": "the tupperware is inside the microwave with the drumstick in it, the door is fully closed "
    "(at most 0.5% open, normalised), the microwave is on (the start button pressed with the door not open; opening "
    "the door turns it off), and the gripper ends more than 0.25 m from the tupperware.",
    "MealPrepStaging": "each pan touches the stove with its centre within 0.08 m (horizontally) of a burner, the two "
    "pans on different burners, and the corn and the steak are in different pans.",
    "MakeLoadedPotato": "the potato, the cheese and the condiment are all on the cutting board, and the gripper ends "
    "more than 0.25 m from all three.",
    "PrepForSanitizing": "the bar soap and the dish brush both touch the counter nearest the cabinet, and the gripper "
    "ends more than 0.25 m from both.",
    "SeasoningSpiceSetup": "both bottles touch the dining counter, and the gripper ends more than 0.25 m from both.",
    "PrepMarinatingMeat": "the shrimp is on the cutting board, the board and the condiment bottle touch the counter "
    "nearest the cabinet, and the gripper ends more than 0.25 m from the shrimp and from the bottle.",
    "PreRinseStation": "the glass cup is in the sink's left basin and the kettle in its right basin, and the gripper "
    "ends more than 0.25 m from both.",
    "SetUpCuttingStation": "the knife and the meat are both on the cutting board, and the gripper ends more than "
    "0.25 m from the knife and from the cutting board.",
    "DessertUpgrade": "both desserts are on the tray, and the gripper ends more than 0.25 m from the tray.",
    "SweetenCoffee": "the sugar cube is in the coffee; the milk and the coffee both touch a counter with their centres "
    "at most 0.25 m apart (horizontally); the gripper ends more than 0.25 m from the milk and from the sugar cube.",
    "CerealAndBowl": "the cereal and the bowl both touch the counter nearest the cabinet, and the cabinet is closed "
    "(every door at most 0.5% open, normalised).",
    "SearingMeat": "the pan touches the stove with its centre within 0.15 m (horizontally) of the rear right burner, "
    "that burner's knob is on (angle from off, in absolute value, between 0.35 rad and 2π − 0.35 rad), the drumstick "
    "is in the pan (touching it, centres within 0.07 m horizontally; on the stove beside the pan does not count), and "
    "the gripper ends more than 0.25 m from the drumstick.",
    "ThawInSink": "the orange is inside the sink and the water is on (the faucet handle's on / off hinge between 0.40 "
    "rad and π rad). " + _HANDLE,
    "ScrubBowl": "the sponge has scrubbed the bowl for at least 15 control steps in all (steps on which it is on the "
    "bowl and moved more than 1 mm), and the gripper ends more than 0.25 m from the bowl.",
    "PlateSteakMeal": "the steak and the asparagus are on the plate, the chili pepper is still on the tray, and the "
    "gripper ends more than 0.25 m from all three.",
    "DrinkwareConsolidation": "the bottled water is inside the cabinet, and the gripper ends more than 0.25 m from it.",
    "ReheatMeal": "the tupperware is inside the microwave with the shrimp and the carrot in it, the door is fully "
    "closed (at most 0.5% open, normalised), the microwave is on (the start button pressed with the door not open; "
    "opening the door turns it off), and the gripper ends more than 0.25 m from the tupperware.",
    "ClearFoodWaste": "both food items are in the colander, and the gripper ends more than 0.25 m from both.",
    "ChooseMeasuringCup": "the smaller measuring cup touches the counter next to the drawer and the larger one does "
    "not, and the gripper ends more than 0.25 m from the smaller cup (the drawer itself is not checked).",
    "OrganizeCoffeeCondiments": "the syrup bottle and the honey bottle both touch the counter under the coffee "
    "machine with their centres less than 0.3 m from the mug's (3-D distance), and the gripper ends more than "
    "0.15 m from both.",
}
