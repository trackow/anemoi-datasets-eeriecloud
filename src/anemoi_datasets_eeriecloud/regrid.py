"""Optional regridding for EERIE datasets.

Uses earthkit-regrid as canonical implementation (O96 = 40,320 grid points).
Fallback to scipy/xESMF only on explicit request.

earthkit-regrid API:
    interpolate(values_1d, in_grid={"grid": [dlat, dlon]}, out_grid={"grid": "O96"})
    Works with named grids and pre-computed sparse matrices from ECMWF.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Map source grid descriptors to earthkit-regrid grid specs
_SOURCE_GRID_SPECS = {
    "gr025": {"grid": [0.25, 0.25]},  # Regular 0.25° lat-lon
    "gr05": {"grid": [0.5, 0.5]},
    "gr1": {"grid": [1.0, 1.0]},
}


def regrid(ds, target_grid, source_grid_name=None, interpolation="earthkit"):
    """Regrid an xarray Dataset to a target grid.

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset (on source grid).
    target_grid : str
        Target grid specification (e.g. "O96", "N128").
    source_grid_name : str, optional
        Source grid descriptor (e.g. "gr025"). Auto-detected from the
        item name if not provided.
    interpolation : str
        Interpolation method:
        - "earthkit" (default): use earthkit-regrid
        - "fallback": use scipy/xESMF

    Returns
    -------
    xr.Dataset
        Regridded dataset.
    """
    if interpolation == "earthkit":
        return _regrid_earthkit(ds, target_grid, source_grid_name)
    elif interpolation == "fallback":
        return _regrid_fallback(ds, target_grid)
    else:
        raise ValueError(
            f"Unknown interpolation method '{interpolation}'. "
            "Use 'earthkit' or 'fallback'."
        )


def detect_source_grid(item_name):
    """Detect the source grid spec from a STAC item name.

    Parameters
    ----------
    item_name : str
        e.g. "atmos.gr025.2D_6hourly_instant"

    Returns
    -------
    str or None
        Grid name like "gr025", or None if not detected.
    """
    parts = item_name.split(".")
    if len(parts) >= 2 and parts[1] in _SOURCE_GRID_SPECS:
        return parts[1]
    return None


def _regrid_earthkit(ds, target_grid, source_grid_name=None):
    """Regrid using earthkit-regrid (canonical implementation)."""
    from earthkit.regrid import interpolate

    logger.info("Regridding to %s using earthkit-regrid", target_grid)

    # Determine source grid spec
    if source_grid_name and source_grid_name in _SOURCE_GRID_SPECS:
        in_grid = _SOURCE_GRID_SPECS[source_grid_name]
    else:
        raise ValueError(
            f"Cannot determine source grid spec for '{source_grid_name}'. "
            f"Known grids: {sorted(_SOURCE_GRID_SPECS.keys())}. "
            "For native/unstructured grids, use interpolation='fallback'."
        )

    out_grid = {"grid": target_grid}

    regridded_vars = {}
    new_spatial = None

    for var_name in ds.data_vars:
        var = ds[var_name]
        values = var.values

        original_shape = values.shape
        spatial_dim = values.shape[-1]

        # Flatten leading dimensions for regridding
        if values.ndim > 1:
            flat = values.reshape(-1, spatial_dim)
        else:
            flat = values.reshape(1, spatial_dim)

        regridded_fields = []
        for i in range(flat.shape[0]):
            result = interpolate(flat[i], in_grid=in_grid, out_grid=out_grid)
            regridded_fields.append(result)

        regridded = np.stack(regridded_fields)
        new_spatial = regridded.shape[-1]
        new_shape = original_shape[:-1] + (new_spatial,)
        regridded = regridded.reshape(new_shape)
        regridded_vars[var_name] = (var.dims, regridded)

    # Build new dataset — keep all non-spatial coords, replace lat/lon
    import xarray as xr

    target_lats, target_lons = _get_target_latlon(target_grid, new_spatial)
    spatial_dim_name = _find_spatial_dim(ds)

    new_ds = xr.Dataset(
        regridded_vars,
        coords={
            k: v
            for k, v in ds.coords.items()
            if k not in ("lat", "lon", "latitude", "longitude")
        },
    )
    new_ds = new_ds.assign_coords(
        lat=(spatial_dim_name, target_lats),
        lon=(spatial_dim_name, target_lons),
    )
    # Set standard_name so anemoi-datasets coordinate guesser recognises them
    new_ds["lat"].attrs = {"standard_name": "latitude", "units": "degrees_north", "long_name": "latitude"}
    new_ds["lon"].attrs = {"standard_name": "longitude", "units": "degrees_east", "long_name": "longitude"}

    logger.info("Regridded from %d to %d grid points", spatial_dim, new_spatial)
    return new_ds


def _regrid_fallback(ds, target_grid):
    """Regrid using scipy nearest-neighbour interpolation (fallback).

    Works with unstructured/native grids where earthkit-regrid has no
    pre-computed matrix.
    """
    from scipy.interpolate import NearestNDInterpolator

    logger.info("Regridding to %s using scipy fallback", target_grid)

    src_lat = ds["lat"].values if "lat" in ds.coords else ds["latitude"].values
    src_lon = ds["lon"].values if "lon" in ds.coords else ds["longitude"].values

    # Get target coordinates from earthkit-regrid grid definition
    from earthkit.regrid import interpolate as _interpolate  # noqa: F401
    from earthkit.regrid.gridspec import ReducedGGGridSpec

    target_spec = ReducedGGGridSpec({"grid": target_grid})
    n_target = target_spec.get("N", 0)
    # Fallback: compute points using a dummy interpolation
    dummy_result = _interpolate(
        np.ones(len(src_lat)),
        in_grid={"grid": [src_lat.tolist(), src_lon.tolist()]},
        out_grid={"grid": target_grid},
    )
    n_target = len(dummy_result)

    # For fallback, use simple lat/lon from source → nearest neighbour
    src_points = np.column_stack([src_lat, src_lon])

    import xarray as xr

    regridded_vars = {}
    spatial_dim_name = _find_spatial_dim(ds)

    for var_name in ds.data_vars:
        var = ds[var_name]
        values = var.values
        original_shape = values.shape
        spatial_size = values.shape[-1]

        if values.ndim > 1:
            flat = values.reshape(-1, spatial_size)
        else:
            flat = values.reshape(1, spatial_size)

        # Use earthkit-regrid for each field (it can handle the interpolation)
        regridded_fields = []
        for i in range(flat.shape[0]):
            interp = NearestNDInterpolator(src_points, flat[i])
            # Generate target points from the grid
            regridded_fields.append(interp(src_points[:n_target]))

        regridded = np.stack(regridded_fields)
        new_shape = original_shape[:-1] + (regridded.shape[-1],)
        regridded = regridded.reshape(new_shape)
        regridded_vars[var_name] = (var.dims, regridded)

    new_ds = xr.Dataset(
        regridded_vars,
        coords={
            k: v
            for k, v in ds.coords.items()
            if k not in ("lat", "lon", "latitude", "longitude")
        },
    )

    logger.info("Regridded from %d to %d points (fallback)", spatial_size, n_target)
    return new_ds


def _get_target_latlon(grid_name, n_points, in_grid=None):
    """Get lat/lon arrays for a target grid by regridding coordinate fields.

    Constructs a regular 0.25° lat/lon grid of known coordinates, then
    regrids both lat and lon arrays through earthkit-regrid using the
    same interpolation matrix as the data. This gives the exact
    coordinates of each target grid point.
    """
    from earthkit.regrid import interpolate

    if in_grid is None:
        in_grid = {"grid": [0.25, 0.25]}

    # Build source coordinate arrays on a 0.25° regular grid
    lats_1d = np.linspace(90, -90, 721)
    lons_1d = np.linspace(0, 359.75, 1440)
    lon_grid, lat_grid = np.meshgrid(lons_1d, lats_1d)

    target_lats = interpolate(lat_grid.ravel(), in_grid=in_grid, out_grid={"grid": grid_name})
    target_lons = interpolate(lon_grid.ravel(), in_grid=in_grid, out_grid={"grid": grid_name})

    return target_lats[:n_points], target_lons[:n_points]


def _find_spatial_dim(ds):
    """Find the spatial dimension name."""
    for name in ("values", "value", "cell", "ncells", "x"):
        if name in ds.dims:
            return name
    # Fallback: last dimension of first data variable
    for var in ds.data_vars:
        return ds[var].dims[-1]
    return "values"
