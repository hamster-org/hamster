from pathlib import Path

def main():
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent.parent

    repos_dir = root / "xvdc" / "repos"
    analysis_dir = root / "xvdc" / "analysis"
    model_dir = root / "xvdc" / "hamster_results" / "model"

    all_repos = [repo for repo in repos_dir.iterdir() if repo.is_dir()]

    unaccounted = 0
    model_generated = 0
    analysis_count = 0
    repo_count = 0

    for repo in all_repos:
        repo_count += 1

        repo_name = repo.name

        model_file = model_dir / repo_name / "hamster.json"
        analysis_file = analysis_dir / repo_name / "symbol_table" / "analysis.json"

        has_analysis = analysis_file.is_file()
        has_model = model_file.is_file()

        if has_analysis:
            analysis_count += 1

        if has_model:
            model_generated += 1
        elif has_analysis: # No model but an analysis file was generated
            unaccounted += 1
            print(f"Hamster model was incorrectly not generated for {repo_name}...")

    print()
    print(f"There are {repo_count} total available repositories...")
    print(f"There are {analysis_count} repositories with generated 'analysis.json' files...")
    print(f"There are {unaccounted} Hamster models that are unexpectedly not generated...")
    print(f"There are {model_generated} Hamster models that are generated...")

if __name__ == "__main__":
    main()

