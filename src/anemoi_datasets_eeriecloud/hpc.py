"""HPC data access for EERIE datasets via kerchunk parquet references.

Used on DKRZ Levante/similar HPC systems where data is on Lustre filesystem.
"""

import logging
from pathlib import Path

import xarray as xr

logger = logging.getLogger(__name__)


def open_dataset_hpc(parquet_path):
    """Open an xarray Dataset from a kerchunk parquet reference file.

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
        raise FileNotFoundError(f"Parquet reference file not found: {parquet_path}")

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

    logger.info("Dataset dimensions: %s", dict(ds.dims))
    logger.info("Dataset variables: %s", list(ds.data_vars))
    return ds


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
    """
    return stac_item["assets"][asset]["href"]
