import re
from typing import List, Tuple

import tree_sitter_java as java_language
from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from tree_sitter import Language, Parser

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.model.models import TestingFramework, FocalClass
from hamster.code_analysis.utils.constants import ASSERTIONS_CATEGORY_MAP, UI_TEST_FRAMEWORKS, API_TEST_FRAMEWORKS, \
    GETTER_METHODS, UI_TEST_FRAMEWORKS_PREFIXES_INVERT, API_TEST_FRAMEWORKS_PREFIXES_INVERT


class FocalClassMethod:
    def __init__(self, analysis: JavaAnalysis,
                 testing_frameworks: List[TestingFramework] = None,
                 application_classes: List[str] = None):
        if testing_frameworks is None:
            testing_frameworks = []
        if application_classes is None:
            application_classes = []

        self.analysis = analysis
        self.testing_frameworks = testing_frameworks
        language = Language(java_language.language())
        self.parser = Parser(language=language)
        self.application_classes = [cls for cls in application_classes]
        self.assertion_methods = self.__get_assertion_methods(testing_frameworks=testing_frameworks)

    @staticmethod
    def __get_assertion_methods(testing_frameworks: List[TestingFramework]) -> List[str]:
        """
        List all the assertion methods
        Args:
            testing_frameworks:

        Returns:

        """
        assertion_methods = []
        for assertion_type, framework_map in ASSERTIONS_CATEGORY_MAP.items():
            for framework, assertions in framework_map.items():
                # Skip if testing framework is not available (Java built-in is automatically assumed)
                if framework not in testing_frameworks:
                    continue
                assertion_methods.extend(assertions)
        return assertion_methods

    def is_ui_api_test(self, method_details: JCallable) -> Tuple[bool, bool]:
        """
        Checks if the test method is related to UI and API test
        Args:
            method_details:

        Returns:
            Tuple[bool, bool]: is UI test, is API test
        """
        is_ui_test = False
        is_api_test = False
        if not (any(framework in self.testing_frameworks for framework in UI_TEST_FRAMEWORKS) or \
                any(framework in self.testing_frameworks for framework in API_TEST_FRAMEWORKS)):
            return False, False
        all_potential_types = []
        for call_site in method_details.call_sites:
            all_potential_types.append(call_site.receiver_type)
            all_potential_types.append(call_site.return_type)
        for variable in method_details.variable_declarations:
            all_potential_types.append(variable.type)

        if any(type.startswith(tuple(UI_TEST_FRAMEWORKS_PREFIXES_INVERT))
               for type in all_potential_types):
            is_ui_test = True

        if any(type.startswith(tuple(API_TEST_FRAMEWORKS_PREFIXES_INVERT))
               for type in all_potential_types):
            is_api_test = True
        return is_ui_test, is_api_test

    def identify_focal_class_and_ui_api_test(self, test_class_name: str, test_method_signature: str,
                                             setup_method_signatures: List[str]) -> Tuple[
        List[FocalClass], bool, bool, bool]:
        """
        Identify focal classes when a test is not UI or API test. If they are, then send the UI or API test
        Args:
            test_class_name:
            test_method_signature:
            setup_method_signatures:

        Returns:
            Tuple[List[FocalClass], bool, bool]: focal classes, is any application used, is UI, is API test
        """
        is_api_test = False
        is_ui_test = False
        all_focal_methods = {}
        focal_class_model_object = []
        # Step 1: Identify all application classes in setup
        setup_application_classes = {}
        for setup_method_signature in setup_method_signatures:
            if setup_method_signature is not None:
                setup_focal_classes, focal_methods, _, is_ui_test_m, is_api_test_m = self.__get_focal_class_and_method(
                    test_class_name,
                    setup_method_signature)
                is_api_test = is_api_test or is_api_test_m
                is_ui_test = is_ui_test or is_ui_test_m
                for f_class in focal_methods:
                    if f_class in all_focal_methods:
                        all_focal_methods[f_class].extend(focal_methods[f_class])
                    else:
                        all_focal_methods[f_class] = focal_methods[f_class]
                for focal_class in setup_focal_classes:
                    setup_application_classes[focal_class] = setup_focal_classes[focal_class]

        # Step 2: Get focal classes from the test
        (focal_classes,
         focal_methods,
         is_application_class_used,
         is_ui_test_m,
         is_api_test_m) = self.__get_focal_class_and_method(test_class_name, test_method_signature,
                                                            setup_application_classes)

        for f_class in focal_methods:
            if f_class in all_focal_methods:
                all_focal_methods[f_class].extend(focal_methods[f_class])
            else:
                all_focal_methods[f_class] = focal_methods[f_class]
        processed_focal_classes = []
        for f_class in focal_classes:
            if focal_classes[f_class] in all_focal_methods:
                is_present = False
                for f in focal_class_model_object:
                    if f.focal_class == focal_classes[f_class] and \
                            f.focal_method_names == all_focal_methods[focal_classes[f_class]]:
                        is_present = True
                        break
                if not is_present:
                    focal_class_model_object.append(FocalClass(focal_class=focal_classes[f_class],
                                                               focal_method_names=all_focal_methods[
                                                                   focal_classes[f_class]]))
            else:
                if focal_classes[f_class] not in processed_focal_classes:
                    processed_focal_classes.append(focal_classes[f_class])
                    focal_class_model_object.append(FocalClass(focal_class=focal_classes[f_class],
                                                               focal_method_names=[]))
        is_api_test = is_api_test or is_api_test_m
        is_ui_test = is_ui_test or is_ui_test_m
        for f in focal_class_model_object:
            f.focal_method_names = list(set(f.focal_method_names))
        return focal_class_model_object, is_application_class_used, is_ui_test, is_api_test

    def __get_focal_class_and_method(self, class_name: str, method_signature: str,
                                     previously_detect_focal_classes: dict = None) -> Tuple[
        dict, dict, bool, bool, bool]:
        """
        Get focal class and other details surrounding that
        Args:
            class_name:
            method_signature:
            previously_detect_focal_classes:

        Returns:
            Tuple[dict, dict, bool, bool, bool]: variable name and corresponding focal class,
            focal class key focal methods, is_application_class_used, is_ui_test, is_api_test
        """
        is_ui_test = False
        is_api_test = False
        focal_methods = {}
        if previously_detect_focal_classes is None:
            previously_detect_focal_classes = {}
        is_application_class_used = False
        method_details = self.analysis.get_method(class_name, method_signature)
        # Step 1: collect all the method including helper methods
        helper_methods = Reachability(self.analysis).get_helper_methods(qualified_class_name=class_name,
                                                                        method_signature=method_signature,
                                                                        add_extended_class=True)

        focal_classes = previously_detect_focal_classes.copy()
        # First process the helper classes
        for helper_class in helper_methods:
            for helper_method_sig in helper_methods[helper_class]:
                helper_method = self.analysis.get_method(helper_class, helper_method_sig)
                if helper_method is not None:
                    is_ui_test_m, is_api_test_m = self.is_ui_api_test(helper_method)
                    is_ui_test = is_ui_test or is_ui_test_m
                    is_api_test = is_api_test or is_api_test_m
                    focal_classes, focal_method_m, is_application_class_used_m = (
                        self.__process_method_for_focal_class(helper_class,
                                                              helper_method,
                                                              focal_classes))
                    for cls in focal_method_m:
                        if cls in focal_methods:
                            focal_methods[cls].extend(focal_method_m[cls])
                        else:
                            focal_methods[cls] = focal_method_m[cls]
                    is_application_class_used = is_application_class_used or is_application_class_used_m
        if method_details is not None:
            is_ui_test_m, is_api_test_m = self.is_ui_api_test(method_details)
            is_ui_test = is_ui_test or is_ui_test_m
            is_api_test = is_api_test or is_api_test_m
            focal_classes, focal_method_m, is_application_class_used_m = (
                self.__process_method_for_focal_class(class_name,
                                                      method_details,
                                                      focal_classes))
            for cls in focal_method_m:
                if cls in focal_methods:
                    focal_methods[cls].extend(focal_method_m[cls])
                else:
                    focal_methods[cls] = focal_method_m[cls]
            is_application_class_used = is_application_class_used or is_application_class_used_m
        return focal_classes, focal_methods, is_application_class_used, is_ui_test, is_api_test

    def __process_method_for_focal_class(self, test_class: str, method: JCallable, focal_classes: dict) -> Tuple[
        dict, dict, bool]:
        variables = focal_classes.copy()
        # Get all the variables
        all_variables = []
        is_application_class_used = False
        all_possible_focal_methods = {}
        focal_methods = {}
        parameter_types = []
        static_types = {}
        for variable in method.variable_declarations:
            all_variables.append([variable.name, variable.type])

        # Add class fields
        class_details = self.analysis.get_class(test_class)
        for declared_var in class_details.field_declarations:
            for variable in declared_var.variables:
                all_variables.append((variable, declared_var.type))

        # Add input parameters
        for param in method.parameters:
            types = self.base_types(param.type)
            for type in types:
                if self.analysis.get_class(type) is not None and type in self.application_classes:
                    is_application_class_used = True
                    variables[param.name] = type
                    parameter_types.append([param.name, type])
        # Get the variable declarations
        for variable_declaration in method.variable_declarations:
            types = self.base_types(variable_declaration.type)
            for type in types:
                # Process only application classes
                if self.analysis.get_class(type) is not None and type in self.application_classes:
                    is_application_class_used = True
                    variables[variable_declaration.name] = type
                else:
                    for class_name in self.application_classes:
                        if type == class_name.split('.')[-1]:
                            variables[variable_declaration.name] = class_name

        # Go through the call sites to get the constructor calls
        for call_site in method.call_sites:
            if call_site.is_constructor_call:
                if self.analysis.get_class(call_site.return_type) is not None and call_site.return_type in self.application_classes:
                    is_application_class_used = True
                    for variable in all_variables:
                        if variable[1].split('.')[-1] == call_site.return_type.split('.')[-1]:
                            variables[variable[0]] = call_site.return_type

        # Go through the call sites for the return and receiver types
        for call_site in method.call_sites:
            if not call_site.is_constructor_call:
                types = self.base_types(call_site.receiver_type)
                # Scenario 1: For static call add the receiver types
                if call_site.is_static_call:
                    for type in types:
                        if self.analysis.get_class(type) is not None and type in self.application_classes:
                            is_application_class_used = True
                            static_types[type.lower()] = type
                            # If the call site is part of an assignment statement
                            decl_param_types = [[vd.initializer, vd.name] for vd in method.variable_declarations]
                            # Add parameter types as well
                            decl_param_types.extend(parameter_types)
                            for v_decl in decl_param_types:
                                if call_site.receiver_expr in v_decl[0]:
                                    variables[v_decl[1]] = type
                # Add that to the list of potential focal methods
                for type in types:
                    if self.analysis.get_class(type) is not None and type in self.application_classes:
                        is_application_class_used = True
                        callee_signature = ''
                        if any(call_site.method_name.startswith(getter_method) for getter_method in GETTER_METHODS):
                            if not self.__is_getter_method(qualified_class_name=type,
                                                           method_name=call_site.method_name):
                                callee_signature = call_site.callee_signature
                        else:
                            callee_signature = call_site.callee_signature
                        # Add these to the potential focal classes
                        if callee_signature != '':
                            if type in all_possible_focal_methods:
                                all_possible_focal_methods[type].append(callee_signature)
                            else:
                                all_possible_focal_methods[type] = [callee_signature]
                # Scenario 2: Add return type and check if matches with the declared fields
                types.extend(self.base_types(call_site.return_type))
                for type in types:
                    if self.analysis.get_class(type) is not None and type in self.application_classes:
                        is_application_class_used = True
                        for variable in all_variables:
                            if variable[1].split('.')[-1] == type.split('.')[-1]:
                                variables[variable[0]] = type

                    # Scenario 3: Receiver type is a static application class
                    receiver_types = self.base_types(call_site.receiver_type)
                    for receiver_type in receiver_types:
                        receiver_class_details = self.analysis.get_class(receiver_type)
                        if receiver_class_details is not None and receiver_type in self.application_classes:
                            is_application_class_used = True
                            if 'static' in receiver_class_details.modifiers:
                                variables[receiver_type.lower()] = receiver_type

        # Identify all the arguments
        accessed_arguments = self.get_arguments(method_details=method)
        # is_application_class_used = False if len(variables) == 0 else True
        # Remove the arguments that are in the focal class
        for arg in accessed_arguments:
            if arg in variables:
                _ = variables.pop(arg)
        # Get focal methods
        for variable in variables:
            if variables[variable] in all_possible_focal_methods:
                if variables[variable] not in focal_methods:
                    focal_methods[variables[variable]] = all_possible_focal_methods[variables[variable]]

        # If no variables are present and all are removed as part of the producer-consumer relation,
        # return the static calls
        if len(variables) == 0 and len(static_types) > 0:
            # get focal methods
            for static_type in static_types:
                if static_types[static_type] in all_possible_focal_methods:
                    if static_types[static_type] not in focal_methods:
                        focal_methods[static_types[static_type]] = all_possible_focal_methods[static_types[static_type]]

            return static_types, focal_methods, is_application_class_used
        return variables, focal_methods, is_application_class_used

    def __get_all_fields(self, qualified_class_name: str) -> List[str]:
        """
        All fields
        Args:
            qualified_class_name:

        Returns:

        """
        fields = []
        class_details = self.analysis.get_class(qualified_class_name)
        if class_details is not None:
            for f in class_details.field_declarations:
                for field in f.variables:
                    fields.append(field)
            extends_list = class_details.extends_list
            for extend in extends_list:
                fields.extend(self.__get_all_fields(extend))
        return fields

    def __is_getter_method(self, qualified_class_name: str, method_name: str) -> bool:
        """
        Checks if the method is a getter method by matching the method name with fields
        Args:
            qualified_class_name:
            method_name:

        Returns:

        """
        fields = self.__get_all_fields(qualified_class_name)
        for getter_prefix in GETTER_METHODS:
            if method_name.startswith(getter_prefix):
                method_name = method_name.replace(getter_prefix, '', 1)
        for field in fields:
            if field.lower() == method_name.lower():
                return True
        return False

    def get_arguments(self, method_details: JCallable) -> List[str]:
        arguments = []
        for call_site in method_details.call_sites:
            method_name = call_site.method_name
            if method_name not in self.assertion_methods:
                arguments.extend(call_site.argument_expr)
        return arguments

    def base_types(self, type_str: str) -> List[str]:
        """
        Given a complex type, return a list of all involved types (outer and base).
        For example, 'Optional[Union[int, List[str]]]' returns:
            ['Optional', 'Union', 'int', 'List', 'str']
        Args:
            type_str (str): Complex type string
        Returns:
            List[str]: All types involved
        """
        s = re.sub(r'\s+', '', type_str)
        innermost, depth, buf, parts = [], 0, [], []

        outer_buf = []

        for ch in s:
            if ch == '<':
                outer_buf.append(''.join(buf))
                buf.clear()
                depth += 1
                continue
            elif ch == '>':
                depth -= 1
                if depth == 0:
                    parts.append(''.join(buf))
                    buf.clear()
                continue
            elif ch == ',' and depth == 1:
                parts.append(''.join(buf))
                buf.clear()
                continue
            buf.append(ch)

        if not parts:
            final = ''.join(buf)
            if '<' in final:
                outer = final[:final.index('<')]
                inner = final[final.index('<') + 1:-1]
                return [outer] + self.base_types(inner)
            else:
                return [final]

        # Recurse for each part
        for p in parts:
            innermost.extend(self.base_types(p))

        return outer_buf + innermost

    @staticmethod
    def node_to_txt(src_code, node):
        if node is None:
            return None
        return src_code[node.start_byte:node.end_byte].strip()