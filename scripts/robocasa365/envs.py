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
