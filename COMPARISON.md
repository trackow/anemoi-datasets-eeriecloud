# Comparison: NEW plugin vs OLD standalone implementation

Comparison of the new `anemoi-datasets-eeriecloud` plugin against the original
standalone implementation in `EERIE-anemoi-code/`.

## What NEW does better

- **Plugin architecture** — proper anemoi-datasets entry point via `pyproject.toml`, just
  `pip install` and use `eeriecloud:` in any recipe
- **Preset system** (`presets.py`) — extensible dict mapping short names to STAC collection IDs
- **Grid auto-detection** from STAC item names (e.g. `atmos.gr025.…` → `{"grid": [0.25, 0.25]}`)
- **NaN handling** — explicit `fillna(0.0)` for ci/sst over land (OLD left NaN as-is)
- **Coordinate standardization** — sets `standard_name`/`units` on lat/lon for anemoi's coord guesser
- **Recipe-based workflow** — declarative YAML, version-controllable, reproducible
- **Multiple interpolation methods** — runtime switch between `earthkit` and `fallback`
- **Cleaner time selection** — pandas DatetimeIndex + `ds.sel()` instead of integer slicing

## What OLD had that NEW is missing

### Critical — accumulated fields (tp, cp)

OLD had full de-accumulation in `eerie_regrid.py` via `diff()` + time intervals. Also handled
the timestamp offset (03/09/15/21 → 00/06/12/18 UTC) with `interp(method='nearest')`.

NEW acknowledges both issues in TODO.md but has no implementation. Open questions:
1. Are EERIE accumulated fields running totals or 6h step totals?
2. De-accumulation inside plugin or via anemoi's `accumulate` filter?
3. Exact variable names and units?

### Important — HPC support

OLD had full parquet-path loading from `anemoi_eerie_config.yaml`:
```yaml
hpc:
  base_path: "/work/bm1344/k202193/Kerchunk/IFS-FESOM_sr/hist-1950/v20240304"
  datasets:
    instant_2d: "atmos/gr025/2D_6hourly_instant.parq"
    accumulated_2d: "atmos/gr025/2D_6hourly_accumulated.parq"
    3d: "atmos/gr025/3D_6hourly.parq"
```

NEW `hpc.py` now reimplements equivalent functionality — open via `reference://` protocol
with `remote_protocol: file`, or fall back to STAC dkrz-disk asset metadata. Use `asset: dkrz-disk`
in a recipe to activate.

### Nice-to-have — not ported

- **Static fields** — `lsm`, `z_sfc` (orography), `sdor`, `slor` from MARS (not in EERIE).
  Not in any NEW recipe. These would need a separate `mars:` source in the recipe.
- **Memory management** — OLD set explicit dask memory limits
  (`distributed.worker.memory.target: 0.7`, etc.). NEW relies on anemoi-datasets defaults.
- **Constants transparency** — OLD had full insolation calculation (solar declination, hour
  angle, S0=1361 W/m²) and local-time longitude offset. NEW defers to anemoi's built-in
  `constants` source.
- **Metadata generation** — OLD added title, source, institution, version to zarr output.
  NEW relies on anemoi-datasets build system.
- **SLURM job script** — OLD included `run_hpc.sh`. NEW users on HPC must write their own.
- **PROGRESS.md** — OLD maintained a detailed troubleshooting/progress log. Useful for
  debugging but not carried over.

## O96 grid: 40,320 points

OLD discovered that earthkit-regrid gives 40,320 points for O96, not 73,728 (192×384 from
xESMF). OLD's PROGRESS.md called this "absolutely disastrous" and reverted to xESMF.

However, **earthkit-regrid is ECMWF's own software** and 40,320 is the correct O96 reduced
Gaussian grid point count. The 192×384 = 73,728 from xESMF was a regular lat-lon
approximation, not a true reduced Gaussian grid. We trust earthkit here.

## Variable coverage comparison

| Category | OLD | NEW | Status |
|----------|-----|-----|--------|
| Surface instant (10) | ✅ | ✅ | Parity |
| Pressure level (6×13 = 78) | ✅ | ✅ | Parity |
| Accumulated (tp, cp) | ✅ De-accum implemented | ⚠️ In recipe, no de-accum | TODO |
| Constants/forcings (9) | ✅ Custom calc | ✅ Via anemoi constants | Parity (different impl) |
| Ocean (tos, zos, siconc) | ❌ | ⚠️ In recipe, no time align | TODO |
| Static (lsm, z_sfc, sdor, slor) | ❌ Documented | ❌ Documented | Neither |
| **Total** | **99** | **99** (when accum done) | |

## Remaining TODOs (from TODO.md)

1. **Accumulated fields** — implement de-accumulation + time alignment
2. **Ocean data** — handle daily→6h time alignment and different grid format
3. **Native grid** — fix >2GB chunk size for TCo1279 (6,599,680 points)
