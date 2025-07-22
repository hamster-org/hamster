import re
from dataclasses import dataclass
from typing import List, Set, Tuple, Dict, Counter
from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from hamster.code_analysis.utils import constants

@dataclass
class ReachabilityConfig:
    allow_repetition: bool = False  # On same level
    only_helpers: bool = False
    add_extended_class: bool = False

class Reachability:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis
        self._reachability_cache: Dict[Tuple, Dict[str, List[str]]] = {}

    def get_helper_methods(
            self,
            qualified_class_name: str,
            method_signature: str,
            depth: int = constants.CONTEXT_SEARCH_DEPTH,
            add_extended_class: bool = False,
            allow_repetition: bool = False,
    ) -> Dict[str, List[str]]:
        """
        Retrieves the helper methods reachable from the given method within the specified depth.

        Args:
            qualified_class_name: The qualified name of the class.
            method_signature: The method signature.
            depth: The depth for search in call hierarchy.
            add_extended_class: If set to True, include methods from classes extended by the given class.
            allow_repetition: If set to True, allow visiting the same method multiple times in the same depth level.

        Returns:
            Dict[str, List[str]]: A map from class names to method signatures of helper methods.
        """
        method_details = self.analysis.get_method(qualified_class_name, method_signature)
        visited: Set[Tuple[str, str]] = set()
        reachability_config = ReachabilityConfig(
            allow_repetition=allow_repetition,
            add_extended_class=add_extended_class,
            only_helpers=True
        )
        reachability_key = self._get_reachability_key(qualified_class_name, method_signature, reachability_config)

        if reachability_key in self._reachability_cache:
            reachable_methods_by_class = self._reachability_cache[reachability_key]
        else:
            reachable_methods_by_class: Dict[str, List[str]] = self._collect_reachable_methods(
                qualified_class_name,
                method_signature,
                depth,
                reachability_config,
                visited
            )
            self._reachability_cache[reachability_key] = reachable_methods_by_class

        final_reachable_methods: Dict[str, List[str]] = {}
        for class_name in reachable_methods_by_class:
            for method_signature in reachable_methods_by_class[class_name]:
                method = self.analysis.get_method(qualified_class_name, method_signature)
                if (
                    method
                    and (class_name != qualified_class_name or method != method_details)
                    and method.code.isascii()
                ):
                    final_reachable_methods.setdefault(class_name, []).append(method_signature)
        return final_reachable_methods

    def _collect_reachable_methods(
            self,
            qualified_class_name: str,
            method_signature: str,
            depth: int,
            reachability_config: ReachabilityConfig,
            visited: Set[Tuple[str, str]] = None,
    ) -> Dict[str, List[str]]:
        """
        Collects reachable methods starting from the given method within a given depth.

        Args:
            qualified_class_name: The qualified name of the class.
            method_signature: The method signature.
            depth: The depth for search in call hierarchy.
            reachability_config: The configurations for reachability computation.
            visited: The set of tuples that have already been visited.

        Returns:
            Dict[str, List[str]]: A map from class names to method signatures of reachable methods.
        """
        if depth < 0:
            return {}

        if visited is None:
            visited: Set[Tuple[str, str]] = set()

        # Normalize constructors
        simple_class_name = qualified_class_name.split('.')[-1]
        if method_signature.startswith(f"{simple_class_name}("):
            method_signature = method_signature.replace(f"{simple_class_name}(", "<init>(")

        basic_key = (qualified_class_name, method_signature)

        # Check for an existing depth-level duplicate
        if basic_key in visited:
            return {}
        visited.add(basic_key)

        reachability_key = self._get_reachability_key(qualified_class_name, method_signature, reachability_config)

        # Check if already expanded in cache
        if reachability_key in self._reachability_cache:
            return self._reachability_cache[reachability_key]

        method_details = self.analysis.get_method(qualified_class_name, method_signature)

        # Check for ensuring valid method
        if not method_details:
            return {}

        # Seed result dictionary with the current method to start
        reachable_methods: Dict[str, List[str]] = {qualified_class_name: [method_signature]}

        # Determine extended classes if needed
        extend_list = []
        if reachability_config.add_extended_class:
            class_details = self.analysis.get_class(qualified_class_name)
            extend_list = class_details.extends_list if class_details else []

        child_counter: Counter[Tuple[str, str]] = Counter()

        # Handle interface-based call sites
        interface_map: Dict[str, List[str]] = {}
        for site in method_details.call_sites:
            receiver = site.receiver_type
            receiver_class = self.analysis.get_class(receiver)
            if receiver_class and receiver_class.is_interface:
                processed_sig = site.callee_signature
                interface_map.setdefault(receiver, []).append(processed_sig)

        # For all call sites with interface receiver types, collect the method signature
        for interface, callee_sigs in interface_map.items():
            for concrete_class in self.get_concrete_classes(interface_class=interface):
                # All concrete classes that implement interface
                if (
                    (not reachability_config.only_helpers or concrete_class == qualified_class_name)
                    or concrete_class in extend_list
                ):
                    for callee_sig in callee_sigs:
                        child_counter[(concrete_class, callee_sig)] += 1

        # Handle direct symbol-table callees
        callees = self.analysis.get_callees(
            source_class_name=qualified_class_name,
            source_method_declaration=method_signature,
            using_symbol_table=True
        ).get('callee_details', [])
        for callee_details in callees:
            callee_class = callee_details['callee_method'].klass
            if (
                (not reachability_config.only_helpers or callee_class == qualified_class_name)
                or callee_class in extend_list
            ):
                callee_sig = callee_details['callee_method'].method.signature
                num_calls = len(callee_details["calling_lines"])
                # CLDK currently has a strange bug with calling_lines returning empty lists...
                # if num_calls == 0:
                #     raise Exception("A called method has no calling lines...")
                child_counter[(callee_class, callee_sig)] += num_calls

        # Now process unique children
        for child_key, num_calls in child_counter.items():
            child_class, child_sig = child_key
            child_reachable_methods = self._collect_reachable_methods(
                child_class, child_sig, depth - 1, reachability_config, visited
            )
            if reachability_config.allow_repetition:
                add_times = num_calls
            else:
                add_times = 1 if num_calls > 0 else 0
            for _ in range(add_times):
                for child_c_class, methods_list in child_reachable_methods.items():
                    reachable_methods.setdefault(child_c_class, []).extend(methods_list)

        # This will allow a parent to revisit at the same level
        if reachability_config.allow_repetition:
            visited.remove(basic_key)

        return reachable_methods

    def get_concrete_classes(self, interface_class: str) -> List[str]:
        """
        Returns a list of concrete classes that implement the given interface class.

        Args:
            interface_class: The interface class.

        Returns:
            List[str]: List of concrete classes that implement the given interface class.
        """
        all_classes_in_application = self.analysis.get_classes()
        concrete_classes = []
        for qualified_class, class_details in all_classes_in_application.items():
            if not class_details.is_interface and "abstract" not in class_details.modifiers:
                if interface_class in class_details.implements_list:
                    concrete_classes.append(qualified_class)
        return concrete_classes

    def _get_reachability_key(self,
                              qualified_class_name: str,
                              method_signature: str,
                              reachability_config: ReachabilityConfig) -> Tuple:
        """
        Generates a unique key for the reachability computation based on the input parameters.

        Args:
            qualified_class_name: The qualified name of the class.
            method_signature: The method signature.
            reachability_config: The configurations for reachability computation.

        Returns:
            Tuple: A unique reachability key.
        """
        reachability_key = (
            qualified_class_name,
            method_signature,
            reachability_config.allow_repetition,
            reachability_config.add_extended_class,
            reachability_config.only_helpers
        )
        return reachability_key