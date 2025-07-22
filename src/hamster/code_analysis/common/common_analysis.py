import json
import re
from dataclasses import asdict
from enum import Enum
from typing import List, Dict, Tuple

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from hamster.code_analysis.model.models import TestingFramework, CallableDetails
from hamster.code_analysis.utils import constants
from hamster.code_analysis.utils.constants import TEST_ANNOTATIONS


# Serializer function for dataclass objects
def dataclass_serializer(obj):
    """
    Helper function to serialize dataclass objects.
    If the object is a dataclass instance, it returns the dictionary of its fields.
    If the object is an Enum, it returns the enum value.
    Raises TypeError if the object is neither a dataclass instance nor an Enum.
    """
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")


class CommonAnalysis:
    """
    Class to encapsulate common code analysis operations on Java code.
    """

    def __init__(self, analysis: JavaAnalysis):
        """
        Initialize with a JavaAnalysis instance.
        """
        self.analysis = analysis

    def get_ncloc(self, declaration: str, body: str) -> int:
        """
        Get the number of non-comment lines.
        Args:
            declaration: The declaration part of the code.
            body: The body part of the code.
        Returns:
            int: Number of non-comment lines.
        """
        code = declaration + body
        code_lines = self.__get_non_comment_lines(code)
        body_lines = self.__get_non_comment_lines(body)
        if body_lines == ['}'] or len(body_lines) == 0 or body_lines == ['{}'] or body_lines == ['{', '}']:
            return 0
        return len(code_lines)

    @staticmethod
    def __get_non_comment_lines(code: str) -> List[str]:
        """
        Helper method to get non-comment lines from a block of code.
        Args:
            code: The code to process.
        Returns:
            List[str]: List of lines with comments removed.
        """
        code_lines = []
        inside_block_comment = False
        lines = code.splitlines()
        for line in lines:
            stripped = line.strip()

            # Handle ongoing block comments
            if inside_block_comment:
                if '*/' in stripped:
                    inside_block_comment = False
                continue

            # Handle block comment start
            if stripped.startswith("/*"):
                inside_block_comment = True
                if '*/' in stripped:  # handle one-line block comments
                    inside_block_comment = False
                continue

            # Remove inline // comments
            no_inline_comment = re.sub(r'//.*', '', line).strip()

            # Skip empty lines after comment removal
            if no_inline_comment == '':
                continue

            code_lines.append(no_inline_comment)

        return code_lines

    def is_mocking_used(self, test_class_qualified_name: str, method_signature: str,
                        extend_class_list: List[str] = None) -> int:
        """
        Determine if mocking is used in a method.
        Args:
            test_class_qualified_name: The full name of the test class.
            method_signature: The signature of the method.
            extend_class_list: List of class names to extend the search.
        Returns:
            int: Count of mocking usage.
        """
        if extend_class_list is None:
            extend_class_list = []

        count = 0
        extend_class_list.append(test_class_qualified_name)
        method_details = None
        # Search for the method in the extended class list (e.g., for inheritance hierarchies)
        for class_name in extend_class_list:
            class_temp = self.analysis.get_class(class_name)
            if class_temp:
                all_methods_in_class = self.analysis.get_methods_in_class(class_name)
                for method in all_methods_in_class:
                    if all_methods_in_class[method].signature == method_signature:
                        test_class_qualified_name = class_name
                        method_details = self.analysis.get_method(class_name, method_signature)
        if method_details is None:
            return 0

        # Retrieve class details for the class where the method was found
        class_details = self.analysis.get_class(test_class_qualified_name)

        # Retrieve imports once for efficiency
        class_imports = CommonAnalysis(self.analysis).get_class_imports(
            qualified_class_name=test_class_qualified_name,
            is_add_application_class=False)
        has_mockito = any(class_import.startswith('org.mockito') for class_import in class_imports)
        has_easymock = any(class_import.startswith('org.easymock') for class_import in class_imports)

        # Check for mocked fields (e.g., @Mock annotations or MockMvc types)
        accessed_fields = method_details.accessed_fields
        for accessed_field in accessed_fields:
            # Check if the field is declared in the same test class
            if accessed_field.startswith(test_class_qualified_name + '.'):
                field_name = accessed_field.split('.')[-1]

                # Get all the declared fields
                class_fields = class_details.field_declarations
                # Match by field name
                for class_field in class_fields:
                    is_field_found = False
                    for variable in class_field.variables:
                        if variable == field_name:
                            is_field_found = True
                            break
                    # If match found, then check if @Mock in the annotation or type is MockMvc
                    if is_field_found:
                        # MockMvc for springtest
                        if class_field.type.split('.')[-1] == 'MockMvc':
                            count += 1
                        for annotation in class_field.annotations:
                            if annotation.startswith('@Mock'):
                                count += 1

        # Initialize flags for WireMock
        is_wire_mock = False
        # Check class annotations for @WireMockTest
        for annotation in class_details.annotations:
            if annotation.startswith('@WireMockTest'):
                is_wire_mock = True
        # Check method annotations for @WireMockTest
        for annotation in method_details.annotations:
            if annotation.startswith('@WireMockTest'):
                is_wire_mock = True

        # Single loop over call sites to check for various mocking patterns
        for call_site in method_details.call_sites:
            callee_signature = call_site.callee_signature
            # Handle cases where receiver_type might be None
            receiver_type = call_site.receiver_type or ''
            receiver_last = receiver_type.lower().split('.')[-1]

            # Pattern: MyService service = mock(MyService.class);
            if callee_signature.startswith('mock'):
                count += 1

            # Specific to Mockito: when, thenReturn, verify, given, willReturn
            if has_mockito and (callee_signature.startswith('when') or callee_signature.startswith('thenReturn') or
                                callee_signature.startswith('verify') or callee_signature.startswith('given')
                                or callee_signature.startswith('willReturn')):
                count += 1

            # Specific to EasyMock: expect, andReturn, replay
            if has_easymock and (callee_signature.startswith('expect') or callee_signature.startswith('andReturn') or
                                 callee_signature.startswith('replay')):
                count += 1

            # PowerMock pattern: e.g., PowerMockito.whenNew(MyClass.class)
            if receiver_last.startswith('powermockito'):
                count += 1

            # WireMock pattern: e.g., WireMock wireMock = wmRuntimeInfo.getWireMock();
            if receiver_last.startswith('wiremock'):
                is_wire_mock = True

            # MockServer pattern: e.g., new MockServerClient("127.0.0.1", 1080).when(request())
            if receiver_last.startswith('mockserver'):
                count += 1

        # Add to count if any indicator of WireMock was found
        if is_wire_mock:
            count += 1

        return count

    def get_class_imports(self, qualified_class_name: str, is_add_application_class: bool = True) -> List[str]:
        """
        Get the imports for a specific class.
        Args:
            qualified_class_name: The full name of the class.
            is_add_application_class: Flag to determine if application classes should be included.
        Returns:
            List[str]: List of imported class names.
        """
        # Get the Java file and compilation unit for the specific class
        java_file = self.analysis.get_java_file(qualified_class_name)
        if not java_file:
            return []
        compilation_unit = self.analysis.get_java_compilation_unit(file_path=java_file)
        imports = compilation_unit.imports
        project_root = self.__get_project_root()

        # Filter imports based on flag
        if not is_add_application_class:
            return [imp for imp in imports if not imp.startswith(project_root)]
        return imports

    def get_imports(self, is_add_application_class: bool = False) -> Dict[List[str], List[str]]:
        """
        Get imports from applications.
        Args:
            is_add_application_class: Add application classes flag.
        Returns:
            dict: Dictionary containing imports and related classes.
            key: List of imports, value: List of classes.
        """
        import_details = {}
        compilation_units = self.analysis.get_compilation_units()
        project_root = self.__get_project_root()
        for compilation_unit in compilation_units:
            classes = list(compilation_unit.type_declarations.keys())
            imports = compilation_unit.imports
            filtered_imports = [imp for imp in imports if is_add_application_class or not imp.startswith(project_root)]
            import_details[tuple(filtered_imports)] = classes

        return import_details

    def __get_project_root(self) -> str:
        """
        Get the project root from class names.
        Returns:
            str: The common root of the project.
        """
        classes = list(self.analysis.get_classes().keys())
        split_class_names = [s.split('.') for s in classes]

        if not split_class_names:
            return ""

        # Find the shortest length of the split strings
        min_length = min(len(s) for s in split_class_names)

        project_root = []

        # Iterate through the indices up to min_length to find common prefix
        for i in range(min_length):
            # Get the set of elements at index i
            elements = set(s[i] for s in split_class_names)

            # If all elements are the same at this position, add to common_parts
            if len(elements) == 1:
                project_root.append(elements.pop())
            else:
                break

        # Join back with '.' to return the common prefix
        return '.'.join(project_root)

    def is_test_class(self, qualified_class_name: str, testing_frameworks: List[TestingFramework]):
        """
        Determine if a class is a test class, which is when there exists a test method.
        Args:
            qualified_class_name: The full name of the class.
            testing_frameworks: List of testing frameworks.
        Returns:
            bool: True if the class is a test class, False otherwise.
        """
        return any(self.is_test_method(method_signature, qualified_class_name, testing_frameworks)
                   for method_signature in self.analysis.get_methods_in_class(qualified_class_name))

    def is_test_method(self, method_signature: str, qualified_class_name: str,
                       testing_frameworks: List[TestingFramework]) -> bool:
        """
        Determine if a method is a test method.
        Args:
            method_signature: The signature of the method.
            qualified_class_name: The full name of the class containing the method.
            testing_frameworks: List of testing frameworks.
        Returns:
            bool: True if the method is a test method, False otherwise.
        """
        method_details = self.analysis.get_method(qualified_class_name, method_signature)
        if not method_details.code.isascii():
            return False
        class_details = self.analysis.get_class(qualified_class_name)
        is_public = "public" in method_details.modifiers

        # Check for standard test annotations on the method
        has_test_annot = any(annot.split("(")[0] in TEST_ANNOTATIONS for annot in method_details.annotations)

        # Check for JUnit3 style test methods
        is_junit3_test = (TestingFramework.JUNIT3 in testing_frameworks and
                          any(ext.endswith("TestCase") for ext in class_details.extends_list) and
                          method_signature.startswith("test") and
                          is_public and
                          method_details.return_type == "void" and
                          len(method_details.parameters) == 0)

        # Check for TestNG style, including class-level @Test
        is_testng_test = (TestingFramework.TESTNG in testing_frameworks and
                          any(annot.split("(")[0] == "@Test" for annot in class_details.annotations) and
                          is_public)

        return has_test_annot or is_junit3_test or is_testng_test

    def get_testing_frameworks_for_class(self, qualified_class_name: str) -> List[TestingFramework]:
        """
        Get the list of testing frameworks for a class.
        Args:
            qualified_class_name: The full name of the class.
        Returns:
            List[TestingFramework]: List of testing frameworks.
        """
        testing_frameworks = set()
        java_file = self.analysis.get_java_file(qualified_class_name)
        if not java_file:
            raise Exception(f"Java file for {qualified_class_name} not found")
        compilation_unit = self.analysis.get_java_compilation_unit(file_path=java_file)
        # Check imports against known framework prefixes
        for imp in compilation_unit.imports:
            for prefix, name in constants.SORTED_FRAMEWORK_PREFIXES:
                if imp.startswith(prefix):
                    testing_frameworks.add(name)
                    break
        return sorted(testing_frameworks, key=lambda x: len(x.value), reverse=True)

    def get_application_call_details(self, method_details: JCallable) -> List[CallableDetails]:
        """
        Get all application calls.
        Args:
            method_details: Details of the method.
        Returns:
            List[CallableDetails]: List of callable details.
        """
        callable_details = []
        for call_site in method_details.call_sites:
            receiver_type = call_site.receiver_type
            if self.analysis.get_class(receiver_type):
                callee_method = self.analysis.get_method(receiver_type, call_site.callee_signature)
                callable_details.append(CallableDetails(
                    method_name=call_site.callee_signature,
                    argument_types=call_site.argument_types,
                    receiver_type=receiver_type,
                    method_code=None if callee_method is None else callee_method.code))

        return callable_details

    def get_library_call_details(self, method_details: JCallable) -> List[CallableDetails]:
        """
        Get all library calls.
        Args:
            method_details: Details of the method.
        Returns:
            List[CallableDetails]: List of callable details.
        """
        callable_details = []
        for call_site in method_details.call_sites:
            receiver_type = call_site.receiver_type
            if self.analysis.get_class(receiver_type) is None and receiver_type != '':
                callable_details.append(CallableDetails(
                    method_name=call_site.callee_signature,
                    argument_types=call_site.argument_types,
                    receiver_type=receiver_type,
                    method_code=None))

        return callable_details

    @staticmethod
    def get_constructor_call_details(method_details: JCallable) -> List[CallableDetails]:
        """
        Get all constructor calls.
        Args:
            method_details: Details of the method.
        Returns:
            List[CallableDetails]: List of constructor call details.
        """
        callable_details = []
        # Check call sites for constructor invocations
        for call_site in method_details.call_sites:
            if 'new ' in call_site.receiver_expr or call_site.is_constructor_call:
                callable_details.append(CallableDetails(
                    method_name=call_site.callee_signature,
                    argument_types=call_site.argument_types,
                    receiver_type=call_site.receiver_type if call_site.receiver_type != '' else None))
        # Check variable declarations for constructor initializers
        for variable in method_details.variable_declarations:
            if 'new ' in variable.initializer:
                callable_details.append(CallableDetails(
                    method_name=variable.type.split('.')[-1] if variable.type != '' else None,
                    argument_types=[],
                    receiver_type=variable.type if variable.type != '' else None)
                )
        return callable_details

    def get_test_methods_classes_and_application_classes(self) -> Tuple[Dict[str, List[str]], List[str]]:
        """
        Get test methods, classes, and application classes.
        Returns:
            Tuple[Dict[str, List[str]], List[str]]: Dictionary of test classes and test methods, and list of application classes.
        """
        test_classes_methods = {}
        application_classes = []
        common_analysis = CommonAnalysis(self.analysis)

        for q_class in self.analysis.get_classes():
            testing_frameworks = self.get_testing_frameworks_for_class(q_class)
            if not testing_frameworks:
                application_classes.append(q_class)
                continue

            test_methods = []
            for method_sig in self.analysis.get_methods_in_class(q_class):
                if common_analysis.is_test_method(method_sig, q_class, testing_frameworks):
                    test_methods.append(method_sig)

            if test_methods:
                test_classes_methods[q_class] = test_methods
            else:
                application_classes.append(q_class)

        return test_classes_methods, application_classes

    @staticmethod
    def print_list_of_pydantic(list_: List):
        """
        Print a Pydantic list in JSON format.
        Args:
            list_: The list of Pydantic models.
        """
        json_str = json.dumps([item.model_dump(mode="json") for item in list_], indent=4)
        print(json_str)

    @staticmethod
    def print_dataclass(obj: any):
        """
        Print a dataclass object in JSON format.
        Args:
            obj: The dataclass object.
        """
        json_str = json.dumps(obj, default=dataclass_serializer, indent=4)
        print(json_str)