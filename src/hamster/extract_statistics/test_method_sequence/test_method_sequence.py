from pathlib import Path
from typing import List

from hamster.code_analysis.model.models import ProjectAnalysis
from hamster.extract_statistics.utils import ExtractStatisticsUtils, TopK
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory


class TestMethodSequence:
    def __init__(self, all_project_analysis: List[ProjectAnalysis], output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path
        self.extract_statistics_util = ExtractStatisticsUtils(filepath=statistics_store_path)

    def extract_details(self) -> dict | None | str:
        ncloc_per_method = []
        testing_types = []
        testing_types_per_test = {}
        cyclomatic_complexity_per_method = []
        is_mocked_used = []
        objects_created = []
        mocks_created = []
        mocking_frameworks = []
        constructor_called = []
        library_called = []
        test_blocks = []
        helper_methods = []
        total_helper_methods = 0
        total_helper_methods_ncloc = 0
        call_assertion_sequences_with__length_1 = 0
        call_assertion_sequences_with__length_gt_1 = 0
        call_sequence = []
        assertion_sequence = []

        top_library_called = TopK(10, "number of library calls in method", keep_largest=True)
        top_ncloc = TopK(10, "number of non-comment lines of code in method", keep_largest=True)

        print()
        print("Processing method statistics...")
        with (ProgressBarFactory.get_progress_bar() as p):
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                for test_class in project_analysis.test_class_analyses:
                    for test_method in test_class.test_method_analyses:
                        helper_methods.append(test_method.number_of_helper_methods)
                        total_helper_methods += test_method.number_of_helper_methods
                        total_helper_methods_ncloc += test_method.helper_method_ncloc
                        testing_types.append(test_method.test_type.value)
                        ncloc_per_method.append(test_method.ncloc_with_helpers if test_method.ncloc_with_helpers else 0)
                        cyclomatic_complexity_per_method.append(test_method.cyclomatic_complexity_with_helpers if test_method.cyclomatic_complexity_with_helpers else 0)
                        top_ncloc.add(test_method.ncloc_with_helpers, test_method.method_signature, test_class.qualified_class_name,
                                      project_analysis.dataset_name)
                        if test_method.test_type.value in testing_types_per_test:
                            testing_types_per_test[test_method.test_type.value].append([
                                project_analysis.dataset_name,
                                test_method.qualified_class_name,
                                test_method.method_signature])
                        else:
                            testing_types_per_test[test_method.test_type.value] = [[project_analysis.dataset_name,
                                                                                    test_method.qualified_class_name,
                                                                                    test_method.method_signature]]
                        objects_created.append(test_method.number_of_objects_created)
                        if test_method.is_mocking_used:
                            mocks_created.append(test_method.number_of_mocks_created)
                        if test_method.mocking_frameworks_used is not None:
                            mocking_frameworks.extend([mocking_framework_used.value
                                                       for mocking_framework_used in test_method.mocking_frameworks_used
                                                       if mocking_framework_used is not None])
                        is_mocked_used.append(test_method.is_mocking_used)
                        constructor_called.append(len(test_method.constructor_call_details))

                        library_called.append(len(test_method.library_call_details))
                        top_library_called.add(len(test_method.library_call_details),
                                               test_method.method_signature, test_class.qualified_class_name,
                                               project_analysis.dataset_name)

                        test_blocks.append(len(test_method.call_assertion_sequences))
                        call_sequence.append(sum([len(call_assertion_sequence.call_sequence_details) for
                                                  call_assertion_sequence in test_method.call_assertion_sequences]))
                        assertion_sequence.append(sum([len(call_assertion_sequence.assertion_details) for
                                                       call_assertion_sequence in
                                                       test_method.call_assertion_sequences]))
                        if len(test_method.call_assertion_sequences) == 1:
                            call_assertion_sequences_with__length_1 += 1
                        elif len(test_method.call_assertion_sequences) > 1:
                            call_assertion_sequences_with__length_gt_1 += len(test_method.call_assertion_sequences)

        # Can store somewhere
        top_library_called = top_library_called.top_k_serialized()
        top_ncloc = top_ncloc.top_k_serialized()

        outlier_tracking = {
            "top_library_called": top_library_called,
            "top_ncloc": top_ncloc,
        }
        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            self.extract_statistics_util.get_box_plot(elements=call_sequence,
                                                      labels=['Call sequence length'],
                                                      title='Box plot of call sequence length',
                                                      filename='test_method_call_sequence_box_plot')
            self.extract_statistics_util.get_box_plot(elements=assertion_sequence,
                                                      labels=['Assertion sequence length'],
                                                      title='Box plot of assertion sequence length',
                                                      filename='test_method_assertion_sequence_box_plot')
            self.extract_statistics_util.get_box_plot(elements=constructor_called,
                                                      labels=['# of constructors created in test method'],
                                                      title='Box plot of # of constructors created in test method',
                                                      filename='test_method_constructor_box_plot')
            self.extract_statistics_util.get_box_plot(elements=library_called,
                                                      labels=['# of library objects called in test method'],
                                                      title='Box plot of # of library objects called in test method',
                                                      filename='test_method_library_box_plot')
            self.extract_statistics_util.get_box_plot(elements=test_blocks,
                                                      labels=['# of test blocks in test method'],
                                                      title='Box plot of # of test blocks in test method',
                                                      filename='test_method_assertion_sequence_box_plot')
            self.extract_statistics_util.get_box_plot(elements=ncloc_per_method,
                                                      labels=['NCLOC'],
                                                      title='Box plot of NCLOC of setup methods',
                                                      filename='test_method_ncloc')
            self.extract_statistics_util.get_box_plot(elements=cyclomatic_complexity_per_method,
                                                      labels=['Cyclomatic complexity'],
                                                      title='Box plot of cyclomatic complexity of setup methods',
                                                      filename='test_method_cyclomatic_complexity')
            self.extract_statistics_util.get_box_plot(elements=objects_created,
                                                      labels=['Objects created inside setup method'],
                                                      title='Box plot of Objects created inside setup method',
                                                      filename='test_method_objects_created')
            self.extract_statistics_util.get_box_plot(elements=mocks_created,
                                                      labels=['Mocking objects created inside setup method'],
                                                      title='Box plot of mocking objects created inside setup method',
                                                      filename='test_method_mocking_objects')
            if len(mocking_frameworks)>0:
                self.extract_statistics_util.get_distribution_figures(elements=mocking_frameworks,
                                                                      xlabel='Mocking Frameworks',
                                                                      ylabel='Percentage (%)',
                                                                      title='Distribution of Mocking Frameworks in Tests',
                                                                      filename='test_method_mocking_framework_distribution')
            self.extract_statistics_util.get_distribution_figures(elements=testing_types,
                                                                  xlabel='Testing types',
                                                                  ylabel='Percentage (%)',
                                                                  title='Distribution of Testing Types in Tests',
                                                                  filename='test_method_testing_types_distribution')

        return {"ncloc_per_test_method": self.extract_statistics_util.get_summary_stats(ncloc_per_method),
                "cyclomatic_complexity_per_method": self.extract_statistics_util.get_summary_stats(cyclomatic_complexity_per_method),
                "total_helper_methods": total_helper_methods,
                "total_helper_methods_ncloc": total_helper_methods_ncloc,
                "helper_method_distribution": self.extract_statistics_util.get_percentiles(helper_methods),
                "testing_types": self.extract_statistics_util.
                get_distribution_percentage(testing_types),
                "objects_created": self.extract_statistics_util.get_percentiles(objects_created),
                "mocks_created": self.extract_statistics_util.get_percentiles(mocks_created) if len(mocks_created) > 0
                else None,
                "constructors_created": self.extract_statistics_util.get_percentiles(constructor_called),
                "library_method_created": self.extract_statistics_util.get_percentiles(library_called),
                "test_blocks": self.extract_statistics_util.get_percentiles(test_blocks),
                "call_sequence_length": self.extract_statistics_util.get_percentiles(call_sequence),
                "call_assertion_sequences_with__length_gt_1": call_assertion_sequences_with__length_gt_1,
                "call_assertion_sequences_with__length_1": call_assertion_sequences_with__length_1,
                # This is more accurately "average number of non-assertion callables in each method"
                "call_assertion_sequence_length": self.extract_statistics_util.get_percentiles(assertion_sequence),
                # This is more accurately "average number of assertions in each method"
                "mocking_framework_distribution": self.extract_statistics_util.
                get_distribution_percentage(mocking_frameworks),
                "outlier_tracking": outlier_tracking,
                "testing_types_per_test": testing_types_per_test}
