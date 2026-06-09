# LoD3 Modeler

Research code and notebooks for enriching LoD2.2 building models into LoD3 building models with facade and roof detail.

## Repository Layout

```text
.
|-- src/lod3_modeler/        Python package code
|-- notebooks/               Executable research notebooks
|-- data/input/              Local input datasets, not committed
|-- data/output/             Generated outputs, not committed
|-- docs/context/            Local reference material, not committed
```

Large geospatial datasets, generated model output, binary artifacts, and reference PDFs are intentionally ignored by Git. Keep them in the folders above on your machine.

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
