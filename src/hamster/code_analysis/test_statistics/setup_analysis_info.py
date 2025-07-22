from typing import List, Dict, Set

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.model.models import SetupAnalysis, TestingFramework, MockingFramework, MockedResource, \
    ExecutionOrder
from hamster.code_analysis.test_statistics.input_analysis import InputAnalysis


class SetupAnalysisInfo:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis

    def get_setup_methods(self, qualified_class_name: str, testing_frameworks: List[TestingFramework]) -> List[str]:
        """
        Get the setup methods given the testing frameworks for a qualified class
        Args:
            qualified_class_name:
            testing_frameworks:

        Returns:

        """
        all_methods: Dict[str, JCallable] = self.analysis.get_methods_in_class(qualified_class_name)
        setup_methods: Set[str] = set()

        name_based_frameworks = {
            TestingFramework.JUNIT3, TestingFramework.SPOCK, TestingFramework.ANDROID_TEST
        }
        annotation_based_frameworks = {
            TestingFramework.JUNIT4, TestingFramework.JUNIT5, TestingFramework.TESTNG, TestingFramework.MOCKITO,
            TestingFramework.SPRING_TEST, TestingFramework.CUCUMBER, TestingFramework.JBEHAVE, TestingFramework.SERENITY,
            TestingFramework.GAUGE, TestingFramework.POWERMOCK, TestingFramework.EASYMOCK, TestingFramework.JMOCKIT,
            TestingFramework.ANDROIDX_TEST, TestingFramework.REST_ASSURED, TestingFramework.SELENDROID, TestingFramework.SELENIUM,
            TestingFramework.SELENIDE, TestingFramework.PLAYRIGHT
        }

        fw = set(testing_frameworks)
        has_name_fw = bool(name_based_frameworks & fw)
        has_annotation_fw = bool(annotation_based_frameworks & fw)

        for method_signature, method_details in all_methods.items():
            if (
                has_name_fw
                and method_signature.startswith(("setUp", "setupSpec"))
            ):
                setup_methods.add(method_signature)

            if (
                has_annotation_fw
                and any(annotation.startswith("@Before") for annotation in method_details.annotations)
            ):
                setup_methods.add(method_signature)

        return sorted(setup_methods)

    def get_setup_method_details(self,
                                 qualified_class_name: str,
                                 method_signature: str,
                                 testing_frameworks: List[TestingFramework],
                                 is_test_method: bool = False) -> SetupAnalysis:
        method_details = self.analysis.get_method(qualified_class_name, method_signature)
        if not method_details:
            return SetupAnalysis(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
            )

        number_of_objects_created: int = 0
        code: str = ''
        constructor_call_details = []
        application_call_details = []
        library_call_details = []

        execution_order = self.__get_setup_execution_order(
            test_qualified_class_name=qualified_class_name,
            method_signature=method_signature,
            testing_frameworks=testing_frameworks
        )

        test_inputs = InputAnalysis(self.analysis).get_input_details(
            qualified_class_name,
            method_signature,
        )

        number_of_mocks_created: int = 0
        is_mocking_used = False
        mocked_resources: List[MockedResource] = []
        mocking_frameworks_used = []

        common_analysis = CommonAnalysis(self.analysis)

        cyclomatic_complexity = method_details.cyclomatic_complexity if method_details.cyclomatic_complexity else 0
        cyclomatic_complexity_with_helpers: int = 0

        ncloc = common_analysis.get_ncloc(method_details.declaration, method_details.code)
        ncloc_with_helpers = 0

        helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
            qualified_class_name=qualified_class_name,
            method_signature=method_signature,
            add_extended_class=True,
            allow_repetition=True,
        )

        all_methods = helper_methods
        all_methods.setdefault(qualified_class_name, []).append(method_signature)

        for class_name in all_methods:
            for method_sig in all_methods[class_name]:
                method = self.analysis.get_method(class_name, method_sig)
                if not method:
                    continue

                #code += method.declaration + method.code + '\n'
                ncloc_with_helpers += common_analysis.get_ncloc(method.declaration, method.code)
                cyclomatic_complexity_with_helpers += method.cyclomatic_complexity if method.cyclomatic_complexity else 0
                number_of_objects_created += self.__get_constructor_call_details(method)

                mocking_created = common_analysis.is_mocking_used(
                    class_name,
                    method.signature,
                )

                constructor_call_details.extend(common_analysis.get_constructor_call_details(method))
                application_call_details.extend(common_analysis.get_application_call_details(method))
                library_call_details.extend(common_analysis.get_library_call_details(method))
                number_of_mocks_created += mocking_created

                is_mocking_used = mocking_created > 0 or is_mocking_used
                if is_mocking_used:
                    if is_test_method:
                        mocking_frameworks_used.extend(
                            self.__get_mocking_frameworks(class_name, method.signature)
                        )
                    else:
                        mocking_frameworks_used.extend(
                            self.__get_mocking_frameworks(class_name)
                        )

        if ncloc > 0:
            return SetupAnalysis(
                qualified_class_name=qualified_class_name,
                method_signature=method_signature,
                ncloc=ncloc,
                ncloc_with_helpers=ncloc_with_helpers,
                cyclomatic_complexity=cyclomatic_complexity,
                cyclomatic_complexity_with_helpers=cyclomatic_complexity_with_helpers,
                number_of_objects_created=number_of_objects_created,
                #code=code,
                execution_order=execution_order,
                constructor_call_details=constructor_call_details,
                application_call_details=application_call_details,
                library_call_details=library_call_details,
                number_of_mocks_created=number_of_mocks_created,
                mocking_frameworks_used=mocking_frameworks_used,
                mocked_resources=mocked_resources,
                test_inputs=test_inputs,
            )
        else:
            return SetupAnalysis(method_signature=method_signature,)

    def __get_setup_execution_order(self, test_qualified_class_name: str,
                                    method_signature: str,
                                    testing_frameworks: List[TestingFramework]) -> ExecutionOrder:
        method_details = self.analysis.get_method(test_qualified_class_name, method_signature)
        annotations = method_details.annotations
        if any(annotation in ['@Before', '@BeforeEach', '@BeforeMethod'] for annotation in annotations):
            return ExecutionOrder.BEFORE_EACH_TEST
        if any(annotation in ['@BeforeClass', '@BeforeAll', '@BeforeSuite'] for annotation in annotations):
            return ExecutionOrder.BEFORE_CLASS
        if method_signature.split('(')[0] == 'setup' and TestingFramework.SPOCK in testing_frameworks:
            return ExecutionOrder.BEFORE_EACH_TEST
        if method_signature.split('(')[0] == 'setupSpec' and TestingFramework.SPOCK in testing_frameworks:
            return ExecutionOrder.BEFORE_CLASS
        return None

    def __get_mocking_frameworks(self, test_qualified_class_name: str, test_method_signature: str = None) -> List[
        MockingFramework]:
        """
        List all mocking frameworks used
        Args:
            test_qualified_class_name:

        Returns:
            List[MockingFramework]:
        """
        mocking_frameworks: List[MockingFramework] = []
        class_details = self.analysis.get_class(test_qualified_class_name)
        if test_method_signature:
            method_details = self.analysis.get_method(test_qualified_class_name, test_method_signature)
            if method_details is not None:
                for call_site in method_details.call_sites:
                    if call_site.receiver_type.startswith('org.mockito'):
                        mocking_frameworks.append(MockingFramework.MOCKITO)
                    elif call_site.receiver_type.startswith('org.easymock'):
                        mocking_frameworks.append(MockingFramework.EASY_MOCK)
                    elif call_site.receiver_type.startswith('org.powermock'):
                        mocking_frameworks.append(MockingFramework.POWER_MOCK)
                    elif call_site.receiver_type.startswith('com.github.tomakehurst.wiremock'):
                        mocking_frameworks.append(MockingFramework.WIRE_MOCK)
                    elif call_site.receiver_type.startswith('org.mockserver'):
                        mocking_frameworks.append(MockingFramework.MOCK_SERVER)
                for accessed_field in method_details.accessed_fields:
                    field_name = ''
                    is_field_found = False
                    if accessed_field.startswith(test_qualified_class_name + '.'):
                        field_name = accessed_field.split('.')[-1]
                        for field in class_details.field_declarations:
                            for variable in field.variables:
                                if field_name == variable:
                                    is_field_found = True
                                    break
                                    # If match found, then check if @Mock in the annotation
                        if is_field_found:
                            # MockMvc for springtest
                            if field.type.split('.')[-1] == 'MockMvc':
                                mocking_frameworks.append(MockingFramework.SPRING_TEST)
                            for annotation in field.annotations:
                                if annotation.startswith('@Mock'):
                                    mocking_frameworks.append(MockingFramework.MOCKITO)
        else:
            imports = CommonAnalysis(self.analysis).get_class_imports(qualified_class_name=test_qualified_class_name,
                                                                      is_add_application_class=False)
            for class_import in imports:
                if class_import.startswith('org.mockito'):
                    mocking_frameworks.append(MockingFramework.MOCKITO)
                elif class_import.startswith('org.easymock'):
                    mocking_frameworks.append(MockingFramework.EASY_MOCK)
                elif class_import.startswith('org.powermock'):
                    mocking_frameworks.append(MockingFramework.POWER_MOCK)
                elif class_import.startswith('com.github.tomakehurst.wiremock'):
                    mocking_frameworks.append(MockingFramework.WIRE_MOCK)
                elif class_import.startswith('org.mockserver'):
                    mocking_frameworks.append(MockingFramework.MOCK_SERVER)
            for field in self.analysis.get_class(test_qualified_class_name).field_declarations:
                if field.type.split('.')[-1] == 'MockMvc':
                    mocking_frameworks.append(MockingFramework.SPRING_TEST)
        return list(set(mocking_frameworks))

    @staticmethod
    def __get_constructor_call_details(method_details: JCallable) -> int:
        objects_created = 0
        for call_site in method_details.call_sites:
            if call_site.is_constructor_call:
                objects_created += 1
        return objects_created
