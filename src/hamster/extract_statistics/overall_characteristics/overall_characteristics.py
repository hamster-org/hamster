import json
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from hamster.code_analysis.model.models import ProjectAnalysis, AppType, TestType, TestingFramework
from hamster.code_analysis.utils.constants import testing_frameworks_by_type
from hamster.extract_statistics.utils import ExtractStatisticsUtils, TopK
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory


class OverallCharacteristics:
    def __init__(self, all_project_analysis: List[ProjectAnalysis], output_format: OutputFormatType,
                 statistics_store_path: Path):
        self.output_format = output_format
        self.all_project_analyses = all_project_analysis
        self.statistics_store_path = statistics_store_path
        self.extract_statistics_utils = ExtractStatisticsUtils(filepath=self.statistics_store_path)

    def extract_details(self) -> dict | str:
        total_tests = 0
        se_projects = []
        api_projects = []
        tests_per_projects = []
        total_application_class = []
        total_application_method = []
        total_test_methods = []
        total_cc = []
        test_framework_per_class = {}
        testing_frameworks = []
        test_nc_loc = []
        fixtures_per_project = []
        testing_frameworks_per_project = {}
        app_types = {}
        total_test_class = 0
        test_class_per_project = []
        android_projects = []
        class_details = {}
        total_projects = 0
        test_types = []
        focal_classes = []
        focal_methods = []
        one_or_more_focal_class = []
        unit_module_focal_method_one_focal_method = 0
        unit_module_focal_method_gt_one_focal_method = 0
        focal_class_vs_focal_method_count = []
        no_focal_method_found = 0
        testing_framework_upset_diagram = {}
        top_num_tests_methods_in_class = TopK(10, "number of test methods in class", keep_largest=True)

        # Go through each project and collect details
        print()
        print("Processing project-level statistics...")
        with ProgressBarFactory.get_progress_bar() as p:
            for project_analysis in p.track(self.all_project_analyses, total=len(self.all_project_analyses)):
                frameworks_in_project = []
                total_projects += 1
                tests_per_project = 0
                test_class_count = 0
                test_method_count = 0
                total_fixtures = 0

                for a_type in project_analysis.application_types:
                    if a_type.value not in app_types:
                        app_types[a_type.value] = 1
                    else:
                        app_types[a_type.value] += 1
                for test_class in project_analysis.test_class_analyses:
                    total_test_class += 1
                    test_class_count += 1
                    for test_framework_in_class in test_class.testing_frameworks:
                        framework_group = self.map_testing_framework_group(test_framework_in_class.value)
                        # if framework_group != '':
                        if framework_group not in testing_framework_upset_diagram:
                            testing_framework_upset_diagram[
                                framework_group] = [
                                project_analysis.dataset_name]
                        else:
                            previous_projects = testing_framework_upset_diagram[
                                framework_group]
                            previous_projects.append(project_analysis.dataset_name)
                            testing_framework_upset_diagram[framework_group] = list(
                                set(previous_projects))
                        if test_framework_in_class.value not in test_framework_per_class:
                            test_framework_per_class[test_framework_in_class.value] = 1

                        else:

                            test_framework_per_class[test_framework_in_class.value] += 1
                    total_fixtures += (len(test_class.setup_analyses) + len(test_class.teardown_analyses))
                    total_tests += len(test_class.test_method_analyses)
                    test_method_count += len(test_class.test_method_analyses)
                    top_num_tests_methods_in_class.add(len(test_class.test_method_analyses),
                                                       qualified_class_name=test_class.qualified_class_name,
                                                       project_name=project_analysis.dataset_name)

                    tests_per_project += len(test_class.test_method_analyses)
                    frameworks_in_project.extend(
                        [test_framework.value for test_framework in test_class.testing_frameworks])
                    testing_frameworks.extend(
                        [test_framework.value for test_framework in test_class.testing_frameworks])
                    for test_method in test_class.test_method_analyses:
                        test_types.append(test_method.test_type.value)
                        test_nc_loc.append(test_method.ncloc_with_helpers)
                        if test_method.test_type == TestType.UNIT_MODULE:
                            focal_method_count = 0

                            for fc in test_method.focal_classes:
                                focal_method_count += len(fc.focal_method_names)

                            if focal_method_count == 1:
                                unit_module_focal_method_one_focal_method += 1
                            elif focal_method_count > 1:
                                unit_module_focal_method_gt_one_focal_method += 1
                            else:
                                no_focal_method_found += 1
                        if test_method.test_type == TestType.API:
                            api_projects.append(project_analysis.dataset_name)
                        if test_method.test_type == TestType.UNIT_MODULE or \
                                test_method.test_type == TestType.INTEGRATION:
                            focal_method_count = 0

                            for fc in test_method.focal_classes:
                                focal_method_count += len(fc.focal_method_names)
                            if len(test_method.focal_classes) > 0:
                                focal_class_vs_focal_method_count.append(
                                    {"focal_class_count": len(test_method.focal_classes),
                                     "focal_method_count": focal_method_count})
                            if len(test_method.focal_classes) == 0:
                                one_or_more_focal_class.append("NO CLASS DETECTED")
                            elif len(test_method.focal_classes) == 1:
                                one_or_more_focal_class.append("YES")
                            else:
                                one_or_more_focal_class.append("NO")
                            focal_classes.append(len(test_method.focal_classes))
                            for focal_class in test_method.focal_classes:
                                if len(focal_class.focal_method_names) > 1:
                                    focal_methods.append(len(focal_class.focal_method_names))
                fixtures_per_project.append(total_fixtures)
                if AppType.ANDROID in project_analysis.application_types:
                    android_projects.append(project_analysis.dataset_name)
                if len(project_analysis.test_class_analyses) > 0:
                    if AppType.JAVA_SE in project_analysis.application_types:
                        se_projects.append(project_analysis.dataset_name)
                    total_application_class.append(project_analysis.application_class_count)
                    total_application_method.append(project_analysis.application_method_count)
                    total_cc.append(project_analysis.application_cyclomatic_complexity)
                    total_test_methods.append(test_method_count)
                    class_details[project_analysis.dataset_name] = {
                        "class_count": project_analysis.application_class_count,
                        "method_count": project_analysis.application_method_count,
                        "cyclomatic_complexity": project_analysis.application_cyclomatic_complexity,
                        "test_count": test_method_count}
                    tests_per_projects.append(tests_per_project)
                    test_class_per_project.append(test_class_count)
                    testing_frameworks_per_project[project_analysis.dataset_name] = frameworks_in_project

        avg_tests_per_project = np.mean(tests_per_projects)
        median_tests_per_project = np.median(tests_per_projects)
        for tf in test_framework_per_class:
            test_framework_per_class[tf] = test_framework_per_class[tf] / total_test_class
        for a_type in app_types:
            app_types[a_type] = app_types[a_type] / total_projects

        # Can store somewhere
        top_num_tests_methods_in_class = top_num_tests_methods_in_class.top_k_serialized()

        outlier_tracking = {
            "top_num_test_methods_in_class": top_num_tests_methods_in_class,
        }
        df = pd.DataFrame(focal_class_vs_focal_method_count)
        # Compute distribution
        distribution_of_testing_framework = (self.extract_statistics_utils
                                             .get_distribution_percentage(testing_frameworks))
        # distribution_of_app_type = (self.extract_statistics_utils
        #                             .get_distribution_percentage(app_types))

        if self.output_format == OutputFormatType.JSON_PDF_FIGURES:
            # save testing framework figure
            (self.extract_statistics_utils.get_distribution_figures
             (elements=testing_frameworks,
              xlabel='Testing Frameworks',
              ylabel='Percentage (%)',
              title="Distribution of Testing Frameworks",
              filename='distribution_of_testing_frameworks'))
            self.extract_statistics_utils.upset_diagram(testing_framework_upset_diagram, 'upset_diagram')
            # Heatmap
            self.extract_statistics_utils.scatter_plot(total_application_class, total_test_methods,
                                                       "Application Class count",
                                                       "Test count",
                                                       "class_count_vs_test_count")

            self.extract_statistics_utils.scatter_plot(total_application_method, total_test_methods,
                                                       "Application Method count",
                                                       "Test count",
                                                       "method_count_vs_test_count")

            self.extract_statistics_utils.scatter_plot(total_cc, total_test_methods,
                                                       "Application Cyclomatic complexity",
                                                       "Test count",
                                                       "cc_vs_test_count")
            self.extract_statistics_utils.get_box_plot(
                elements=[fc["focal_method_count"] for fc in focal_class_vs_focal_method_count],
                labels=["Focal Method Count"],
                title='',
                filename="focal_method_box_plot"
                )
            self.extract_statistics_utils.get_box_plot(
                elements=[fc["focal_class_count"] for fc in focal_class_vs_focal_method_count],
                labels=["Focal Class Count"],
                title='',
                filename="focal_class_box_plot"
            )
            # save app framework figure
            # (self.extract_statistics_utils
            #  .get_distribution_figures(elements=app_types,
            #                            xlabel='Application types',
            #                            ylabel='Percentage (%)',
            #                            title="Distribution of Application types",
            #                            filename='distribution_of_application_types'))
        # api_projects = list(set(api_projects))
        one_focal_class = len([1 for item in one_or_more_focal_class if item == "YES"]) / len(one_or_more_focal_class)
        more_than_one_focal_class = (len([1 for item in one_or_more_focal_class if item == "NO"]) /
                                     len(one_or_more_focal_class))
        unable_to_generate = (len([1 for item in one_or_more_focal_class if item == "NO CLASS DETECTED"]) /
                              len(one_or_more_focal_class))
        return {
            "total_application_class": sum(total_application_class),
            "avg_application_class": np.mean(total_application_class),
            "application_class_distribution": self.extract_statistics_utils.get_percentiles(total_application_class),
            "total_application_method": sum(total_application_method),
            "avg_application_method": np.mean(total_application_method),
            "application_method_distribution": self.extract_statistics_utils.get_percentiles(
                total_application_method),

            "total_test_class": total_test_class,
            "avg_test_class_per_project": np.mean(test_class_per_project),
            "test_class_distribution": self.extract_statistics_utils.get_percentiles(
                test_class_per_project),
            "total_tests": total_tests,
            "avg_tests_per_project": avg_tests_per_project,
            "test_method_distribution": self.extract_statistics_utils.get_percentiles(
                tests_per_projects),
            "total_fixtures": sum(fixtures_per_project),
            "avg_fixtures_per_project": np.mean(fixtures_per_project),
            "test_fixtures_distribution": self.extract_statistics_utils.get_percentiles(
                fixtures_per_project),
            "total_test_ncloc": sum(test_nc_loc),
            "avg_test_ncloc": np.mean(test_nc_loc),
            "test_ncloc_distribution": self.extract_statistics_utils.get_percentiles(
                test_nc_loc),
            # "median_tests_per_project": median_tests_per_project,
            "distribution_of_testing_framework": test_framework_per_class,
            "distribution_of_app_type": app_types,
            # "outlier_tracking": outlier_tracking,
            "test_type_distribution": (self.extract_statistics_utils
                                       .get_distribution_percentage(test_types)),
            "focal_class_distribution": (self.extract_statistics_utils
                                         .get_percentiles(focal_classes)),
            "focal_method_distribution": (self.extract_statistics_utils
                                          .get_percentiles(focal_methods)),
            "one_focal_class": one_focal_class,
            "more_than_one_focal_class": more_than_one_focal_class,
            "unable_to_detect": unable_to_generate,
            "unit-module-one-focal-method": unit_module_focal_method_one_focal_method / (
                    unit_module_focal_method_gt_one_focal_method + unit_module_focal_method_one_focal_method + no_focal_method_found),
            "unit-module-gt_one-focal-method": unit_module_focal_method_gt_one_focal_method / (
                    unit_module_focal_method_gt_one_focal_method + unit_module_focal_method_one_focal_method + no_focal_method_found),
            "no-focal-method-found": no_focal_method_found / (
                    unit_module_focal_method_gt_one_focal_method + unit_module_focal_method_one_focal_method + no_focal_method_found),
            # "API_projects": api_projects
            # "android_projects": android_projects,
            # "class_details": json.dumps(class_details, indent=4),
            # "SE projects": se_projects
            # "testing_framework_distribution": json.dumps(testing_frameworks_per_project, indent=4)
        }

    @staticmethod
    def map_testing_framework_group(testing_framework: str) -> str:
        for item in testing_frameworks_by_type:
            if testing_framework in testing_frameworks_by_type[item]:
                return item
        return ''
