import glob
import json
import os
import traceback
from pathlib import Path
from typing import List, Dict

import ray
from cldk import CLDK
from cldk.analysis import AnalysisLevel

from hamster.code_analysis.common.common_analysis import CommonAnalysis
from hamster.code_analysis.common.reachability import Reachability
from hamster.code_analysis.focal_class_method.focal_class_method import FocalClassMethod
from hamster.code_analysis.model.models import ProjectAnalysis, TestingFramework
from hamster.code_analysis.test_statistics.call_and_assertion_sequence_details_info import \
    CallAndAssertionSequenceDetailsInfo
from hamster.code_analysis.test_statistics.setup_analysis_info import SetupAnalysisInfo
from hamster.code_analysis.test_statistics.test_method_analysis_info import TestMethodAnalysisInfo
from hamster.utils.pretty import ProgressBarFactory

hamster_analysis_parent_directory = "hamster_results/<old_model>"
cldk_analysis_parent_directory = "hamster/analysis"
store_path = 'hamster_results/<new_model>'

class HamsterModelAlterer:
    def __init__(self, analysis_path: str, project_analysis_file: str, store_path: str):
        self.analysis = CLDK(language="java").analysis(
            project_path='',
            analysis_backend_path=None,
            analysis_level=AnalysisLevel.symbol_table,
            analysis_json_path=analysis_path,
        )
        with open(project_analysis_file, 'r') as f:
            file_content = json.load(f)
            self.project_analysis = ProjectAnalysis.model_validate(file_content)
        self.store_path = store_path
        _, self.application_classes = CommonAnalysis(self.analysis).get_test_methods_classes_and_application_classes()

    def alter_focal_class(self):
        """
        Alter the focal class details.
        """
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                testing_frameworks = cls.testing_frameworks
                setup_methods = SetupAnalysisInfo(self.analysis).get_setup_methods(
                    qualified_class_name=cls.qualified_class_name,
                    testing_frameworks=testing_frameworks,
                )
                for method in cls.test_method_analyses:
                    focal_classes, is_application_classed_used, is_ui_test, is_api_test = \
                        (FocalClassMethod(
                            analysis=self.analysis,
                            testing_frameworks=testing_frameworks,
                            application_classes=self.application_classes
                        ).identify_focal_class_and_ui_api_test(
                            test_class_name=cls.qualified_class_name,
                            test_method_signature=method.method_signature,
                            setup_method_signatures=setup_methods
                        ))
                    method.focal_classes = focal_classes

    def alter_test_type_focal_classes(self):
        """
        Alter the test type and focal classes.
        """
        for cls in self.project_analysis.test_class_analyses:
            testing_frameworks = cls.testing_frameworks
            setup_methods = SetupAnalysisInfo(self.analysis).get_setup_methods(
                qualified_class_name=cls.qualified_class_name,
                testing_frameworks=testing_frameworks,
            )
            for method in cls.test_method_analyses:
                test_type, focal_classes = TestMethodAnalysisInfo(
                    analysis=self.analysis,
                    dataset_name=self.project_analysis.dataset_name,
                    application_classes=self.application_classes
                ).get_test_type_focal_classes(
                    cls.qualified_class_name,
                    method.method_signature,
                    testing_frameworks,
                    setup_methods
                )
                method.test_type = test_type
                method.focal_classes = focal_classes

    def alter_call_assertion_sequences(self):
        """
        Alter the call and assertion sequences.
        """
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                testing_frameworks = cls.testing_frameworks
                for method in cls.test_method_analyses:
                    call_assertion_sequences = CallAndAssertionSequenceDetailsInfo(
                        self.analysis,
                        self.project_analysis.dataset_name
                    ).get_call_and_assertion_sequence_details_info(
                        qualified_class_name=cls.qualified_class_name,
                        method_signature=method.method_signature,
                        testing_frameworks=testing_frameworks
                    )
                    method.call_assertion_sequences = call_assertion_sequences

    def alter_testing_framework(self):
        """
        Add two android testing frameworks
        Returns:

        """
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                testing_frameworks = CommonAnalysis(self.analysis).get_testing_frameworks_for_class(
                    qualified_class_name=cls.qualified_class_name)
                if TestingFramework.ROBOTIUM in testing_frameworks:
                    cls.testing_frameworks.append(TestingFramework.ROBOTIUM)
                if TestingFramework.APPIUM in testing_frameworks:
                    cls.testing_frameworks.append(TestingFramework.APPIUM)

    def alter_method_for_cyclo(self):
        """
        Alter the method's cyclomatic complexity.
        """
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                for method in cls.test_method_analyses:
                    qualified_class_name = cls.qualified_class_name
                    method_signature = method.method_signature

                    method_details = self.analysis.get_method(qualified_class_name, method_signature)
                    if not method_details:
                        continue

                    helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
                        qualified_class_name,
                        method_signature,
                        add_extended_class=True,
                        allow_repetition=True
                    )

                    all_methods = helper_methods
                    all_methods.setdefault(qualified_class_name, []).append(method_signature)

                    cyclomatic_complexity_with_helpers = 0
                    for class_name in all_methods:
                        for method_sig in all_methods[class_name]:
                            method_details = self.analysis.get_method(class_name, method_sig)
                            if not method_details:
                                continue

                            cyclomatic_complexity_with_helpers += method_details.cyclomatic_complexity if method_details.cyclomatic_complexity else 0

                    method.cyclomatic_complexity_with_helpers = cyclomatic_complexity_with_helpers
                    method.cyclomatic_complexity = method_details.cyclomatic_complexity if method_details.cyclomatic_complexity else 0

    def alter_method_for_helper_methods(self):
        """
        Alter method analysis to add helper methods details.
        """
        common_analysis = CommonAnalysis(self.analysis)
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                qualified_class_name = cls.qualified_class_name
                all_analyses = cls.test_method_analyses
                for analysis_obj in all_analyses:
                    method_signature = analysis_obj.method_signature

                    method_details = self.analysis.get_method(qualified_class_name, method_signature)
                    if not method_details:
                        continue



                    helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
                        qualified_class_name,
                        method_signature,
                        add_extended_class=True,
                        allow_repetition=True
                    )
                    all_methods = helper_methods
                    helper_method_count = 0
                    for klazz in helper_methods:
                        helper_method_count += len(helper_methods[klazz])
                    helper_ncloc = sum(
                        common_analysis.get_ncloc(helper_details.declaration, helper_details.code)
                        for class_name in all_methods
                        for method_sig in all_methods[class_name]
                        if (helper_details := self.analysis.get_method(class_name, method_sig)) is not None
                    )
                    analysis_obj.number_of_helper_methods = helper_method_count
                    analysis_obj.helper_method_ncloc = helper_ncloc

    def alter_method_for_ncloc(self):
        """
        Alter method's AND fixture method's NCLOC, and also add NCLOC with helpers.
        """
        common_analysis = CommonAnalysis(self.analysis)
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                qualified_class_name = cls.qualified_class_name
                all_analyses = [
                    *cls.setup_analyses,
                    *cls.teardown_analyses,
                    *cls.test_method_analyses
                ]
                for analysis_obj in all_analyses:
                    method_signature = analysis_obj.method_signature

                    method_details = self.analysis.get_method(qualified_class_name, method_signature)
                    if not method_details:
                        continue

                    ncloc = common_analysis.get_ncloc(method_details.declaration, method_details.code)

                    helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
                        qualified_class_name,
                        method_signature,
                        add_extended_class=True,
                        allow_repetition=True
                    )

                    all_methods = helper_methods
                    all_methods.setdefault(qualified_class_name, []).append(method_signature)

                    ncloc_with_helpers = sum(
                        common_analysis.get_ncloc(helper_details.declaration, helper_details.code)
                        for class_name in all_methods
                        for method_sig in all_methods[class_name]
                        if (helper_details := self.analysis.get_method(class_name, method_sig)) is not None
                    )

                    analysis_obj.ncloc = ncloc
                    analysis_obj.ncloc_with_helpers = ncloc_with_helpers

    def alter_method_for_ncloc_and_qualified_class(self):
        """
        Alter method's AND fixture method's NCLOC, and also add NCLOC with helpers.
        Also, add qualified class name to each.
        """
        common_analysis = CommonAnalysis(self.analysis)
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                qualified_class_name = cls.qualified_class_name
                all_analyses = [
                    *cls.setup_analyses,
                    *cls.teardown_analyses,
                    *cls.test_method_analyses
                ]
                for analysis_obj in all_analyses:
                    method_signature = analysis_obj.method_signature

                    method_details = self.analysis.get_method(qualified_class_name, method_signature)
                    if not method_details:
                        continue

                    ncloc = common_analysis.get_ncloc(method_details.declaration, method_details.code)

                    helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
                        qualified_class_name,
                        method_signature,
                        add_extended_class=True,
                        allow_repetition=True
                    )

                    all_methods = helper_methods
                    all_methods.setdefault(qualified_class_name, []).append(method_signature)

                    ncloc_with_helpers = sum(
                        common_analysis.get_ncloc(helper_details.declaration, helper_details.code)
                        for class_name in all_methods
                        for method_sig in all_methods[class_name]
                        if (helper_details := self.analysis.get_method(class_name, method_sig)) is not None
                    )

                    analysis_obj.ncloc = ncloc
                    analysis_obj.ncloc_with_helpers = ncloc_with_helpers
                    analysis_obj.qualified_class_name = qualified_class_name

    def alter_method_for_ncloc_cyclo_qualified(self):
        """
                Alter method's AND fixture method's NCLOC, and also add NCLOC with helpers.
                Also, add qualified class name to each.
                """
        common_analysis = CommonAnalysis(self.analysis)
        with (ProgressBarFactory.get_progress_bar() as p):
            for cls in p.track(self.project_analysis.test_class_analyses, total=len(self.project_analysis.test_class_analyses)):
                qualified_class_name = cls.qualified_class_name
                all_analyses = [
                    *cls.setup_analyses,
                    *cls.teardown_analyses,
                    *cls.test_method_analyses
                ]
                for analysis_obj in all_analyses:
                    method_signature = analysis_obj.method_signature

                    method_details = self.analysis.get_method(qualified_class_name, method_signature)
                    if not method_details:
                        continue

                    ncloc = common_analysis.get_ncloc(method_details.declaration, method_details.code)
                    cyclo_complexity = method_details.cyclomatic_complexity if method_details.cyclomatic_complexity else 0

                    helper_methods: Dict[str, List[str]] = Reachability(self.analysis).get_helper_methods(
                        qualified_class_name,
                        method_signature,
                        add_extended_class=True,
                        allow_repetition=True
                    )

                    all_methods = helper_methods
                    all_methods.setdefault(qualified_class_name, []).append(method_signature)

                    ncloc_with_helpers = 0
                    cyclo_with_helpers = 0
                    for class_name in all_methods:
                        for method_sig in all_methods[class_name]:
                            if (helper_details := self.analysis.get_method(class_name, method_sig)) is not None:
                                ncloc_with_helpers += common_analysis.get_ncloc(helper_details.declaration, helper_details.code)
                                cyclo_with_helpers += helper_details.cyclomatic_complexity if helper_details.cyclomatic_complexity else 0

                    analysis_obj.ncloc = ncloc
                    analysis_obj.ncloc_with_helpers = ncloc_with_helpers
                    analysis_obj.cyclomatic_complexity = cyclo_complexity
                    analysis_obj.cyclomatic_complexity_with_helpers = cyclo_with_helpers
                    analysis_obj.qualified_class_name = qualified_class_name


    def save(self):
        """
        Save the altered project analysis to the store path.
        """
        project_analysis_str = self.project_analysis.model_dump_json()
        output_dir = Path(self.store_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, 'w') as f:
            f.write(project_analysis_str)


@ray.remote
def alter_hamster_model(file):
    try:
        directory_name = file.replace(hamster_analysis_parent_directory, '').replace('hamster.json', '').replace('/', '')
        analysis_path = os.path.join(cldk_analysis_parent_directory, directory_name, 'symbol_table')
        store_path_file = file.replace(hamster_analysis_parent_directory, store_path)

        alterer = HamsterModelAlterer(analysis_path=analysis_path,
                                      project_analysis_file=file,
                                      store_path=store_path_file)

        # Choose which alterations to perform
        # alterer.alter_focal_class()
        # alterer.alter_test_type_focal_classes()
        alterer.alter_call_assertion_sequences()
        # alterer.alter_method_for_cyclo()
        # alterer.alter_method_for_ncloc_cyclo_qualified()
        # alterer.alter_method_for_helper_methods()
        # alterer.alter_testing_framework()

        alterer.save()

    except Exception as e:
        print(f"Error parsing hamster.json from: {file} {e}")


if __name__ == '__main__':
    pattern = os.path.join(hamster_analysis_parent_directory, "**", 'hamster.json')
    all_files = glob.glob(pattern, recursive=True)
    print("Loading Hamster analyses from files...")
    print(f"Processing {len(all_files)} total repositories...")
    # alter_hamster_model(all_files[1])
    ray_tasks = [
        alter_hamster_model.remote(
            file
        )
        for file in all_files
    ]
    try:
        ray.get(ray_tasks)
    except Exception:
        traceback.print_exc()

    print("Completed model generation...")
    ray.shutdown()