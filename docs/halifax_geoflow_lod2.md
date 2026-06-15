# Halifax Geoflow LoD2 Reconstruction

This note records the local Geoflow setup for reconstructing LoD2.2 buildings from the Halifax footprints and point clouds.

## Inputs

Footprints are in:

```text
data/input/halifax_footprints/
```

Per-building point clouds are in:

```text
data/input/halifax_lidar/
```

Examples:

```text
data/input/halifax_footprints/victorian_joined_2961.gpkg
data/input/halifax_lidar/victorian.las
```

Both should be in the same horizontal CRS as the point clouds, `EPSG:2961` / `NAD83(CSRS) UTM zone 20N`.

## Flowchart

Use the repo-local patched flowchart:

```text
flowcharts/reconstruct.json
```

Do not rely on the executable's automatic flowchart loading. In our tests, `lod22-reconstruct` automatically loaded:

```text
C:\Program Files\Geoflow\share\geoflow\gfc-brecon\single\reconstruct.json
```

That installed flowchart includes CityJSON metadata parameters such as `meta_poc_address`, but the installed writer node does not expose that parameter, causing:

```text
key not found in node parameters: meta_poc_address
```

The repo-local copy removes those unsupported metadata parameters.

## Command

Run from the repository root:

```powershell
lod22-reconstruct `
  --flowchart=flowcharts/reconstruct.json `
  --input_footprint=data/input/halifax_footprints/victorian_joined_2961.gpkg `
  --input_footprint_select_sql= `
  --input_pointcloud=data/input/halifax_lidar/victorian.las `
  --output_cityjson=data/output/victorian_lod22.city.json `
  --output_obj_lod12=data/output/victorian_lod12.obj `
  --output_obj_lod13=data/output/victorian_lod13.obj `
  --output_obj_lod22=data/output/victorian_lod22.obj
```

Notes:

- Use normal ASCII hyphens in arguments: `--output_obj_lod22`, not `–-output_obj_lod22`.
- The flowchart does not define `output_obj_dir`; it defines explicit OBJ file outputs: `output_obj_lod12`, `output_obj_lod13`, and `output_obj_lod22`.
- If a footprint file contains only one feature, use an empty `input_footprint_select_sql` as shown above. If it contains multiple features, set a valid OGR SQL filter such as `fid=47`.

## Other Samples

Swap the sample names as needed:

```powershell
lod22-reconstruct `
  --flowchart=flowcharts/reconstruct.json `
  --input_footprint=data/input/halifax_footprints/lala_shop_joined_2961.gpkg `
  --input_footprint_select_sql= `
  --input_pointcloud=data/input/halifax_lidar/lala_shop.las `
  --output_cityjson=data/output/lala_shop_lod22.city.json `
  --output_obj_lod12=data/output/lala_shop_lod12.obj `
  --output_obj_lod13=data/output/lala_shop_lod13.obj `
  --output_obj_lod22=data/output/lala_shop_lod22.obj
```

```powershell
lod22-reconstruct `
  --flowchart=flowcharts/reconstruct.json `
  --input_footprint=data/input/halifax_footprints/mary_queen_joined_2961.gpkg `
  --input_footprint_select_sql= `
  --input_pointcloud=data/input/halifax_lidar/mary_queen.las `
  --output_cityjson=data/output/mary_queen_lod22.city.json `
  --output_obj_lod12=data/output/mary_queen_lod12.obj `
  --output_obj_lod13=data/output/mary_queen_lod13.obj `
  --output_obj_lod22=data/output/mary_queen_lod22.obj
```
