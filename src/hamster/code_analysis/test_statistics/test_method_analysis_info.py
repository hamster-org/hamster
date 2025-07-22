from typing import List, Dict, Tuple

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.focal_class_method.focal_class_method import FocalClassMethod
from hamster.code_analysis.model.models import TestingFramework, TestMethodAnalysis, TestType, FocalClass
from hamster.code_analysis.test_statistics.input_analysis import InputAnalysis
from hamster.code_analysis.test_statistics.setup_analysis_info import SetupAnalysisInfo
from hamster.code_analysis.test_statistics.call_and_assertion_sequence_details_info import \
    CallAndAssertionSequenceDetailsInfo
from hamster.code_analysis.utils.constants import BDD_TEST_FRAMEWORKS, BDD_ANNOTATIONS


class TestMethodAnalysisInfo:
    def __init__(self, analysis: JavaAnalysis, dataset_name: str, application_classes: List[str], ):
        self.analysis = analysis
        self.dataset_name = dataset_name
        self.application_classes = application_classes

    def get_test_method_analysis_info(self,
                                      testing_frameworks: List[TestingFramework],
                                      qualified_class_name: str,
                                      method_signature: str,
                                      setup_methods: List[str]) -> TestMethodAnalysis:
        """
        Analyzes a test method and its helpers to gather detailed test analysis information.

        Args:
            testing_frameworks: List of testing frameworks used in the test.
            qualified_class_name: Fully qualified name of the class containing the test method.
            method_signature: Signature of the test method to analyze.
            setup_methods: List of setup method signatures associated with the test.

        Returns:
            TestMethodAnalysis: An object containing comprehensive analysis of the test method.
        """
        # Retrieve method details or return a default analysis if not found
        method_details = self.analysis.get_method(qualified_class_name, method_signature)
        if not method_details:
            return TestMethodAnalysis(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
                method_declaration="",
                test_type=TestType.UNKNOWN,
                ncloc=0,
            )

        # Check if the test uses BDD style based on frameworks and annotations
        is_bdd = False
        if any(testing_framework in BDD_TEST_FRAMEWORKS
               for testing_framework in testing_frameworks):
            for annotation in method_details.annotations:
                if annotation.split('(')[0] in BDD_ANNOTATIONS:
                    is_bdd = True

        # Extract basic method information
        method_declaration = method_details.declaration
        annotations = method_details.annotations
        thrown_exceptions = method_details.thrown_exceptions

        # Determine test type and focal classes
        test_type, focal_classes = self.get_test_type_focal_classes(qualified_class_name,
                                                                    method_signature,
                                                                    testing_frameworks,
                                                                    setup_methods)

        # Initialize common analysis utility
        common_analysis = CommonAnalysis(self.analysis)

        # Compute metrics for the test method itself
        ncloc: int = common_analysis.get_ncloc(method_declaration, method_details.code)
        ncloc_with_helpers: int = 0

        cyclomatic_complexity: int = method_details.cyclomatic_complexity if method_details.cyclomatic_complexity else 0
        cyclomatic_complexity_with_helpers: int = 0

        # Gather input details for the test method
        test_inputs = InputAnalysis(self.analysis).get_input_details(
            qualified_class_name,
            method_signature,
        )

        # Initialize variables for aggregated metrics across method and helpers
        is_mocking_used = False
        number_of_objects_created = 0
        constructor_call_details = []
        application_call_details = []
        library_call_details = []

        # Get all reachable helper methods including those from extended classes
        helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
            qualified_class_name,
            method_signature,
            add_extended_class=True,
            allow_repetition=True
        )

        # Include the original method in the set of methods to analyze
        all_methods = helper_methods
        all_methods.setdefault(qualified_class_name, []).append(method_signature)

        # Aggregate metrics from all methods (test + helpers)
        for class_name in all_methods:
            for method_sig in all_methods[class_name]:
                method = self.analysis.get_method(class_name, method_sig)
                if not method:
                    continue

                is_mocking_used = self.__is_mocking_used(class_name, method.signature) or is_mocking_used
                number_of_objects_created += self.__get_number_of_objects_created(method)
                cyclomatic_complexity_with_helpers += method.cyclomatic_complexity if method.cyclomatic_complexity else 0
                ncloc_with_helpers += common_analysis.get_ncloc(method.declaration, method.code)
                constructor_call_details.extend(common_analysis.get_constructor_call_details(method))
                application_call_details.extend(common_analysis.get_application_call_details(method))
                library_call_details.extend(common_analysis.get_library_call_details(method))

        # Initialize mocking-related variables
        number_of_mocks_created = 0
        mocking_frameworks_used = None
        mocked_resources = []
        # Collect mocking details only if mocking is detected
        if is_mocking_used:
            for class_name in all_methods:
                for method_sig in all_methods[class_name]:
                    method = self.analysis.get_method(class_name, method_sig)
                    if not method:
                        continue

                    # Use SetupAnalysisInfo to gather mocking details (applies to test methods too)
                    mocked_details = SetupAnalysisInfo(self.analysis).get_setup_method_details(
                        qualified_class_name=class_name,
                        method_signature=method.signature,
                        testing_frameworks=testing_frameworks,
                        is_test_method=True
                    )
                    number_of_mocks_created += mocked_details.number_of_mocks_created
                    if mocking_frameworks_used is None:
                        mocking_frameworks_used = mocked_details.mocking_frameworks_used
                    method_mocked_resources = mocked_details.mocked_resources
                    if method_mocked_resources is not None:
                        mocked_resources.extend(method_mocked_resources)

        # Retrieve call and assertion sequence details
        call_assertion_sequences = (
            CallAndAssertionSequenceDetailsInfo(self.analysis,
                                                self.dataset_name).get_call_and_assertion_sequence_details_info(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
                testing_frameworks=testing_frameworks
            )
        )

        # Construct and return the analysis object
        return TestMethodAnalysis(qualified_class_name=qualified_class_name,
                                  method_signature=method_signature,
                                  method_declaration=method_declaration,
                                  annotations=annotations,
                                  thrown_exceptions=thrown_exceptions,
                                  test_type=test_type,
                                  ncloc=ncloc,
                                  ncloc_with_helpers=ncloc_with_helpers,
                                  cyclomatic_complexity=cyclomatic_complexity,
                                  cyclomatic_complexity_with_helpers=cyclomatic_complexity_with_helpers,
                                  test_inputs=test_inputs,
                                  is_mocking_used=is_mocking_used,
                                  number_of_mocks_created=number_of_mocks_created,
                                  mocking_frameworks_used=mocking_frameworks_used,
                                  mocked_resources=mocked_resources,
                                  number_of_objects_created=number_of_objects_created,
                                  constructor_call_details=constructor_call_details,
                                  application_call_details=application_call_details,
                                  library_call_details=library_call_details,
                                  call_assertion_sequences=call_assertion_sequences,
                                  focal_classes=focal_classes,
                                  is_bdd=is_bdd)

    def get_test_type_focal_classes(self, test_class_qualified_name: str,
                                    test_method_signature: str,
                                    testing_frameworks: List[TestingFramework],
                                    setup_methods: List[str]) -> Tuple[TestType, List[FocalClass]]:
        """
        Determines the test type and identifies focal classes for a given test method.

        Args:
            test_class_qualified_name: Fully qualified name of the test class.
            test_method_signature: Signature of the test method.
            testing_frameworks: List of testing frameworks used.
            setup_methods: List of setup method signatures.

        Returns:
            Tuple[TestType, List[FocalClass]]: The determined test type and list of focal classes.
        """
        # Identify focal classes and flags for UI/API test detection
        focal_classes, is_application_classed_used, is_ui_test, is_api_test = \
            (FocalClassMethod(analysis=self.analysis,
                              testing_frameworks=testing_frameworks,
                              application_classes=self.application_classes)
             .identify_focal_class_and_ui_api_test(test_class_name=test_class_qualified_name,
                                                   test_method_signature=test_method_signature,
                                                   setup_method_signatures=setup_methods))

        # Classify test type based on flags and focal class count
        if is_ui_test:
            return TestType.UI, focal_classes
        if is_api_test:
            return TestType.API, focal_classes

        num_focal_classes = len(focal_classes)
        if num_focal_classes == 1:
            return TestType.UNIT_MODULE, focal_classes
        if num_focal_classes > 1:
            return TestType.INTEGRATION, focal_classes
        if not is_application_classed_used:
            return TestType.LIBRARY, focal_classes

        return TestType.UNKNOWN, focal_classes

    def __is_mocking_used(self,
                          test_class_qualified_name: str,
                          method_signature: str) -> bool:
        return CommonAnalysis(self.analysis).is_mocking_used(test_class_qualified_name, method_signature) > 0

    def __get_number_of_objects_created(self, method_details: JCallable) -> int:
        """
        Calculates the number of objects created via constructor calls in the method.

        Args:
            method_details: Details of the method to analyze.

        Returns:
            int: The count of constructor calls (objects created).
        """
        return len(CommonAnalysis(self.analysis).get_constructor_call_details(method_details))