import glob
import json
import os
import sys
import traceback
from pathlib import Path
from typing import List, Dict

import ray

from hamster.code_analysis.model.models import ProjectAnalysis

dir = "/home/hamster/xvdc/hamster_results/new_model"

class HamsterModelScanner:
    def __init__(self, model_file: str):
        with open(model_file, 'r') as f:
            file_content = json.load(f)
            self.project_analysis = ProjectAnalysis.model_validate(file_content)

    def scan_assertions(self):
        pass

@ray.remote
def scan_hamster_models(file: str):
    comparator = HamsterModelScanner(model_file = file)
    comparator.scan_assertions()

if __name__ == '__main__':
    pattern = os.path.join(dir, "**", 'hamster.json')
    all_files = glob.glob(pattern, recursive=True)
    print(f"Found {len(all_files)} old files.")

    print(f"Processing {len(all_files)} files...")

    ray.init(ignore_reinit_error=True)

    ray_tasks = [scan_hamster_models.remote(file) for file in all_files]

    for idx, task in enumerate(ray_tasks):
        try:
            ray.get(task)
        except Exception as e:
            print("ERROR!")
            traceback.print_exc()

    ray.shutdown()