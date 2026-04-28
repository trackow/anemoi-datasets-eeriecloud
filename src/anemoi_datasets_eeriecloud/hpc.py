"""HPC data access for EERIE datasets via kerchunk parquet references.

Used on DKRZ Levante/similar HPC systems where data is on Lustre filesystem.
Supports two modes:
1. Explicit parquet path (via ``base_path`` + item descriptor)
2. STAC-derived path (via ``dkrz-disk`` asset in STAC item metadata)
"""

import logging
from pathlib import Path

import xarray as xr

logger = logging.getLogger(__name__)

# Default HPC base path for EERIE kerchunk references on DKRZ Levante
DEFAULT_HPC_BASE_PATH = "/work/bm1344/k202193/Kerchunk/IFS-FESOM_sr/hist-1950/v20240304"

# Map STAC item descriptors to parquet sub-paths under the base path
_ITEM_TO_PARQUET = {
    "atmos.gr025.2D_6hourly_instant": "atmos/gr025/2D_6hourly_instant.parq",
    "atmos.gr025.2D_6hourly_accumulated": "atmos/gr025/2D_6hourly_accumulated.parq",
    "atmos.gr025.3D_6hourly": "atmos/gr025/3D_6hourly.parq",
    "atmos.native.2D_6hourly_instant": "atmos/native/2D_6hourly_instant.parq",
    "atmos.native.3D_6hourly": "atmos/native/3D_6hourly.parq",
    "ocean.gr025.2D_daily_avg_1950-2014": "ocean/gr025/2D_daily_avg_1950-2014.parq",
    "land.native.3D_daily_avg": "land/native/3D_daily_avg.parq",
}


def open_dataset_hpc(parquet_path):
    """Open an xarray Dataset from a kerchunk parquet reference file.

    Uses the fsspec ``reference://`` protocol to read zarr data via
    kerchunk parquet indices on the local filesystem.

    Parameters
    ----------
    parquet_path : str or Path
        Path to the .parq kerchunk reference file on the HPC filesystem.

    Returns
    -------
    xr.Dataset
        Lazily-loaded xarray dataset.
    """
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Parquet reference file not found: {parquet_path}. "
            f"Are you running on a DKRZ HPC node with access to Lustre?"
        )

    logger.info("Opening HPC dataset from: %s", parquet_path)

    ds = xr.open_dataset(
        f"reference://{parquet_path}",
        engine="zarr",
        backend_kwargs={
            "consolidated": False,
            "storage_options": {
                "fo": str(parquet_path),
                "remote_protocol": "file",
            },
        },
        chunks="auto",
    )

    logger.info("Dataset dimensions: %s", dict(ds.sizes))
    logger.info("Dataset variables: %s", list(ds.data_vars))
    return ds


def resolve_hpc_path(item, base_path=None):
    """Resolve an item descriptor to a local parquet path on HPC.

    Parameters
    ----------
    item : str
        STAC item descriptor (e.g. "atmos.gr025.2D_6hourly_instant").
    base_path : str or Path, optional
        Base path to kerchunk parquet directory. Defaults to the known
        DKRZ Levante path for IFS-FESOM hist-1950.

    Returns
    -------
    Path
        Full path to the parquet reference file.

    Raises
    ------
    ValueError
        If the item descriptor is not in the known mapping.
    """
    if base_path is None:
        base_path = DEFAULT_HPC_BASE_PATH

    if item not in _ITEM_TO_PARQUET:
        available = ", ".join(sorted(_ITEM_TO_PARQUET.keys()))
        raise ValueError(
            f"Unknown item '{item}' for HPC access. Known items: {available}"
        )

    return Path(base_path) / _ITEM_TO_PARQUET[item]


def parquet_path_from_stac(stac_item, asset="dkrz-disk"):
    """Extract the local filesystem path from a STAC item's HPC asset.

    Parameters
    ----------
    stac_item : dict
        STAC item JSON.
    asset : str
        Asset key for HPC access.

    Returns
    -------
    str
        Local filesystem path to the parquet reference.

    Raises
    ------
    KeyError
        If the asset key is not present in the STAC item.
    """
    if asset not in stac_item.get("assets", {}):
        available = ", ".join(sorted(stac_item.get("assets", {}).keys()))
        raise KeyError(
            f"Asset '{asset}' not found in STAC item. Available: {available}"
        )
    return stac_item["assets"][asset]["href"]
