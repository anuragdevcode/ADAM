"""ADAM CLI entry point.

The CLI is implemented as a package at adam/cli/ (H5 – module splitting).
This file exists solely to satisfy the pyproject.toml entry-point:
    adam = "adam.cli:cli"

All command groups are defined in adam/cli/_<group>.py sub-modules and
registered via adam/cli/__init__.py.
"""

# Re-export the assembled `cli` group so that `adam.cli:cli` continues to work
# as the setuptools console_scripts entry point.
from adam.cli import cli  # noqa: F401

if __name__ == "__main__":
    cli()
