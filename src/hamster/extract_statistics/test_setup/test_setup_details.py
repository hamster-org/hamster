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


class TestSetupDetails:
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
        code_details = []
        total_projects = 0
        total_mocking = 0
        setup_execution_order = []
        before_method_setup_percentage = 0
        before_class_setup_percentage = 0
        print()
        print("Processing setup statistics...")
        with (ProgressBarFactory.get_progress_bar() as p):
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                if len(project_analysis.test_class_analyses) > 0:
                    total_projects += 1
                for test_class in project_analysis.test_class_analyses:
                    for setup_analysis in test_class.setup_analyses:
                        if setup_analysis.number_of_mocks_created>0:
                            total_mocking += 1
                        size_bucket = None
                        if setup_analysis is not None:
                            if setup_analysis.ncloc_with_helpers > 0:
                                if 0 < setup_analysis.ncloc_with_helpers <= 2:
                                    size_bucket = SetupSize.ONE_TO_TWO.value
                                elif 2 < setup_analysis.ncloc_with_helpers <= 5:
                                    size_bucket = SetupSize.THREE_TO_FIVE.value
                                elif 5 < setup_analysis.ncloc_with_helpers <= 10:
                                    size_bucket = SetupSize.FIVE_TO_TEN.value
                                else:
                                    size_bucket = SetupSize.TEN_PLUS.value
                                code_details.append({"dataset": project_analysis.dataset_name,
                                                     "test_class": test_class.qualified_class_name,
                                                     "size": size_bucket,
                                                     # "code": setup_analysis.code
                                                     })
                                ncloc_per_method.append(setup_analysis.ncloc_with_helpers)
                                cyclomatic_complexity.append(setup_analysis.cyclomatic_complexity_with_helpers)
                                objects_created.append(setup_analysis.number_of_objects_created)
                                if setup_analysis.number_of_mocks_created > 0:
                                    mocks_created.append(setup_analysis.number_of_mocks_created)
                                if setup_analysis.execution_order is not None:
                                    if setup_analysis.execution_order == ExecutionOrder.BEFORE_CLASS:
                                        before_class_setup_percentage += 1
                                    if setup_analysis.execution_order == ExecutionOrder.BEFORE_EACH_TEST:
                                        before_method_setup_percentage += 1
                                    setup_execution_order.append(setup_analysis.execution_order)
                                if setup_analysis.mocking_frameworks_used is not None:
                                    mocking_frameworks.extend([mocking_framework_used.value
                                                               for mocking_framework_used in
                                                               setup_analysis.mocking_frameworks_used
                                                               if mocking_framework_used is not None])
        before_class_setup_percentage = before_class_setup_percentage / len(setup_execution_order) if len(setup_execution_order)>0 else 0
        before_method_setup_percentage = before_method_setup_percentage / len(setup_execution_order) if len(setup_execution_order)>0 else 0

        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            self.extract_statistics_util.get_box_plot(elements=ncloc_per_method,
                                                      labels=['NCLOC'],
                                                      title='Box plot of NCLOC of setup methods',
                                                      filename='setup_ncloc')
            self.extract_statistics_util.get_box_plot(elements=cyclomatic_complexity,
                                                      labels=['Cyclomatic Complexity'],
                                                      title='Box plot of Cyclomatic Complexity of setup methods',
                                                      filename='setup_cyclomatic_complexity')
            self.extract_statistics_util.get_box_plot(elements=objects_created,
                                                      labels=['Objects created inside setup method'],
                                                      title='Box plot of Objects created inside setup method',
                                                      filename='setup_objects_created')
            if len(mocks_created) > 0:
                self.extract_statistics_util.get_box_plot(elements=mocks_created,
                                                          labels=['Mocking objects created inside setup method'],
                                                          title='Box plot of mocking objects created inside setup method',
                                                          filename='setup_mocking_objects')
            if len(mocking_frameworks) > 0:
                self.extract_statistics_util.get_distribution_figures(elements=mocking_frameworks,
                                                                      xlabel='Mocking Frameworks',
                                                                      ylabel='Percentage (%)',
                                                                      title='Distribution of Mocking Frameworks in Setup Methods',
                                                                      filename='setup_mocking_framework_distribution')
        code_details.sort(key=lambda x: size_order[x["size"]])
        return {"ncloc": self.extract_statistics_util.get_percentiles(ncloc_per_method),
                "total_setup_methods": len(ncloc_per_method),
                "total_setup_method_with_mocking": total_mocking,
                "avg_setup_methods": len(ncloc_per_method) / total_projects,
                "cyclomatic_complexity": self.extract_statistics_util.get_percentiles(cyclomatic_complexity),
                "objects_created": self.extract_statistics_util.get_percentiles(objects_created),
                "mocks_created": self.extract_statistics_util.get_percentiles(mocks_created) if len(mocks_created) > 0 else None,
                "before_class_setup_percentage": before_class_setup_percentage,
                "before_method_setup_percentage": before_method_setup_percentage,
                "mocking_framework_distribution": self.extract_statistics_util.
                get_distribution_percentage(mocking_frameworks) if len(mocking_frameworks) > 0 else None,
                "code_details": code_details}
