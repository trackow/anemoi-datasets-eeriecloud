# TODO — anemoi-datasets-eeriecloud

## Native Grid

Plugin works on native TCo1279 grid (6,599,680 points) — STAC fetch, variable selection, constants all OK. However zarr write fails with `Codec does not support buffers of > 2147483647 bytes` because the default chunk (1, 92, 1, 6599680) exceeds 2GB. Need to configure chunking in recipe output or anemoi-datasets config. Also: native 2D instant only has 5 vars (`10si, 10u, 10v, 2d, 2t`) — other surface vars (msl, sp, skt, etc.) must be in different STAC items; need to discover which ones.

## Accumulated Fields (tp, cp)

The EERIE STAC item `atmos.gr025.2D_6hourly_accumulated` contains `tp` (total precipitation) and `cp` (convective precipitation).

**Timestamps are offset**: the accumulated dataset uses 03/09/15/21 UTC (not 00/06/12/18 like instant fields). Need to handle time alignment — either shift timestamps or use `method="nearest"` in `select_time`.

Before implementing their ingestion, **check with colleagues**:

1. **Are EERIE accumulated fields stored as running totals (from forecast start) or as 6h step totals?**
   - If running totals → need de-accumulation (compute step differences)
   - If 6h totals → can ingest directly, no special processing

2. **Should de-accumulation be handled inside the plugin or via the built-in `accumulate` filter?**
   - Option A: Handle inside `eeriecloud` source (compute diffs before returning FieldList)
   - Option B: Wrap with anemoi-datasets' `accumulate` filter in the recipe
   - Option C: Not needed if EERIE already stores per-step values

3. **What are the exact variable names and units in the EERIE accumulated dataset?**
   - Confirm they are `tp` and `cp` (same as MARS convention)
   - Check units — MARS uses kg/m² (= mm), EERIE may differ

## Ocean Data (avg_tos, avg_zos, avg_siconc)

The EERIE ocean dataset `ocean.gr025.2D_daily_avg_1950-2014` has two differences from the atmosphere data:

1. **Grid format**: Uses `(time, lev, lat, lon, depth)` — a proper 2D lat/lon grid, not the flat `(time, value)` layout used by atmosphere data. The regrid and source code currently assumes `(time, value)` with 1D lat/lon.

2. **Temporal resolution**: Daily averages at 00:00 UTC, not 6-hourly. Need to decide how to align with the 6h atmosphere timestamps — forward-fill daily values, or interpolate.