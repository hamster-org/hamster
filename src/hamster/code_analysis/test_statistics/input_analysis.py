from typing import List, Set, Dict, Optional

from cldk.analysis.java import JavaAnalysis
from cldk.models.java import JCallable
from cldk.models.java.models import JCallSite

from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.model.models import TestInput, InputType
from hamster.code_analysis.utils.constants import STRUCTURED_INPUT_MAP

class InputAnalysis:
    def __init__(self, analysis: JavaAnalysis):
        self.analysis = analysis

    def get_input_details(self, qualified_class_name: str, method_signature: str) -> List[TestInput]:
        """
        Retrieves a list of test inputs for the given method and its reachable helper methods.

        Args:
            qualified_class_name: The fully qualified name of the class containing the method.
            method_signature: The signature of the method to analyze.

        Returns:
            List[TestInput]: A list of identified test inputs from the method and its helpers.
        """
        method_details = self.analysis.get_method(qualified_class_name, method_signature)
        if not method_details:
            return []

        test_inputs: List[TestInput] = []

        # Get all reachable helper methods, including those from extended classes
        helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
            qualified_class_name,
            method_signature,
            add_extended_class=True,
            allow_repetition=True
        )

        # Include the original method in the analysis
        all_methods = helper_methods
        all_methods.setdefault(qualified_class_name, []).append(method_signature)

        # Collect inputs from all relevant methods
        for class_name in all_methods:
            for method_sig in all_methods[class_name]:
                method = self.analysis.get_method(class_name, method_sig)
                if not method:
                    continue
                test_inputs.extend(self.__collect_inputs(method))

        return test_inputs

    def __get_input_type(self, call_site: JCallSite) -> Optional[List[InputType]]:
        input_types: Set[InputType] = set()

        is_ctor = call_site.is_constructor_call
        recv_type = call_site.receiver_type or ''
        recv_expr = call_site.receiver_expr or ''
        callee_sig = call_site.callee_signature or ''
        method_called = call_site.method_name or ''

        for input_type, prefix_maps in STRUCTURED_INPUT_MAP.items():
            for prefix, method_names in prefix_maps.items():

                # Handle malformed constructor calls where signature is missing
                if is_ctor and not callee_sig:
                    if any(m.startswith("new ") and m[4:] == recv_type for m in method_names):
                        input_types.add(input_type)
                    continue

                # Check receiver type or expression for prefix matching
                if recv_type:
                    # Skip if receiver type does not start with the prefix
                    if not recv_type.startswith(prefix):
                        continue
                else:
                    # For static calls without receiver type, check expression against prefix end
                    if prefix.rsplit(".", 1)[-1] != recv_expr:
                        continue

                # Match method names or constructor invocations
                for candidate in method_names:
                    if not is_ctor:
                        if candidate == method_called:
                            input_types.add(input_type)
                            break
                    else:
                        if candidate.startswith("new "):
                            ctor_name = callee_sig.split("(", 1)[0]
                            if candidate[4:] == ctor_name:
                                input_types.add(input_type)
                                break

        return list(input_types) if input_types else None

    def __collect_inputs(self, method_details: JCallable) -> List[TestInput]:
        input_details: List[TestInput] = []

        # Check call sites for classpath-based resources (java.lang.Class.getResources)
        for call_site in method_details.call_sites:
            input_type = self.__get_input_type(call_site)
            if input_type:
                input_details.append(
                    TestInput(
                        method_name=call_site.method_name,
                        method_signature=call_site.callee_signature,
                        receiver_type=call_site.receiver_type,
                        receiver_expr=call_site.receiver_expr,
                        input_type=input_type
                    )
                )

        # Note: Any wrapper classes will be parsed through reachability
        return input_details