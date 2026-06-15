# Halifax Point-Cloud Download Workflow

This document describes how to identify and download CanElevation LiDAR point-cloud tiles for the Halifax city-core study area.

## Data Sources

CanElevation public S3 bucket:

```powershell
s3://canelevation-lidar-point-clouds/pointclouds_nuagespoints/
```

The bucket is public, but AWS CLI commands must use:

```powershell
--no-sign-request
```

Local project inputs used in this workflow:

```text
data/input/halifax_footprints/Buildings_1792650129607592726.gpkg
data/input/canelevation_index/Index_LiDARtiles_tuileslidar.shp
```

The Halifax footprints GeoPackage covers a broad Halifax municipal/county area. Using the full footprint extent selects thousands of tiles, so the working area should be selected from a specific project coordinate or buffered area.

## Download the CanElevation Tile Index

The tile index is a shapefile distributed as a zip file.

```powershell
New-Item -ItemType Directory -Force -Path data\input\canelevation_index | Out-Null

& 'C:\Program Files\Amazon\AWSCLIV2\aws.exe' s3 cp `
  --no-sign-request `
  s3://canelevation-lidar-point-clouds/pointclouds_nuagespoints/Index_LiDARtiles_tuileslidar.zip `
  data\input\canelevation_index\Index_LiDARtiles_tuileslidar.zip

Expand-Archive `
  -LiteralPath data\input\canelevation_index\Index_LiDARtiles_tuileslidar.zip `
  -DestinationPath data\input\canelevation_index `
  -Force
```

## Identify Candidate Tiles

The helper module is:

```text
src/lod3_modeler/halifax_pointcloud_loader.py
```

It can:

- Read footprint extents from a GeoPackage.
- Transform bounds between coordinate reference systems.
- Search the CanElevation tile index.
- Deduplicate overlapping Coastal/Inland project tiles.
- Write CSV manifests with ready-to-use S3 URIs.

For the current target area, the project coordinate is in Web Mercator:

```text
EPSG:3857 x: -7077485.33
EPSG:3857 y:  5564996.32
WGS84 lon:    -63.57813245
WGS84 lat:     44.63982441
COPC CRS:      EPSG:2961, NAD83(CSRS) / UTM zone 20N
COPC easting:  454149.58
COPC northing: 4943102.24
```

Generated manifests are stored locally in:

```text
data/input/halifax_lidar/
```

Two tile-selection options were created around this coordinate:

```text
data/input/halifax_lidar/target_-7077485_5564996/direct_1km_recommended_tiles.csv
data/input/halifax_lidar/target_-7077485_5564996/area_2km_recommended_tiles.csv
```

The smaller direct option uses a 1 km radius and contains 6 unique COPC LAZ tiles. The broader 2 km option contains 16 unique COPC LAZ tiles. Same-named Coastal/Inland records are deduplicated by preferring the footprint that contains the target center point, then the larger intersecting footprint. This avoids selecting small Coastal slivers when the actual target point is in an Inland tile.

## Download the Smaller Direct Tile Option

Run this from the repository root:

```powershell
$manifest = 'data\input\halifax_lidar\target_-7077485_5564996\direct_1km_recommended_tiles.csv'
$destination = 'data\input\halifax_lidar\target_-7077485_5564996\direct_1km_tiles'
$aws = 'C:\Program Files\Amazon\AWSCLIV2\aws.exe'

New-Item -ItemType Directory -Force -Path $destination | Out-Null

Import-Csv $manifest | ForEach-Object {
    $fileName = "$($_.tile_name).copc.laz"
    $target = Join-Path $destination $fileName

    if (Test-Path -LiteralPath $target) {
        Write-Host "Skipping existing $fileName"
    } else {
        Write-Host "Downloading $fileName"
        & $aws s3 cp --no-sign-request $_.s3_uri $target
        if ($LASTEXITCODE -ne 0) {
            throw "Download failed for $fileName"
        }
    }
}
```

## Verify the Download

```powershell
Get-ChildItem -File data\input\halifax_lidar\target_-7077485_5564996\direct_1km_tiles\*.copc.laz |
  Measure-Object -Property Length -Sum |
  Select-Object Count,Sum
```

Expected result for the current direct 1 km set:

```text
Count: 6
Total size: 386,290,051 bytes
```

## Current Direct 1 km Tile Set

```text
CG11153_2018_PointCloud_CGVD2013.copc.laz
CG11154_2018_PointCloud_CGVD2013.copc.laz
CG11155_2018_PointCloud_CGVD2013.copc.laz
CG11237_2018_PointCloud_CGVD2013.copc.laz
CG11238_2018_PointCloud_CGVD2013.copc.laz
CG11239_2018_PointCloud_CGVD2013.copc.laz
```

The target point falls inside `CG11238_2018_PointCloud_CGVD2013.copc.laz`. In the COPC CRS, the target is approximately 500 m from that tile center.

## Broader 2 km Option

Use this manifest if the full 2 km range around the same target coordinate is needed:

```text
data/input/halifax_lidar/target_-7077485_5564996/area_2km_recommended_tiles.csv
```

It contains 16 unique tiles:

```text
CG11073_2018_PointCloud_CGVD2013.copc.laz
CG11074_2018_PointCloud_CGVD2013.copc.laz
CG11075_2018_PointCloud_CGVD2013.copc.laz
CG11076_2018_PointCloud_CGVD2013.copc.laz
CG11153_2018_PointCloud_CGVD2013.copc.laz
CG11154_2018_PointCloud_CGVD2013.copc.laz
CG11155_2018_PointCloud_CGVD2013.copc.laz
CG11156_2018_PointCloud_CGVD2013.copc.laz
CG11237_2018_PointCloud_CGVD2013.copc.laz
CG11238_2018_PointCloud_CGVD2013.copc.laz
CG11239_2018_PointCloud_CGVD2013.copc.laz
CG11240_2018_PointCloud_CGVD2013.copc.laz
CG11332_2018_PointCloud_CGVD2013.copc.laz
CG11333_2018_PointCloud_CGVD2013.copc.laz
CG11334_2018_PointCloud_CGVD2013.copc.laz
CG11335_2018_PointCloud_CGVD2013.copc.laz
```

## Git Policy

Point-cloud files, tile indexes, and manifests in `data/input/` are local data artifacts and are intentionally ignored by Git. Commit the code and documentation only.
