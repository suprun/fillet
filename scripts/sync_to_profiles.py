# -*- coding: utf-8 -*-
import os
import shutil
import zipfile

appdata = os.environ.get("APPDATA", "")
zip_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist", "fillet.zip"))

for qgis_ver in ["QGIS3", "QGIS4"]:
    target_plugins = os.path.join(appdata, "QGIS", qgis_ver, "profiles", "default", "python", "plugins")
    os.makedirs(target_plugins, exist_ok=True)
    dest = os.path.join(target_plugins, "fillet")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_plugins)
    print(f"Synchronized {qgis_ver} -> {dest}")
