# -*- coding: utf-8 -*-
"""Build a deterministic runtime-only QGIS plugin archive."""

from pathlib import Path
import zipfile


PLUGIN_DIR_NAME = "fillet"
RUNTIME_FILES = (
    "__init__.py",
    "plugin.py",
    "metadata.txt",
    "README.md",
    "LICENSE",
    "icon.png",
    "icon.svg",
    "core/__init__.py",
    "core/constants.py",
    "core/geometry_engine.py",
    "core/snapping_helper.py",
    "gui/__init__.py",
    "gui/array_canvas_widget.py",
    "gui/array_map_tool.py",
    "gui/canvas_widget.py",
    "gui/clean_duplicate_nodes_map_tool.py",
    "gui/divide_line_canvas_widget.py",
    "gui/divide_line_map_tool.py",
    "gui/edge_offset_canvas_widget.py",
    "gui/edge_offset_map_tool.py",
    "gui/explode_canvas_widget.py",
    "gui/explode_map_tool.py",
    "gui/gui_utils.py",
    "gui/map_tool.py",
    "gui/mirror_canvas_widget.py",
    "gui/mirror_map_tool.py",
    "gui/ortho_angles_canvas_widget.py",
    "gui/ortho_angles_map_tool.py",
    "gui/polar_array_canvas_widget.py",
    "gui/polar_array_map_tool.py",
    "gui/restore_canvas_widget.py",
    "gui/restore_map_tool.py",
    "gui/rotate_map_tool.py",
    "gui/rotation_canvas_widget.py",
    "gui/scale_rotate_canvas_widget.py",
    "gui/scale_rotate_map_tool.py",
    "gui/settings_widget.py",
    "gui/two_line_map_tool.py",
    "resources/icons/chamfer.svg",
    "resources/icons/fillet.svg",
    "resources/icons/locked.svg",
    "resources/icons/mActionChamferFillet.svg",
    "resources/icons/mActionChamferFilletBatch.svg",
    "resources/icons/mActionCleanDuplicateNodes.svg",
    "resources/icons/mActionDivideLine.svg",
    "resources/icons/mActionEdgeOffsetCAD.svg",
    "resources/icons/mActionExplodeLine.svg",
    "resources/icons/mActionFeatureArray.svg",
    "resources/icons/mActionFeatureArrayLine.svg",
    "resources/icons/mActionFeatureArrayPoint.svg",
    "resources/icons/mActionFeatureArrayPolygon.svg",
    "resources/icons/mActionLink.svg",
    "resources/icons/mActionMirrorCAD.svg",
    "resources/icons/mActionOrthoAngles.svg",
    "resources/icons/mActionPolarArray.svg",
    "resources/icons/mActionRestoreCorners.svg",
    "resources/icons/mActionRotateCAD.svg",
    "resources/icons/mActionScaleRotateCAD.svg",
    "resources/icons/mActionTwoLineFillet.svg",
    "resources/icons/mActionUnlink.svg",
    "resources/icons/unlocked.svg",
)
TRANSLATION_LOCALES = (
    "ar", "bg", "ca", "cs", "da", "de", "el", "en", "es", "et",
    "eu", "fi", "fr", "gl", "hi", "hr", "hu", "id", "it", "ja",
    "ko", "lt", "lv", "nb", "nl", "pl", "pt", "pt_BR", "ro", "sk",
    "sl", "sr", "sv", "th", "tr", "uk", "vi", "zh", "zh_CN", "zh_TW",
)


def runtime_paths(root_dir: Path):
    """Return the explicit, sorted set of files required at plugin runtime."""
    paths = []
    for relative_path in RUNTIME_FILES:
        path = root_dir / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Missing runtime file: {relative_path}")
        paths.append(path)

    for locale in TRANSLATION_LOCALES:
        path = root_dir / "i18n" / f"fillet_{locale}.qm"
        if not path.is_file():
            raise FileNotFoundError(f"Missing translation: {path.name}")
        paths.append(path)

    unique_paths = sorted(set(paths), key=lambda path: path.as_posix().lower())
    for path in unique_paths:
        if path.is_symlink():
            raise RuntimeError(f"Symlinks are not allowed in the package: {path}")
    return unique_paths


def package_plugin():
    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = root_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dist_dir / "fillet.zip"

    files = runtime_paths(root_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative_path = path.relative_to(root_dir).as_posix()
            archive.write(path, f"{PLUGIN_DIR_NAME}/{relative_path}")

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("Package contains duplicate paths")
        if not names or any(
            not name.startswith(f"{PLUGIN_DIR_NAME}/") for name in names
        ):
            raise RuntimeError("Package must contain exactly one fillet/ root")

    print(f"Created package: {zip_path} ({len(files)} runtime files)")


if __name__ == "__main__":
    package_plugin()
