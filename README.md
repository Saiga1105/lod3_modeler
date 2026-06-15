# LoD3 Modeler

Research code and notebooks for reconstructing LoD2 buildings and enriching them into LoD3 building models with facade and roof detail.

## Repository Layout

```text
.
|-- src/lod3_modeler/        Python package code
|-- notebooks/               Executable research notebooks
|-- data/input/              Local input datasets, not committed
|-- data/output/             Generated outputs, not committed
|-- docs/context/            Reference screenshots and local background material
```

Large geospatial datasets, generated model output, binary artifacts, reference PDFs, and slide decks are intentionally ignored by Git. Keep them in the folders above on your machine.

## Setup

Create a virtual environment and install the package in editable mode:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Some dependencies, such as `geomapi` or `cityview`, may require project-specific installation steps depending on the environment.

## Notebook

Open `notebooks/building_enrichment.ipynb` from the repository root. The notebook adds `src/` to `sys.path` so it can import the local package during development.

## Proof-of-Concept Documentation

- [Carleton LoD2 proof of concept](docs/carleton_proof_of_concept.md)
- [Halifax point-cloud download workflow](docs/halifax_pointcloud_download.md)
- [Halifax Geoflow LoD2 reconstruction notes](docs/halifax_geoflow_lod2.md)
