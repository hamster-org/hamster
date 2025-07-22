import re
from collections import defaultdict
from typing import List, Dict, Set, Optional

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.model.models import TestingFramework, ExecutionOrder, TeardownAnalysis, CallAndAssertionSequenceDetails, CleanupType, CleanupDetails, CallableDetails
from hamster.code_analysis.test_statistics.call_and_assertion_sequence_details_info import \
    CallAndAssertionSequenceDetailsInfo
from hamster.code_analysis.utils.constants import CLEANUP_NAME_PATTERNS, CLEANUP_CATEGORY_TO_RECEIVER_SUBSTRING, \
    CLEANUP_CATEGORY_TO_PREFIXES

_RECEIVER_SUBSTRING_TO_CLEANUP_TYPE: Dict[str, Set[CleanupType]] = defaultdict(set)
for category, receiver_substrs in CLEANUP_CATEGORY_TO_RECEIVER_SUBSTRING.items():
    for receiver_substr in receiver_substrs:
        _RECEIVER_SUBSTRING_TO_CLEANUP_TYPE[receiver_substr].add(category)

_PACKAGE_PREFIX_TO_CLEANUP_TYPE: Dict[str, Set[CleanupType]] = defaultdict(set)
for category, packages in CLEANUP_CATEGORY_TO_PREFIXES.items():
    for package in packages:
        _PACKAGE_PREFIX_TO_CLEANUP_TYPE[package].add(category)

_GENERIC_RE = re.compile(r"<[^>]*>")

class TeardownAnalysisInfo:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis

    def __normalize(self, type_str: str) -> str:
        """Strip generics, lower-case, trim."""
        # Flaky generic stripping
        no_gen = _GENERIC_RE.sub("", type_str)
        return no_gen.strip().lower()

    def __get_cleanup_type(self, receiver_type: str) -> List[CleanupType]:
        if not receiver_type:
            return [CleanupType.UNKNOWN]

        norm_receiver = self.__normalize(receiver_type)

        # Try package prefix matching first, sorted by longest prefix for specificity
        for package_prefix, types in sorted(_PACKAGE_PREFIX_TO_CLEANUP_TYPE.items(), key=lambda x: -len(x[0])):
            if norm_receiver.startswith(package_prefix):
                return list(types)

        # Handle specific ambiguous cases
        if "socketchannel" in norm_receiver or "serversocketchannel" in norm_receiver:
            return [CleanupType.NETWORK]
        elif "filechannel" in norm_receiver:
            return [CleanupType.INPUT_OUTPUT]
        # Note: Falls through to I/O if just "channel"

        for receiver_substr, cleanup_types in _RECEIVER_SUBSTRING_TO_CLEANUP_TYPE.items():
            if receiver_substr in norm_receiver:
                return list(cleanup_types)

        return [CleanupType.UNKNOWN]

    def get_teardown_methods(self, qualified_class_name: str, testing_frameworks: List[TestingFramework]) -> List[str]:
        """
        Retrieves a list of teardown methods in the specified class based on the provided testing frameworks.

        Args:
            qualified_class_name: The fully qualified name of the class to analyze.
            testing_frameworks: A list of testing frameworks to consider for detection logic.

        Returns:
            List[str]: A sorted list of teardown method signatures.
        """
        all_methods: Dict[str, JCallable] = self.analysis.get_methods_in_class(qualified_class_name)
        teardown_methods: Set[str] = set()

        name_based_frameworks = {
            TestingFramework.JUNIT3, TestingFramework.SPOCK, TestingFramework.ANDROID_TEST
        }
        annotation_based_frameworks = {
            TestingFramework.JUNIT4, TestingFramework.JUNIT5, TestingFramework.TESTNG, TestingFramework.MOCKITO,
            TestingFramework.SPRING_TEST, TestingFramework.CUCUMBER, TestingFramework.JBEHAVE,
            TestingFramework.SERENITY,
            TestingFramework.GAUGE, TestingFramework.POWERMOCK, TestingFramework.EASYMOCK, TestingFramework.JMOCKIT,
            TestingFramework.ANDROIDX_TEST, TestingFramework.REST_ASSURED, TestingFramework.SELENDROID,
            TestingFramework.SELENIUM,
            TestingFramework.SELENIDE, TestingFramework.PLAYRIGHT
        }

        fw = set(testing_frameworks)
        has_name_fw = bool(name_based_frameworks & fw)
        has_annotation_fw = bool(annotation_based_frameworks & fw)

        # Identify teardown methods based on framework conventions
        for method_signature, method_details in all_methods.items():
            # Older naming-convention-based frameworks
            if (
                has_name_fw
                and method_signature.startswith(("tearDown", "cleanup"))
            ):
                teardown_methods.add(method_signature)

            # Annotation-based frameworks seem to start with @After
            if (
                has_annotation_fw
                and any(annotation.startswith("@After") for annotation in method_details.annotations)
            ):
                teardown_methods.add(method_signature)

        return sorted(teardown_methods)

    def get_teardown_method_details(
        self,
        qualified_class_name: str,
        method_signature: str,
        testing_frameworks: List[TestingFramework],
    ) -> TeardownAnalysis:
        """
        Retrieves analysis of a teardown method, including metrics from the method and its helper methods.

        Args:
            qualified_class_name: The fully qualified name of the class containing the method.
            method_signature: The signature of the teardown method to analyze.
            testing_frameworks: List of testing frameworks used, affecting execution order determination.

        Returns:
            TeardownAnalysis: An object containing the collected analysis data. Returns partial data if method is empty.
        """
        method_details = self.analysis.get_method(qualified_class_name, method_signature)
        if not method_details:
            return TeardownAnalysis(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
            )

        # Initialize counters and collections
        number_of_objects_created: int = 0
        number_of_cleanup_calls: int = 0
        code = ''

        annotations = []
        constructor_call_details: List[CallableDetails] = []
        application_call_details: List[CallableDetails] = []
        library_call_details: List[CallableDetails] = []
        cleanup_details: List[CleanupDetails] = []

        # Create common analysis instance for utility functions
        common_analysis = CommonAnalysis(self.analysis)

        # Determine the execution order based on framework and annotations
        execution_order = self.__get_teardown_execution_order(
            qualified_class_name=qualified_class_name,
            method_signature=method_signature,
            testing_frameworks=testing_frameworks
        )

        # Retrieve call and assertion sequence information
        call_assertion_sequences: List[CallAndAssertionSequenceDetails] = (
            CallAndAssertionSequenceDetailsInfo(self.analysis).get_call_and_assertion_sequence_details_info(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
                testing_frameworks=testing_frameworks
            )
        )
        number_of_assertions = self.__get_number_of_assertions(call_assertion_sequences)

        # Calculate base metrics for the method
        ncloc: int = common_analysis.get_ncloc(method_details.declaration, method_details.code)
        ncloc_with_helpers: int = 0

        cyclomatic_complexity: int = method_details.cyclomatic_complexity if method_details.cyclomatic_complexity else 0
        cyclomatic_complexity_with_helpers: int = 0

        # Get all reachable helper methods, including from extended classes
        helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
            qualified_class_name=qualified_class_name,
            method_signature=method_signature,
            add_extended_class=True,
            allow_repetition=True,
        )

        all_methods = helper_methods
        all_methods.setdefault(qualified_class_name, []).append(method_signature)

        # Analyze metrics across the method and all helper methods
        for class_name in all_methods:
            for method_sig in all_methods[class_name]:
                method = self.analysis.get_method(class_name, method_sig)
                if not method:
                    continue

                #code += method.declaration + method.code + '\n'
                ncloc_with_helpers += common_analysis.get_ncloc(method.declaration, method.code)
                cyclomatic_complexity_with_helpers += method.cyclomatic_complexity if method.cyclomatic_complexity else 0
                number_of_objects_created += self.__get_constructor_call_details(method)
                constructor_call_details.extend(common_analysis.get_constructor_call_details(method))
                application_call_details.extend(common_analysis.get_application_call_details(method))
                library_call_details.extend(common_analysis.get_library_call_details(method))

                method_cleanup_calls = self.__get_cleanup_calls(method)
                cleanup_details.extend(method_cleanup_calls)
                number_of_cleanup_calls += len(method_cleanup_calls)

        if ncloc > 0:
            return TeardownAnalysis(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
                ncloc=ncloc,
                ncloc_with_helpers=ncloc_with_helpers,
                cyclomatic_complexity=cyclomatic_complexity,
                cyclomatic_complexity_with_helpers=cyclomatic_complexity_with_helpers,
                number_of_objects_created=number_of_objects_created,
                # code=code,
                annotations=annotations,
                execution_order=execution_order,
                constructor_call_details=constructor_call_details,
                application_call_details=application_call_details,
                library_call_details=library_call_details,
                number_of_assertions=number_of_assertions,
                number_of_cleanup_calls=number_of_cleanup_calls,
                cleanup_details=cleanup_details,
            )
        else:
            return TeardownAnalysis(method_signature=method_signature,)

    def __get_number_of_assertions(self, call_assertion_sequences: List[CallAndAssertionSequenceDetails]) -> int:
        return sum([len(seq.assertion_details) for seq in call_assertion_sequences]) if call_assertion_sequences else 0

    def __is_cleanup_call(self, method_signature: str) -> Optional[str]:
        method_name = method_signature.split('(')[0]
        for regex, canonical in CLEANUP_NAME_PATTERNS:
            if regex.fullmatch(method_name):
                return canonical
        return None

    def __get_cleanup_calls(self, method_details: JCallable) -> List[CleanupDetails]:
        cleanup_method_details: List[CleanupDetails] = []

        for call_site in method_details.call_sites:
            method_signature = call_site.callee_signature

            cleanup_canonical = self.__is_cleanup_call(method_signature)
            if not cleanup_canonical:
                continue

            cleanup_types = self.__get_cleanup_type(call_site.receiver_type)
            cleanup_method_details.append(
                CleanupDetails(
                    receiver_type=call_site.receiver_type,
                    method_name=method_signature,
                    canonical_cleanup_method=cleanup_canonical,
                    cleanup_type=cleanup_types,
                )
            )

        return cleanup_method_details

    def __get_teardown_execution_order(
        self,
        qualified_class_name: str,
        method_signature: str,
        testing_frameworks: List[TestingFramework]
    ) -> ExecutionOrder | None:
        method_details = self.analysis.get_method(
            qualified_class_name, method_signature
        )
        annotations = method_details.annotations
        simple_name = method_signature.split("(")[0]

        # Check for annotation-based teardown annotations
        if any(a in ("@After", "@AfterEach", "@AfterMethod") for a in annotations):
            return ExecutionOrder.AFTER_EACH_TEST

        if any(a in ("@AfterClass", "@AfterAll", "@AfterSuite") for a in annotations):
            return ExecutionOrder.AFTER_CLASS

        # Check for name-convention-based teardown in specific frameworks
        if simple_name == "cleanupSpec" and TestingFramework.SPOCK in testing_frameworks:
            return ExecutionOrder.AFTER_CLASS

        if (
            (simple_name == "tearDown" and TestingFramework.JUNIT3 in testing_frameworks)
            or (simple_name == "cleanup" and TestingFramework.SPOCK in testing_frameworks)
            or (simple_name.startswith(("tearDown", "cleanup")) and TestingFramework.ANDROID_TEST in testing_frameworks)
        ):
            return ExecutionOrder.AFTER_EACH_TEST

        return None

    @staticmethod
    def __get_constructor_call_details(method_details: JCallable) -> int:
        objects_created = 0
        for call_site in method_details.call_sites:
            if call_site.is_constructor_call:
                objects_created += 1
        return objects_created