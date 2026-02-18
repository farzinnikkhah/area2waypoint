# GitHub Upload Guide

## Files included (converter only)

These are the only files that will be committed:

```
.gitignore
GITHUB_UPLOAD.md
README.md
pyproject.toml
requirements.txt
setup.py
src/__init__.py
src/cli.py
src/wpml/__init__.py
src/wpml/build.py
src/wpml/compute.py
src/wpml/parse.py
tests/fixtures/area_minimal.kmz
tests/fixtures/area_minimal.wpml
tests/fixtures/area_minimal_template.kml
tests/test_area2waypoint.py
```

## Steps to upload

1. **Create repo on GitHub**: New repository named `area2waypoint` (or your choice). Do not add a README.

2. **Initialize and push**:
   ```bash
   cd /scratch/kgc2mj/NewComp
   git init
   git add .
   git status    # Should show only the 17 files above
   git commit -m "Initial commit: Area mission to waypoint converter"
   git branch -M main
   git remote add origin https://github.com/farzinnikkhah/area2waypoint.git
   git push -u origin main
   ```

3. **Replace `YOUR_USERNAME`** in the remote URL and in `README.md` (clone URL) with your GitHub username.

4. **Optional**: Add a `LICENSE` file (e.g. MIT).
