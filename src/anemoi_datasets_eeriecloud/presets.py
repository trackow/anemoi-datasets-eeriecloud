"""Dataset presets for known EERIE simulations.

Maps short preset names to STAC collection IDs and item ID components.
"""

PRESETS = {
    "eerie-ifs-fesom-hist-1950": {
        "collection": "eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304",
        "item_prefix": (
            "eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304"
            "-disk.model-output.ifs-fesom2-sr.hist-1950.v20240304"
        ),
        "suffix": "-zarr-kerchunk",
    },
}


def resolve_preset(dataset, item):
    """Resolve a dataset preset name + item to full STAC collection and item ID.

    Parameters
    ----------
    dataset : str
        Preset name, e.g. "eerie-ifs-fesom-hist-1950"
    item : str
        Item descriptor, e.g. "atmos.gr025.2D_6hourly_instant"

    Returns
    -------
    tuple[str, str]
        (collection_id, full_stac_item_id)

    Raises
    ------
    ValueError
        If dataset preset is not found.
    """
    if dataset not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(
            f"Unknown dataset preset '{dataset}'. Available: {available}"
        )

    preset = PRESETS[dataset]
    collection = preset["collection"]
    full_item_id = f"{preset['item_prefix']}.{item}{preset['suffix']}"
    return collection, full_item_id


def list_presets():
    """Return list of available preset names."""
    return sorted(PRESETS.keys())
