"""STAC API access for EERIE datasets.

Fetches STAC item metadata and opens xarray datasets from cloud storage.
"""

import logging

import requests
import xarray as xr

logger = logging.getLogger(__name__)

DEFAULT_STAC_URL = "https://stac2.cloud.dkrz.de/fastapi"
DEFAULT_ASSET = "eerie-cloud"


def fetch_stac_item(collection, item_id, stac_url=DEFAULT_STAC_URL):
    """Fetch a STAC item's JSON metadata.

    Parameters
    ----------
    collection : str
        STAC collection ID.
    item_id : str
        Full STAC item ID.
    stac_url : str
        Base URL of the STAC API.

    Returns
    -------
    dict
        STAC item JSON.
    """
    url = f"{stac_url}/collections/{collection}/items/{item_id}"
    logger.info("Fetching STAC item: %s", url)

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def open_dataset(stac_item, asset=DEFAULT_ASSET):
    """Open an xarray Dataset from a STAC item asset.

    Uses the ``xarray:open_kwargs`` and ``xarray:storage_options``
    embedded in the STAC item metadata for zero-config access.

    Parameters
    ----------
    stac_item : dict
        STAC item JSON (as returned by :func:`fetch_stac_item`).
    asset : str
        Asset key to use (e.g. "eerie-cloud" or "dkrz-disk").

    Returns
    -------
    xr.Dataset
        Lazily-loaded xarray dataset.
    """
    asset_meta = stac_item["assets"][asset]
    href = asset_meta["href"]

    open_kwargs = asset_meta.get("xarray:open_kwargs", {}).copy()
    storage_options = asset_meta.get("xarray:storage_options", {})

    # Ensure lazy loading
    if "chunks" not in open_kwargs:
        open_kwargs["chunks"] = "auto"

    logger.info("Opening dataset: %s", href)
    ds = xr.open_dataset(href, storage_options=storage_options, **open_kwargs)
    logger.info("Dataset dimensions: %s", dict(ds.sizes))
    logger.info("Dataset variables: %s", list(ds.data_vars))
    return ds
