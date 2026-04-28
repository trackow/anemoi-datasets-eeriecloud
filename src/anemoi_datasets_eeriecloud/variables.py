"""Variable and pressure level selection from EERIE xarray datasets."""

import logging

import xarray as xr

logger = logging.getLogger(__name__)

# Known dimension names for pressure levels across EERIE datasets
_LEVEL_DIM_NAMES = ("plev", "lev", "level", "pressure", "depth")

# Known dimension names for time
_TIME_DIM_NAMES = ("time", "valid_time", "forecast_time")


def select_variables(ds, params):
    """Subset an xarray Dataset to the requested variables.

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset.
    params : list[str] or None
        Variable names to keep. If None, keep all data variables.

    Returns
    -------
    xr.Dataset
        Dataset with only the requested variables.
    """
    if params is None:
        return ds

    available = set(ds.data_vars)
    requested = set(params)
    missing = requested - available
    if missing:
        raise ValueError(
            f"Variables not found in dataset: {sorted(missing)}. "
            f"Available: {sorted(available)}"
        )

    return ds[list(params)]


def select_levels(ds, levels):
    """Select pressure levels from a multi-level dataset.

    Auto-detects the level dimension name and handles unit conversion
    (Pa vs hPa).

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset with a level dimension.
    levels : list[int|float] or None
        Pressure levels to select (in hPa). If None, keep all levels.

    Returns
    -------
    xr.Dataset
        Dataset with only the requested levels.
    """
    if levels is None:
        return ds

    level_dim = _find_level_dim(ds)
    if level_dim is None:
        raise ValueError(
            f"No level dimension found. Dimensions: {list(ds.dims)}. "
            f"Expected one of: {_LEVEL_DIM_NAMES}"
        )

    level_coord = ds[level_dim]

    # Auto-detect units: if max value > 2000, assume Pa → convert request to Pa
    requested = [float(lev) for lev in levels]
    if float(level_coord.max()) > 2000:
        logger.info("Level coordinate appears to be in Pa, converting request")
        requested = [lev * 100.0 for lev in requested]

    ds = ds.sel({level_dim: requested})
    logger.info("Selected %d levels on dimension '%s'", len(levels), level_dim)
    return ds


def select_time(ds, dates):
    """Select timesteps matching the requested dates.

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset.
    dates : list[datetime.datetime]
        Dates to select.

    Returns
    -------
    xr.Dataset
        Dataset with only the requested time steps.
    """
    time_dim = _find_time_dim(ds)
    if time_dim is None:
        logger.warning("No time dimension found, returning dataset as-is")
        return ds

    return ds.sel({time_dim: dates})


def _find_level_dim(ds):
    """Find the level/pressure dimension in a dataset."""
    for name in _LEVEL_DIM_NAMES:
        if name in ds.dims:
            return name
    return None


def _find_time_dim(ds):
    """Find the time dimension in a dataset."""
    for name in _TIME_DIM_NAMES:
        if name in ds.dims:
            return name
    return None
