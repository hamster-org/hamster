from enum import Enum
from pathlib import Path
from typing import List

from hamster.code_analysis.model.models import ProjectAnalysis, ExecutionOrder
from hamster.extract_statistics.utils import ExtractStatisticsUtils
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory


class SetupSize(str, Enum):
    ONE_TO_TWO = "1-2"
    THREE_TO_FIVE = "3-5"
    FIVE_TO_TEN = "5-10"
    TEN_PLUS = "10+"


size_order = {
    SetupSize.ONE_TO_TWO: 1,
    SetupSize.THREE_TO_FIVE: 2,
    SetupSize.FIVE_TO_TEN: 3,
    SetupSize.TEN_PLUS: 4
}


class TestTeardownDetails:
    def __init__(self, all_project_analysis: List[ProjectAnalysis], output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path
        self.extract_statistics_util = ExtractStatisticsUtils(filepath=statistics_store_path)

    def extract_details(self) -> dict | str:
        ncloc_per_method = []
        cyclomatic_complexity = []
        objects_created = []
        mocks_created = []
        mocking_frameworks = []
        constructor_called = []
        library_called = []
        cleanup_type_details = []
        cleanup = []
        assertion = []
        code_details = []
        total_projects = 0
        teardown_execution_order = []
        before_method_teardown_percentage = 0
        before_class_teardown_percentage = 0
        print()
        print("Processing teardown statistics...")
        with (ProgressBarFactory.get_progress_bar() as p):
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                if len(project_analysis.test_class_analyses) > 0:
                    total_projects += 1
                for test_class in project_analysis.test_class_analyses:
                    for teardown_analysis in test_class.teardown_analyses:
                        size_bucket = None
                        if teardown_analysis is not None:
                            if teardown_analysis.ncloc_with_helpers > 0:
                                library_called.append(len(teardown_analysis.library_call_details))
                                constructor_called.append(len(teardown_analysis.constructor_call_details))
                                assertion.append(teardown_analysis.number_of_assertions)
                                cleanup.append(teardown_analysis.number_of_cleanup_calls)
                                if teardown_analysis.cleanup_details is not None:
                                    for cleanup_info in teardown_analysis.cleanup_details:
                                        for type in cleanup_info.cleanup_type:
                                            cleanup_type_details.append(type.value)
                                code_details.append({"dataset": project_analysis.dataset_name,
                                                     "test_class": test_class.qualified_class_name,
                                                    "number_of_assertions": teardown_analysis.number_of_assertions
                                                     # "code": teardown_analysis.code
                                                     })
                                ncloc_per_method.append(teardown_analysis.ncloc_with_helpers)
                                cyclomatic_complexity.append(teardown_analysis.cyclomatic_complexity_with_helpers)
                                objects_created.append(teardown_analysis.number_of_objects_created)


                                if teardown_analysis.execution_order is not None:
                                    if teardown_analysis.execution_order == ExecutionOrder.BEFORE_CLASS:
                                        before_class_teardown_percentage += 1
                                    if teardown_analysis.execution_order == ExecutionOrder.BEFORE_EACH_TEST:
                                        before_method_teardown_percentage += 1
                                    teardown_execution_order.append(teardown_analysis.execution_order)
        if len(teardown_execution_order) > 0:
            before_class_teardown_percentage = before_class_teardown_percentage / len(teardown_execution_order)
            before_method_teardown_percentage = before_method_teardown_percentage / len(teardown_execution_order)
        else:
            before_class_teardown_percentage = 0
            before_method_teardown_percentage = 0

        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            self.extract_statistics_util.get_box_plot(elements=ncloc_per_method,
                                                      labels=['NCLOC'],
                                                      title='Box plot of NCLOC of teardown methods',
                                                      filename='teardown_ncloc')
            self.extract_statistics_util.get_box_plot(elements=cyclomatic_complexity,
                                                      labels=['Cyclomatic Complexity'],
                                                      title='Box plot of Cyclomatic Complexity of teardown methods',
                                                      filename='teardown_cyclomatic_complexity')
            self.extract_statistics_util.get_box_plot(elements=objects_created,
                                                      labels=['Objects created inside teardown method'],
                                                      title='Box plot of Objects created inside teardown method',
                                                      filename='teardown_objects_created')
            if len(mocks_created) > 0:
                self.extract_statistics_util.get_box_plot(elements=mocks_created,
                                                          labels=['Mocking objects created inside teardown method'],
                                                          title='Box plot of mocking objects created inside teardown method',
                                                          filename='teardown_mocking_objects')
            if len(mocking_frameworks) > 0:
                self.extract_statistics_util.get_distribution_figures(elements=mocking_frameworks,
                                                                      xlabel='Mocking Frameworks',
                                                                      ylabel='Percentage (%)',
                                                                      title='Distribution of Mocking Frameworks in teardown Methods',
                                                                      filename='teardown_mocking_framework_distribution')

        return {"ncloc": self.extract_statistics_util.get_percentiles(ncloc_per_method),
                "total_teardown_methods": len(ncloc_per_method),
                "avg_teardown_methods": len(ncloc_per_method) / total_projects,
                "library_call_details": self.extract_statistics_util.get_percentiles(library_called),
                "constructor_calls": self.extract_statistics_util.get_percentiles(constructor_called),
                "cleanup_calls": self.extract_statistics_util.get_percentiles(cleanup),
                "cleanup_type_distribution": self.extract_statistics_util.get_distribution_percentage(cleanup_type_details) if len(cleanup_type_details) > 0 else None,
                "cyclomatic_complexity": self.extract_statistics_util.get_percentiles(cyclomatic_complexity),
                "objects_created": self.extract_statistics_util.get_percentiles(objects_created),
                # "mocks_created": self.extract_statistics_util.get_percentiles(mocks_created) if len(mocks_created) > 0 else None,
                "before_class_teardown_percentage": before_class_teardown_percentage,
                "before_method_teardown_percentage": before_method_teardown_percentage,
                "mocking_framework_distribution": self.extract_statistics_util.
                get_distribution_percentage(mocking_frameworks) if len(mocking_frameworks) > 0 else None,
                "code_details": code_details}
