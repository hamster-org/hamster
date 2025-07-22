import copy
import json
import os
import re
import subprocess
from pathlib import Path
from time import sleep

import pandas as pd
import requests

from config.config import Config

config_file = Path("../config/config.toml")
# read configuration from config file
config = Config(config_file, reuse=False)
token = config.get("github", "token")
print(token)
GITHUB_TOKEN = token  # Replace with your GitHub token
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}
GITHUB_API = "https://api.github.com"
# Modify the date range here
START_YEAR = 2010
END_YEAR = 2025


class ExtractGitInfo:

    @staticmethod
    def clone_repo(clone_url, dest_dir):
        """
        Clone repository from clone_url to dest_dir
        Args:
            clone_url:
            dest_dir:

        Returns:

        """
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, dest_dir],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Git clone failed: {e}")
            return False

    @staticmethod
    def generate_date_queries(start_year, end_year):
        """
        Generate date queries starting from start_year to end_year.
        This is done to divide the query into buckets as Git has a restriction on 1000 repos per query
        Args:
            start_year:
            end_year:

        Returns:

        """
        queries = []
        for year in range(start_year, end_year + 1):
            start = f"{year}-01-01"
            end = f"{year}-12-31"
            queries.append(f"language:Java stars:>=1000 created:{start}..{end}")
        return queries

    def is_organization(self, owner_url):
        """
        Check if owner_url is an organization
        Args:
            owner_url:

        Returns:

        """
        response = requests.get(owner_url, headers=HEADERS)
        if response.status_code == 200:
            return response.json().get("type") == "Organization"
        return False

    def count_java_classes_and_lines(self, repo_path):
        """
        Count the number of java classes and lines in a repository
        Args:
            repo_path:

        Returns:

        """
        java_class_count = 0
        java_line_count = 0
        for root, _, files in os.walk(repo_path):
            for file in files:
                if file.endswith(".java"):
                    try:
                        with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            java_line_count += len(lines)
                            java_class_count += sum(1 for line in lines if re.search(r'\bclass\b', line))
                    except Exception as e:
                        print(f"Error reading {file}: {e}")
        return java_class_count, java_line_count

    def get_total_repo_count(self):
        """
        Get the total number of repositories in the Github
        Returns:

        """
        query = "language:Java stars:>=1000"
        url = f"{GITHUB_API}/search/repositories?q={query}&per_page=1"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json().get("total_count", 0)
        return 0

    def search_repos(self, query):
        """
        Clone the GitHub repositories and collect their details
        Args:
            query:

        Returns:

        """
        # query = "language:Java stars:>=1000"
        per_page = 100
        max_pages = 10  # GitHub only returns first 1000 results
        repos_info = []
        for page in range(1, max_pages + 1):
            print(f"Fetching page {page}...")
            # Form the URL
            url = f"{GITHUB_API}/search/repositories?q={query}&sort=stars&order=desc&per_page={per_page}&page={page}"
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"GitHub API error: {response.status_code}")
                break
            items = response.json().get("items", [])
            for item in items:
                if self.is_organization(item["owner"]["url"]):
                    # try:
                    print(f"Processing {item['full_name']}...")
                    repo_path = Path.cwd().joinpath('repos').joinpath(item["full_name"].replace('/', '_'))
                    # Check if repo already cloned
                    if not repo_path.exists():
                        # Create the directory
                        os.makedirs(repo_path, exist_ok=True)
                        # Clone it
                        self.clone_repo(item["clone_url"], repo_path.__str__())
                    classes, lines = self.count_java_classes_and_lines(repo_path)
                    repo_data = {
                        "path": repo_path.__str__(),
                        "name": item["full_name"],
                        "stars": item["stargazers_count"],
                        "clone_url": item["clone_url"],
                        "html_url": item["html_url"],
                        "api_data": json.dumps(item, indent=2),
                        "owner_type": "Organization",
                        "class_count": classes,
                        "loc": lines
                    }
                    repos_info.append(repo_data)

                    # shutil.rmtree(temp_dir)
                    # except Exception as e:
                    #     print(f"Error processing {item['full_name']}: {e}")
            sleep(1)  # Respect API rate limits
        return repos_info


if __name__ == "__main__":
    extract_git_details = ExtractGitInfo()
    total = extract_git_details.get_total_repo_count()
    repo_info = []
    print(f"\n🔍 Total Java repos with ≥1000 stars: {total} (Only first 1000 will be fetched)")
    for query in extract_git_details.generate_date_queries(START_YEAR, END_YEAR):
        results = extract_git_details.search_repos(query)
        if results is not None:
            repo_info.extend(results)
        # Store the details
        df = pd.DataFrame(repo_info)
        df.to_json("java_repos_with_stats.json")
    print("✅ Saved results")
