#!/usr/bin/env python3
import subprocess
import traceback
from pathlib import Path
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
# Set this to true if want to remove the model directory and do a clean generation.
# If not set, then it will restart and generate only the new hamster models that are not present in the model directory.
EAGER = False

def process_repo(repo_dir, analysis_dir, model_dir, src_dir):
    repo_name = repo_dir.name
    analysis_file_dir = analysis_dir / repo_name / "symbol_table"  # analysis.json is not included in this path
    analysis_file = analysis_file_dir / "analysis.json"

    if not analysis_file.is_file():
        print(f"Skipping the {repo_name} project since an analysis file was not found...\n", flush=True)
        return

    print(f"Processing '{repo_name}'...", flush=True)

    cmd = [
        # "poetry", "run",
        "python", "-m", "hamster.cli", "analysis",
        "--project-path", str(repo_dir),
        "--analysis-path", str(analysis_file_dir),
        "--store-hamster-model-path", str(model_dir),
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            cwd=src_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed on {repo_name}", flush=True)
        print(f"Return code: {e.returncode}")
        print(f"STDOUT:\n{e.stdout}")
        print(f"STDERR:\n{e.stderr}")
    else:
        print(f"Done with {repo_name}", flush=True)

def main():
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent.parent

    # Put your repo path and replace "example" here
    repos_dir = root / "example" / "repos"
    analysis_dir = root / "example" / "analysis"
    model_dir = root / "example" / "hamster_results" / "model"
    src_dir = root / "hamster" / "src"

    model_dir.mkdir(parents=True, exist_ok=True)
    if EAGER:
        all_repos = [directory for directory in repos_dir.iterdir() if directory.is_dir()]
    else:
        analysis_folders = {p.name for p in analysis_dir.iterdir() if p.is_dir()}
        hamster_folders  = {p.name for p in model_dir.iterdir()  if p.is_dir()}

        difference = sorted(analysis_folders - hamster_folders)

        all_repos = [analysis_dir / name for name in difference]

    print(f"Processing {len(all_repos)} total repositories...")

    max_workers = min(len(all_repos), os.cpu_count() or 1)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for repo_dir in all_repos:
            futures.append(
                executor.submit(process_repo, repo_dir, analysis_dir, model_dir, src_dir)
            )

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error during parallel execution: {e}")

    print("Completed model generation...")


if __name__ == "__main__":
    main()
