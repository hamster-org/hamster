import argparse
import csv
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

EVOSUITE_JAR = os.path.expandvars("$HOME/lib/evosuite-1.2.0.jar")
EVOSUITE_STATS_FILE = "evosuite-report/statistics.csv"

class EvosuiteRunner:

    def __init__(self, project_root: Path):
        self.project_root = project_root
        maven_pom = self.project_root.joinpath("pom.xml")
        self.maven_build_file = maven_pom if maven_pom.exists() else None
        gradle_build = self.project_root.joinpath("build.gradle")
        self.gradle_build_file = gradle_build if gradle_build.exists() else None
        self.target_classes_dir = self.__find_target_classes()

    def __get_maven_root_and_namespace(self) -> (ET.Element|None, Dict[str, str]|None):
        if self.maven_build_file:
            ns = {"": "http://maven.apache.org/POM/4.0.0"}
            tree = ET.parse(source=self.maven_build_file)
            return tree.getroot(), ns
        return None, None

    def get_module_names(self) -> List[str]:
        root, ns = self.__get_maven_root_and_namespace()
        if root is None or ns is None:
            return []
        modules = root.find("modules", ns)
        if modules is None:
            return []
        return [module.text.strip() for module in root.findall("./modules/module", ns) if module.text]

    def is_evosuite_compatible(self) -> Dict[str, str|bool]:
        """
        Checks whether the project is a Java 8 or 9 project to determine compatibility with EvoSuite.

        Returns:
            bool: True if project is EvoSuite compatible; False otherwise
        """
        # return false if maven pom doesn't exist
        compatibility_info = {
            "is_compatible": False
        }
        if not self.maven_build_file:
            compatibility_info["maven_pom_exists"] = False
            return compatibility_info
        compatibility_info["maven_pom_exists"] = True
        root, ns = self.__get_maven_root_and_namespace()

        # get java version from properties
        compiler_level_properties = [
            "./properties/maven.compiler.target",
            "./properties/maven.compiler.release",
            "./properties/java.version",
        ]
        java_version = None
        for comiler_prop in compiler_level_properties:
            version_element = root.find(comiler_prop, ns)
            if version_element is not None:
                java_version = version_element.text.split(".")[-1].strip()

        # if not found, look for maven compiler pzszlugin
        if not java_version:
            for plugin in root.findall(".//plugin", ns):
                artifact_id = plugin.find("artifactId", ns)
                if artifact_id is not None and artifact_id.text == "maven-compiler-plugin":
                    conf = plugin.find("configuration", ns)
                    if conf is not None:
                        target_elem = conf.find("target", ns)
                        if target_elem is not None:
                            java_version = target_elem.text.split(".")[-1].strip()
                            break
                        release_elem = conf.find("release", ns)
                        if release_elem is not None:
                            java_version = release_elem.text.strip()
                    break

        print(f"Java version: {java_version}")
        compatibility_info["java_version"] = java_version
        if java_version in ["8", "9"]:
            compatibility_info["is_compatible"] = True
        return compatibility_info


    def __get_classpath(self) -> str:
        """
        Computes and returns the classpath string consisting of all project dependencies.

        Returns:
            str: string representing classpath dependencies of project
        """
        classpath_file = tempfile.NamedTemporaryFile(delete=False)
        if self.maven_build_file:
            try:
                subprocess.run(
                    [
                        "mvn",
                        "dependency:build-classpath",
                        f"-Dmdep.outputFile={classpath_file.name}"
                    ],
                    cwd=self.project_root,
                    capture_output=True,
                    check=True,
                    text=True
                )
                with open(classpath_file.name, "r") as f:
                    classpath = f.read().strip()
                return classpath
            except subprocess.CalledProcessError as e:
                with open(self.project_root.joinpath("evosuite_build_classpath_err.txt"), "w") as f:
                    f.write(e.stderr)
                raise Exception(f"Error creating dependency:build-classpath for {str(self.project_root)}: {e.stderr}")
            finally:
                classpath_file.close()
                os.unlink(classpath_file.name)


    def __find_target_classes(self) -> Path:
        """
        Returns the target classes directory for the project. If the directory does not exist, compiles
        the project in the case of maven. Raises an exception if the project is not a maven project or
        for a maven project compilation fails.

        Returns:
            Path: path to the target classes directory
        """
        command = None
        if self.maven_build_file:
            target_classes_dir = self.project_root.joinpath("target", "classes")
            if target_classes_dir.exists():
                return target_classes_dir
            else:
                print(f"{target_classes_dir} not found; compiling project with maven")
                command = [
                    "mvn", "compile", "-Dtest.skip", "-Drat.skip",
                    "-Dfindbugs.skip", "-Dcheckstyle.skip", "-Dpmd.skip=true",
                    "-Dspotbugs.skip", "-Denforcer.skip", "-Dlicense.skip=true"
                ]
        elif self.gradle_build_file:
            command = [
                "gradlew", "classes"
            ]
            raise Exception(f"Gradle project not supported: {str(self.project_root)}")
        else:
            raise Exception(f"Non-maven/gradle project not supported: {str(self.project_root)}")
        if command:
            try:
                subprocess.run(
                    command,
                    cwd=self.project_root,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                with open(self.project_root.joinpath("evosuite_compile_err.txt"), "w") as f:
                    f.write(e.output)
                raise Exception(f"Error compiling {str(self.project_root)}: {e.output}")
        return target_classes_dir


    def __parse_statistics(self) -> Dict[str, float|int] | None:
        stats_file = self.project_root.joinpath(EVOSUITE_STATS_FILE)
        if not stats_file.exists():
            return None
        total_tests = 0
        total_classes = 0
        total_line_coverage = 0.0
        total_branch_coverage = 0.0
        total_method_coverage = 0
        total_mutation_score = 0.0
        with open(stats_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_classes += 1
                total_tests += int(row.get("Size"), 0)
                total_line_coverage += float(row.get("LineCoverage", 0.0))
                total_branch_coverage += float(row.get("BranchCoverage", 0.0))
                total_method_coverage += float(row.get("MethodCoverage", 0.0))
                total_mutation_score += float(row.get("MutationScore", 0.0))

        return {
            "total_classes": total_classes,
            "total_tests": total_tests,
            "line_coverage": total_line_coverage / total_classes,
            "branch_coverage": total_branch_coverage / total_classes,
            "method_coverage": total_method_coverage / total_classes,
            "mutation_score": total_mutation_score / total_classes
        }


    def run_evosuite(self, target_class: str = None, search_budget: int = 60,
                     reset_statistics: bool = True, output_dir: Path = Path("src/test/java")) -> Dict[str, int|float] | None:
        """
        Runs Evosuite on the entire project or a specific class if provided. Returns st

        Args:
            target_class (str): Optional fully qualified name of class
            search_budget (int): Optional time budget per class in seconds
            reset_statistics (bool): Optional boolean indicating whether the Evosuite stats file
                should be cleared before test generation
            output_dir (Path): Optional output directory to put the generated tests in

        Returns:
            dict: Dictionary containing information about number of classes, number of generated tests,
                line coverage, branch coverage, method coverage, and mutation score
        """
        if not self.maven_build_file:
            raise Exception(f"Non-maven project {str(self.project_root)} not supported for EvoSuite run")
        print(f"Running EvoSuite on: {str(self.project_root)}; target_class={target_class}; search_budget={search_budget}")
        classpath = self.__get_classpath()
        # classes_dir = self.__find_target_classes()
        full_classpath = f"{classpath}:{self.target_classes_dir}"

        # if reset stats specified, remove evosuite statistics file
        if reset_statistics:
            self.project_root.joinpath(EVOSUITE_STATS_FILE).unlink(missing_ok=True)

        # create output directory
        output_test_dir = self.project_root.joinpath(output_dir)
        output_test_dir.mkdir(parents=True, exist_ok=True)

        evosuite_command = ["java", "-jar", EVOSUITE_JAR]
        evosuite_command.extend(["-class", target_class] if target_class else ["-target", self.target_classes_dir])
        evosuite_command.extend([
            "-projectCP", str(full_classpath),
            "-Doutput_variables=TARGET_CLASS,criterion,Size,LineCoverage,BranchCoverage,MethodCoverage,MutationScore",
            f"-Dsearch_budget={search_budget}",
            f"-Dtest_dir={str(output_test_dir)}"
        ])
        print(f"Running EvoSuite command: {evosuite_command}")
        try:
            result = subprocess.run(
                evosuite_command,
                cwd=self.project_root,
                check=True,
                capture_output=False,
                text=True
            )
        except subprocess.CalledProcessError as e:
            with open(self.project_root.joinpath("evosuite_err.txt"), "w") as f:
                f.write(e.stderr)
            raise Exception(f"EvoSuite run failed: {e.stderr}")

        print("EvoSuite finished successfully; parsing test generation statistics")
        evosuite_stats = self.__parse_statistics()
        print(f"EvoSuite stats: {evosuite_stats}")
        return evosuite_stats


def _run_evosuite_and_write_stats(evosuite_runner: EvosuiteRunner,
                                  target_class: str, search_budget: int,
                                  output_dir: Path) -> None:
    es_stats = evosuite_runner.run_evosuite(
        target_class=target_class,
        search_budget=search_budget,
        reset_statistics=True,
        output_dir=output_dir
    )
    if es_stats is not None:
        stats_file = Path(project_root).joinpath("evosuite_stats.json")
        with open(stats_file, "w") as f:
            json.dump(es_stats, f, indent=4)
        print(f"EvoSuite stats written to {stats_file}")
    else:
        print("EvoSuite statistics not created")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run EvoSuite on a given Java maven project")
    parser.add_argument("--project-root", "-pr", required=True,
                        help="Path to project root directory")
    parser.add_argument("--target-class", "-tc", default=None,
                        help="Path to project root directory")
    parser.add_argument("--search-budget", "-sb", type=int, default=60,
                        help="Search budget (in seconds) per class")
    parser.add_argument("--output-dir", "-od", type=str, default="src/test/java",
                        help="Output directory for the generated tests")
    args = parser.parse_args()
    project_root = args.project_root

    evosuite_runner = EvosuiteRunner(project_root=Path(project_root))
    module_names = evosuite_runner.get_module_names()
    if module_names:
        for module_name in module_names:
            print(f"Running evosuite on module {module_name} of project {project_root}")
            _run_evosuite_and_write_stats(
                evosuite_runner=EvosuiteRunner(project_root=Path(project_root).joinpath(module_name)),
                target_class=args.target_class,
                search_budget=args.search_budget,
                output_dir=args.output_dir
            )
    else:
        _run_evosuite_and_write_stats(evosuite_runner=evosuite_runner)
        es_stats = evosuite_runner.run_evosuite(
            target_class=args.target_class,
            search_budget=args.search_budget,
            reset_statistics=True,
            output_dir=args.output_dir
        )
