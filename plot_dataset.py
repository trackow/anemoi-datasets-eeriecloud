#!/usr/bin/env python3
"""Plot all variables from an anemoi-datasets zarr output.

Adapted from EERIE-anemoi-code/inspect_output_dataset.py for the
anemoi-datasets zarr format (flat cell dimension with separate lat/lon arrays).

Usage:
    python plot_dataset.py test-demo.zarr
    python plot_dataset.py test-demo.zarr --timestep 4 --output-dir my_plots
"""

import argparse
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_dataset(zarr_path):
    """Load an anemoi-datasets zarr and return lats, lons, variable names, and data."""
    import anemoi.datasets as ad

    ds = ad.open_dataset(zarr_path)
    logger.info("Loaded %s: shape=%s, variables=%s", zarr_path, ds.shape, len(ds.variables))
    logger.info("Dates: %s to %s", ds.dates[0], ds.dates[-1])

    import zarr
    z = zarr.open(zarr_path, "r")
    lats = z["latitudes"][:]
    lons = z["longitudes"][:]
    return ds, lats, lons


def categorize_variables(variables):
    """Split variables into surface, pressure-level sets, and constants."""
    surface, pressure, constants = [], {}, []
    for var in variables:
        if any(x in var for x in ["cos_", "sin_", "insolation"]):
            constants.append(var)
        elif "_" in var and var.rsplit("_", 1)[-1].isdigit():
            base, level = var.rsplit("_", 1)
            pressure.setdefault(base, []).append((int(level), var))
        else:
            surface.append(var)
    # Sort levels descending (1000 first)
    for base in pressure:
        pressure[base].sort(key=lambda x: x[0], reverse=True)
    return surface, pressure, constants


def plot_scatter_map(ax, lons, lats, values, title, cmap="RdBu_r"):
    """Plot values on a lat/lon map using triangulated contour fill."""
    from matplotlib.tri import Triangulation

    vmin, vmax = np.nanmin(values), np.nanmax(values)

    # Uniform field: tricontourf can't render it, use a solid color fill instead
    if vmin == vmax or (vmax - vmin) < 1e-12 * max(abs(vmin), 1):
        ax.set_facecolor(plt.get_cmap(cmap)(0.5))
        ax.set_xlim(0, 360)
        ax.set_ylim(-90, 90)
        ax.set_aspect("auto")
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        val_str = f"constant value = {vmin:.6f}"
        ax.text(0.5, 0.5, val_str, transform=ax.transAxes, ha="center", va="center",
                fontsize=14, bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))
        return

    # Use tricontourf for smooth filled contours on unstructured grids
    tri = Triangulation(lons, lats)
    tcf = ax.tricontourf(tri, values, levels=64, cmap=cmap, vmin=vmin, vmax=vmax)
    plt.colorbar(tcf, ax=ax, shrink=0.8)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_xlim(0, 360)
    ax.set_ylim(-90, 90)
    ax.set_aspect("auto")

    stats = f"min={np.nanmin(values):.2e}, mean={np.nanmean(values):.2e}, max={np.nanmax(values):.2e}"
    ax.text(0.02, 0.98, stats, transform=ax.transAxes, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8), fontsize=7)


def plot_variable(ds, var_idx, var_name, timestep, lats, lons, output_path):
    """Plot a single variable."""
    values = ds[timestep, var_idx, 0, :]
    fig, ax = plt.subplots(figsize=(12, 5))
    date_str = str(ds.dates[timestep])[:19]
    plot_scatter_map(ax, lons, lats, values, f"{var_name}  —  {date_str}")
    plt.tight_layout()
    plt.savefig(output_path / f"{var_name}.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_pressure_levels(ds, base_var, levels_list, timestep, lats, lons, output_path, var_index):
    """Plot all pressure levels for one variable."""
    n = len(levels_list)
    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4.5 * nrows))
    if n == 1:
        axes = np.array([axes])
    axes = np.asarray(axes).flatten()

    date_str = str(ds.dates[timestep])[:19]
    for idx, (level, var_name) in enumerate(levels_list):
        vi = var_index[var_name]
        values = ds[timestep, vi, 0, :]
        plot_scatter_map(axes[idx], lons, lats, values, f"{level} hPa")

    for idx in range(n, len(axes)):
        axes[idx].axis("off")

    fig.suptitle(f"{base_var} — Pressure Levels\n{date_str}", fontsize=13, fontweight="bold", y=1.00)
    plt.tight_layout()
    plt.savefig(output_path / f"{base_var}_all_levels.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_all(zarr_path, timestep=0, output_dir="output_plots"):
    ds, lats, lons = load_dataset(zarr_path)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    variables = list(ds.variables)
    var_index = {v: i for i, v in enumerate(variables)}
    surface, pressure, constants = categorize_variables(variables)

    logger.info("Surface: %d, Pressure sets: %d, Constants: %d", len(surface), len(pressure), len(constants))

    for var in surface:
        logger.info("  Plotting %s", var)
        plot_variable(ds, var_index[var], var, timestep, lats, lons, output_path)

    for base_var, levels_list in pressure.items():
        logger.info("  Plotting %s (%d levels)", base_var, len(levels_list))
        plot_pressure_levels(ds, base_var, levels_list, timestep, lats, lons, output_path, var_index)

    for var in constants:
        logger.info("  Plotting %s", var)
        plot_variable(ds, var_index[var], var, timestep, lats, lons, output_path)

    logger.info("All plots saved to %s/ (%d files)", output_dir, len(surface) + len(pressure) + len(constants))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot all variables from an anemoi zarr dataset")
    parser.add_argument("zarr_path", help="Path to the zarr dataset")
    parser.add_argument("--timestep", type=int, default=0, help="Timestep index to plot (default: 0)")
    parser.add_argument("--output-dir", default="output_plots", help="Output directory for plots")
    args = parser.parse_args()
    plot_all(args.zarr_path, timestep=args.timestep, output_dir=args.output_dir)
