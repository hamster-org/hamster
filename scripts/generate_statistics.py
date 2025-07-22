import subprocess
import traceback
from pathlib import Path

from hamster.utils.output_format import OutputFormatType

def main():
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent.parent
    src_dir = root / "hamster" / "src"
    # Put your repo here
    hamster_results = root / "example" / "hamster_results"
    model_dir = hamster_results / "model"
    statistics_dir = hamster_results / "statistics"
    output_format = OutputFormatType.JSON_PDF_FIGURES

    cmd = [
        "poetry", "run",
        "python", "-m", "hamster.cli", "statistics",
        "--hamster-analysis-parent-directory", str(model_dir),
        "--statistics-store-path", str(statistics_dir),
        "--output-format", output_format.value,
    ]

    print("Attempting to generate statistics...")
    print()

    try:
        subprocess.run(cmd, check=True, cwd=src_dir)
    except subprocess.CalledProcessError as e:
        print(f"Failed... Exit code {e.returncode}")
        print("Python stack trace for CalledProcessError:")
        traceback.print_exc()
    else:
        print(f"Done. Output in {statistics_dir}\n", flush=True)

if __name__ == "__main__":
    main()