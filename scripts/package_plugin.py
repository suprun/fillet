# -*- coding: utf-8 -*-
"""
Helper script to package the QGIS plugin cleanly according to repository rules.
"""

import os
import zipfile

IGNORED_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".zip", ".log", ".swp", ".swo", ".db"}
IGNORED_DIRS = {"__pycache__", ".git", ".idea", ".vscode", ".venv", "venv", "dist", "build", "tests", "scratch", "scripts"}
IGNORED_FILES = {"AGENTS.md", "desktop.ini", "Thumbs.db", ".DS_Store"}


def package_plugin():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(root_dir, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    zip_path = os.path.join(dist_dir, "fillet.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(root_dir):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in IGNORED_EXTENSIONS or file.startswith(".") or file in IGNORED_FILES:
                    continue

                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, root_dir)
                # Put inside plugin folder in zip
                archive_path = os.path.join("fillet", rel_path)
                zf.write(abs_path, archive_path)

    print(f"Created package: {zip_path}")


if __name__ == "__main__":
    package_plugin()
