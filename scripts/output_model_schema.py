import json

from hamster.code_analysis.model.models import ProjectAnalysis

def main():
    schema_json = ProjectAnalysis.model_json_schema()
    print(json.dumps(schema_json, indent=2))

if __name__ == "__main__":
    main()