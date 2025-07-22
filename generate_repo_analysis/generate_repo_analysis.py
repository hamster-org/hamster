import json
import os
from pathlib import Path
from typing import Tuple
import ray

ray.init()
from cldk import CLDK
from cldk.analysis import AnalysisLevel

from hamster.utils.pretty import ProgressBarFactory


class GenerateAnalysis:
    @staticmethod
    def __run_cldk(repo_path: Path, store_path: Path) -> Tuple[bool, bool, str, str]:
        is_call_graph = True
        is_symbol_table = True
        call_graph_error = ''
        symbol_table_error = ''
        call_graph_path = store_path.joinpath('call_graph')
        symbol_table_path = store_path.joinpath('symbol_table')
        os.makedirs(call_graph_path, exist_ok=True)
        os.makedirs(symbol_table_path, exist_ok=True)
        try:
            analysis = CLDK(language="java").analysis(
                project_path=repo_path,
                analysis_backend_path=None,
                analysis_level=AnalysisLevel.call_graph,
                analysis_json_path=call_graph_path,
            )
        except Exception as e:
            is_call_graph = False
            call_graph_error = e.__str__()
            pass
        try:
            analysis = CLDK(language="java").analysis(
                project_path=repo_path,
                analysis_backend_path=None,
                analysis_level=AnalysisLevel.symbol_table,
                analysis_json_path=symbol_table_path,
            )
        except Exception as e:
            is_symbol_table = False
            symbol_table_error = e.__str__()
            pass
        return is_call_graph, is_symbol_table, call_graph_error, symbol_table_error

    def generate(self, dataset_path: Path, store_path: Path):
        report = []
        folder_list = [folder for folder in os.listdir(dataset_path) if
                       os.path.isdir(os.path.join(dataset_path, folder))]
        with (ProgressBarFactory.get_progress_bar() as p):
            for folder in p.track(folder_list, total=len(folder_list)):
                dataset_name = folder.split('/')[-1]
                dataset_store_path = Path(store_path).joinpath(dataset_name)
                os.makedirs(dataset_store_path, exist_ok=True)
                is_call_graph, is_symbol_table, call_graph_error, symbol_table_error = self.__run_cldk(
                    Path(dataset_path).joinpath(folder),
                    dataset_store_path)
                report.append(
                    {"dataset name": dataset_name,
                     "is_call_graph_generated": is_call_graph,
                     "is_symbol_table_generated": is_symbol_table,
                     "call_graph_error": call_graph_error,
                     "symbol_table_error": symbol_table_error
                     }
                )
                with open('report.json', 'w') as f:
                    json.dump(report, f, indent=4)



