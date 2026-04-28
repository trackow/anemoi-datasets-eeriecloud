# Plan: anemoi-datasets-eeriecloud Plugin

## TL;DR

Create `anemoi-datasets-eeriecloud` — a source plugin for anemoi-datasets. Two key parameters: `collection` (which EERIE simulation) and `item` (which specific dataset within it). Optional `grid` for regridding, `param`/`levelist` for variable selection. Named `dataset` presets provide shorthand for known simulations.

## Interface Design

### STAC Item ID Structure

```
{collection}-disk.model-output.{source_id}.{experiment}.{version}.{item}-zarr-kerchunk
└────────────── collection ──────────────┘                                └─ item ─┘
```

Example full ID:
```
eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304-disk.model-output.ifs-fesom2-sr.hist-1950.v20240304.atmos.native.2D_6hourly_instant-zarr-kerchunk
```

The `item` encodes: `{realm}.{grid}.{descriptor}` — e.g., `atmos.native.2D_6hourly_instant`

### Recipe Interface

```yaml
# Minimal: dataset preset + item + params
eeriecloud:
    dataset: eerie-ifs-fesom-hist-1950          # preset → resolves collection + item prefix
    item: atmos.gr025.2D_6hourly_instant  # which specific STAC dataset
    param: [10u, 10v, 2t, 2d, msl, sp]

# With regridding
eeriecloud:
    dataset: eerie-ifs-fesom-hist-1950
    item: atmos.gr025.3D_6hourly
    param: [t, u, v, w, z, q]
    levelist: [1000, 925, 850, 700, 500, 250]
    grid: O96

# Fully explicit (no preset)
eeriecloud:
    collection: eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304
    item: land.native.3D_daily_avg
    param: [...]

# Ocean
eeriecloud:
    dataset: eerie-ifs-fesom-hist-1950
    item: ocean.gr025.2D_daily_avg_1950-2014
    param: [avg_tos, avg_zos, avg_siconc]
    grid: O96
```

### Full Coupled Recipe Example

```yaml
dates:
  start: "1970-01-01T06:00:00"
  end: "2014-12-31T18:00:00"
  frequency: "6h"

input:
  join:
    - eeriecloud:
        dataset: eerie-ifs-fesom-hist-1950
        item: atmos.gr025.2D_6hourly_instant
        param: [10u, 10v, 2t, 2d, msl, sp, skt, tcw, ci, sst]
        grid: O96
    - eeriecloud:
        dataset: eerie-ifs-fesom-hist-1950
        item: atmos.gr025.3D_6hourly
        param: [t, u, v, w, z, q]
        levelist: [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
        grid: O96
    - eeriecloud:
        dataset: eerie-ifs-fesom-hist-1950
        item: atmos.gr025.2D_6hourly_accumulated
        param: [tp, cp]
        grid: O96
        # TODO: Check with colleagues — de-accumulation needed? See TODO.md
    - eeriecloud:
        dataset: eerie-ifs-fesom-hist-1950
        item: ocean.gr025.2D_daily_avg_1950-2014
        param: [avg_tos, avg_zos, avg_siconc]
        grid: O96
    - forcings:
        template: "${input.join.0.eeriecloud}"
        param: [cos_latitude, sin_latitude, cos_longitude, sin_longitude,
                cos_julian_day, sin_julian_day, cos_local_time, sin_local_time,
                insolation]

output:
  flatten_grid: true
  order_by: [valid_datetime, param_level]

build:
  group_by: [year, month]
  remapping:
    param_level: "{param}_{levelist}"
```

## Steps

### Phase 1: Project Scaffolding

1. Create project at `/Users/natr/Documents/anemoi-datasets-eerie/`
2. `pyproject.toml`:
   - Package: `anemoi-datasets-eeriecloud`
   - Entry point: `eeriecloud = "anemoi_datasets_eeriecloud.source:EerieCloudSource"` under `anemoi.datasets.create.sources`
   - Deps: `anemoi-datasets`, `earthkit-data`, `earthkit-regrid`, `xarray`, `fsspec`, `s3fs`, `requests`
3. `src/anemoi_datasets_eeriecloud/__init__.py`

### Phase 2: STAC Data Access (*parallel with Phase 3*)

4. `src/anemoi_datasets_eeriecloud/stac.py`
   - `fetch_stac_item(collection, item, stac_url)` → GET STAC item JSON, construct full item ID from `{collection}-disk.model-output.{...}.{item}-zarr-kerchunk`
   - `open_dataset(stac_item, asset)` → open lazy `xr.Dataset` using `xarray:open_kwargs` from STAC metadata
   - Default STAC URL: `https://stac2.cloud.dkrz.de/fastapi`
   - Default asset: `eerie-cloud` (cloud access), `dkrz-disk` (HPC)

### Phase 3: HPC Data Access (*parallel with Phase 2*)

5. `src/anemoi_datasets_eeriecloud/hpc.py`
   - `open_dataset_hpc(parquet_path)` → open via kerchunk reference filesystem
   - HPC parquet path derivable from STAC item `dkrz-disk` asset `href`

### Phase 4: Variable Extraction

6. `src/anemoi_datasets_eeriecloud/variables.py`
   - `select_variables(ds, params)` → subset to requested variables
   - `select_levels(ds, levels)` → select pressure levels, auto-detect dim name and units
   - No reshape, no per-level renaming — stays in native format

### Phase 5: Regridding (Optional)

7. `src/anemoi_datasets_eeriecloud/regrid.py`
   - Only invoked when `grid:` specified in recipe
   - Default `interpolation: "earthkit"` — earthkit-regrid is canonical (O96 = 40,320 pts)
   - `interpolation: "fallback"` → scipy/xESMF, only on explicit request
   - Without `grid:`, data passes through on source grid

### Phase 6: Dataset Presets

8. `src/anemoi_datasets_eeriecloud/presets.py`
   - Maps dataset name → `{collection, item_prefix, suffix}`
   - `eerie-ifs-fesom-hist-1950`:
     - collection: `eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304`
     - item_prefix: `eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304-disk.model-output.ifs-fesom2-sr.hist-1950.v20240304`
     - suffix: `-zarr-kerchunk`
   - `resolve_preset(dataset, item)` → returns full STAC collection ID and item ID
   - Extensible for future experiments (nextGEMS, hackathon, etc.)

### Phase 7: Main Source Plugin (*depends on 4-8*)

9. `src/anemoi_datasets_eeriecloud/source.py`
   - `EerieCloudSource(LegacySource)` registered as `"eeriecloud"`
   - `_execute(context, dates, *, dataset=None, collection=None, item, param=None, levelist=None, grid=None, interpolation="earthkit", asset="eerie-cloud", **kwargs)`
   - Flow:
     1. Resolve `collection` from `dataset` preset, or use explicit `collection`
     2. Construct full STAC item ID from `collection` + `item`
     3. Fetch STAC item metadata, open xarray dataset lazily
     4. Select requested `param` and `levelist`
     5. Optionally regrid if `grid` specified
     6. Convert to `earthkit.data.FieldList` via XarrayFieldList
     7. Filter to requested `dates`
     8. Return FieldList

### Phase 8: Example Recipes

10. `recipes/eerie-ifs-fesom-hist1950-o96.yaml` — Coupled atmos+ocean with regrid to O96
11. `recipes/eerie-ifs-fesom-hist1950-native.yaml` — Native TCo1279 atmos, no regridding
12. `recipes/eerie-ifs-fesom-hist1950-test.yaml` — Quick test (24 timesteps, 3 levels)

### Phase 9: Testing & Documentation

13. `tests/test_source.py` — Unit tests (presets, STAC mock, variable selection)
14. `README.md` — Installation, quick start, available items, presets

## Relevant Files (from existing codebase)

- `eerie_data_loader.py` — STAC loading patterns, HPC parquet loading, variable extraction
- `eerie_regrid.py` — regridding fallback patterns (xESMF/scipy)
- `anemoi_eerie_config.yaml` — Variable lists, pressure levels, collection IDs
- anemoi-datasets `xarray_support/grid.py` — `UnstructuredGrid`, `MeshedGrid`
- anemoi-datasets `xarray_support/flavour.py` — Coordinate auto-detection

## Verification

1. `pip install -e .` succeeds in fresh venv with anemoi-datasets
2. Entry point `eeriecloud` discoverable
3. `anemoi-datasets create recipes/eerie-ifs-fesom-hist1950-test.yaml test.zarr` runs end-to-end
4. Output has expected shape and variable count:
   - Surface instant: 10 (10u, 10v, 2d, 2t, msl, sp, skt, tcw, ci, sst)
   - Pressure level: 78 (6 vars × 13 levels: q, t, u, v, w, z)
   - Accumulated: 2 (tp, cp) — TODO: verify de-accumulation, see TODO.md
   - Constants/forcings: 9
   - **Total: 99 variables** (101 with orographic fields from MARS if added)
   - Grid: O96 = 40,320 points
5. `pytest tests/` passes

## Decisions

- **Primary interface**: `dataset` (preset) + `item` (STAC descriptor). Two params to identify any EERIE dataset.
- **Fallback**: explicit `collection` + `item` for datasets not in presets
- **No reshaping**: native formats work directly with anemoi-datasets grid support
- **Regridding**: Optional `grid` param. earthkit-regrid canonical (O96=40,320). `interpolation: "fallback"` for scipy/xESMF.
- **Multi-realm via join**: atmos + ocean + land combined in recipe with separate `eeriecloud` calls
- **Constants**: Standard `forcings` source
- **Base class**: `LegacySource` with `_execute()`
