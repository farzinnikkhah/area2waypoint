"""Setup for area2waypoint - supports both pip install . and pip install -e ."""

from setuptools import setup, find_packages


setup(
    name="area2waypoint",
    version="0.1.0",
    description="Convert area mission KMZ to waypoint KMZ for DJI Pilot 2",
    python_requires=">=3.6",
    packages=find_packages(),
    entry_points={"console_scripts": ["area2waypoint = src.cli:main"]},
)
