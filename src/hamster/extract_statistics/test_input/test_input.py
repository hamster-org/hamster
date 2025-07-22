from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Dict

import numpy as np

from hamster.code_analysis.model.models import ProjectAnalysis, InputType, AppType, TestInput, TestClassAnalysis, TestMethodAnalysis, SetupAnalysis
from hamster.extract_statistics.utils import ExtractStatisticsUtils, TopK
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory

class TestInputDetails:
    def __init__(self, all_project_analysis: List[ProjectAnalysis], output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path

    def extract_details(self) -> dict | None | str:
        # Lists for per-method statistics
        number_test_inputs_per_method = []
        ncloc_per_method = []
        num_constructor_calls_per_method = []
        num_application_calls_per_method = []
        num_focal_methods_per_method = []
        num_mocked_resources_per_method = []

        # Lists for per-setup statistics
        number_test_inputs_per_setup = []
        cc_per_setup = []
        num_constructor_calls_per_setup = []

        # Counters
        test_input_counts_by_type: Dict[InputType, int] = Counter()
        test_input_counts_by_type_per_app_type: Dict[AppType, Dict[InputType, int]] = defaultdict(Counter)

        # For combination of inputs in same method
        input_type_groupings: Dict[tuple, int] = Counter()

        # Top-K trackers
        top_test_inputs_methods = TopK(10, "number of test inputs in method", keep_largest=True)
        top_test_inputs_setups = TopK(10, "number of test inputs in setup", keep_largest=True)

        ignored_types = {InputType.BINARY, InputType.SERIALIZED}

        def safe_corrcoef(x, y):
            if len(x) < 2:
                return 0.0
            corr = np.corrcoef(x, y)[0, 1]
            return 0.0 if np.isnan(corr) else corr

        print("\nProcessing test input statistics...")
        with ProgressBarFactory.get_progress_bar() as p:
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                project_input_type_counts = Counter()  # Local Counter for project's input types

                for test_class in project_analysis.test_class_analyses:
                    # Process setups
                    for setup in test_class.setup_analyses or []:
                        test_inputs = setup.test_inputs or []
                        num_effective = 0
                        types_in_setup = set()
                        for ti in test_inputs:
                            non_ignored = [it for it in ti.input_type or [] if it not in ignored_types]
                            if non_ignored:
                                num_effective += 1
                                for it in non_ignored:
                                    test_input_counts_by_type[it] += 1
                                    project_input_type_counts[it] += 1
                                types_in_setup.update(non_ignored)
                        num = num_effective
                        number_test_inputs_per_setup.append(num)
                        top_test_inputs_setups.add(num, setup.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)
                        cc_per_setup.append(setup.cyclomatic_complexity)
                        num_constructor_calls_per_setup.append(setup.number_of_objects_created)

                        if types_in_setup:
                            grouping = tuple(sorted(t.value for t in types_in_setup))
                            input_type_groupings[grouping] += 1

                    # Process test methods
                    for test_method in test_class.test_method_analyses:
                        test_inputs = test_method.test_inputs or []
                        num_effective = 0
                        types_in_method = set()
                        for ti in test_inputs:
                            non_ignored = [it for it in ti.input_type or [] if it not in ignored_types]
                            if non_ignored:
                                num_effective += 1
                                for it in non_ignored:
                                    test_input_counts_by_type[it] += 1
                                    project_input_type_counts[it] += 1
                                types_in_method.update(non_ignored)
                        num = num_effective
                        number_test_inputs_per_method.append(num)
                        top_test_inputs_methods.add(num, test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)
                        ncloc_per_method.append(test_method.ncloc)
                        num_constructor_calls_per_method.append(test_method.number_of_objects_created)
                        num_application_calls_per_method.append(len(test_method.application_call_details or []))
                        num_focal = sum(len(fc.focal_method_names or []) for fc in test_method.focal_classes or [])
                        num_focal_methods_per_method.append(num_focal)
                        num_mocked_resources_per_method.append(len(test_method.mocked_resources or []))

                        if types_in_method:
                            grouping = tuple(sorted(t.value for t in types_in_method))
                            input_type_groupings[grouping] += 1

                # Aggregate input types per application type
                for app_type in project_analysis.application_types:
                    for input_type, count in project_input_type_counts.items():
                        test_input_counts_by_type_per_app_type[app_type][input_type] += count

        # Compute stats
        number_test_inputs_per_method_stats = ExtractStatisticsUtils.get_summary_stats(number_test_inputs_per_method)
        number_test_inputs_per_setup_stats = ExtractStatisticsUtils.get_summary_stats(number_test_inputs_per_setup)
        ncloc_per_method_stats = ExtractStatisticsUtils.get_summary_stats(ncloc_per_method)
        num_constructor_calls_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_constructor_calls_per_method)
        num_application_calls_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_application_calls_per_method)
        num_focal_methods_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_focal_methods_per_method)
        num_mocked_resources_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_mocked_resources_per_method)

        num_methods_with_test_inputs = sum(1 for n in number_test_inputs_per_method if n > 0)

        # Compute correlations -> TODO: Maybe change
        corr_cc_inputs_setup = safe_corrcoef(cc_per_setup, number_test_inputs_per_setup)
        corr_ncloc_inputs_method = safe_corrcoef(ncloc_per_method, number_test_inputs_per_method)
        corr_inputs_constructors_method = safe_corrcoef(number_test_inputs_per_method, num_constructor_calls_per_method)
        corr_inputs_constructors_setup = safe_corrcoef(number_test_inputs_per_setup, num_constructor_calls_per_setup)
        corr_inputs_app_calls = safe_corrcoef(number_test_inputs_per_method, num_application_calls_per_method)
        corr_inputs_focal_methods = safe_corrcoef(number_test_inputs_per_method, num_focal_methods_per_method)
        corr_inputs_mocked = safe_corrcoef(number_test_inputs_per_method, num_mocked_resources_per_method)

        # Prepare groupings as dict with string keys
        sorted_groupings = sorted(input_type_groupings.items(), key=lambda item: item[1], reverse=True)
        groupings_dict = {', '.join(k): v for k, v in sorted_groupings}

        # Serialize top-K
        outlier_tracking = {
            "top_test_inputs_methods": top_test_inputs_methods.top_k_serialized(),
            "top_test_inputs_setups": top_test_inputs_setups.top_k_serialized(),
        }

        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            utils = ExtractStatisticsUtils(filepath=self.statistics_store_path)
            utils.get_box_plot(number_test_inputs_per_method, ["# of test inputs per method"], "Box plot of test inputs per test method", "test_inputs_per_method_plot")
            utils.get_box_plot(number_test_inputs_per_setup, ["# of test inputs per setup"], "Box plot of test inputs per setup method", "test_inputs_per_setup_plot")
            utils.get_box_plot(ncloc_per_method, ["NCLOC per method"], "Box plot of NCLOC per test method", "ncloc_per_method_plot")
            utils.get_box_plot(num_constructor_calls_per_method, ["# of constructor calls per method"], "Box plot of constructor calls per test method", "constructor_calls_per_method_plot")
            utils.get_box_plot(num_application_calls_per_method, ["# of application calls per method"], "Box plot of application calls per test method", "application_calls_per_method_plot")
            utils.get_box_plot(num_focal_methods_per_method, ["# of focal methods per method"], "Box plot of focal methods per test method", "focal_methods_per_method_plot")
            utils.get_box_plot(num_mocked_resources_per_method, ["# of mocked resources per method"], "Box plot of mocked resources per test method", "mocked_resources_per_method_plot")

        # Sort for comparison
        sorted_test_input_counts_by_type = sorted(test_input_counts_by_type.items(), key=lambda x: x[1], reverse=True)
        test_input_counts_by_type_dict = {k.value: v for k, v in sorted_test_input_counts_by_type}

        app_totals = [(app, sum(inner.values())) for app, inner in test_input_counts_by_type_per_app_type.items()]
        sorted_app_totals = sorted(app_totals, key=lambda x: x[1], reverse=True)
        test_input_counts_by_type_per_app_type_dict = {}
        for app, _ in sorted_app_totals:
            inner = test_input_counts_by_type_per_app_type[app]
            sorted_inner = sorted(inner.items(), key=lambda x: x[1], reverse=True)
            inner_dict = {itype.value: count for itype, count in sorted_inner}
            test_input_counts_by_type_per_app_type_dict[app.value] = inner_dict

        result = {
            "number_test_inputs_per_method_stats": number_test_inputs_per_method_stats,
            "number_test_inputs_per_setup_stats": number_test_inputs_per_setup_stats,
            "num_methods_with_test_inputs": num_methods_with_test_inputs,
            "total_test_methods": len(number_test_inputs_per_method),
            "test_input_counts_by_type": test_input_counts_by_type_dict,
            "input_type_groupings": groupings_dict,
            "correlation_cc_inputs_setup": corr_cc_inputs_setup,
            "correlation_ncloc_inputs_method": corr_ncloc_inputs_method,
            "correlation_inputs_constructors_method": corr_inputs_constructors_method,
            "correlation_inputs_constructors_setup": corr_inputs_constructors_setup,
            "correlation_inputs_app_calls": corr_inputs_app_calls,
            "correlation_inputs_focal_methods": corr_inputs_focal_methods,
            "correlation_inputs_mocked_resources": corr_inputs_mocked,
            "outlier_tracking": outlier_tracking,
            "test_input_counts_by_type_per_app_type": test_input_counts_by_type_per_app_type_dict,
            "ncloc_per_method_stats": ncloc_per_method_stats,
            "num_constructor_calls_per_method_stats": num_constructor_calls_per_method_stats,
            "num_application_calls_per_method_stats": num_application_calls_per_method_stats,
            "num_focal_methods_per_method_stats": num_focal_methods_per_method_stats,
            "num_mocked_resources_per_method_stats": num_mocked_resources_per_method_stats,
        }

        return result