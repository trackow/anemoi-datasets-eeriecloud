"""Tests for the anemoi-datasets-eeriecloud plugin."""

import datetime

import pytest


class TestPresets:
    """Test preset resolution."""

    def test_resolve_known_preset(self):
        from anemoi_datasets_eeriecloud.presets import resolve_preset

        collection, item_id = resolve_preset(
            "eerie-ifs-fesom-hist-1950",
            "atmos.gr025.2D_6hourly_instant",
        )
        assert collection == "eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304"
        assert item_id.endswith(".atmos.gr025.2D_6hourly_instant-zarr-kerchunk")
        assert "disk.model-output" in item_id

    def test_resolve_unknown_preset_raises(self):
        from anemoi_datasets_eeriecloud.presets import resolve_preset

        with pytest.raises(ValueError, match="Unknown dataset preset"):
            resolve_preset("nonexistent-preset", "atmos.gr025.2D_6hourly_instant")

    def test_list_presets(self):
        from anemoi_datasets_eeriecloud.presets import list_presets

        presets = list_presets()
        assert "eerie-ifs-fesom-hist-1950" in presets

    def test_preset_item_id_structure(self):
        from anemoi_datasets_eeriecloud.presets import resolve_preset

        _, item_id = resolve_preset(
            "eerie-ifs-fesom-hist-1950",
            "atmos.native.3D_6hourly",
        )
        # Full ID should follow the pattern:
        # {collection}-disk.model-output.{model}.{exp}.{ver}.{item}-zarr-kerchunk
        assert "-disk.model-output." in item_id
        assert ".atmos.native.3D_6hourly-zarr-kerchunk" in item_id


class TestVariables:
    """Test variable and level selection."""

    def test_select_variables(self):
        import numpy as np
        import xarray as xr

        from anemoi_datasets_eeriecloud.variables import select_variables

        ds = xr.Dataset(
            {
                "10u": (("time", "values"), np.ones((4, 10))),
                "10v": (("time", "values"), np.ones((4, 10))),
                "2t": (("time", "values"), np.ones((4, 10))),
            }
        )
        result = select_variables(ds, ["10u", "2t"])
        assert set(result.data_vars) == {"10u", "2t"}

    def test_select_variables_none_keeps_all(self):
        import numpy as np
        import xarray as xr

        from anemoi_datasets_eeriecloud.variables import select_variables

        ds = xr.Dataset(
            {
                "10u": (("time", "values"), np.ones((4, 10))),
                "10v": (("time", "values"), np.ones((4, 10))),
            }
        )
        result = select_variables(ds, None)
        assert set(result.data_vars) == {"10u", "10v"}

    def test_select_variables_missing_raises(self):
        import numpy as np
        import xarray as xr

        from anemoi_datasets_eeriecloud.variables import select_variables

        ds = xr.Dataset(
            {"10u": (("time", "values"), np.ones((4, 10)))}
        )
        with pytest.raises(ValueError, match="Variables not found"):
            select_variables(ds, ["10u", "missing_var"])

    def test_select_levels_hpa(self):
        import numpy as np
        import xarray as xr

        from anemoi_datasets_eeriecloud.variables import select_levels

        ds = xr.Dataset(
            {"t": (("time", "plev", "values"), np.ones((4, 5, 10)))},
            coords={"plev": [1000, 850, 700, 500, 250]},
        )
        result = select_levels(ds, [1000, 500])
        assert result.sizes["plev"] == 2

    def test_select_levels_pa_autodetect(self):
        import numpy as np
        import xarray as xr

        from anemoi_datasets_eeriecloud.variables import select_levels

        # Levels in Pa (> 2000 threshold)
        ds = xr.Dataset(
            {"t": (("time", "plev", "values"), np.ones((4, 3, 10)))},
            coords={"plev": [100000.0, 50000.0, 25000.0]},
        )
        result = select_levels(ds, [1000, 500])  # Request in hPa
        assert result.sizes["plev"] == 2

    def test_select_levels_none_keeps_all(self):
        import numpy as np
        import xarray as xr

        from anemoi_datasets_eeriecloud.variables import select_levels

        ds = xr.Dataset(
            {"t": (("time", "plev", "values"), np.ones((4, 5, 10)))},
            coords={"plev": [1000, 850, 700, 500, 250]},
        )
        result = select_levels(ds, None)
        assert result.sizes["plev"] == 5


class TestRegrid:
    """Test regridding utilities."""

    def test_detect_source_grid_gr025(self):
        from anemoi_datasets_eeriecloud.regrid import detect_source_grid

        assert detect_source_grid("atmos.gr025.2D_6hourly_instant") == "gr025"

    def test_detect_source_grid_native(self):
        from anemoi_datasets_eeriecloud.regrid import detect_source_grid

        assert detect_source_grid("atmos.native.2D_6hourly_instant") is None

    def test_detect_source_grid_unknown(self):
        from anemoi_datasets_eeriecloud.regrid import detect_source_grid

        assert detect_source_grid("ocean.some_grid.daily") is None


class TestSourceExtractModel:
    """Test the model part extraction helper."""

    def test_extract_model_part(self):
        from anemoi_datasets_eeriecloud.source import _extract_model_part

        result = _extract_model_part(
            "eerie-eerie-ecmwf-awi-ifs-fesom2-sr-hist-1950-v20240304"
        )
        assert result == "ifs-fesom2-sr.hist-1950.v20240304"

    def test_extract_model_part_no_version_raises(self):
        from anemoi_datasets_eeriecloud.source import _extract_model_part

        with pytest.raises(ValueError, match="Cannot extract model part"):
            _extract_model_part("no-version-here")
