from typing import List, Dict, Tuple

from cldk.analysis.java import JavaAnalysis

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.model.models import ProjectAnalysis, AppType, TestingFramework
from hamster.code_analysis.test_statistics.test_class_analysis_info import TestClassAnalysisInfo
from hamster.code_analysis.utils import constants
from hamster.utils.pretty.progress_bar import ProgressBarFactory


class ProjectAnalysisInfo:
    def __init__(self, analysis: JavaAnalysis, dataset_name: str):
        self.analysis = analysis
        self.dataset_name = dataset_name

    def gather_project_analysis_info(self) -> ProjectAnalysis:
        """
        Gather project analysis data
        Returns:
            ProjectAnalysis: project analysis details
        """
        dataset_name = self.dataset_name
        application_types = self.__get_application_types()
        test_class_analyses = []
        test_class_methods, application_classes = CommonAnalysis(self.analysis).get_test_methods_classes_and_application_classes()

        test_class_analysis_obj = TestClassAnalysisInfo(
            analysis=self.analysis,
            dataset_name=self.dataset_name,
            application_classes=application_classes,
        )

        print(f"Processing {self.dataset_name} with {len(test_class_methods)} test classes...")
        with (ProgressBarFactory.get_progress_bar() as p):
            for test_class in p.track(test_class_methods, total=len(test_class_methods)):
                test_class_analyses.append(test_class_analysis_obj.get_test_class_analysis(
                    qualified_class_name = test_class,
                    test_methods = test_class_methods[test_class],
                ))

        application_method_count, application_cyclomatic_complexity = self.__get_application_method_details(
            classes=application_classes)

        return ProjectAnalysis(dataset_name=dataset_name,
                               application_class_count=len(application_classes),
                               application_method_count=application_method_count,
                               application_cyclomatic_complexity=application_cyclomatic_complexity,
                               application_types=application_types,
                               test_class_analyses=test_class_analyses)

    def __get_application_method_details(self, classes: List[str]):
        """
        Get application method count and total cyclomatic complexity
        Args:
            classes: application class

        Returns:
            Tuple[int, int]: application method count and total cyclomatic complexity
        """
        application_method_count = 0
        application_cyclomatic_complexity = 0
        for class_name in classes:
            methods = self.analysis.get_methods_in_class(class_name)
            application_method_count += len(methods)
            for method in methods:
                application_cyclomatic_complexity += methods[method].cyclomatic_complexity
        return application_method_count, application_cyclomatic_complexity

    def __get_application_types(self) -> List[AppType]:
        app_type = []
        imports = []
        non_app_imports_dict = CommonAnalysis(self.analysis).get_imports(is_add_application_class=False)
        non_app_imports = list(non_app_imports_dict.keys())
        for non_app_import in non_app_imports:
            imports.extend(non_app_import)
        imports = list(set(imports))
        for app_import in imports:
            if AppType.WEB_APPLICATION not in app_type:
                for web_app_import in constants.WEB_APPLICATION:
                    if app_import.startswith(web_app_import):
                        app_type.append(AppType.WEB_APPLICATION)

            if AppType.WEB_API not in app_type:
                for web_api_import in constants.WEB_API:
                    if app_import.startswith(web_api_import):
                        app_type.append(AppType.WEB_API)

            if AppType.JAVA_EE not in app_type:
                for java_ee_import in constants.JAVA_EE:
                    if app_import.startswith(java_ee_import):
                        app_type.append(AppType.JAVA_EE)

            if AppType.ANDROID not in app_type:
                for android_import in constants.ANDROID:
                    if app_import.startswith(android_import):
                        app_type.append(AppType.ANDROID)
        if len(app_type) == 0:
            app_type.append(AppType.JAVA_SE)
        return app_type
