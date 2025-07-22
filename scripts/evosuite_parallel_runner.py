import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import List

import ray
from tqdm import tqdm

EVOSUITE_STATS_FILE = "evosuite_stats.json"

@ray.remote(num_cpus=1)
def _evosuite_task(project_root: Path, search_budget: str, cwd: Path) -> None:
    """
    Runs EvoSuite on the given project as a remote Ray task.
    """
    command = [
        "python", "evosuite_runner.py",
        "--project-root", str(project_root)
        # "--search-budget", search_budget
    ]
    try:
        print(f"[→] Running {command}", flush=True)
        result = subprocess.run(
            command,
            check=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[✗] Run failed on {command}", flush=True)
        return project_root.name, False, e.stderr
    else:
        with open(project_root.joinpath(EVOSUITE_STATS_FILE),"r") as f:
            es_stats = json.load(f)
        print(f"[✓] Done with {command}: {es_stats}", flush=True)
        return project_root.name, True, es_stats


def _run_evosuite_tasks(dataset_root: Path, java_apps: List[str], evosuite_search_budget: str,
                        output_dir: Path) -> None:
    script_dir = Path(__file__).resolve().parent
    print(f"Initial list of Java apps for EvoSuite run: {len(java_apps)}")
    # if evosuite_stats.json exists for app, remove it from the app list
    java_apps_filtered = [
        app for app in java_apps if not dataset_root.joinpath(app, EVOSUITE_STATS_FILE).exists()
    ]
    print(f"Running EvoSuite in parallel on {len(java_apps_filtered)} filtered Java apps")

    # create ray tasks for running evosuite
    ray.init(num_cpus=10, include_dashboard=False)
    ray_tasks = [
        _evosuite_task.remote(
            dataset_root.joinpath(app),
            evosuite_search_budget,
            script_dir
        )
        for app in java_apps_filtered
    ]

    # read existing summary data if it exists
    summary_data = {}
    summary_file = Path("evosuite_evaluation_summary.json")
    if summary_file.exists():
        with open(summary_file, "r") as f:
            summary_data = json.load(f)

    # track progress with tqdm
    with tqdm(total=len(ray_tasks), desc="Running EvoSuite", ncols=80) as pbar:
        while ray_tasks:
            done, ray_tasks = ray.wait(ray_tasks, num_returns=1)
            app_name, success, result = ray.get(done[0])
            # update summary data with result and write to json
            summary_data[app_name] = {
                "success": success,
                "result": result
            }
            with open(summary_file, "w") as f:
                json.dump(summary_data, f, indent=4)
            pbar.update(1)
    ray.shutdown()

    print(f"Execution complete; summary results written to {summary_file}")

def _get_app_list_from_java_version_file(app_java_version_file: Path) -> List[str]:
    java_apps = []
    with open(app_java_version_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("build-system") == "maven" and row.get("status") == "success":
                if row.get("java-version").startswith("8.0.") or row.get("java-version").startswith("11.0."):
                    java_apps.append(row.get("project"))
    return java_apps

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run EvoSuite in parallel on the given dataset")
    parser.add_argument("--dataset-root", "-dr", required=True,
                        help="Path to dataset root directory")
    parser.add_argument("--app-category-file", "-acf", required=False,
                        help="Path to json file containing app characteristics data")
    parser.add_argument("--app-file", "-af", required=False,
                        help="Path to text file containing list of app names")
    parser.add_argument("--app-java-version-file", "-ajvf", required=False,
                        help="Path to csv file containing list of apps with build information")
    parser.add_argument("--search-budget", "-sb", type=str, default=60,
                        help="Search budget (in seconds) per class")
    parser.add_argument("--output-dir", "-od", type=str, default="src/test/java",
                        help="Output directory for the generated tests")
    args = parser.parse_args()
    if args.app_category_file is None and args.app_file is None and args.app_java_version_file is None:
        print(f"One of --app-category-file/-acf, --app-file/-af, or --app-java-version-file/ajvf must be specified")
        sys.exit(1)

    if args.app_file:
        with open(args.app_file, "r") as f:
            java_apps = [line.strip() for line in f if line.strip()]
        print(f"Using app-file {args.app_file} listing {len(java_apps)} apps")
    elif args.app_java_version_file:
        java_apps = _get_app_list_from_java_version_file(app_java_version_file=Path(args.app_java_version_file))
        print(f"Using app-java-version-file {args.app_java_version_file} listing {len(java_apps)} apps")
    elif args.app_category_file:
        with open(args.app_category_file, "r") as f:
            java_apps = json.load(f)["SE projects"]
        print(f"Using app-category-file {args.app_category_file}: {len(java_apps)} compatible apps")
    _run_evosuite_tasks(
        dataset_root=Path(args.dataset_root),
        java_apps=java_apps,
        evosuite_search_budget=args.search_budget,
        output_dir=Path(args.output_dir)
    )
