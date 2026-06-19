"""Small standalone CityJSON/LAS HTML viewer used by the notebooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go


def _cityjson_vertices(cityjson_data: dict[str, Any]) -> np.ndarray:
    vertices = np.asarray(cityjson_data.get("vertices", []), dtype=float)
    transform = cityjson_data.get("transform")
    if transform and vertices.size:
        scale = np.asarray(transform.get("scale", [1, 1, 1]), dtype=float)
        translate = np.asarray(transform.get("translate", [0, 0, 0]), dtype=float)
        vertices = vertices * scale + translate
    return vertices


def _iter_faces(boundaries: Any):
    if not isinstance(boundaries, list):
        return
    if boundaries and all(isinstance(v, int) for v in boundaries):
        yield boundaries
        return
    for item in boundaries:
        yield from _iter_faces(item)


def _cityjson_mesh(cityjson_data: dict[str, Any]) -> go.Mesh3d | None:
    vertices = _cityjson_vertices(cityjson_data)
    if vertices.size == 0:
        return None

    i: list[int] = []
    j: list[int] = []
    k: list[int] = []
    for city_object in cityjson_data.get("CityObjects", {}).values():
        for geometry in city_object.get("geometry", []):
            for face in _iter_faces(geometry.get("boundaries", [])):
                if len(face) < 3:
                    continue
                for idx in range(1, len(face) - 1):
                    i.append(face[0])
                    j.append(face[idx])
                    k.append(face[idx + 1])

    if not i:
        return None
    return go.Mesh3d(
        x=vertices[:, 0],
        y=vertices[:, 1],
        z=vertices[:, 2],
        i=i,
        j=j,
        k=k,
        name="CityJSON",
        color="lightgray",
        opacity=0.75,
    )


def _sample_pointcloud(path: str | Path | None, max_points: int) -> go.Scatter3d | None:
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None

    import laspy

    las = laspy.read(path)
    count = len(las.x)
    if count == 0:
        return None
    if count > max_points:
        rng = np.random.default_rng(42)
        indices = rng.choice(count, size=max_points, replace=False)
    else:
        indices = np.arange(count)

    return go.Scatter3d(
        x=np.asarray(las.x)[indices],
        y=np.asarray(las.y)[indices],
        z=np.asarray(las.z)[indices],
        mode="markers",
        marker={"size": 1, "opacity": 0.45},
        name=path.name,
    )


def generate_viewer(
    cityjson_data: dict[str, Any] | str | Path,
    als_laz_path: str | Path | None,
    output_path: str | Path,
    mls_laz_path: str | Path | None = None,
    max_pts: int = 150_000,
    pcd_radius: float | None = None,
) -> Path:
    """Write a simple Plotly HTML viewer and return its path.

    Parameters match the historical notebook helper. ``pcd_radius`` is accepted
    for compatibility; point filtering should happen before calling this helper.
    """

    del pcd_radius

    if isinstance(cityjson_data, (str, Path)):
        cityjson_data = json.loads(Path(cityjson_data).read_text(encoding="utf-8"))

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    viewer_path = output_path / "viewer_lod3.html"

    traces = []
    mesh = _cityjson_mesh(cityjson_data)
    if mesh is not None:
        traces.append(mesh)
    for pointcloud_path in (als_laz_path, mls_laz_path):
        cloud = _sample_pointcloud(pointcloud_path, max_pts // 2 if mls_laz_path else max_pts)
        if cloud is not None:
            traces.append(cloud)

    fig = go.Figure(data=traces)
    fig.update_layout(
        title="LoD3 CityJSON Viewer",
        scene={"aspectmode": "data"},
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )
    fig.write_html(viewer_path, include_plotlyjs="cdn")
    return viewer_path
