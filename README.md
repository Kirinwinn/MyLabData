# MyLabData

MyLabData, a Flask-based laboratory molecular data management and analysis platform for uniformly browsing, retrieving, and comparing **wet lab** (Wet) and **dry lab** (Dry) molecular data. It supports online file previews, 44-feature molecular property distributions, AI prediction results, and multi-batch experimental comparisons, all within a single interface.

## Installation

Firstly clone the repo and into the directory

```bash
git clone https://github.com/Kirinwinn/MyLabData.git
cd MyLabData
conda env create -f environment.yml
```

## Usage

Activate the environment and launch the web server

```bash
conda activate MyLabData
python MyLabData/launch.py
```

The application will be available at:

```
http://127.0.0.1:8501
```

## Data Organization

### Dry Data

A data root directory is required (configured via `DRY_DATA_ROOT`), containing the following subdirectories:

```text
{DRY_DATA_ROOT}/
├── Separate/                # SMILES list — one Parquet file per batch
│   └── {BatchCode}.parquet  #   Must contain a SMILES column
├── Property/                # Molecular properties — one Parquet file per batch
│   └── {BatchCode}.parquet  #   Contains 44 feature columns + SMILES column
└── Prediction/              # AI prediction data
    └── {Model}/             #   One directory per model (e.g., Proby, Tox21)
        ├── {BatchCode}/     #     Raw data directory (xlsx or csv)
        └── {BatchCode}.parquet  # Normalized Parquet output
```

Please place raw prediction results into `{Model}/{BatchCode}/` and run `Supporting/Prediction_Normalize.ipynb` to normalize them into Parquet files at the same directory level.

### Wet Data

An experimental data root directory is required (configured via `WET_DATA_ROOT`):

```text
{WET_DATA_ROOT}/
└── {Molecule}/
    └── {ExpType}/           # solventscom / fluostable / uvstable / mtt / e / selectivei
        └── {Batch}/
            ├── RData/       # Raw data (CSV / XLSX / SPC, etc.)
            ├── PData/       # Processed data
            └── SData/       # Auxiliary info (Markdown, images, etc.)
```

The Wet pipeline automatically scans and indexes into `Wet.db` on first Refresh. For naming conventions, refer to the Wet Lab Naming Conventions document.

## Modes

### Wet Section

| Mode | Description |
|------|-------------|
| `ViewMode` | Select molecule → experiment type → browse batches and preview files (CSV, XLSX, Markdown, images, SPC) |
| `CompareMode` | Aggregate multi-batch data; analyze solvent comparisons, stability trends, MTT results via interactive ECharts |

### Dry Section

| Mode | Description |
|------|-------------|
| `ViewMode` | Select batch → view 44-property distribution histograms → click a bin to browse molecules in that range |
| `SearchMode` | Select batches → define property filter conditions → view filtered distribution → download results as ZIP |
| `CompareMode` | Search by LabID or SMILES → full molecular profile (44 properties + model predictions) → download package (CSV + 2D SVG + 3D SDF) |
| `Prediction` | Browse prediction result distributions by model and solvent using interactive histograms |

## Structure

```
MyLabData/
├── App/
│   ├── app.py              # Router
│   ├── templates/          # Interface
│   └── static/
├── Database/
│   ├── Wet/                # Wet database pipeline
│   ├── Dry/                # Dry database pipeline
│   └── Tools/              # Supporting tools (prediction normalization, etc.)
├── Search/
│   ├── Wet_ViewMode.py
│   ├── Wet_CompareMode.py
│   ├── Dry_ViewMode.py
│   ├── Dry_CompareMode.py
│   ├── Dry_SearchMode.py
│   └── Dry_Prediction.py
├── Supporting/
│   ├── structures/         # Cached 2D structure SVGs
│   └── specs/              # Naming convention documents
└── launch.py               # Web server launcher
```

## Acknowledgements

MyLabData is based on the following open-source libraries and tools and we sincerely thank all the creators:

(1)[Flask](https://github.com/pallets/flask) — web application framework

(2)[pandas](https://github.com/pandas-dev/pandas) — data manipulation and analysis

(3)[NumPy](https://github.com/numpy/numpy) — numerical computing

(4)[Apache Arrow / PyArrow](https://github.com/apache/arrow) — columnar data format and Parquet I/O

(5)[RDKit](https://www.rdkit.org/) — chemical informatics and molecular structure rendering

(6)[Bootstrap](https://github.com/twbs/bootstrap) — frontend UI framework

(7)[ECharts](https://github.com/apache/echarts) — interactive charting and visualization

(8)[3Dmol.js](https://github.com/3dmol/3Dmol.js) — 3D molecular visualization in the browser

(9)[Font Awesome](https://github.com/FortAwesome/Font-Awesome) — icon library

(10)[tqdm](https://github.com/tqdm/tqdm) — progress bars for pipeline processing

(11)[Python-Markdown](https://github.com/Python-Markdown/markdown) — Markdown rendering

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).  
For full terms, please refer to the [LICENSE](LICENSE) file.
