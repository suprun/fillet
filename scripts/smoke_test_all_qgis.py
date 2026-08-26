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
    "tests/test_rotate_tool.py",
    "tests/test_mirror_tool.py",
    "tests/test_scale_rotate_tool.py",
    "tests/test_edge_offset_tool.py",
    "tests/test_clean_duplicate_nodes_tool.py",
    "tests/test_array_tool.py",
]

def find_qgis_python_executables():
    """Finds all available QGIS python launcher scripts on the system."""
    found = []
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

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    qgis_versions = find_qgis_python_executables()

    if not qgis_versions:
        print("No QGIS installations found on this system.")
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
