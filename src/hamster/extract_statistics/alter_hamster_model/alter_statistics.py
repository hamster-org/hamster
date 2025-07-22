import glob
import json
import os
import traceback
from pathlib import Path
from typing import List, Dict

import ray
from cldk import CLDK
from cldk.analysis import AnalysisLevel

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.focal_class_method.focal_class_method import FocalClassMethod
from hamster.code_analysis.model.models import ProjectAnalysis
from hamster.code_analysis.test_statistics.call_and_assertion_sequence_details_info import \
    CallAndAssertionSequenceDetailsInfo
from hamster.code_analysis.test_statistics.setup_analysis_info import SetupAnalysisInfo
from hamster.code_analysis.test_statistics.test_method_analysis_info import TestMethodAnalysisInfo
from hamster.extract_statistics.utils import ExtractStatisticsUtils
from hamster.utils.pretty import ProgressBarFactory

statistics_dir = "/home/hamster/xvdc/hamster_results/statistics"
store_dir = '/home/hamster/xvdc/hamster_results/statistics'

class StatisticsModelUpdater:
    def __init__(self, statistics_dir: str, store_dir: str):
        self.statistics_dir = Path(statistics_dir)
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def alter_assertion_details_for_percentages(self):
        with open(self.statistics_dir / "assertion_details.json", 'r') as f:
            assertion_details = json.load(f)

        assertion_counts_by_type_dict = assertion_details["assertion_counts_by_type"]
        assertion_counts_dict = assertion_details["assertion_counts"]
        assertion_pairs_dict = assertion_details["assertion_pairs"]
        assertion_counts_by_type_per_app_type_dict = assertion_details["assertion_counts_by_type_per_app_type"]

        assertion_percentages_by_type = ExtractStatisticsUtils.get_percentage_dict(assertion_counts_by_type_dict)
        assertion_percentages = ExtractStatisticsUtils.get_percentage_dict(assertion_counts_dict)
        assertion_pair_percentages = ExtractStatisticsUtils.get_percentage_dict(assertion_pairs_dict)
        assertion_percentages_by_type_per_app_type = {
            app_type: ExtractStatisticsUtils.get_percentage_dict(assertion_count_type_dict)
            for app_type, assertion_count_type_dict in assertion_counts_by_type_per_app_type_dict.items()
        }

        assertion_details["assertion_percentages_by_type"] = assertion_percentages_by_type
        assertion_details["assertion_percentages"] = assertion_percentages
        assertion_details["assertion_pair_percentages"] = assertion_pair_percentages
        assertion_details["assertion_percentages_by_type_per_app_type"] = assertion_percentages_by_type_per_app_type

        self.save("new_assertion_details.json", assertion_details)

    def alter_input_details_for_percentages(self):
        with open(self.statistics_dir / "test_input_details_v2.json", 'r') as f:
            test_input_details = json.load(f)

        test_input_counts_by_type_dict = test_input_details["test_input_counts_by_type"]
        test_input_counts_by_type_per_app_type_dict = test_input_details["test_input_counts_by_type_per_app_type"]

        test_input_percentages_by_type = ExtractStatisticsUtils.get_percentage_dict(test_input_counts_by_type_dict)
        test_input_percentages_by_type_per_app_type = {
            app_type: ExtractStatisticsUtils.get_percentage_dict(input_count_dict)
            for app_type, input_count_dict in test_input_counts_by_type_per_app_type_dict.items()
        }

        test_input_details["test_input_percentages_by_type"] = test_input_percentages_by_type
        test_input_details["test_input_percentages_by_type_per_app_type"] = test_input_percentages_by_type_per_app_type

        self.save("new_test_input_details.json", test_input_details)


    def save(self, file_name: str, details: dict):
        """
        Save the altered statistics to file
        """
        with open(self.store_dir / file_name, 'w') as f:
            print("Saving to ", str(self.store_dir / file_name))
            f.write(json.dumps(details))


def alter_statistics_model():
    alterer = StatisticsModelUpdater(statistics_dir=statistics_dir, store_dir=store_dir)
    alterer.alter_assertion_details_for_percentages()
    alterer.alter_input_details_for_percentages()

if __name__ == '__main__':
    alter_statistics_model()

