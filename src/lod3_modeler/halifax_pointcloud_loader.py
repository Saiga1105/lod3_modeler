"""Helpers for selecting and downloading CanElevation point-cloud tiles."""

from __future__ import annotations

import csv
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import shapefile
from pyproj import CRS, Transformer
from shapely import from_wkb


CAN_ELEVATION_TILE_INDEX_URL = (
    "s3://canelevation-lidar-point-clouds/pointclouds_nuagespoints/"
    "Index_LiDARtiles_tuileslidar.zip"
)


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned bounds as minx, miny, maxx, maxy."""

    minx: float
    miny: float
    maxx: float
    maxy: float

    def intersects(self, other: "Bounds") -> bool:
        return not (
            self.maxx < other.minx
            or self.minx > other.maxx
            or self.maxy < other.miny
            or self.miny > other.maxy
        )

    def padded(self, amount: float) -> "Bounds":
        return Bounds(
            self.minx - amount,
            self.miny - amount,
            self.maxx + amount,
            self.maxy + amount,
        )


@dataclass(frozen=True)
class TileRecord:
    provider: str
    project: str
    tile_name: str
    url: str
    bounds: Bounds

    @property
    def s3_uri(self) -> str:
        if self.url.startswith("https://canelevation-lidar-point-clouds.s3.ca-central-1.amazonaws.com/"):
            key = self.url.split(".amazonaws.com/", 1)[1]
            return f"s3://canelevation-lidar-point-clouds/{key}"
        return self.url


def footprint_bounds(gpkg_path: str | Path, table: str | None = None) -> tuple[Bounds, int, int]:
    """Return bounds, feature count, and CRS EPSG code for a GeoPackage feature table."""

    gpkg_path = Path(gpkg_path)
    with sqlite3.connect(gpkg_path) as con:
        if table is None:
            table = con.execute(
                "select table_name from gpkg_contents where data_type = 'features' limit 1"
            ).fetchone()[0]
        geom_column, srs_id = con.execute(
            "select column_name, srs_id from gpkg_geometry_columns where table_name = ?",
            (table,),
        ).fetchone()
        feature_count = con.execute(f'select count(*) from "{table}"').fetchone()[0]

        bounds: Bounds | None = None
        for (blob,) in con.execute(f'select "{geom_column}" from "{table}" where "{geom_column}" is not null'):
            geom_bounds = _geopackage_binary_bounds(blob)
            bounds = geom_bounds if bounds is None else _merge_bounds(bounds, geom_bounds)

    if bounds is None:
        raise ValueError(f"No geometries found in {gpkg_path}")
    return bounds, feature_count, int(srs_id)


def transform_bounds(bounds: Bounds, source_epsg: int, target_epsg: int = 4326) -> Bounds:
    """Transform bounds between CRSs, densifying edges enough for area queries."""

    transformer = Transformer.from_crs(
        CRS.from_epsg(source_epsg),
        CRS.from_epsg(target_epsg),
        always_xy=True,
    )
    points = []
    steps = 16
    for i in range(steps + 1):
        t = i / steps
        x = bounds.minx + (bounds.maxx - bounds.minx) * t
        y = bounds.miny + (bounds.maxy - bounds.miny) * t
        points.extend(
            [
                transformer.transform(x, bounds.miny),
                transformer.transform(x, bounds.maxy),
                transformer.transform(bounds.minx, y),
                transformer.transform(bounds.maxx, y),
            ]
        )
    xs, ys = zip(*points)
    return Bounds(min(xs), min(ys), max(xs), max(ys))


def lonlat_bounds_around_point(lon: float, lat: float, radius_m: float) -> Bounds:
    """Return lon/lat bounds around a WGS84 point using a local azimuthal projection."""

    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"
    )
    to_local = Transformer.from_crs(CRS.from_epsg(4326), local_crs, always_xy=True)
    to_lonlat = Transformer.from_crs(local_crs, CRS.from_epsg(4326), always_xy=True)
    center_x, center_y = to_local.transform(lon, lat)
    local_bounds = Bounds(
        center_x - radius_m,
        center_y - radius_m,
        center_x + radius_m,
        center_y + radius_m,
    )
    return transform_bounds_with_transformer(local_bounds, to_lonlat)


def transform_bounds_with_transformer(bounds: Bounds, transformer: Transformer) -> Bounds:
    """Transform bounds with an existing transformer, densifying edges."""

    points = []
    steps = 16
    for i in range(steps + 1):
        t = i / steps
        x = bounds.minx + (bounds.maxx - bounds.minx) * t
        y = bounds.miny + (bounds.maxy - bounds.miny) * t
        points.extend(
            [
                transformer.transform(x, bounds.miny),
                transformer.transform(x, bounds.maxy),
                transformer.transform(bounds.minx, y),
                transformer.transform(bounds.maxx, y),
            ]
        )
    xs, ys = zip(*points)
    return Bounds(min(xs), min(ys), max(xs), max(ys))


def find_tiles_for_bounds(
    tile_index_shp: str | Path,
    bounds_lonlat: Bounds,
    providers: Sequence[str] | None = None,
    projects: Sequence[str] | None = None,
) -> list[TileRecord]:
    """Find tile-index polygons whose bounding boxes intersect ``bounds_lonlat``."""

    provider_filter = {value.lower() for value in providers} if providers else None
    project_filter = {value.lower() for value in projects} if projects else None

    records: list[TileRecord] = []
    reader = shapefile.Reader(str(tile_index_shp))
    for shape_record in reader.iterShapeRecords():
        data = shape_record.record.as_dict()
        provider = data["Provider"]
        project = data["Project"]
        if provider_filter and provider.lower() not in provider_filter:
            continue
        if project_filter and project.lower() not in project_filter:
            continue

        bbox = shape_record.shape.bbox
        tile_bounds = Bounds(bbox[0], bbox[1], bbox[2], bbox[3])
        if not tile_bounds.intersects(bounds_lonlat):
            continue

        records.append(
            TileRecord(
                provider=provider,
                project=project,
                tile_name=data["Tile_name"],
                url=data["URL"],
                bounds=tile_bounds,
            )
        )
    return records


def write_tile_manifest(records: Iterable[TileRecord], output_csv: str | Path) -> None:
    """Write selected tile metadata to CSV."""

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "provider",
                "project",
                "tile_name",
                "url",
                "s3_uri",
                "min_lon",
                "min_lat",
                "max_lon",
                "max_lat",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "provider": record.provider,
                    "project": record.project,
                    "tile_name": record.tile_name,
                    "url": record.url,
                    "s3_uri": record.s3_uri,
                    "min_lon": record.bounds.minx,
                    "min_lat": record.bounds.miny,
                    "max_lon": record.bounds.maxx,
                    "max_lat": record.bounds.maxy,
                }
            )


def deduplicate_tiles(
    records: Iterable[TileRecord],
    preferred_projects: Sequence[str] | None = None,
    center_lonlat: tuple[float, float] | None = None,
) -> list[TileRecord]:
    """Deduplicate records by tile name.

    If ``center_lonlat`` is provided, records whose bounds contain the center
    are preferred over same-named records that only intersect the search area.
    This matters near the coast, where Coastal and Inland projects can publish
    same-named partial tiles with different footprints.
    """

    project_rank = {
        project.lower(): rank
        for rank, project in enumerate(preferred_projects or [])
    }
    default_rank = len(project_rank)

    selected: dict[str, TileRecord] = {}
    for record in records:
        existing = selected.get(record.tile_name)
        if existing is None:
            selected[record.tile_name] = record
            continue

        if _tile_sort_key(record, project_rank, default_rank, center_lonlat) < _tile_sort_key(
            existing,
            project_rank,
            default_rank,
            center_lonlat,
        ):
            selected[record.tile_name] = record

    return sorted(selected.values(), key=lambda tile: tile.tile_name)


def _tile_sort_key(
    record: TileRecord,
    project_rank: dict[str, int],
    default_rank: int,
    center_lonlat: tuple[float, float] | None,
) -> tuple[int, float, int]:
    contains_center = 1
    if center_lonlat is not None:
        lon, lat = center_lonlat
        if record.bounds.minx <= lon <= record.bounds.maxx and record.bounds.miny <= lat <= record.bounds.maxy:
            contains_center = 0

    area = (record.bounds.maxx - record.bounds.minx) * (record.bounds.maxy - record.bounds.miny)
    project_preference = project_rank.get(record.project.lower(), default_rank)
    return (contains_center, -area, project_preference)


def _merge_bounds(left: Bounds, right: Bounds) -> Bounds:
    return Bounds(
        min(left.minx, right.minx),
        min(left.miny, right.miny),
        max(left.maxx, right.maxx),
        max(left.maxy, right.maxy),
    )


def _geopackage_binary_bounds(blob: bytes) -> Bounds:
    """Extract the envelope from a GeoPackage geometry blob."""

    if blob[:2] != b"GP":
        raise ValueError("Geometry is not GeoPackage binary")

    flags = blob[3]
    byte_order = "<" if flags & 1 else ">"
    envelope_type = (flags >> 1) & 0b111
    if envelope_type == 0:
        geometry = from_wkb(blob[8:])
        minx, miny, maxx, maxy = geometry.bounds
        return Bounds(minx, miny, maxx, maxy)

    envelope_lengths = {
        1: 4,
        2: 6,
        3: 6,
        4: 8,
    }
    value_count = envelope_lengths[envelope_type]
    values = struct.unpack(f"{byte_order}{value_count}d", blob[8 : 8 + value_count * 8])
    minx, maxx, miny, maxy = values[:4]
    return Bounds(minx, miny, maxx, maxy)
