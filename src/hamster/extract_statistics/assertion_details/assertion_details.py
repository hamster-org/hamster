from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Dict

import numpy as np

from hamster.code_analysis.model.models import ProjectAnalysis, AssertionType, CallAndAssertionSequenceDetails, AppType, CallableDetails, AssertionDetails as ModelAssertionDetails
from hamster.extract_statistics.utils import ExtractStatisticsUtils, TopK
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory

# NOTE: We renamed AssertDetails import from model
class AssertionDetails:
    def __init__(self, all_project_analysis: List[ProjectAnalysis], output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path

    def extract_details(self) -> dict | None | str:
        # Lists for per-method statistics
        number_test_blocks_per_method = []
        number_assertions_per_method = []
        number_assertion_sequences_per_method = []
        num_methods_with_two_or_more_call_assert_blocks = 0
        num_methods_with_fluid_assertion_chains = 0
        num_methods_with_helper_assertions = 0
        num_methods_with_no_assertions = 0
        num_ambiguous_assertions = 0
        length_callable_sequences = []
        length_assertion_sequences = []
        assertion_percentage_entities_per_method = []
        assertion_percentage_ncloc_per_method = []
        secondary_assertions_per_method = []
        secondary_assertions_per_method_with_fluid = []
        secondary_getter_assertions_per_method = []
        assertions_in_helper_per_method = []
        assertions_in_helper_per_method_with_helper = []
        fluid_chain_lengths = []

        # Counters
        assertion_counts_by_type: Counter[str] = Counter()
        assertion_counts: Counter[str] = Counter()  # Counts by assertion name (for unique assertions)
        ambiguous_assertion_counts: Dict[str, int] = Counter()  # Assertions with multiple types
        assertion_pairs: Dict[tuple, int] = Counter()  # Pairs of consecutive assertions
        fluid_chain_breakers: Counter[str] = Counter()
        assertion_counts_by_type_per_app_type: Dict[AppType, Dict[AssertionType, int]] = defaultdict(Counter)  # Per application type

        # Top-K trackers
        top_test_blocks = TopK(10, "number of test blocks in method", keep_largest=True)
        top_callable_seq_lengths = TopK(10, "callable sequence length in method", keep_largest=True)
        top_assertion_seq_lengths = TopK(10, "assertion sequence length in method", keep_largest=True)
        top_fluid_chain_lengths = TopK(5, "fluid chain length in method", keep_largest=True)

        # Ignored assertion types
        ignored_types = { AssertionType.UTILITY }

        print("\nProcessing assertion statistics...")
        with ProgressBarFactory.get_progress_bar() as p:
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                project_assertion_type_counts = Counter()  # Local counter for this project's assertion types

                for test_class in project_analysis.test_class_analyses:
                    for test_method in test_class.test_method_analyses:
                        seqs: List[CallAndAssertionSequenceDetails] = test_method.call_assertion_sequences

                        if not seqs:
                            number_test_blocks_per_method.append(0)
                            number_assertions_per_method.append(0)
                            number_assertion_sequences_per_method.append(0)
                            assertion_percentage_entities_per_method.append(0)
                            assertion_percentage_ncloc_per_method.append(0)
                            secondary_assertions_per_method.append(0)
                            secondary_getter_assertions_per_method.append(0)
                            assertions_in_helper_per_method.append(0)
                            continue

                        # Per-method calculations
                        num_test_blocks = len(seqs)
                        number_test_blocks_per_method.append(num_test_blocks)
                        top_test_blocks.add(num_test_blocks, test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)

                        num_assertion_sequences = sum(1 for seq in seqs if seq.assertion_details)
                        number_assertion_sequences_per_method.append(num_assertion_sequences)

                        num_assertions = sum(
                            sum(1 for ad in seq.assertion_details if set(ad.assertion_type) - ignored_types)
                            for seq in seqs
                        )
                        number_assertions_per_method.append(num_assertions)

                        if num_assertions == 0:
                            num_methods_with_no_assertions += 1

                        num_secondary = 0
                        num_secondary_getter = 0
                        num_assertions_in_helper = 0

                        num_callables = sum(len(seq.call_sequence_details) for seq in seqs)

                        for seq in seqs:
                            # Callable sequence stats
                            call_details = seq.call_sequence_details
                            length_callable_sequences.append(len(call_details))
                            top_callable_seq_lengths.add(len(call_details), test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)

                            # Process secondary assertions
                            for cd in call_details:
                                if cd.secondary_assertion:
                                    num_secondary += 1
                                    if cd.method_name.startswith("get"):
                                        num_secondary_getter += 1

                            assert_details = seq.assertion_details
                            filtered_assert_details = [ad for ad in assert_details if set(ad.assertion_type) - ignored_types]
                            # Ensure there exists atleast one non-ignored assertion
                            if filtered_assert_details:
                                length_assertion_sequences.append(len(filtered_assert_details))
                                top_assertion_seq_lengths.add(len(filtered_assert_details),
                                                              test_method.method_signature,
                                                              test_class.qualified_class_name,
                                                              project_analysis.dataset_name)

                                # Assertion pairs for patterns (using filtered list)
                                for k in range(len(filtered_assert_details) - 1):
                                    if (
                                            AssertionType.WRAPPER not in filtered_assert_details[k].assertion_type
                                            and AssertionType.WRAPPER not in filtered_assert_details[k + 1].assertion_type
                                    ):
                                        pair = (filtered_assert_details[k].assertion_name,
                                                filtered_assert_details[k + 1].assertion_name)
                                        assertion_pairs[pair] += 1

                                # Count assertions in helpers, types, names, ambiguous
                                for ad in assert_details:
                                    # Skip
                                    if not (set(ad.assertion_type) - ignored_types):
                                        continue

                                    assertion_name = ad.assertion_name
                                    assertion_counts[assertion_name] += 1

                                    if len(ad.assertion_type) > 1:
                                        ambiguous_assertion_counts[assertion_name] += 1
                                        num_ambiguous_assertions += 1

                                    # Count each non-ignored type (handles multi-type assertions)
                                    for assertion_type in ad.assertion_type:
                                        if assertion_type not in ignored_types:
                                            assertion_counts_by_type[assertion_type.value] += 1
                                            project_assertion_type_counts[assertion_type] += 1

                                    if ad.in_helper:
                                        num_assertions_in_helper += 1

                        # Collect flattened sequences then process for fluid assertion chain length
                        has_fluid_chain = False
                        curr_fluid_chain_length = 0
                        for seq in seqs:
                            for cd in seq.call_sequence_details:
                                if curr_fluid_chain_length > 0:
                                    if cd.secondary_assertion:
                                        pass
                                    else:
                                        if curr_fluid_chain_length > 2:
                                            fluid_chain_lengths.append(curr_fluid_chain_length)
                                            top_fluid_chain_lengths.add(curr_fluid_chain_length, test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)
                                            has_fluid_chain = True
                                        elif curr_fluid_chain_length == 1:
                                            fluid_chain_breakers[cd.method_name] += 1
                                        curr_fluid_chain_length = 0

                            for ad in seq.assertion_details:
                                # If wrapped assertion within an assertion chain
                                if curr_fluid_chain_length > 0 and ad.is_wrapped:
                                    curr_fluid_chain_length += 1
                                # If not in an assertion chain
                                else:
                                    # If new assertion, we consider flush old chain to list if > 1
                                    if curr_fluid_chain_length > 2:
                                        fluid_chain_lengths.append(curr_fluid_chain_length)
                                        top_fluid_chain_lengths.add(curr_fluid_chain_length, test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)
                                        has_fluid_chain = True

                                    # If the chain length was 1, we check why it is breaking
                                    if curr_fluid_chain_length == 1:
                                        fluid_chain_breakers[ad.assertion_name] += 1

                                    # We set to one if it is a WRAPPER, or 0 otherwise
                                    if AssertionType.WRAPPER in ad.assertion_type:
                                        curr_fluid_chain_length = 1
                                    elif curr_fluid_chain_length > 0:
                                        curr_fluid_chain_length = 0

                        if curr_fluid_chain_length > 2:
                            fluid_chain_lengths.append(curr_fluid_chain_length)
                            top_fluid_chain_lengths.add(curr_fluid_chain_length, test_method.method_signature, test_class.qualified_class_name, project_analysis.dataset_name)
                            has_fluid_chain = True

                        valid_secondary = num_secondary - num_secondary_getter
                        secondary_assertions_per_method.append(valid_secondary)
                        if has_fluid_chain:
                            secondary_assertions_per_method_with_fluid.append(valid_secondary)
                        secondary_getter_assertions_per_method.append(num_secondary_getter)
                        assertions_in_helper_per_method.append(num_assertions_in_helper)
                        if num_assertions_in_helper > 0:
                            assertions_in_helper_per_method_with_helper.append(num_assertions_in_helper)

                        # Percentage of entities that are assertions
                        total_entities = num_callables + num_assertions
                        percentage_entities = (num_assertions / total_entities * 100) if total_entities > 0 else 0
                        assertion_percentage_entities_per_method.append(percentage_entities)

                        # Percentage of NCLOC that are assertions
                        percentage_ncloc = (num_assertions / test_method.ncloc_with_helpers * 100) if test_method.ncloc_with_helpers > 0 else 0
                        assertion_percentage_ncloc_per_method.append(percentage_ncloc)

                        if num_assertion_sequences >= 2:
                            num_methods_with_two_or_more_call_assert_blocks += 1
                        if has_fluid_chain:
                            num_methods_with_fluid_assertion_chains += 1
                        if num_assertions_in_helper > 0:
                            num_methods_with_helper_assertions += 1

                # Aggregate assertion types per application type after processing project
                for app_type in project_analysis.application_types:
                    for assertion_type, count in project_assertion_type_counts.items():
                        assertion_counts_by_type_per_app_type[app_type][assertion_type] += count

        # Aggregate for total counts
        total_number_assertions = sum(number_assertions_per_method)
        total_number_methods = len(number_assertions_per_method)

        # Compute stats
        number_test_blocks_per_method_stats = ExtractStatisticsUtils.get_summary_stats(number_test_blocks_per_method)
        number_assertions_per_method_stats = ExtractStatisticsUtils.get_summary_stats(number_assertions_per_method)
        number_assertion_sequences_per_method_stats = ExtractStatisticsUtils.get_summary_stats(number_assertion_sequences_per_method)
        length_callable_sequences_stats = ExtractStatisticsUtils.get_summary_stats(length_callable_sequences)
        length_assertion_sequences_stats = ExtractStatisticsUtils.get_summary_stats(length_assertion_sequences)
        secondary_assertions_per_method_stats = ExtractStatisticsUtils.get_summary_stats(secondary_assertions_per_method)
        secondary_getter_assertions_per_method_stats = ExtractStatisticsUtils.get_summary_stats(secondary_getter_assertions_per_method)
        secondary_assertions_per_method_with_fluid_stats = ExtractStatisticsUtils.get_summary_stats(secondary_assertions_per_method_with_fluid)
        assertions_in_helper_per_method_stats = ExtractStatisticsUtils.get_summary_stats(assertions_in_helper_per_method)
        assertions_in_helper_per_method_with_helper_stats = ExtractStatisticsUtils.get_summary_stats(assertions_in_helper_per_method_with_helper)
        assertion_percentage_entities_per_method_stats = ExtractStatisticsUtils.get_summary_stats(assertion_percentage_entities_per_method)
        assertion_percentage_ncloc_per_method_stats = ExtractStatisticsUtils.get_summary_stats(assertion_percentage_ncloc_per_method)
        fluid_chain_lengths_stats = ExtractStatisticsUtils.get_summary_stats(fluid_chain_lengths)

        unique_assertions = len(assertion_counts)

        # Grouped assertions count
        total_grouped_assertions = assertion_counts_by_type[AssertionType.GROUPED.value]

        # Serialize top-K
        outlier_tracking = {
            #"top_test_blocks": top_test_blocks.top_k_serialized(),
            #"top_callable_seq_lengths": top_callable_seq_lengths.top_k_serialized(),
            #"top_assertion_seq_lengths": top_assertion_seq_lengths.top_k_serialized(),
            "top_fluid_chain_lengths": top_fluid_chain_lengths.top_k_serialized()
        }

        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            utils = ExtractStatisticsUtils(filepath=self.statistics_store_path)
            utils.get_box_plot(number_test_blocks_per_method, ["# of test blocks per method"], "Box plot of test blocks per test method", "test_blocks_per_method_plot")
            utils.get_box_plot(number_assertions_per_method, ["# of assertions per method"], "Box plot of assertions per test method", "assertions_per_method_box_plot")
            utils.get_box_plot(number_assertion_sequences_per_method, ["# of assertion sequences per method"], "Box plot of assertion sequences per method", "assertion_sequences_per_method_box_plot")
            utils.get_box_plot(length_callable_sequences, ["Callable sequence lengths"], "Box plot of callable sequence lengths", "callable_sequence_length_box_plot")
            utils.get_box_plot(length_assertion_sequences, ["Assertion sequence lengths"], "Box plot of assertion sequence lengths", "assertion_sequence_length_box_plot")
            utils.get_box_plot(secondary_assertions_per_method, ["# of secondary assertions per method"], "Box plot of secondary assertions per method", "secondary_assertions_per_method_box_plot")
            utils.get_box_plot(secondary_getter_assertions_per_method, ["# of secondary getter assertions per method"], "Box plot of secondary getter assertions per method", "secondary_getter_assertions_per_method_box_plot")
            utils.get_box_plot(assertions_in_helper_per_method, ["# of assertions in helper per method"], "Box plot of assertions in helper per method", "assertions_in_helper_per_method_box_plot")
            utils.get_box_plot(assertion_percentage_entities_per_method, ["Assertion % entities per method"], "Box plot of assertion percentage entities per test method", "assertion_percentage_entities_per_method_box_plot")
            utils.get_box_plot(assertion_percentage_ncloc_per_method, ["Assertion % NCLOC per method"], "Box plot of assertion percentage NCLOC per test method", "assertion_percentage_ncloc_per_method_box_plot")
            if len(fluid_chain_lengths)>0:
                utils.get_box_plot(fluid_chain_lengths, ["Fluid chain lengths"], "Box plot of fluid assertion chain lengths", "fluid_chain_lengths_box_plot")

        # Sort for easy comparison
        assertion_counts_by_type_dict = dict(assertion_counts_by_type.most_common(15))

        assertion_counts_dict = dict(assertion_counts.most_common(5))

        sorted_ambiguous = sorted(ambiguous_assertion_counts.items(), key=lambda x: x[1], reverse=True)
        ambiguous_assertion_counts_dict = dict(sorted_ambiguous)

        sorted_pairs = sorted(assertion_pairs.items(), key=lambda x: x[1], reverse=True)
        assertion_pairs_dict = {str(k): v for k, v in sorted_pairs}

        fluid_chain_breakers_dict = dict(fluid_chain_breakers.most_common(5))

        app_totals = [(app, sum(inner.values())) for app, inner in assertion_counts_by_type_per_app_type.items()]
        sorted_app_totals = sorted(app_totals, key=lambda x: x[1], reverse=True)
        assertion_counts_by_type_per_app_type_dict = {}
        for app, _ in sorted_app_totals:
            inner = assertion_counts_by_type_per_app_type[app]
            sorted_inner = sorted(inner.items(), key=lambda x: x[1], reverse=True)
            inner_dict = {atype.value: count for atype, count in sorted_inner}
            assertion_counts_by_type_per_app_type_dict[app.value] = inner_dict

        # Get certain counter dicts as percentages
        assertion_percentages_by_type = ExtractStatisticsUtils.get_percentage_dict(assertion_counts_by_type_dict)
        assertion_percentages = ExtractStatisticsUtils.get_percentage_dict(assertion_counts_dict)
        assertion_pair_percentages = ExtractStatisticsUtils.get_percentage_dict(assertion_pairs_dict)
        assertion_percentages_by_type_per_app_type = {
            app_type: ExtractStatisticsUtils.get_percentage_dict(assertion_count_type_dict)
            for app_type, assertion_count_type_dict in assertion_counts_by_type_per_app_type_dict.items()
        }

        result = {
            "total_number_methods": total_number_methods,
            "total_number_assertions": total_number_assertions,
            "num_methods_with_two_or_more_call_assert_blocks": num_methods_with_two_or_more_call_assert_blocks,
            "num_methods_with_fluid_assertion_chains": num_methods_with_fluid_assertion_chains,
            "num_methods_with_helper_assertions": num_methods_with_helper_assertions,
            "num_methods_with_no_assertions": num_methods_with_no_assertions,
            "num_ambiguous_assertions": num_ambiguous_assertions,
            "number_test_blocks_per_method_stats": number_test_blocks_per_method_stats,
            "number_assertions_per_method_stats": number_assertions_per_method_stats,
            "number_assertion_seq_per_method_stats": number_assertion_sequences_per_method_stats,
            "length_callable_sequence_stats": length_callable_sequences_stats,
            "length_assertion_sequence_stats": length_assertion_sequences_stats,
            "secondary_assertions_per_method_stats": secondary_assertions_per_method_stats,
            "secondary_getter_assertions_per_method_stats": secondary_getter_assertions_per_method_stats,
            "secondary_assertions_per_method_with_fluid_stats": secondary_assertions_per_method_with_fluid_stats,
            "unique_assertions": unique_assertions,
            "assertion_counts_by_type": assertion_counts_by_type_dict,
            "assertion_percentages_by_type": assertion_percentages_by_type,
            "assertion_counts": assertion_counts_dict,
            "assertion_percentages": assertion_percentages,
            "ambiguous_assertion_counts": ambiguous_assertion_counts_dict,
            "outlier_tracking": outlier_tracking,
            "assertions_in_helper_per_method_stats": assertions_in_helper_per_method_stats,
            "assertions_in_helper_per_method_with_helper_stats": assertions_in_helper_per_method_with_helper_stats,
            "assertion_percentage_entities_stats": assertion_percentage_entities_per_method_stats,
            "assertion_percentage_ncloc_stats": assertion_percentage_ncloc_per_method_stats,
            "fluid_chain_length_stats": fluid_chain_lengths_stats,
            "fluid_chain_breakers": fluid_chain_breakers_dict,
            "total_grouped_assertions": total_grouped_assertions,
            #"assertion_pairs": assertion_pairs_dict,
            #"assertion_pair_percentages": assertion_pair_percentages,
            "assertion_counts_by_type_per_app_type": assertion_counts_by_type_per_app_type_dict,
            "assertion_percentages_by_type_per_app_type": assertion_percentages_by_type_per_app_type,
        }

        return result