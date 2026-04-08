# Hash table mapping materials to their base operating temperatures
BASE_TEMP = {
    "copper": 300.0,
    "aluminum": 200.0,
    "fiber": 50.0
}

def calculate_wire_temp(material: str, load_percentage: int) -> float:
    """
    Calculates the expected temperature of a wire based on its material and load.
    """
    if material not in BASE_TEMP:
        raise ValueError(f"Invalid material: '{material}'")

    # BUG: Floor division (//) forces any percentage under 100 to become 0.
    # This multiplies the base temperature by 0, making all wires read 0.0 degrees!
    # FIX: Change // to / for standard float division.
    load_factor = load_percentage // 100

    return BASE_TEMP[material] * load_factor
