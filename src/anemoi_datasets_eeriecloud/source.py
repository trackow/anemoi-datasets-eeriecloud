"""EERIE cloud data source plugin for anemoi-datasets.

Registers the ``eeriecloud`` source for use in anemoi dataset recipes.
Fetches data from the EERIE STAC catalogue at DKRZ and converts it to
an earthkit FieldList compatible with the anemoi-datasets pipeline.
"""

import datetime
import logging
from typing import Any

from anemoi.datasets.create.sources.legacy import LegacySource

logger = logging.getLogger(__name__)


class EerieCloudSource(LegacySource):
    """Source plugin that loads EERIE data from STAC/cloud or HPC."""

    @staticmethod
    def _execute(
        context: Any,
        dates: list[datetime.datetime],
        *,
        dataset: str | None = None,
        collection: str | None = None,
        item: str,
        param: list[str] | None = None,
        levelist: list[int] | None = None,
        grid: str | None = None,
        interpolation: str = "earthkit",
        asset: str = "eerie-cloud",
        base_path: str | None = None,
        **kwargs: Any,
    ):
        """Execute the eeriecloud source.

        Parameters
        ----------
        context : Any
            anemoi-datasets build context.
        dates : list[datetime.datetime]
            Dates to load data for.
        dataset : str, optional
            Preset name (e.g. "eerie-ifs-fesom-hist-1950").
        collection : str, optional
            Explicit STAC collection ID (alternative to dataset).
        item : str
            STAC item descriptor (e.g. "atmos.gr025.2D_6hourly_instant").
        param : list[str], optional
            Variable names to select.
        levelist : list[int], optional
            Pressure levels to select (hPa).
        grid : str, optional
            Target grid for regridding (e.g. "O96"). If None, no regridding.
        interpolation : str
            Regridding method ("earthkit" or "fallback").
        asset : str
            STAC asset key ("eerie-cloud" for cloud, "dkrz-disk" for HPC).
        base_path : str, optional
            HPC base path for direct parquet access (skips STAC entirely).
        """
        from .presets import resolve_preset
        from .regrid import detect_source_grid, regrid
        from .stac import fetch_stac_item, open_dataset
        from .variables import select_levels, select_time, select_variables

        # 0. Direct HPC access — skip STAC entirely
        if base_path is not None:
            from .hpc import open_dataset_hpc, resolve_hpc_path

            parquet_path = resolve_hpc_path(item, base_path=base_path)
            logger.info("Direct HPC access: %s", parquet_path)
            ds = open_dataset_hpc(parquet_path)
        else:
            # 1. Resolve collection + item ID via STAC
            if dataset is not None:
                collection_id, full_item_id = resolve_preset(dataset, item)
            elif collection is not None:
                full_item_id = f"{collection}-disk.model-output.{_extract_model_part(collection)}.{item}-zarr-kerchunk"
                collection_id = collection
            else:
                raise ValueError(
                    "Either 'dataset' (preset name) or 'collection' (STAC collection ID) must be provided."
                )

            logger.info("Loading EERIE data: collection=%s, item=%s", collection_id, item)

            # 2. Fetch STAC metadata and open dataset
            stac_item = fetch_stac_item(collection_id, full_item_id)

            if asset == "dkrz-disk":
                from .hpc import open_dataset_hpc, parquet_path_from_stac

                parquet_path = parquet_path_from_stac(stac_item, asset=asset)
                ds = open_dataset_hpc(parquet_path)
            else:
                ds = open_dataset(stac_item, asset=asset)

        # 3. Select variables and levels
        ds = select_variables(ds, param)
        ds = select_levels(ds, levelist)

        # 4. Select requested dates
        # dates may be a GroupOfDates or similar iterable — normalize to list
        import numpy as np
        import pandas as pd

        date_list = list(dates)
        date_list_np = pd.DatetimeIndex(date_list)
        ds = select_time(ds, date_list_np)

        # 5. Regrid if requested
        if grid is not None:
            source_grid_name = detect_source_grid(item)
            ds = regrid(ds, grid, source_grid_name=source_grid_name, interpolation=interpolation)

        # 6. Fill NaN values (e.g. ci/sst are NaN over land in EERIE, unlike ERA5)
        ds = ds.fillna(0.0)

        # 7. Ensure lat/lon have standard_name attributes for anemoi coordinate guesser
        for coord_name in ("lat", "latitude"):
            if coord_name in ds.coords and "standard_name" not in ds[coord_name].attrs:
                ds[coord_name].attrs["standard_name"] = "latitude"
                ds[coord_name].attrs["units"] = "degrees_north"
        for coord_name in ("lon", "longitude"):
            if coord_name in ds.coords and "standard_name" not in ds[coord_name].attrs:
                ds[coord_name].attrs["standard_name"] = "longitude"
                ds[coord_name].attrs["units"] = "degrees_east"

        # 7. Convert to earthkit FieldList via XarrayFieldList
        from anemoi.datasets.create.sources.xarray_support import XarrayFieldList

        result = XarrayFieldList.from_xarray(ds)

        logger.info(
            "Returning %d fields for %d dates",
            len(result),
            len(date_list),
        )
        return result


def _extract_model_part(collection):
    """Extract the model-output part from a collection ID.

    Example:
        "eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304"
        → "ifs-fesom2-sr.hist-1950.v20240304"

    This is a best-effort extraction. For reliable results, use presets.
    """
    # The collection ID pattern:
    #   eerie-{project}-{institution}-{model}-{experiment}-{version}
    # The model-output part in STAC item ID uses dots:
    #   {model}.{experiment}.{version}
    # This heuristic extracts from known patterns
    parts = collection.split("-")

    # Find the version (starts with 'v' + digit)
    version_idx = None
    for i, part in enumerate(parts):
        if part.startswith("v") and len(part) > 1 and part[1:].isdigit():
            version_idx = i
            break

    if version_idx is None:
        raise ValueError(
            f"Cannot extract model part from collection '{collection}'. "
            "Use a dataset preset instead, or provide the full item ID."
        )

    # For eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304:
    # institution parts: ecmwf-awi (indices 2-3)
    # model: ifs-fesom2-sr (indices 4 to experiment start)
    # experiment: hist-1950 (to version)
    # version: v20240304

    # Find experiment boundary: look for known experiment prefixes
    exp_start = None
    for i in range(4, version_idx):
        if parts[i] in ("hist", "ssp", "amip", "piControl", "control"):
            exp_start = i
            break

    if exp_start is None:
        raise ValueError(
            f"Cannot extract experiment from collection '{collection}'. "
            "Use a dataset preset instead."
        )

    model = "-".join(parts[4:exp_start])
    experiment = "-".join(parts[exp_start:version_idx])
    version = parts[version_idx]

    return f"{model}.{experiment}.{version}"
