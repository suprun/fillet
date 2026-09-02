import argparse
import glob
import os
import subprocess
import sys

# List of test files to run
TEST_FILES = [
    "tests/test_geometry.py",
    "tests/test_plugin_lifecycle.py",
    "tests/test_translations.py",
    "tests/test_settings_persistence.py",
    "tests/test_two_line_fillet.py",
]

def find_windows_qgis_python_executables():
    """Find installed Windows QGIS Python launchers."""
    found = []
    if os.name != "nt":
        return found
    base_dirs = glob.glob(r"C:\Program Files\QGIS*")
    base_dirs.sort()
    for base in base_dirs:
        version_name = os.path.basename(base)
        for cand in ("python-qgis-ltr.bat", "python-qgis.bat"):
            p = os.path.join(base, "bin", cand)
            if os.path.exists(p):
                found.append((version_name, p))
                break
    return found


def parse_explicit_launcher(value):
    """Parse LABEL=PATH supplied for Linux, macOS, or custom installations."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected LABEL=PATH")
    name, path = value.split("=", 1)
    name = name.strip()
    path = os.path.abspath(os.path.expanduser(path.strip()))
    if not name or not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f"launcher does not exist: {path}")
    return name, path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Fillet Toolkit tests in discovered or explicit QGIS Python environments."
    )
    parser.add_argument(
        "--qgis-python",
        action="append",
        default=[],
        type=parse_explicit_launcher,
        metavar="LABEL=PATH",
        help="Explicit QGIS Python launcher; repeat for Linux, macOS, or custom installs.",
    )
    parser.add_argument(
        "--no-windows-autodiscovery",
        action="store_true",
        help="Use only launchers passed with --qgis-python.",
    )
    args = parser.parse_args(argv)

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    qgis_versions = list(args.qgis_python)
    if not args.no_windows_autodiscovery:
        qgis_versions.extend(find_windows_qgis_python_executables())

    unique_versions = []
    seen_paths = set()
    for name, path in qgis_versions:
        normalized_path = os.path.normcase(os.path.abspath(path))
        if normalized_path not in seen_paths:
            unique_versions.append((name, path))
            seen_paths.add(normalized_path)
    qgis_versions = unique_versions

    if not qgis_versions:
        print(
            "No QGIS Python launchers found. On Linux/macOS pass one or more "
            "--qgis-python LABEL=/path/to/launcher arguments."
        )
        return 1

    print(f"=== Found {len(qgis_versions)} QGIS installations ===")
    for name, path in qgis_versions:
        print(f" - {name}: {path}")

    overall_success = True
    summary = []

    for name, py_bat in qgis_versions:
        print(f"\n========================================================")
        print(f"  RUNNING SMOKE TESTS ON: {name}")
        print(f"========================================================")
        version_success = True
        env = os.environ.copy()
        env["PYTHONPATH"] = root_dir + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")

        for test_file in TEST_FILES:
            test_path = os.path.join(root_dir, test_file)
            print(f"--> [{name}] Running {test_file}...")
            cmd = [py_bat, test_path]
            res = subprocess.run(cmd, cwd=root_dir, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"  FAIL: {test_file}")
                if res.stdout:
                    print(res.stdout[-500:])
                if res.stderr:
                    print(res.stderr[-500:])
                version_success = False
                overall_success = False
            else:
                print(f"  OK: {test_file}")

        status_str = "PASSED (100%)" if version_success else "FAILED"
        summary.append((name, status_str))

    print("\n" + "=" * 60)
    print("           QGIS MULTI-VERSION TEST SUMMARY")
    print("=" * 60)
    for name, status in summary:
        print(f"  {name.ljust(25)} : {status}")
    print("=" * 60)

    return 0 if overall_success else 1

if __name__ == "__main__":
    sys.exit(main())
