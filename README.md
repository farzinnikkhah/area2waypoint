# Area Mission to Waypoint Converter

Convert DJI area mission KMZ files (from Pilot 2) into waypoint mission KMZ files for use in DJI Pilot 2. Extracts shot points from `multipleDistance` triggers and outputs waypoint missions with `orientedShoot` actions.

## Features

- **Ortho and oblique routes**: Extracts all routes from area missions (ortho at -90° gimbal, oblique at -40° or custom)
- **Shot point computation**: Uses `multipleDistance` + `takePhoto` action groups to place waypoints along the path
- **DJI Pilot 2 compatible**: Outputs KMZ with correct `template.kml` and `waylines.wpml` format
- **Split or combined output**: One KMZ with all routes, or `--split-routes` for separate files per route

## Requirements

- Python 3.6+
- No external dependencies (uses stdlib only)

## Installation

### Option 1: From source (recommended)

```bash
git clone https://github.com/farzinnikkhah/area2waypoint.git
cd area2waypoint
pip install .
```

For systems where you don’t have write access to system Python:

```bash
pip install --user .
# or use a virtual environment:
python -m venv venv && source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate   # Windows
pip install .
```

### Option 2: Run without installing

```bash
python -m src.cli --help
```

## Usage

### Basic conversion

```bash
area2waypoint area_mission.kmz
# Output: area_mission_waypoints.kmz
```

### Specify output path

```bash
area2waypoint area_mission.kmz -o output.kmz
```

### Split routes (recommended for Pilot 2)

Pilot 2 may only display the first route when importing a combined file. Use `--split-routes` to write one KMZ per route:

```bash
area2waypoint area_mission.kmz --split-routes
# Output: area_mission_ortho.kmz, area_mission_oblique1.kmz, ...
```

### Override shot points from CSV

```bash
area2waypoint area_mission.kmz --metadata-csv shots.csv
```

CSV columns: `lat`, `lon`, `rel_alt` (or `alt`), `gimbal_pitch`, `gimbal_yaw`, `flight_yaw` (or `heading`)

### Lens and focal length

```bash
area2waypoint area_mission.kmz --lens "ir,wide,zoom" --focal-length 48
```

## Options

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Output KMZ path (default: `input_waypoints.kmz`) |
| `--split-routes` | Write one KMZ per route (ortho, oblique1, oblique2, ...) |
| `--metadata-csv` | Override shot positions from CSV |
| `--lens` | Payload lens list (default: `ir,wide,zoom`) |
| `--focal-length` | Focal length for orientedShoot (default: 48) |

## Input format

Expects a DJI area mission KMZ containing `wpmz/waylines.wpml` with:

- Multiple `Folder` elements (ortho = waylineId 0, oblique = waylineId 1+)
- Path waypoints (`Placemark` with `Point`/`coordinates`)
- Action groups with `multipleDistance` trigger and `takePhoto` (+ `gimbalRotate`)

## Output format

Produces KMZ with:

- `wpmz/template.kml` – waypoint template
- `wpmz/waylines.wpml` – executable waylines with `orientedShoot` at each shot point

Import the KMZ into DJI Pilot 2 via **Flight Route → Import Route (KMZ/KML)**.

## Project structure

```
area2waypoint/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Entry point
│   └── wpml/
│       ├── __init__.py
│       ├── parse.py        # Parse area waylines.wpml
│       ├── compute.py      # Shot points from multipleDistance
│       └── build.py        # Build waypoint KMZ
├── tests/
│   ├── test_area2waypoint.py
│   └── fixtures/
│       └── area_minimal.kmz
├── pyproject.toml
├── setup.py
├── requirements.txt
└── README.md
```

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

## Uploading to GitHub

1. **Create a new repository** on GitHub (e.g. `area2waypoint`). Do not initialize with a README if you already have one locally.

2. **Initialize git and push** from your project directory:

```bash
cd /path/to/your/converter/project
git init
git add .
git status   # Verify only converter files are staged (no thermal_alignment, odm_project, etc.)
git commit -m "Initial commit: Area mission to waypoint converter"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/area2waypoint.git
git push -u origin main
```

3. **Update the clone URL** in this README: replace `YOUR_USERNAME` with your GitHub username in the `git clone` URL.

4. **Optional**: Add a LICENSE file (e.g. MIT).

## License

MIT (or your chosen license)
