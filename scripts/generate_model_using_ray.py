import subprocess
from pathlib import Path
import traceback
import ray
import shutil
from typing import List, Dict, Tuple
import argparse
import cProfile
import os
import pstats
import sys
import traceback
import random

# Set this to true if want to remove the model directory and do a clean generation.
# If not set, then it will restart and generate only the new hamster models that are not present in the model directory.
EAGER = False
DIVIDE = 300
def split_list_evenly(lst, num_sublists):
    base_size = len(lst) // num_sublists  # 13
    remainder = len(lst) % num_sublists   # 1

    result = []
    start = 0
    for i in range(num_sublists):
        extra = 1 if i < remainder else 0  # First 'remainder' lists get an extra item
        end = start + base_size + extra
        result.append(lst[start:end])
        start = end
    for i in range(len(result)):
        print(f"Divide {i} has items {len(result[i])}")
    return result



def process_repo(repo_dir_str: str,
                 analysis_dir_str: str,
                 model_dir_str: str,
                 src_dir_str: str) -> None:
    """
    Remote Ray task: build a Hamster model for one repository.
    """
    repo_dir      = Path(repo_dir_str)
    analysis_dir  = Path(analysis_dir_str)
    model_dir     = Path(model_dir_str)
    src_dir   = Path(src_dir_str)

    repo_name = repo_dir.name
    analysis_file_dir = analysis_dir / repo_name / "symbol_table"
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
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed on {repo_name}", flush=True)
        print(f"Return code: {e.returncode}")
        print(f"STDOUT:\n{e.stdout}")
        print(f"STDERR:\n{e.stderr}")
    else:
        print(f"Done with {repo_name}", flush=True)

@ray.remote
def process_repo_list(repo_dir_lst: List[str],
                 analysis_dir_str: str,
                 model_dir_str: str,
                 src_dir_str: str):
    for repo_dir_str in repo_dir_lst:
        process_repo(repo_dir_str,
                 analysis_dir_str,
                 model_dir_str,
                 src_dir_str)

def _run(local_mode: bool = False):
    """Kick off the Ray job once, in either local-mode or cluster mode."""
    ray.init(
        local_mode=local_mode,          # True == everything runs inline
        num_cpus=os.cpu_count(),        # 2️⃣  right-size the pool
    )
    script_dir = Path(__file__).resolve().parent
    root       = script_dir.parent.parent

    # Put your repo path and replace "example" here
    repos_dir = root / "example" / "repos"
    analysis_dir = root / "example" / "analysis"
    model_dir = root / "example" / "hamster_results" / "model"
    src_dir = root / "hamster" / "src"

    # if model_dir.exists() and EAGER:
    #     shutil.rmtree(model_dir)
    # model_dir.mkdir(parents=True, exist_ok=True)
    EAGER = False
    if EAGER:
        all_repos = [d for d in repos_dir.iterdir() if d.is_dir()]
    else:
        analysis_folders = {p.name for p in analysis_dir.iterdir() if p.is_dir()}
        hamster_folders  = {p.name for p in model_dir.iterdir()  if p.is_dir()}

        difference = sorted(analysis_folders - hamster_folders)

        all_repos = [analysis_dir / name for name in difference]
    print(f"Processing {len(all_repos)} total repositories...")

    divided_repos = scrambled(split_list_evenly(all_repos, DIVIDE))
    print(f"Processing {len(all_repos)} total repositories...")
    ray_tasks = [
        process_repo_list.remote(
            [str(repo_dir) for repo_dir in repo_dir_lst],
            str(analysis_dir),
            str(model_dir),
            str(hamster_dir),
        )
        for repo_dir_lst in divided_repos
    ]

    try:
        ray.get(ray_tasks)
    except Exception:  
        traceback.print_exc()

    print("Completed model generation...")
    ray.shutdown()

def scrambled(orig):
    dest = orig[:]
    random.shuffle(dest)
    return dest

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run repo processing on Ray."
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run a single-process profile with Ray local_mode=True.",
    )
    args = parser.parse_args(argv)

    if args.profile:
        print("Profiling one pass in local mode…")
        with cProfile.Profile() as pr:
            _run(local_mode=True)
        stats = pstats.Stats(pr, stream=sys.stdout).sort_stats("cumulative")
        stats.print_stats(25)           # top 25 hotspots
    else:
        _run(local_mode=False)


if __name__ == "__main__":
    main()
