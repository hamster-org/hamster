from __future__ import annotations

import json
import re
from collections import defaultdict
from enum import Enum
from typing import List, Dict, Optional, Union, Tuple, Set
from itertools import zip_longest
from dataclasses import dataclass, field, asdict

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from cldk.models.java.models import JCallSite

from tree_sitter import Language, Parser, Node
import tree_sitter_java as java_language

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.model.models import (CallAndAssertionSequenceDetails, TestingFramework,
                                                    AssertionType, CallableDetails, AssertionDetails, ParameterType,
                                                    )
from hamster.code_analysis.utils.constants import TREE_SITTER_CALLABLE_TYPES, CONTEXT_SEARCH_DEPTH, \
    CLDK_TREE_SITTER_CALLABLE_TYPES, ASSERTIONS_CATEGORY_MAP, TYPE_TO_PARAMETER_MAP, BUILTIN_ASSERTION_COMPLEMENTS

# Increase recursive depth for deep Tree Sitter trees due to recursive processing in graph cleaning
import sys

from hamster.utils.pretty import RichLog

sys.setrecursionlimit(3000)

_WRAPPED_FRAMEWORKS = {TestingFramework.GOOGLE_TRUTH, TestingFramework.HAMCREST, TestingFramework.ASSERTJ}

_TREE_SITTER_TO_TYPES: Dict[str, ParameterType] = {}
for _param_type, _tree_sitter_types in TYPE_TO_PARAMETER_MAP["Tree-Sitter"].items():
    for _tree_sitter_type in _tree_sitter_types:
        _TREE_SITTER_TO_TYPES[_tree_sitter_type] = _param_type

_JAVA_TO_TYPES: Dict[str, ParameterType] = {}
for _param_type, _java_types in TYPE_TO_PARAMETER_MAP["Java"].items():
    for _j_type in _java_types:
        _JAVA_TO_TYPES[_j_type] = _param_type

_BUILTIN_TO_CATEGORY: Dict[str, Set[AssertionType]] = defaultdict(set)
for _category, _method_mappings in BUILTIN_ASSERTION_COMPLEMENTS.items():
    for _method in _method_mappings:
        _BUILTIN_TO_CATEGORY[_method].add(_category)

@dataclass
class MethodNode:
    """Represents information of all method invocations of a provided AST."""
    method_name: str

    arguments: List[Union[str, List[MethodNode], MethodNode]] = field(
        default_factory=list)  # Arguments are str, List[MethodNode], or MethodNode
    # Note: Tree-sitter qualifies variables as "identifier"s
    argument_types: List[ParameterType] = field(default_factory=list)
    # "string_literal", "method_invocation", "decimal_integer_literal", "field_access", "class_literal", "lambda_expression"

    receiver_expression: Optional[str] = None
    receiver_type: Optional[ParameterType] = None

    child_invocation: Optional[MethodNode] = None
    body_invocations: Optional[List[MethodNode]] = field(default_factory=list)  # Process body before child invocations

    method_code: Optional[str] = None
    start_line: int = -1
    end_line: int = -1
    start_column: int = -1
    end_column: int = -1


@dataclass
class CallableClassification:
    """Represents a processed method node."""
    node: MethodNode
    classifications: List[AssertionType] = field(default_factory=list)  # In-case it is a non-assertion method call
    secondary_assertion: bool = False  # If the call is complementary to an assertion (e.g., "contains" in "assertTrue(list.contains(...))")
    is_wrapped: bool = False  # If the call is wrapped by an assertion matcher (e.g., "assertThat")


class EdgeType(Enum):
    ARGUMENT = "argument"
    RECEIVER = "receiver"
    BODY = "body"  # Body and receiver both get processed to child invocation
    OTHER = "other"


@dataclass
class CategorizationParams:
    assert_param_type: Optional[ParameterType] = None
    has_parent_assertion: bool = False
    is_wrapped: bool = False


@dataclass
class ExtractMethodChainParams:
    method_details: Optional[JCallable]
    call_site_mapping: Dict[Tuple[int, int, int, int], JCallSite]
    first_line_offset: float | None = None


@dataclass
class NonAssertionCallableParams:
    method_details: Optional[JCallable]
    call_site_mapping: Dict[Tuple[int, int, int, int], JCallSite]
    testing_frameworks: List[TestingFramework]
    class_struct: CallableClassification
    helper_methods: Dict[str, List[str]]
    qualified_class_name: str
    visited: Set[Tuple[str, str]]
    depth: int


class CallAndAssertionSequenceDetailsInfo:
    def __init__(self, analysis: JavaAnalysis, dataset_name: str | None = None):
        self.analysis = analysis
        self.dataset_name = dataset_name
        language = Language(java_language.language())
        self.parser = Parser(language=language)

    def __build_callable_details(self, classification_struct: CallableClassification, is_helper: bool = False):
        node = classification_struct.node
        return CallableDetails(
            method_name=node.method_name,
            argument_types=node.argument_types,
            receiver_type=node.receiver_type,
            method_code=node.method_code,
            secondary_assertion=classification_struct.secondary_assertion,
            is_helper=is_helper,
        )

    def __build_assertion_details(self, classification_struct: CallableClassification,
                                  is_helper: bool = False,
                                  is_wrapped: bool = False) -> AssertionDetails:
        return AssertionDetails(
            assertion_name=classification_struct.node.method_name,
            assertion_type=classification_struct.classifications,
            assertion_code=classification_struct.node.method_code,
            argument_types=classification_struct.node.argument_types,
            in_helper=is_helper,
            is_wrapped=is_wrapped
        )

    def __prune_args_in_signature(self, method_signature: str) -> str:
        """
        DEPRECATED DUE TO CHANGES TO CLDK...

        Removes things like 'java.lang.String' in callee signature and returns 'String' in accordance to
        method signature returned in helpers"""
        prefix_erasure_pattern = r'\b(?:[\w_]+\.)+([\w_]+)'
        return re.sub(prefix_erasure_pattern, r'\1', method_signature)

    def __get_assertion_types(self, method_name: str, testing_frameworks: List[TestingFramework],
                              is_wrapped: bool) -> List[AssertionType]:
        possible_categories = set()

        # Only add the Java built-in framework if the "assert" keyword is used
        if method_name == "<<ASSERT_STATEMENT>>" and TestingFramework.JAVA_BUILTIN not in testing_frameworks:
            testing_frameworks.append(TestingFramework.JAVA_BUILTIN)
            possible_categories.add(AssertionType.TRUTHINESS)

        for assertion_type, framework_map in ASSERTIONS_CATEGORY_MAP.items():
            for framework, assertions in framework_map.items():
                # Skip if testing framework is not available (Java built-in is automatically assumed)
                if framework not in testing_frameworks:
                    continue

                # If method is not one of the assertions for the framework, we skip
                if method_name not in assertions:
                    continue

                # If in Google Truth, Hamcrest, or AssertJ, it should be wrapped UNLESS it is the WRAPPER itself
                if framework in _WRAPPED_FRAMEWORKS and not is_wrapped and assertion_type != AssertionType.WRAPPER:
                    continue

                possible_categories.add(assertion_type)

        return sorted(possible_categories, key=lambda assertion_type: assertion_type.value)

    def __is_builtin(self, method_name: str) -> bool:
        return method_name in _BUILTIN_TO_CATEGORY

    def __is_numeric_tolerance(self, method_name: str, argument_types: List[ParameterType],
                             testing_frameworks: List[TestingFramework]) -> bool:
        """assertEquals and assertNotEquals have optional parameters for numeric tolerance"""
        if method_name not in ("assertEquals", "assertNotEquals"):
            return False

        is_junit = (
                TestingFramework.JUNIT3 in testing_frameworks
                or TestingFramework.JUNIT4 in testing_frameworks
                or TestingFramework.JUNIT5 in testing_frameworks
        )
        is_testng = (
                TestingFramework.TESTNG in testing_frameworks
        )

        if (
                (is_junit or is_testng)
                and len(argument_types) > 2
        ):
            return True

        return False

    def __get_param_type_from_tree(self, tree_type: str) -> ParameterType:
        return _TREE_SITTER_TO_TYPES.get(tree_type, ParameterType.UNKNOWN)

    def __get_param_type_from_raw(self, raw_type: str) -> Optional[ParameterType]:
        if not raw_type:
            return None

        raw_type = raw_type.strip()

        # Decide if it is a custom type
        class_details = self.analysis.get_class(raw_type)
        if class_details:
            return ParameterType.CUSTOM

        # Class literal
        if raw_type.endswith(".class"):
            return ParameterType.CLASS_LITERAL

        # Arrays - contains square brackets
        if re.search(r"\[\]", raw_type):
            return ParameterType.COLLECTION

        # Generics - contains angled brackets
        if re.search(r"<[^>]+>", raw_type):
            return ParameterType.COLLECTION

        base_type = raw_type.rsplit('.', 1)[-1]
        return _JAVA_TO_TYPES.get(base_type, ParameterType.UNKNOWN)

    def __get_call_site_mapping(self, method_details: JCallable) -> Dict[Tuple[int, int, int, int], JCallSite]:
        call_site_mapping: Dict[Tuple[int, int, int, int], JCallSite] = {}

        if method_details is None:
            return call_site_mapping

        first_line_offset = 1e9  # Adjust code that exists on the same line as the open bracket
        for call_site in method_details.call_sites:
            if call_site.start_line - method_details.code_start_line == 0:  # On the same line as open bracket
                first_line_offset = min(first_line_offset, call_site.start_column - 1)

        for call_site in method_details.call_sites:
            rel_start_line = call_site.start_line - method_details.code_start_line
            rel_end_line = call_site.end_line - method_details.code_start_line
            rel_start_col = call_site.start_column - 1  # CLDK adds one extra to the start column
            rel_end_col = call_site.end_column
            if call_site.start_line - method_details.code_start_line == 0:
                rel_start_col = call_site.start_column - 1 - first_line_offset  # CLDK adds one extra to the start column
            if call_site.end_line - method_details.code_start_line == 0:
                rel_end_col = call_site.end_column - first_line_offset

            call_site_mapping[(
                rel_start_line,
                rel_end_line,
                rel_start_col,
                rel_end_col
            )] = call_site

        return call_site_mapping

    def __get_call_site(self, start_line: int, end_line: int, start_column: int,
                        end_column: int, method_details: JCallable) -> Optional[JCallSite]:
        for call_site in method_details.call_sites:
            exact_code_match = (
                    call_site.start_line - method_details.code_start_line == start_line
                    and call_site.end_line - method_details.code_start_line == end_line
                    and call_site.start_column - 1 == start_column  # Note: CLDK start column is offset 1
                    and call_site.end_column == end_column
            )
            if exact_code_match:
                return call_site
        return None

    def __get_arg_types_from_sig(self, method_signature: str) -> List[str]:
        match = re.search(r'\((.*?)\)', method_signature)
        if not match:
            return []
        args_string = match.group(1).strip()
        if not args_string:
            return []
        return [arg.strip() for arg in args_string.split(',')]

    def __get_arg_types_from_site(self, call_site: JCallSite) -> List[Optional[str]]:
        """Generates arguments from call site arguments first, then backs to the callee signature. Call site arguments
        reflect what were actually passed in."""
        arg_types = []
        if not call_site:
            return arg_types

        call_site_args = call_site.argument_types if call_site.argument_types else []
        call_site_args = [arg.strip() for arg in call_site_args]
        signature_args = self.__get_arg_types_from_sig(call_site.callee_signature) if call_site.callee_signature else []
        # Recent CLDK change made callee_signature varargs into arrays automatically

        for cs_arg, sig_arg in zip_longest(call_site_args, signature_args, fillvalue=None):
            if cs_arg:  # Default to the call site argument if truthy
                arg_types.append(cs_arg)
            elif sig_arg:  # If call site arg is not truthy but signature argument is
                arg_types.append(sig_arg)
            else:
                arg_types.append(None)

        return arg_types

    def __handle_var_args(self, call_site_args, signature_args: List[str]):
        """DEPRECATED DUE TO CHANGES TO CLDK..."""
        var_base = signature_args[-1].removesuffix("...")
        fixed_prefix = signature_args[:-1]  # Before the vararg
        n_fixed = len(fixed_prefix)
        n_call = len(call_site_args)
        if n_call > n_fixed:
            # Extend signature args to have the var args
            signature_args[:] = fixed_prefix + [var_base] * (n_call - n_fixed)
        else:
            # Remove the varargs if unused in call
            signature_args[:] = fixed_prefix

    def __convert_arg_to_parameter_type(self, arg_types: List[str]) -> List[Optional[ParameterType]]:
        cleaned_args: List[ParameterType] = []
        for arg_type in arg_types:
            cleaned_args.append(self.__get_param_type_from_raw(arg_type))
        return cleaned_args

    def __traverse_tree(self, node: Node, parent: Optional[MethodNode], edge: Optional[EdgeType],
                        params: ExtractMethodChainParams, collector: List[MethodNode], ) -> MethodNode | None:
        # Skip non-call nodes
        if node.type not in TREE_SITTER_CALLABLE_TYPES:
            for ch in node.named_children:
                self.__traverse_tree(ch, parent, edge, params, collector)
            return None

        # Receiver chain -> Build first to get left-to-right ordering
        receiver_field = node.child_by_field_name("object")
        receiver_root: Optional[MethodNode] = None
        if receiver_field and receiver_field.type in TREE_SITTER_CALLABLE_TYPES:
            receiver_root = self.__traverse_tree(
                receiver_field,  # Start of receiver chain
                None,  # Has no parents
                None,
                params,
                collector,  # Send collector to add when root
            )

        # Build method node
        rel_start_row, rel_end_row = node.start_point.row, node.end_point.row
        rel_start_col = node.start_point.column - (params.first_line_offset if rel_start_row == 0 else 0)
        rel_end_col = node.end_point.column - (params.first_line_offset if rel_end_row == 0 else 0)

        cs_key = (rel_start_row, rel_end_row, rel_start_col, rel_end_col)
        call_site = params.call_site_mapping.get(cs_key)

        method_name, receiver_expression, receiver_type = self.__decode_name_and_receiver(node, call_site)

        method_node = MethodNode(
            method_name=method_name,
            method_code=node.text.decode().strip(),
            receiver_expression=receiver_expression,
            receiver_type=receiver_type,
            start_line=rel_start_row,
            end_line=rel_end_row,
            start_column=rel_start_col,
            end_column=rel_end_col,
        )

        # Add the current call at the end of the receiver chain if it exists
        if receiver_root:
            tail = receiver_root
            while tail.child_invocation:
                tail = tail.child_invocation
            tail.child_invocation = method_node
            root_for_parent = receiver_root
        else:
            root_for_parent = method_node
            if parent is None:  # top‑level when there is no receiver
                collector.append(root_for_parent)

        # Handle the body calls
        if parent is not None and edge == EdgeType.BODY:
            # Append root incase it is nested chain inside body
            parent.body_invocations.append(root_for_parent)

        # Handle arguments
        arg_list = node.child_by_field_name("arguments")
        if arg_list:
            raw_types: List[str] = self.__get_arg_types_from_site(call_site)
            processed_types: List[Optional[ParameterType]] = self.__convert_arg_to_parameter_type(raw_types)

            for idx, arg_node in enumerate(arg_list.named_children):
                self.__process_arguments(arg_node, idx, method_node, processed_types, params)

        # Handle conditions and message in assertion statements
        assert_nodes = []
        if node.type == "assert_statement":
            for idx, assert_node in enumerate(node.named_children):
                self.__process_arguments(assert_node, idx, method_node, [], params)
                assert_nodes.append(assert_node)

        # Handle body of anonymous subclass or lambda
        body_nodes: List[Node] = []
        named_body = node.child_by_field_name("body")
        if named_body:
            body_nodes.append(named_body)
        if node.type in ("class_instance_creation_expression", "object_creation_expression"):
            body_nodes.extend(
                ch for ch in node.named_children if ch.type == "class_body"
            )

        for body in body_nodes:
            for ch in body.named_children:
                self.__traverse_tree(ch, method_node, EdgeType.BODY, params,
                                     collector=[])  # Reinit collector to avoid appending to top nodes

        # Additional exhaustiveness
        skip_children = {receiver_field} if receiver_field else set()
        if arg_list:
            skip_children.add(arg_list)
        skip_children.update(body_nodes)
        skip_children.update(assert_nodes)

        for ch in node.named_children:
            if ch in skip_children:  # Since we have already visited
                continue
            # Propagate edge relationship to children that might have identifiers before (i.e., foo(this.obj.bar()))
            self.__traverse_tree(ch, parent, edge, params, collector)

        return root_for_parent

    def extract_method_nodes(self, code: str, params: ExtractMethodChainParams) -> List[MethodNode]:
        """Extract top-level method nodes"""
        byte_code = code.encode("utf-8")
        syntax_tree = self.parser.parse(byte_code)
        root = syntax_tree.root_node
        params.first_line_offset = self.__compute_line_offset(root)
        top_level_nodes = []
        self.__traverse_tree(root, None, None, params, top_level_nodes)
        return top_level_nodes

    def __process_arguments(self, arg_node: Node, index: int, parent_method_node: MethodNode,
                            processed_types: List[Optional[ParameterType]], params: ExtractMethodChainParams):
        nested_roots: List[MethodNode] = []
        self.__traverse_tree(arg_node, None, None, params, nested_roots)

        if nested_roots:
            parent_method_node.arguments.append(nested_roots)
        else:
            parent_method_node.arguments.append(arg_node.text.decode().strip())

        if index < len(processed_types) and processed_types[index] and processed_types[index] != ParameterType.UNKNOWN:
            processed_type = processed_types[index]
        else:
            processed_type = self.__get_param_type_from_tree(arg_node.type)

        parent_method_node.argument_types.append(processed_type)

    def __decode_name_and_receiver(self, node: Node,
                                   call_site: Optional[JCallSite]) -> Tuple[
        str, Optional[str], Optional[ParameterType]]:
        if node.type in ("object_creation_expression", "class_instance_creation_expression"):
            constructor_name = node.child_by_field_name("type").text.decode() if node.child_by_field_name("type") else "UNKNOWN"
            method_name = f"<<CONSTRUCTOR>> {constructor_name}"
        elif node.type == "lambda_expression":
            method_name = "<<LAMBDA_EXPRESSION>>"
        elif node.type == "assert_statement":
            method_name = "<<ASSERT_STATEMENT>>"
        elif node.type == "method_reference":
            name_node = node.child_by_field_name("name")
            method_name = name_node.text.decode() if name_node else "<<METHOD_REFERENCE>>"
        else:
            name_node = node.child_by_field_name("name")
            call_site_method_name = call_site.method_name if call_site else "<<UNKNOWN>>"
            method_name = name_node.text.decode() if name_node else call_site_method_name

        if call_site:
            rexpr = call_site.receiver_expr
            rtype = self.__get_param_type_from_raw(call_site.receiver_type)
        else:
            obj = node.child_by_field_name("object")
            rexpr = obj.text.decode() if obj else None
            rtype = None

        return method_name, rexpr, rtype

    def __compute_line_offset(self, root: Node) -> int:
        min_col: Optional[int] = None

        def scan(node: Node) -> None:
            nonlocal min_col
            if (node.type in CLDK_TREE_SITTER_CALLABLE_TYPES
                    and (node.parent is None or node.parent.type not in CLDK_TREE_SITTER_CALLABLE_TYPES)):
                if node.start_point.row == 0:
                    col = node.start_point.column
                    min_col = col if min_col is None else min(min_col, col)
            for ch in node.named_children:
                scan(ch)

        scan(root)
        return min_col or 0

    def __remove_optional_string(self, node: MethodNode, testing_frameworks: List[TestingFramework]) -> List[
        ParameterType]:
        """For assertEquals and assertNotEquals, there maybe an optional string in the arguments which can degrade further processing"""
        if node.method_name not in ("assertEquals", "assertNotEquals") or not node.argument_types:
            return node.argument_types

        def _is(tf: TestingFramework) -> bool:
            return tf in testing_frameworks

        is_junit34 = _is(TestingFramework.JUNIT3) or _is(TestingFramework.JUNIT4)
        is_junit5 = _is(TestingFramework.JUNIT5)
        is_testng = _is(TestingFramework.TESTNG)

        # First argument might be optional message
        if (
                is_junit34
                and len(node.argument_types) > 2
                and node.argument_types[0] == ParameterType.STRING
        ):
            return node.argument_types[1:]

        # Third argument might be optional message OR fourth argument if including tolerance
        if (
                (is_junit5 or is_testng)
                and len(node.argument_types) > 3
                and node.argument_types[3] == ParameterType.STRING
        ):
            return node.argument_types[:3]
        elif (
                (is_junit5 or is_testng)
                and len(node.argument_types) > 2
                and node.argument_types[2] == ParameterType.STRING
        ):
            return node.argument_types[:2]

        return node.argument_types

    def __pick_category(self, node: MethodNode, testing_frameworks: List[TestingFramework],
                        params: CategorizationParams) -> List[AssertionType]:
        """
        Handles assertions with conflicting categories and selects the most appropriate one.

        Args:
            node:
            testing_frameworks:

        Returns:

        """
        categories: List[AssertionType] = self.__get_assertion_types(node.method_name,
                                                                     testing_frameworks,
                                                                     is_wrapped=params.is_wrapped)

        if not categories or len(categories) == 1: # If there is one category, there is no confusion
            return categories

        # Equality family assertion conflicts
        if node.method_name in {
            "assertEquals",
            "assertNotEquals",
            "isEqualTo",
            "isNotEqualTo",
            "equalTo"
        }:
            arg_types = self.__remove_optional_string(node, testing_frameworks)

            if self.__is_numeric_tolerance(node.method_name, arg_types, testing_frameworks):
                return [AssertionType.NUMERIC_TOLERANCE]

            if params.is_wrapped and params.assert_param_type == ParameterType.COLLECTION:
                return [AssertionType.COLLECTION]
            if params.is_wrapped and params.assert_param_type == ParameterType.STRING:
                return [AssertionType.STRING]

            if any(t == ParameterType.COLLECTION for t in arg_types):
                return [AssertionType.COLLECTION]
            if any(t == ParameterType.STRING for t in arg_types):
                return [AssertionType.STRING]

            if all(t == ParameterType.UNKNOWN for t in arg_types):  # If we cannot tell any of the arg types
                return [
                    AssertionType.STRING,
                    AssertionType.COLLECTION,
                    AssertionType.EQUALITY
                ]
            else:  # If there is an argument but it's not a string or collection
                return [AssertionType.EQUALITY]

        # Collection assertion conflicts
        if node.method_name in {
            "contains",
            "doesNotContain",
            "hasSize",
            "containsOnlyOnce"
            "isEmpty",
            "isNotEmpty",
        }:
            if params.is_wrapped and params.assert_param_type == ParameterType.STRING:
                return [AssertionType.STRING]
            if params.is_wrapped and params.assert_param_type == ParameterType.COLLECTION:
                return [AssertionType.COLLECTION]

            if len(node.argument_types) == 0: # If no arguments, then we cannot decide
                return [AssertionType.STRING, AssertionType.COLLECTION]
            elif ( # If there are arguments, try and decide based on their types
                node.method_name in {"contains", "doesNotContain", "containsOnlyOnce"}
                and all(t == ParameterType.STRING for t in node.argument_types)
            ):
                return [AssertionType.STRING,
                        AssertionType.COLLECTION]  # Not sure which of the two unless we are given the object type for assertThat
            else:  # Contains a non-string
                return [AssertionType.COLLECTION]

        return categories

    def __process_children(self, parent: MethodNode, testing_frameworks: List[TestingFramework],
                           categories: List[CallableClassification], params: CategorizationParams,
                           in_args: bool):

        # Handle body invocations FIRST
        for node in parent.body_invocations:
            if in_args:
                self.__collect_categories_args(
                    node, testing_frameworks, categories, params
                )
            else:
                self.__collect_categories(
                    node, testing_frameworks, categories, params
                )

        # Handle child invocations SECOND
        if in_args:
            self.__collect_categories_args(
                parent.child_invocation, testing_frameworks, categories, params
            )
        else:
            self.__collect_categories(
                parent.child_invocation, testing_frameworks, categories, params
            )

    def __process_argument_collection(self, node: MethodNode, testing_frameworks: List[TestingFramework],
                                      categories: List[CallableClassification], params: CategorizationParams,
                                      lambda_deferred: List[MethodNode]):
        if node.method_name == "<<LAMBDA_EXPRESSION>>":
            lambda_deferred.append(node)
        else:
            self.__collect_categories_args(node, testing_frameworks, categories, params)

    def __process_node_common(self, curr: MethodNode, testing_frameworks: List[TestingFramework],
                              categories: List[CallableClassification], params: CategorizationParams,
                              in_args: bool):
        if not curr:
            return

        # Save local flags for processing and restoring
        local_is_wrapped = params.is_wrapped
        local_has_parent = params.has_parent_assertion
        local_assert_param_type = params.assert_param_type

        lambda_deferred = []  # Collect lambdas during arg processing

        # Find categories for the current node -> Determine if there is a wrapping assertion to categorize built-in methods
        curr_categories = self.__pick_category(curr, testing_frameworks, params)
        is_secondary_assertion = False

        if (
            curr_categories
            and self.__is_builtin(curr.method_name)
            and not params.is_wrapped # Shouldn't rely on receiver type -> Cannot be processed with Hamcrest
        ):  # If it is builtin method with a classification, it must have an assertThat call before
            curr_categories = []
            is_secondary_assertion = True

        elif in_args and not curr_categories and params.has_parent_assertion:
            # If it is in args with a parent assertion, all built-in methods (no classification) are classified as secondary assertions
            is_secondary_assertion = True

        # If assertion wrapper, we process the subject separately, then the nested calls
        if AssertionType.WRAPPER in curr_categories:
            params.has_parent_assertion = True

            # If there are arguments, capture assertThat type and recurse potentially
            if curr.arguments:
                # First argument is the assertThat subject
                first = curr.arguments[0]
                if isinstance(first, list):
                    for node in first:
                        self.__process_argument_collection(node, testing_frameworks, categories, params,
                                                           lambda_deferred)

                # Only assign after, since we do not want the assertThat subject built-ins to be qualified as assertions
                # Marks subsequent calls as wrapped
                params.is_wrapped = True
                params.assert_param_type = curr.argument_types[0]

                for arg in (a for a in curr.arguments[1:] if isinstance(a, list)):
                    for node in arg:
                        self.__process_argument_collection(node, testing_frameworks, categories, params,
                                                           lambda_deferred)

            # Ensure child calls are wrapped regardless of arguments
            params.is_wrapped = True

        else:
            if categories:  # There exists an assertion in the parent call, process for arguments
                params.has_parent_assertion = True

            for arg in (a for a in curr.arguments if isinstance(a, list)):
                for node in arg:
                    self.__process_argument_collection(node, testing_frameworks, categories, params, lambda_deferred)

        # Append current categories -> lambda expressions are not associated with call sites
        if curr.method_name != "<<LAMBDA_EXPRESSION>>":
            categories.append(
                CallableClassification(
                    node=curr,
                    classifications=curr_categories,
                    secondary_assertion=is_secondary_assertion,
                    is_wrapped=local_is_wrapped
                )
            )

        # Process all lambda functions after the current call
        for lambda_node in lambda_deferred:
            self.__collect_categories_args(lambda_node, testing_frameworks, categories, params)

        # Processed child nodes and body invocations
        self.__process_children(curr, testing_frameworks, categories, params, in_args)

        # Restore flags for siblings
        params.is_wrapped = local_is_wrapped
        params.has_parent_assertion = local_has_parent
        params.assert_param_type = local_assert_param_type


    def __collect_categories_args(self, curr: MethodNode, testing_frameworks: List[TestingFramework],
                                  categories: List[CallableClassification],
                                  categorization_params: CategorizationParams):
        """Adds additional logic from __collect_categories for when we are in an argument -> Allows builtin methods to be classified
        as secondary assertions if it has a parent assertion."""
        if not curr:
            return

        self.__process_node_common(
            curr,
            testing_frameworks,
            categories,
            categorization_params,
            in_args=True,
        )

    def __collect_categories(self, curr: MethodNode, testing_frameworks: List[TestingFramework],
                             categories: List[CallableClassification], params: CategorizationParams):
        """Recursively collect categories for a method node chain."""
        if not curr:
            return

        self.__process_node_common(
            curr,
            testing_frameworks,
            categories,
            params,
            in_args=False,
        )

    def __categorize_chain(self, root: MethodNode,
                           testing_frameworks: List[TestingFramework]) -> List[CallableClassification]:
        categories: List[CallableClassification] = []
        self.__collect_categories(root, testing_frameworks, categories, CategorizationParams())
        return categories

    def __match_helper(self, call_site: JCallSite, params: NonAssertionCallableParams) -> Optional[JCallable]:
        method_sig = (
            call_site.callee_signature
            if call_site and call_site.callee_signature else None
        )
        if not method_sig:
            return None

        for q_class in params.helper_methods:
            for helper_sig in params.helper_methods[q_class]:
                if helper_sig == method_sig:
                    return self.analysis.get_method(q_class, helper_sig)

        return None

    def __handle_helper_call(self,
                             params: NonAssertionCallableParams,
                             helper_sig: str,
                             curr: CallAndAssertionSequenceDetails,
                             sequences: List[CallAndAssertionSequenceDetails]) -> CallAndAssertionSequenceDetails:
        q_class = params.qualified_class_name
        testing_frameworks = params.testing_frameworks
        visited = params.visited
        depth = params.depth

        helper_seqs = []
        if (q_class, helper_sig) not in visited:
            helper_seqs: List[CallAndAssertionSequenceDetails] = (
                self.get_call_and_assertion_sequence_details_info(
                    q_class,
                    helper_sig,
                    testing_frameworks,
                    visited,
                    depth - 1,
                    is_helper=True
                )
            )

        if not helper_seqs:
            return curr  # Return current sequence and do nothing to remainder

        # Handle the front
        first = helper_seqs[0]
        if not curr.assertion_details:
            # If the curr sequence is not ended, we append to the first sequence of the helper
            curr.call_sequence_details.extend(first.call_sequence_details)
            curr.assertion_details = first.assertion_details
            first.call_sequence_details = curr.call_sequence_details
        elif first.call_sequence_details:
            # Our curr seq has an assertion and the new helper call and assertion seq starts with a non-assertion, so we
            # end the current sequence and insert
            helper_seqs.insert(0, curr)
        else:
            # The first sequence of the helper call seqs is just assertions
            curr.assertion_details.extend(first.assertion_details)
            helper_seqs[0] = curr

        # Take from the back to get the new curr_sequence
        if len(helper_seqs) == 1:
            return helper_seqs[0]

        new_curr = helper_seqs.pop()
        sequences.extend(helper_seqs)
        return new_curr

    def __add_non_assertion_callable(self, call_and_assertion_sequences: List[CallAndAssertionSequenceDetails],
                                     curr_sequence: CallAndAssertionSequenceDetails,
                                     params: NonAssertionCallableParams, is_helper: bool = False):
        if curr_sequence.assertion_details:
            # End current sequence
            call_and_assertion_sequences.append(curr_sequence)
            curr_sequence = CallAndAssertionSequenceDetails()

        curr_sequence.call_sequence_details.append(
            self.__build_callable_details(params.class_struct, is_helper=is_helper)
        )
        return curr_sequence

    def __handle_non_assertion(self, sequences: List[CallAndAssertionSequenceDetails],
                               curr_sequence: CallAndAssertionSequenceDetails,
                               params: NonAssertionCallableParams) -> CallAndAssertionSequenceDetails:
        node = params.class_struct.node

        call_site = params.call_site_mapping.get(
            (node.start_line, node.end_line, node.start_column, node.end_column), None
        )
        # if call_site is None: # CLDK might not catch method references
        #    print(f"Problem with project {self.dataset_name}! No call site found for {node.method_name} with code {node.method_code}...")

        helper = self.__match_helper(call_site, params) if call_site else None

        # Record current call
        curr_sequence = self.__add_non_assertion_callable(
            sequences, curr_sequence, params, is_helper=bool(helper)
        )

        # If it is a helper call, we process the callables within
        if helper:
            curr_sequence = self.__handle_helper_call(
                params, helper.signature, curr_sequence, sequences
            )

        return curr_sequence

    def get_call_and_assertion_sequence_details_info(self, qualified_class_name: str,
                                                     method_signature: str,
                                                     testing_frameworks: List[TestingFramework],
                                                     visited: Optional[Set[Tuple[str, str]]] = None,
                                                     depth: int = CONTEXT_SEARCH_DEPTH,
                                                     is_helper: bool = False) -> List[
        CallAndAssertionSequenceDetails]:
        """
        Returns a list of the call & assertion sequence chunks within a test method call. The call and assertion
        sequences are grouped together, with each grouping containing a list of non-assertion callables, then the list
        of assertion callables.
        Args:
            qualified_class_name: The qualified class name of the class containing the test method call.
            method_signature: The method signature of the test method being analyzed.
            testing_frameworks: The testing frameworks imported in the compilation unit containing the class and test
            method.
            visited: A tuple containing the (qualified_class_name, method_signature) of the methods already visited
            during helper calls.
            depth: An integer defining the amount of depth that is allowed to be recursively processed.
            is_helper: A boolean indicating if the current call_and_assertion_sequence is within a helper

        Returns:
            List: A list of the call and assertion sequence chunks.

        """
        if visited is None:
            visited = set()

        if (qualified_class_name, method_signature) in visited or depth <= 0:
            return []

        visited.add((qualified_class_name, method_signature))  # Ensure the same method is never re-processed

        call_and_assertion_sequences: List[CallAndAssertionSequenceDetails] = []

        method_details = self.analysis.get_method(qualified_class_name, method_signature)

        if method_details is None:
            RichLog.error(f"Error in processing method details for {method_signature} in {qualified_class_name}")
            return []

        call_site_mapping = self.__get_call_site_mapping(method_details)

        # Get 1-level helper methods
        helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
            qualified_class_name=qualified_class_name,
            method_signature=method_signature,
            depth=1,
            add_extended_class=True,
            allow_repetition=False,
        )

        method_chain_params = ExtractMethodChainParams(
            method_details=method_details,
            call_site_mapping=call_site_mapping
        )
        callable_chains = []
        if method_details is not None:
            callable_chains = self.extract_method_nodes(method_details.code, method_chain_params)

        # print("Callable chain details for :", method_signature)
        # CommonAnalysis.print_dataclass(callable_chains)

        curr_sequence = CallAndAssertionSequenceDetails()
        for root in callable_chains:

            for class_struct in self.__categorize_chain(root, testing_frameworks):
                if class_struct.classifications:
                    curr_sequence.assertion_details.append(
                        self.__build_assertion_details(class_struct, is_helper=is_helper, is_wrapped=class_struct.is_wrapped)
                    )
                else:  # If classifications are an empty list
                    params = NonAssertionCallableParams(
                        method_details=method_details,
                        call_site_mapping=call_site_mapping,
                        testing_frameworks=testing_frameworks,
                        class_struct=class_struct,
                        helper_methods=helper_methods,
                        qualified_class_name=qualified_class_name,
                        visited=visited,
                        depth=depth,
                    )
                    curr_sequence = self.__handle_non_assertion(
                        call_and_assertion_sequences, curr_sequence, params
                    )

        # Flush unclosed sequence
        if curr_sequence.call_sequence_details or curr_sequence.assertion_details:
            call_and_assertion_sequences.append(curr_sequence)

        # print("Call and assertion details for: ", method_signature)
        # CommonAnalysis.print_list_of_pydantic(call_and_assertion_sequences)

        # Important for allowing the same method to be reprocessed when duplicated with a shared parent
        visited.remove((qualified_class_name, method_signature))

        return call_and_assertion_sequences