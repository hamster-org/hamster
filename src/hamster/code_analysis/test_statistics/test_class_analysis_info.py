from typing import List

from cldk.analysis.java import JavaAnalysis

from hamster.code_analysis.model.models import TestClassAnalysis, TestingFramework, SetupAnalysis, TeardownAnalysis
from hamster.code_analysis.test_statistics.setup_analysis_info import SetupAnalysisInfo
from hamster.code_analysis.test_statistics.teardown_analysis_info import TeardownAnalysisInfo
from hamster.code_analysis.test_statistics.test_method_analysis_info import TestMethodAnalysisInfo
from hamster.code_analysis.common.common_analysis import CommonAnalysis


class TestClassAnalysisInfo:
    def __init__(self, analysis: JavaAnalysis, dataset_name: str, application_classes: List[str]) -> None:
        """
        Initializes the TestClassAnalysisInfo with the given analysis, dataset name, and application classes.

        Args:
            analysis: The JavaAnalysis instance.
            dataset_name: The name of the dataset.
            application_classes: List of application classes.
        """
        self.analysis = analysis
        self.dataset_name = dataset_name
        self.application_classes = application_classes

    def get_test_class_analysis(self, qualified_class_name: str, test_methods: List[str] | None) -> TestClassAnalysis:
        """
        Retrieves the analysis for a test class, including testing frameworks, setups, teardowns, and individual test method analyses.

        Args:
            qualified_class_name: The fully qualified name of the test class.
            test_methods: List of test method signatures, or None.

        Returns:
            TestClassAnalysis: The analysis object for the test class.
        """
        if not test_methods:
            raise Exception("Called test class analysis on class with no test methods...")

        testing_frameworks = CommonAnalysis(self.analysis).get_testing_frameworks_for_class(
            qualified_class_name=qualified_class_name)
        setup_analyses_info = self._get_setup_analysis_info(testing_frameworks=testing_frameworks,
                                                            test_class_qualified_name=qualified_class_name)
        teardown_analyses_info = self._get_teardown_analysis_info(testing_frameworks=testing_frameworks,
                                                                  test_class_qualified_name=qualified_class_name)
        is_order_dependent = self._is_test_order_dependent(test_class_qualified_name=qualified_class_name)
        is_bdd = self._is_bdd(testing_frameworks=testing_frameworks)

        setup_methods = SetupAnalysisInfo(self.analysis).get_setup_methods(
            qualified_class_name=qualified_class_name,
            testing_frameworks=testing_frameworks,
        )

        test_method_analysis = TestMethodAnalysisInfo(
            analysis = self.analysis,
            dataset_name = self.dataset_name,
            application_classes = self.application_classes,
        )

        # Analyze each test method individually
        test_method_analyses = []
        for test_method in test_methods:
            test_method_analysis_info = (
                test_method_analysis.get_test_method_analysis_info(
                    testing_frameworks=testing_frameworks,
                    qualified_class_name=qualified_class_name,
                    method_signature=test_method,
                    setup_methods=setup_methods,
                )
            )
            test_method_analyses.append(test_method_analysis_info)

        # Construct and return the TestClassAnalysis object with all collected data
        return TestClassAnalysis(qualified_class_name=qualified_class_name,
                                 testing_frameworks=testing_frameworks,
                                 setup_analyses=setup_analyses_info,
                                 teardown_analyses=teardown_analyses_info,
                                 test_method_analyses=test_method_analyses,
                                 is_order_dependent=is_order_dependent,
                                 is_bdd=is_bdd)

    @staticmethod
    def _is_bdd(testing_frameworks: List[TestingFramework]) -> bool:
        """
        Checks if BDD testing frameworks are being used

        Args:
            testing_frameworks:

        Returns:
            bool: True if any BDD framework is present, False otherwise.
        """
        return any(testing_framework in
                   [TestingFramework.SPOCK, TestingFramework.CUCUMBER,
                    TestingFramework.JBEHAVE, TestingFramework.SERENITY,
                    TestingFramework.GAUGE] for testing_framework in testing_frameworks)

    def _get_setup_analysis_info(self, testing_frameworks: List[TestingFramework],
                                 test_class_qualified_name: str) -> List[SetupAnalysis]:
        setup_methods: List[str] = SetupAnalysisInfo(self.analysis).get_setup_methods(
            test_class_qualified_name,
            testing_frameworks
        )

        if not setup_methods:
            return []

        # Collect detailed analyses for each setup method
        setup_analyses: List[SetupAnalysis] = []
        for setup_method in setup_methods:
            setup_analyses.append(
                SetupAnalysisInfo(self.analysis).get_setup_method_details(
                    test_class_qualified_name, setup_method, testing_frameworks
                )
            )

        return setup_analyses

    def _get_teardown_analysis_info(self, test_class_qualified_name: str,
                                    testing_frameworks: List[TestingFramework], ) -> List[TeardownAnalysis]:
        teardown_methods: List[str] = TeardownAnalysisInfo(self.analysis).get_teardown_methods(
            test_class_qualified_name,
            testing_frameworks
        )

        if not teardown_methods:
            return []

        # Collect detailed analyses for each teardown method
        teardown_analyses: List[TeardownAnalysis] = []
        for teardown_method in teardown_methods:
            teardown_analyses.append(
                TeardownAnalysisInfo(self.analysis).get_teardown_method_details(
                    test_class_qualified_name, teardown_method, testing_frameworks
                )
            )

        return teardown_analyses

    def _is_test_order_dependent(self, test_class_qualified_name: str) -> bool:
        return False