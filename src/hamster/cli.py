import glob
import json
import os
from pathlib import Path
from typing import Annotated, List

import typer
from cldk import CLDK
from cldk.analysis import AnalysisLevel

from hamster.code_analysis.model.models import ProjectAnalysis
from hamster.code_analysis.test_statistics.project_analysis_info import ProjectAnalysisInfo
from hamster.code_analysis.utils import constants
from hamster.extract_statistics.assertion_details.assertion_details import AssertionDetails
from hamster.extract_statistics.overall_characteristics.overall_characteristics import OverallCharacteristics
from hamster.extract_statistics.test_input.test_input import TestInputDetails
from hamster.extract_statistics.test_input.test_input_v2 import TestInputDetailsV2
from hamster.extract_statistics.test_method_sequence.test_method_sequence import TestMethodSequence
from hamster.extract_statistics.test_method_sequence.test_method_sequence_per_type_test_scope import \
    TestMethodPerTestScope
from hamster.extract_statistics.test_setup.test_setup_details import TestSetupDetails
from hamster.extract_statistics.test_setup.test_teardown_details import TestTeardownDetails
from hamster.utils.output_format import OutputFormatType
from hamster.utils.pretty import ProgressBarFactory

app = typer.Typer(help="Hamster",
                  pretty_exceptions_enable=False,
                  pretty_exceptions_show_locals=False, add_completion=False)


@app.callback()
def main() -> None:
    """Handles the global options"""
    return


@app.command()
def analysis(
        project_path: Annotated[
            str,
            typer.Option(
                help="Path to the root directory of the application under test.",
                show_default=False,
            ),
        ] = None,
        analysis_path: Annotated[
            str,
            typer.Option(
                help="Path to the root directory of the application under test.",
                show_default=False,
            ),
        ] = None,
        store_hamster_model_path: Annotated[
            str,
            typer.Option(
                help="Path where hamster model data is stored",
                show_default=False,
            )] = None,
):
    cldk = CLDK(language="java").analysis(
        project_path=project_path,
        analysis_backend_path=None,
        analysis_level=AnalysisLevel.symbol_table,
        analysis_json_path=analysis_path,
    )
    project_analysis = (ProjectAnalysisInfo(analysis=cldk,
                                            dataset_name=Path(project_path).name)
                        .gather_project_analysis_info())
    project_analysis_str = project_analysis.model_dump_json()

    output_dir = Path(store_hamster_model_path) / Path(project_path).name
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "hamster.json", 'w') as f:
        f.write(project_analysis_str)


@app.command()
def statistics(
        hamster_analysis_parent_directory: Annotated[
            str,
            typer.Option(
                help="Path to the root directory where all the hamster analyses are stored.",
                show_default=False,
            ),
        ] = None,
        statistics_store_path: Annotated[
            str,
            typer.Option(
                help="Path where all the statistics are stored.",
                show_default=False,
            ),
        ] = constants.ANALYSIS_FOLDER.__str__(),
        output_format: Annotated[
            OutputFormatType,
            typer.Option(
                help="Output format type.",
                show_default=False,
            ),
        ] = OutputFormatType.JSON_PDF_FIGURES.value,
):
    print(hamster_analysis_parent_directory)
    pattern = os.path.join(hamster_analysis_parent_directory, "**", 'hamster.json')
    all_files = glob.glob(pattern, recursive=True)

    def load_project(file: str) -> ProjectAnalysis | None:
        try:
            with open(file, 'r') as f:
                file_content = json.load(f)
                return ProjectAnalysis.model_validate(file_content)
        except Exception as e:
            print(f"Error parsing hamster.json from: {file}")
            return None

    print("Loading Hamster analyses from files...")
    all_project_analyses: List[ProjectAnalysis] = []
    with ProgressBarFactory.get_progress_bar() as p:
        for file in p.track(all_files):
            result = load_project(file)
            if result:
                all_project_analyses.append(result)
            else:
                print("Error processing a hamster.json...")

    os.makedirs(Path(statistics_store_path), exist_ok=True)

    # Remove empty projects
    relevant_project_analyses: List[ProjectAnalysis] = []
    empty_project_analyses: List[ProjectAnalysis] = []
    for proj_analysis in all_project_analyses:
        if proj_analysis.test_class_analyses:
            relevant_project_analyses.append(proj_analysis)
        else:
            empty_project_analyses.append(proj_analysis)

    print()
    print(f"{len(empty_project_analyses)} projects contained no test classes or methods...")
    print(f"Analyzing the {len(relevant_project_analyses)} non-empty project analyses...")

    if len(relevant_project_analyses) > 0:

        print("Running extractors sequentially...")

        assertion_details = AssertionDetails(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        overall_characteristics = OverallCharacteristics(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        test_input_details = TestInputDetails(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        test_input_details_v2 = TestInputDetailsV2(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        test_method_sequence_details = TestMethodSequence(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        test_method_sequence_details_per_test_scope = TestMethodPerTestScope(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        test_setup_details_details = TestSetupDetails(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()
        test_teardown_details_details = TestTeardownDetails(relevant_project_analyses, output_format, Path(statistics_store_path)).extract_details()

        print()
        print("Statistics generated! Writing to JSON files...")

        with open(Path(statistics_store_path).joinpath('assertion_details.json'), 'w') as f:
            f.write(json.dumps(assertion_details))
        with open(Path(statistics_store_path).joinpath('overall_characteristics.json'), 'w') as f:
            f.write(json.dumps(overall_characteristics))
        with open(Path(statistics_store_path).joinpath('test_input_details.json'), 'w') as f:
            f.write(json.dumps(test_input_details))
        with open(Path(statistics_store_path).joinpath('test_input_details_v2.json'), 'w') as f:
            f.write(json.dumps(test_input_details_v2))
        with open(Path(statistics_store_path).joinpath('test_method_sequence_details.json'), 'w') as f:
            f.write(json.dumps(test_method_sequence_details))
        with open(Path(statistics_store_path).joinpath('test_method_sequence_details_per_test_scope.json'), 'w') as f:
            f.write(json.dumps(test_method_sequence_details_per_test_scope))
        with open(Path(statistics_store_path).joinpath('test_setup_details_details.json'), 'w') as f:
            f.write(json.dumps(test_setup_details_details))
        with open(Path(statistics_store_path).joinpath('test_teardown_details_details.json'), 'w') as f:
            f.write(json.dumps(test_teardown_details_details))

        print()
        print("Statistics processing completed!")


if __name__ == "__main__":
    app()