from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Dict

import numpy as np

from hamster.code_analysis.model.models import ProjectAnalysis, InputType, AppType, TestInput, TestClassAnalysis, TestMethodAnalysis, SetupAnalysis
from hamster.extract_statistics.utils import ExtractStatisticsUtils, TopK
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory

class TestInputDetailsV2:
    def __init__(self, all_project_analysis: List[ProjectAnalysis],
                 output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path

    def extract_details(self) -> dict | None | str:
        number_test_inputs_per_method = []
        ncloc_per_method = []
        cyclomatic_complexity_per_method = []
        num_constructor_calls_per_method = []
        num_application_calls_per_method = []
        num_focal_methods_per_method = []
        num_mocks_created_per_method = []
        num_assertions_per_method = []
        num_ambiguous_inputs = 0

        # Counters
        test_input_counts_by_type: Dict[InputType, int] = Counter()
        test_input_counts_by_type_per_app_type: Dict[AppType, Dict[InputType, int]] = defaultdict(Counter)
        ambiguous_input_counts: dict[str, int] = Counter()

        # For combination of inputs in same method
        input_type_groupings: Dict[tuple, int] = Counter()

        # Top-K trackers
        top_test_inputs_methods = TopK(10, "number of test inputs in method including setups", keep_largest=True)

        ignored_types = {InputType.BINARY, InputType.SERIALIZED}

        def safe_corrcoef(x, y):
            if len(x) < 2:
                return 0.0
            corr = np.corrcoef(x, y)[0, 1]
            return 0.0 if np.isnan(corr) else corr

        print("\nProcessing test input statistics v2...")
        with ProgressBarFactory.get_progress_bar() as p:
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                project_input_type_counts = Counter()

                for test_class in project_analysis.test_class_analyses:
                    # Process setup methods
                    combined_setup_num = 0
                    combined_setup_constructors = 0
                    combined_setup_types = set()
                    combined_setup_cyclomatic = 0
                    combined_setup_ncloc = 0
                    combined_setup_mocks_created = 0
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
                        combined_setup_num += num_effective
                        combined_setup_constructors += setup.number_of_objects_created
                        combined_setup_cyclomatic += setup.cyclomatic_complexity_with_helpers
                        combined_setup_ncloc += setup.ncloc_with_helpers
                        combined_setup_mocks_created += setup.number_of_mocks_created
                        combined_setup_types.update(types_in_setup)

                    # Process test methods
                    for test_method in test_class.test_method_analyses:
                        test_inputs = test_method.test_inputs or []
                        num_effective = 0
                        types_in_method = set()
                        for ti in test_inputs:
                            non_ignored = [it for it in ti.input_type or [] if it not in ignored_types]
                            if non_ignored:
                                num_effective += 1
                                #for it in non_ignored:
                                if len(non_ignored) == 1:
                                    it = non_ignored[0]
                                    test_input_counts_by_type[it] += 1
                                    project_input_type_counts[it] += 1
                                    types_in_method.add(it)
                                elif len(non_ignored) > 1:
                                    num_ambiguous_inputs += 1
                                    ambiguous_input_counts[", ".join([ti.receiver_type, ti.method_signature, ti.method_name])] += 1
                                #types_in_method.update(non_ignored)

                        combined_num = combined_setup_num + num_effective
                        combined_types = combined_setup_types.union(types_in_method)
                        combined_cyclomatic = combined_setup_cyclomatic + test_method.cyclomatic_complexity_with_helpers
                        combined_ncloc = combined_setup_ncloc + test_method.ncloc_with_helpers
                        combined_constructors = combined_setup_constructors + test_method.number_of_objects_created
                        combined_mocks_created = combined_setup_mocks_created + test_method.number_of_mocks_created

                        number_test_inputs_per_method.append(combined_num)
                        top_test_inputs_methods.add(combined_num, test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)
                        ncloc_per_method.append(combined_ncloc)
                        cyclomatic_complexity_per_method.append(combined_cyclomatic)
                        num_constructor_calls_per_method.append(combined_constructors)
                        num_application_calls_per_method.append(len(test_method.application_call_details or []))
                        num_focal = sum(len(fc.focal_method_names or []) for fc in test_method.focal_classes or [])
                        num_focal_methods_per_method.append(num_focal)
                        num_mocks_created_per_method.append(combined_mocks_created)
                        num_assertions = sum(len(seq.assertion_details or []) for seq in test_method.call_assertion_sequences or [])
                        num_assertions_per_method.append(num_assertions)

                        if combined_types:
                            grouping = tuple(sorted(t.value for t in combined_types))
                            input_type_groupings[grouping] += 1

                # Aggregate input types per application type
                for app_type in project_analysis.application_types:
                    for input_type, count in project_input_type_counts.items():
                        test_input_counts_by_type_per_app_type[app_type][input_type] += count

        # Filter lists for methods with and without test inputs
        with_inputs_indices = [i for i, n in enumerate(number_test_inputs_per_method) if n > 0]
        without_inputs_indices = [i for i, n in enumerate(number_test_inputs_per_method) if n == 0]

        # For methods with test inputs
        number_test_inputs_with = [number_test_inputs_per_method[i] for i in with_inputs_indices]
        ncloc_with = [ncloc_per_method[i] for i in with_inputs_indices]
        cyclo_with = [cyclomatic_complexity_per_method[i] for i in with_inputs_indices]
        num_constructors_with = [num_constructor_calls_per_method[i] for i in with_inputs_indices]
        num_app_calls_with = [num_application_calls_per_method[i] for i in with_inputs_indices]
        num_focal_with = [num_focal_methods_per_method[i] for i in with_inputs_indices]
        num_mocked_with = [num_mocks_created_per_method[i] for i in with_inputs_indices]
        num_assertions_with = [num_assertions_per_method[i] for i in with_inputs_indices]

        # For methods without test inputs
        ncloc_without = [ncloc_per_method[i] for i in without_inputs_indices]
        cyclo_without = [cyclomatic_complexity_per_method[i] for i in without_inputs_indices]
        num_constructors_without = [num_constructor_calls_per_method[i] for i in without_inputs_indices]
        num_app_calls_without = [num_application_calls_per_method[i] for i in without_inputs_indices]
        num_focal_without = [num_focal_methods_per_method[i] for i in without_inputs_indices]
        num_mocked_without = [num_mocks_created_per_method[i] for i in without_inputs_indices]
        num_assertions_without = [num_assertions_per_method[i] for i in without_inputs_indices]

        # GET DISTRIBUTION STATS
        # Compute stats for all
        number_test_inputs_per_method_stats = ExtractStatisticsUtils.get_summary_stats(number_test_inputs_per_method)
        ncloc_per_method_stats = ExtractStatisticsUtils.get_summary_stats(ncloc_per_method)
        cyclo_complexity_per_method_stats = ExtractStatisticsUtils.get_summary_stats(cyclomatic_complexity_per_method)
        num_constructor_calls_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_constructor_calls_per_method)
        num_application_calls_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_application_calls_per_method)
        num_focal_methods_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_focal_methods_per_method)
        num_mocks_created_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_mocks_created_per_method)
        num_assertions_per_method_stats = ExtractStatisticsUtils.get_summary_stats(num_assertions_per_method)

        # Compute stats for with test inputs
        number_test_inputs_with_stats = ExtractStatisticsUtils.get_summary_stats(number_test_inputs_with)
        ncloc_with_stats = ExtractStatisticsUtils.get_summary_stats(ncloc_with)
        cyclo_with_stats = ExtractStatisticsUtils.get_summary_stats(cyclo_with)
        num_constructors_with_stats = ExtractStatisticsUtils.get_summary_stats(num_constructors_with)
        num_app_calls_with_stats = ExtractStatisticsUtils.get_summary_stats(num_app_calls_with)
        num_focal_with_stats = ExtractStatisticsUtils.get_summary_stats(num_focal_with)
        num_mocked_with_stats = ExtractStatisticsUtils.get_summary_stats(num_mocked_with)
        num_assertions_with_stats = ExtractStatisticsUtils.get_summary_stats(num_assertions_with)

        # Compute stats for without test inputs
        ncloc_without_stats = ExtractStatisticsUtils.get_summary_stats(ncloc_without)
        cyclo_without_stats = ExtractStatisticsUtils.get_summary_stats(cyclo_without)
        num_constructors_without_stats = ExtractStatisticsUtils.get_summary_stats(num_constructors_without)
        num_app_calls_without_stats = ExtractStatisticsUtils.get_summary_stats(num_app_calls_without)
        num_focal_without_stats = ExtractStatisticsUtils.get_summary_stats(num_focal_without)
        num_mocked_without_stats = ExtractStatisticsUtils.get_summary_stats(num_mocked_without)
        num_assertions_without_stats = ExtractStatisticsUtils.get_summary_stats(num_assertions_without)

        num_methods_with_test_inputs = len(with_inputs_indices)
        num_methods_without_test_inputs = len(without_inputs_indices)

        # Compute correlations
        corr_ncloc_inputs_method = safe_corrcoef(ncloc_per_method, number_test_inputs_per_method)
        corr_cyclo_inputs_method = safe_corrcoef(number_test_inputs_per_method, cyclomatic_complexity_per_method)
        corr_inputs_constructors_method = safe_corrcoef(number_test_inputs_per_method, num_constructor_calls_per_method)
        corr_inputs_app_calls = safe_corrcoef(number_test_inputs_per_method, num_application_calls_per_method)
        corr_inputs_focal_methods = safe_corrcoef(number_test_inputs_per_method, num_focal_methods_per_method)
        corr_inputs_mocked = safe_corrcoef(number_test_inputs_per_method, num_mocks_created_per_method)

        # Prepare groupings as dict with string keys (already sorted)
        sorted_groupings = sorted(input_type_groupings.items(), key=lambda item: item[1], reverse=True)
        groupings_dict = {', '.join(k): v for k, v in sorted_groupings}

        # Serialize top-K
        outlier_tracking = {
            "top_test_inputs_methods": top_test_inputs_methods.top_k_serialized(),
        }

        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            utils = ExtractStatisticsUtils(filepath=self.statistics_store_path)
            utils.get_box_plot(number_test_inputs_per_method, ["# of test inputs per method"], "Box plot of test inputs per test method", "test_inputs_per_method_plot")
            utils.get_box_plot(ncloc_per_method, ["NCLOC per method"], "Box plot of NCLOC per test method", "ncloc_per_method_plot")
            utils.get_box_plot(num_constructor_calls_per_method, ["# of constructor calls per method"], "Box plot of constructor calls per test method", "constructor_calls_per_method_plot")
            utils.get_box_plot(num_application_calls_per_method, ["# of application calls per method"], "Box plot of application calls per test method", "application_calls_per_method_plot")
            utils.get_box_plot(num_focal_methods_per_method, ["# of focal methods per method"], "Box plot of focal methods per test method", "focal_methods_per_method_plot")
            utils.get_box_plot(num_mocks_created_per_method, ["# of mocked resources per method"], "Box plot of mocked resources per test method", "mocked_resources_per_method_plot")

        # Sort counters
        sorted_test_input_counts_by_type = sorted(test_input_counts_by_type.items(), key=lambda x: x[1], reverse=True)
        test_input_counts_by_type_dict = {k.value: v for k, v in sorted_test_input_counts_by_type}

        app_totals = [(app, sum(inner.values())) for app, inner in test_input_counts_by_type_per_app_type.items()]
        sorted_app_totals = sorted(app_totals, key=lambda x: x[1], reverse=True)
        test_input_counts_by_type_per_app_type_dict: dict[str, dict[str, int]] = {}
        for app, _ in sorted_app_totals:
            inner = test_input_counts_by_type_per_app_type[app]
            sorted_inner = sorted(inner.items(), key=lambda x: x[1], reverse=True)
            inner_dict = {itype.value: count for itype, count in sorted_inner}
            test_input_counts_by_type_per_app_type_dict[app.value] = inner_dict

        # Get certain counter dicts as percentages
        test_input_percentages_by_type = ExtractStatisticsUtils.get_percentage_dict(test_input_counts_by_type_dict)
        test_input_percentages_by_type_per_app_type = {
            app_type: ExtractStatisticsUtils.get_percentage_dict(input_count_dict)
            for app_type, input_count_dict in test_input_counts_by_type_per_app_type_dict.items()
        }

        result = {
            "number_test_inputs_per_method_stats": number_test_inputs_per_method_stats,
            "num_methods_with_test_inputs": num_methods_with_test_inputs,
            "num_methods_without_test_inputs": num_methods_without_test_inputs,
            "num_ambiguous_inputs": num_ambiguous_inputs,
            "total_test_methods": len(number_test_inputs_per_method),
            "test_input_counts_by_type": test_input_counts_by_type_dict,
            "test_input_percentages_by_type": test_input_percentages_by_type,
            "input_type_groupings": groupings_dict,
            "ambiguous_input_counts": ambiguous_input_counts,
            "correlation_ncloc_inputs_method": corr_ncloc_inputs_method,
            "correlation_cyclomatic_complexity_inputs_method": corr_cyclo_inputs_method,
            "correlation_inputs_constructors_method": corr_inputs_constructors_method,
            "correlation_inputs_app_calls": corr_inputs_app_calls,
            "correlation_inputs_focal_methods": corr_inputs_focal_methods,
            "correlation_inputs_mocked_resources": corr_inputs_mocked,
            # "outlier_tracking": outlier_tracking,
            "test_input_counts_by_type_per_app_type": test_input_counts_by_type_per_app_type_dict,
            "test_input_percentages_by_type_per_app_type": test_input_percentages_by_type_per_app_type,
            "ncloc_per_method_stats": ncloc_per_method_stats,
            "cyclo_complexity_per_method_stats": cyclo_complexity_per_method_stats,
            "num_constructor_calls_per_method_stats": num_constructor_calls_per_method_stats,
            "num_application_calls_per_method_stats": num_application_calls_per_method_stats,
            "num_focal_methods_per_method_stats": num_focal_methods_per_method_stats,
            "num_mocks_created_per_method_stats": num_mocks_created_per_method_stats,
            "num_assertions_per_method_stats": num_assertions_per_method_stats,
            # Stats for tests with test inputs
            "number_test_inputs_with_stats": number_test_inputs_with_stats,
            "ncloc_with_inputs_stats": ncloc_with_stats,
            "cyclo_with_inputs_stats": cyclo_with_stats,
            "num_constructors_with_inputs_stats": num_constructors_with_stats,
            "num_application_calls_with_inputs_stats": num_app_calls_with_stats,
            "num_focal_methods_with_inputs_stats": num_focal_with_stats,
            "num_mocks_created_with_inputs_stats": num_mocked_with_stats,
            "num_assertions_with_inputs_stats": num_assertions_with_stats,
            # Stats for tests without test inputs
            "ncloc_without_inputs_stats": ncloc_without_stats,
            "cyclo_without_inputs_stats": cyclo_without_stats,
            "num_constructors_without_inputs_stats": num_constructors_without_stats,
            "num_application_calls_without_inputs_stats": num_app_calls_without_stats,
            "num_focal_methods_without_inputs_stats": num_focal_without_stats,
            "num_mocks_created_without_inputs_stats": num_mocked_without_stats,
            "num_assertions_without_inputs_stats": num_assertions_without_stats,
        }

        return result