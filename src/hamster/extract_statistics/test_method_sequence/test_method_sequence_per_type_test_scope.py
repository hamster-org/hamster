from itertools import combinations
from pathlib import Path
from typing import List

from hamster.code_analysis.model.models import ProjectAnalysis, TestType
from hamster.extract_statistics.utils import ExtractStatisticsUtils, TopK
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory


class TestMethodPerTestScope:
    def __init__(self, all_project_analysis: List[ProjectAnalysis], output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path
        self.extract_statistics_util = ExtractStatisticsUtils(filepath=statistics_store_path)

    def extract_details(self) -> dict | None | str:
        ncloc_per_method = {}
        cyclomatic_complexity_per_method = {}
        total_tests = 0
        total_ui_tests = 0
        total_api_test = 0
        total_library_test = 0
        total_rest_of_the_tests = 0
        helper_methods = []
        is_mocked_used = {}
        call_assertion_sequence = {}
        total_call_sequences = 0
        objects_created = {}
        mocks_created = {}
        constructor_called = {}
        application_called = {}
        call_sequence_match = {}
        all_order_independent_matches = {
            '100% match': 0,
            '>=70% match': 0,
            '>=50% match': 0,
            '>=30% match': 0,
            '<30% match': 0
        }
        all_order_dependent_matches = {
            '100% match': 0,
            '>=70% match': 0,
            '>=50% match': 0,
            '>=30% match': 0,
            '<30% match': 0
        }
        library_called = {}
        test_blocks = []
        call_sequence = {}
        assertion_sequence = {}

        # top_library_called = TopK(10, "number of library calls in method", keep_largest=True)
        # top_ncloc = TopK(10, "number of non-comment lines of code in method", keep_largest=True)

        print()
        print("Processing method statistics per test scope...")
        with ProgressBarFactory.get_progress_bar() as p:
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                call_sequence_match[project_analysis.dataset_name] = []
                for test_class in project_analysis.test_class_analyses:
                    for test_method in test_class.test_method_analyses:
                        total_tests += 1
                        if test_method.test_type == TestType.UI:
                            total_ui_tests += 1
                        elif test_method.test_type == TestType.API:
                            total_api_test += 1
                        elif test_method.test_type == TestType.LIBRARY:
                            total_library_test += 1
                        elif test_method.test_type in [TestType.UNIT_MODULE, TestType.UNIT, TestType.INTEGRATION]:
                            total_rest_of_the_tests += 1

                        if test_method.test_type.value in ncloc_per_method:
                            ncloc_per_method[test_method.test_type.value].append(test_method.ncloc_with_helpers)
                        else:
                            ncloc_per_method[test_method.test_type.value] = [test_method.ncloc_with_helpers]

                        if test_method.test_type.value in cyclomatic_complexity_per_method:
                            cyclomatic_complexity_per_method[test_method.test_type.value].append(test_method.cyclomatic_complexity_with_helpers)
                        else:
                            cyclomatic_complexity_per_method[test_method.test_type.value] = [test_method.cyclomatic_complexity_with_helpers]

                        if test_method.test_type.value in objects_created:
                            objects_created[test_method.test_type.value].append(test_method.number_of_objects_created)
                        else:
                            objects_created[test_method.test_type.value] = [test_method.number_of_objects_created]

                        if test_method.number_of_mocks_created > 0:
                            if test_method.test_type.value in mocks_created:
                                mocks_created[test_method.test_type.value].append(test_method.number_of_mocks_created)
                            else:
                                mocks_created[test_method.test_type.value] = [test_method.number_of_mocks_created]
                        # else:
                        #     if test_method.test_type.value in mocks_created:
                        #         mocks_created[test_method.test_type.value].append(0)
                        #     else:
                        #         mocks_created[test_method.test_type.value] = [0]

                        if test_method.test_type.value in constructor_called:
                            constructor_called[test_method.test_type.value].append(
                                len(test_method.constructor_call_details))
                        else:
                            constructor_called[test_method.test_type.value] = [
                                len(test_method.constructor_call_details)]

                        if test_method.test_type.value in library_called:
                            library_called[test_method.test_type.value].append(len(test_method.library_call_details))
                        else:
                            library_called[test_method.test_type.value] = [len(test_method.library_call_details)]

                        if test_method.test_type.value in application_called:
                            application_called[test_method.test_type.value].append(
                                len(test_method.application_call_details))
                        else:
                            application_called[test_method.test_type.value] = [
                                len(test_method.application_call_details)]

                        if test_method.test_type.value in call_sequence:
                            call_sequence[test_method.test_type.value].append(
                                sum([len(call_assertion_sequence.call_sequence_details) for
                                     call_assertion_sequence in test_method.call_assertion_sequences]))
                        else:
                            call_sequence[test_method.test_type.value] = [
                                sum([len(call_assertion_sequence.call_sequence_details) for
                                     call_assertion_sequence in test_method.call_assertion_sequences])]

                        if test_method.test_type.value in assertion_sequence:
                            assertion_sequence[test_method.test_type.value].append(
                                sum([len(call_assertion_sequence.assertion_details) for
                                     call_assertion_sequence in
                                     test_method.call_assertion_sequences]))
                        else:
                            assertion_sequence[test_method.test_type.value] = [
                                sum([len(call_assertion_sequence.call_sequence_details) for
                                     call_assertion_sequence in
                                     test_method.call_assertion_sequences])]

                        if test_method.test_type.value in call_assertion_sequence:
                            call_assertion_sequence[test_method.test_type.value].append(
                                len(test_method.call_assertion_sequences))
                        else:
                            call_assertion_sequence[test_method.test_type.value] = [
                                len(test_method.call_assertion_sequences)]

                        call_sequences = []
                        total_helper_methods = 0
                        if len(test_method.call_assertion_sequences) > 1:
                            for c_a_sequence in test_method.call_assertion_sequences:

                                call_sequences_per_sequence = []
                                total_call_sequences += 1
                                for call_sequence_detail in c_a_sequence.call_sequence_details:
                                    if call_sequence_detail.is_helper:
                                        total_helper_methods += 1
                                    fqmn = call_sequence_detail.receiver_type + '.' + call_sequence_detail.method_name \
                                        if call_sequence_detail.receiver_type is not None else call_sequence_detail.method_name
                                    call_sequences_per_sequence.append(fqmn)
                                call_sequences.append(call_sequences_per_sequence)
                            order_in_matches, order_de_matches = self.extract_statistics_util.match_percentage(
                                call_sequences)
                            # if matches['100% match'] > 0 or matches['>=70% match']>0 or matches['>=50% match'] > 0:
                            #     call_sequence_match[project_analysis.dataset_name].append({"class": test_class.qualified_class_name,
                            #                                                                "method": test_method.method_signature,
                            #                                                                "match": matches})
                            # Count all matches
                            helper_methods.append(total_helper_methods)
                            for match in order_in_matches:
                                all_order_independent_matches[match] += order_in_matches[match]

                            for match in order_de_matches:
                                all_order_dependent_matches[match] += order_de_matches[match]
        total_mocks = 0
        for type in mocks_created:
            total_mocks += len(mocks_created[type])
        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            self.extract_statistics_util.multiple_thin_box_plot(list_of_dicts=[ncloc_per_method,
                                                                               cyclomatic_complexity_per_method,
                                                                               # objects_created,
                                                                               mocks_created,
                                                                               constructor_called,
                                                                               application_called,
                                                                               library_called,
                                                                               call_assertion_sequence,
                                                                               call_sequence,
                                                                               assertion_sequence],
                                                                filename='thin_box_plot',
                                                                figure_names=["NCLOC",
                                                                              "Cyclomatic complexity",
                                                                              "#_of mocks",
                                                                              "#_of constructor_calls",
                                                                              "#_of application_calls",
                                                                              "#_of library_calls",
                                                                              "#_of call-assertion sequences",
                                                                              "Call sequence length",
                                                                              "Assertion sequence length"])
            self.extract_statistics_util.thin_box_plot(input_data=ncloc_per_method,
                                                       filename='ncloc_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=cyclomatic_complexity_per_method,
                                                       filename='cyclomatic_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=objects_created,
                                                       filename='objects_created_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=mocks_created,
                                                       filename='mocks_created_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=constructor_called,
                                                       filename='constructor_called_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=application_called,
                                                       filename='application_called_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=library_called,
                                                       filename='library_called_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=call_assertion_sequence,
                                                       filename='call_assertion_sequence_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=call_sequence,
                                                       filename='call_sequences_thin_box_plot')
            self.extract_statistics_util.thin_box_plot(input_data=assertion_sequence,
                                                       filename='assertion_sequence_thin_box_plot')
        # if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
        #     self.extract_statistics_util.get_box_plot(elements=call_sequence,
        #                                               labels=['Call sequence length'],
        #                                               title='Box plot of call sequence length',
        #                                               filename='test_method_call_sequence_box_plot')
        #     self.extract_statistics_util.get_box_plot(elements=assertion_sequence,
        #                                               labels=['Assertion sequence length'],
        #                                               title='Box plot of assertion sequence length',
        #                                               filename='test_method_assertion_sequence_box_plot')
        #     self.extract_statistics_util.get_box_plot(elements=constructor_called,
        #                                               labels=['# of constructors created in test method'],
        #                                               title='Box plot of # of constructors created in test method',
        #                                               filename='test_method_constructor_box_plot')
        #     self.extract_statistics_util.get_box_plot(elements=library_called,
        #                                               labels=['# of library objects called in test method'],
        #                                               title='Box plot of # of library objects called in test method',
        #                                               filename='test_method_library_box_plot')
        #     self.extract_statistics_util.get_box_plot(elements=test_blocks,
        #                                               labels=['# of test blocks in test method'],
        #                                               title='Box plot of # of test blocks in test method',
        #                                               filename='test_method_assertion_sequence_box_plot')
        #     self.extract_statistics_util.get_box_plot(elements=ncloc_per_method,
        #                                               labels=['NCLOC'],
        #                                               title='Box plot of NCLOC of setup methods',
        #                                               filename='test_method_ncloc')
        #     self.extract_statistics_util.get_box_plot(elements=objects_created,
        #                                               labels=['Objects created inside setup method'],
        #                                               title='Box plot of Objects created inside setup method',
        #                                               filename='test_method_objects_created')
        #     self.extract_statistics_util.get_box_plot(elements=mocks_created,
        #                                               labels=['Mocking objects created inside setup method'],
        #                                               title='Box plot of mocking objects created inside setup method',
        #                                               filename='test_method_mocking_objects')
        #     if len(mocking_frameworks)>0:
        #         self.extract_statistics_util.get_distribution_figures(elements=mocking_frameworks,
        #                                                               xlabel='Mocking Frameworks',
        #                                                               ylabel='Percentage (%)',
        #                                                               title='Distribution of Mocking Frameworks in Tests',
        #                                                               filename='test_method_mocking_framework_distribution')
        #     self.extract_statistics_util.get_distribution_figures(elements=testing_types,
        #                                                           xlabel='Testing types',
        #                                                           ylabel='Percentage (%)',
        #                                                           title='Distribution of Testing Types in Tests',
        #                                                           filename='test_method_testing_types_distribution')
        # print(total_call_sequences)
        # print(all_matches)
        for match in all_order_dependent_matches:
            all_order_dependent_matches[match] = all_order_dependent_matches[match] / total_call_sequences

        for match in all_order_independent_matches:
            all_order_independent_matches[match] = all_order_independent_matches[match] / total_call_sequences
        return {
            "total_tests": total_tests,
            "total_ui_tests": total_ui_tests,
            "total_library_tests": total_library_test,
            "total_rest_of_the_tests": total_rest_of_the_tests,
            "ncloc_per_test_method": self.extract_statistics_util.get_percentiles_per_type(ncloc_per_method),
            "cyclomatic_complexity_per_test_method": self.extract_statistics_util.get_percentiles_per_type(cyclomatic_complexity_per_method),
            "objects_created": self.extract_statistics_util.get_percentiles_per_type(objects_created),
            "mocks_created": self.extract_statistics_util.get_percentiles_per_type(mocks_created) if len(
                mocks_created) > 0
            else None,
            "constructors_created": self.extract_statistics_util.get_percentiles_per_type(constructor_called),
            "application_created": self.extract_statistics_util.get_percentiles_per_type(application_called),
            "library_method_created": self.extract_statistics_util.get_percentiles_per_type(library_called),
            "number_of_call_assertion_sequence": self.extract_statistics_util.get_percentiles_per_type(
                call_assertion_sequence),
            "number_of_calls": self.extract_statistics_util.get_percentiles_per_type(call_sequence),
            # This is more accurately "average number of non-assertion callables in each method"
            "number_of_assertions": self.extract_statistics_util.get_percentiles_per_type(assertion_sequence),
            "total_order_dependent_match_distribution": all_order_dependent_matches,
            "total_order_independent_match_distribution": all_order_independent_matches,
            "total_call_sequences": total_call_sequences,
            "total_test_with_mock": total_mocks,
            "helper_method_distribution": self.extract_statistics_util.get_percentiles(helper_methods),
            "percentage_tests_with_helper_method": len([helper_method for helper_method in
                                                        helper_methods if helper_method > 0]) / total_tests
            # "match_by_project": call_sequence_match
        }
