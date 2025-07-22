import glob
import json
import os
import sys
import traceback
from pathlib import Path
from typing import List, Dict

import ray

from hamster.code_analysis.model.models import ProjectAnalysis

old_dir = "/home/hamster/xvdc/hamster_results/new_model"
new_dir = '/home/hamster/xvdc/hamster_results/new_new_new_model'

class HamsterModelComparator:
    def __init__(self, old_model: str, new_model: str):
        with open(old_model, 'r') as f:
            file_content = json.load(f)
            self.old_project_analysis = ProjectAnalysis.model_validate(file_content)

        with open(new_model, 'r') as f:
            file_content = json.load(f)
            self.new_project_analysis = ProjectAnalysis.model_validate(file_content)

    def compare_mocking(self):
        old_mocking_count = 0
        new_mocking_count = 0

        for cls in self.old_project_analysis.test_class_analyses:
            #for setup in cls.setup_analyses:
            for method in cls.test_method_analyses:
                if method.is_mocking_used:
                    old_mocking_count += method.number_of_mocks_created

        for cls in self.new_project_analysis.test_class_analyses:
            for method in cls.test_method_analyses:
                if method.is_mocking_used:
                    new_mocking_count += method.number_of_mocks_created

        assert old_mocking_count == new_mocking_count, f"Mocking counts differ: old {old_mocking_count}, new {new_mocking_count}"

@ray.remote
def compare_hamster_models(old_file: str, new_file: str):
    comparator = HamsterModelComparator(old_model=old_file, new_model=new_file)
    comparator.compare_mocking()

if __name__ == '__main__':
    pattern = os.path.join(old_dir, "**", 'hamster.json')
    all_old_files = glob.glob(pattern, recursive=True)
    print(f"Found {len(all_old_files)} old files.")

    pairs = []
    for old_file in all_old_files:
        rel_path = os.path.relpath(old_file, old_dir)
        new_file = os.path.join(new_dir, rel_path)
        if os.path.exists(new_file):
            pairs.append((old_file, new_file))
        else:
            print(f"Missing new file for {old_file}: {new_file}")

    print(f"Processing {len(pairs)} pairs...")

    ray.init(ignore_reinit_error=True)

    ray_tasks = [compare_hamster_models.remote(old, new) for old, new in pairs]

    failures = []
    for idx, task in enumerate(ray_tasks):
        old_file, new_file = pairs[idx]
        project_dir = os.path.dirname(old_file)
        try:
            ray.get(task)
        except Exception as e:
            print(f"FAILURE: Error comparing {project_dir}: {e}")
            traceback.print_exc()
            failures.append((project_dir, e))

    ray.shutdown()

    if failures:
        print()
        print("SUMMARY: Some comparisons failed...")
        for proj, err in failures:
            print(f" - Failed project: {proj} with error: {err}")
        print(f"Total failures: {len(failures)} out of {len(pairs)}")
        sys.exit(1)
    else:
        print()
        print("SUMMARY: All comparisons successful!")