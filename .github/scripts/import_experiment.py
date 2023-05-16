#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import date
from jsonpath_ng.ext import parse
import argparse
import json
import os
import requests
import sys
import toml
import urllib.request


def get_experiment_json(exp_id):
    # Get experiment JSON from Nimbus API
    host = "https://stage.experimenter.nonprod.dataops.mozgcp.net"
    url = f"{host}/api/v6/draft-experiments/{exp_id}/"
    try:
        data = urllib.request.urlopen(url)
    except urllib.error.HTTPError as e:
        print(f"Experiment with ID {exp_id} not found.")
        sys.exit(e)

    return json.load(data)


def generate_ftl_file(recipe):
    # Generate a FTL file from the recipe

    file_content = [
        "# This Source Code Form is subject to the terms of the Mozilla Public",
        "# License, v. 2.0. If a copy of the MPL was not distributed with this",
        "# file, You can obtain one at http://mozilla.org/MPL/2.0/.\n",
    ]
    parsed_ids = {}

    for branch in recipe["branches"]:
        file_content.append(f"## Branch: {branch['slug']}\n")
        for feature in branch["features"]:
            # Find all $l10n keys in the branch value
            branch_value = feature["value"]["content"]
            jsonpath_expression = parse('$.."$l10n"')
            for match in jsonpath_expression.find(branch_value):
                id = match.value["id"]
                text = match.value["text"]
                comment = match.value.get("comment", "")
                if id in parsed_ids:
                    # We already parsed a string with this ID. Verify that the
                    # text is the same, if not send a warning.
                    if parsed_ids[id] != text:
                        print(f"WARNING: the ID {id} is used with different values")
                        print(f"Previous: {parsed_ids['id']}")
                        print(f"New: {text}")
                else:
                    if comment:
                        file_content.append(f"# {comment}")
                    file_content.append(f"{id} = {text}\n")
                    # Store in dictionary to avoid duplicates
                    parsed_ids[id] = text

    return "\n".join(file_content)


def print_toml_file(toml_data):
    # Format the TOML file to minimize difference with the format normally used

    def print_locales(locales, indent=0):
        # Order and format list of locales
        locales.sort()
        lines = ["locales = ["]
        for i, loc in enumerate(locales, start=1):
            line = f'    "{loc}"'
            if i < len(locales):
                line += ","
            lines.append(line)
        lines.append("]")

        if indent:
            spaces = " " * indent
            lines = [f"{spaces}{line}" for line in lines]

        return lines

    file_content = []
    file_content.append(f"basepath = \"{toml_data['basepath']}\"\n")
    file_content += print_locales(toml_data["locales"])
    for path in toml_data["paths"]:
        file_content.append("\n[[paths]]")
        file_content.append(f"    reference = \"{path['reference']}\"")
        file_content.append(f"    l10n = \"{path['l10n']}\"")
        if "locales" in path:
            file_content += print_locales(path["locales"], 4)
    file_content.append("")

    return "\n".join(file_content)


def read_toml_content(toml_file):
    # Read project config (TOML) content

    if not os.path.exists(toml_file):
        sys.exit(f"TOML file does not exist ({toml_file})")
    with open(toml_file) as f:
        toml_data = toml.load(f)

    return toml_data


def write_toml_content(toml_file, toml_data):
    # Write project config (TOML) content

    with open(toml_file, "w") as f:
        f.write(print_toml_file(toml_data))


def issue_exists(repo, issue_number):
    # Verify if an issue number is available

    if not issue_number:
        return False

    url = f"https://github.com/{repo}/issues/{issue_number}"
    response = requests.get(url, allow_redirects=False)

    if response.status_code != 200:
        return False

    return True


def create_issue(repo, experiment_id, file_name, recipe_locales, api_token):
    # Create a new issue

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"token {api_token}"}

    issue_body = f"""
**Experiment ID**: `{experiment_id}`
**Localization file**: `{file_name}`
**Locales**: {', '.join(recipe_locales)}
    """
    payload = {
        "title": f"Localization request for experiment {experiment_id}",
        "body": issue_body,
        "assignees": ["flodolo"],
    }

    r = requests.post(url=url, headers=headers, data=json.dumps(payload))
    try:
        issue_number = r.json()["number"]
        print(f"Created a new issue: {issue_number}")
        return issue_number
    except:
        print("Error creating a new issue")
        print(r.status_code)
        return ""


def main():
    # Read command line input parameters
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--toml", dest="toml_path", help="Path to l10n.toml file", required="True"
    )
    parser.add_argument("--id", dest="exp_id", help="Experiment ID", required="True")
    parser.add_argument("--issue", dest="issue", help="Issue number", default=0)
    parser.add_argument("--token", dest="token", help="API Token", required=True)
    parser.add_argument("--repo", dest="repo", help="GitHub repository", required=True)
    args = parser.parse_args()

    # Store paths
    script_path = os.path.dirname(__file__)
    root_path = os.path.abspath(os.path.join(script_path, os.pardir, os.pardir))
    ftl_path = os.path.join(root_path, "en-US", "subset")
    ftl_rel_path = os.path.relpath(ftl_path, root_path)
    storage_path = os.path.join(root_path, ".github", "storage")

    # Get the JSON with the list of experiments already stored in the repository
    experiments_json = os.path.join(storage_path, "experiments.json")
    if not os.path.exists(experiments_json):
        experiments = {}
    else:
        with open(experiments_json) as f:
            experiments = json.load(f)

    # Get the experiment recipe (JSON), generate the FTL file and store it in the repository
    experiment_id = args.exp_id
    recipe = get_experiment_json(experiment_id)
    file_name = f"{experiment_id.replace('-', '_')}_{date.today().year}.ftl"
    with open(os.path.join(ftl_path, file_name), "w") as f:
        f.write(generate_ftl_file(recipe))

    # Get the list of locales from the recipe
    # TODO: https://github.com/mozilla/experimenter/pull/8820
    recipe_locales = ["de", "fr", "it"]

    # Parse and update the existing TOML file:
    # - Make sure that the list of locales include all locales requested in the recipe
    # - Add the new file
    toml_file = args.toml_path
    toml_data = read_toml_content(toml_file)
    toml_data["locales"] = recipe_locales
    file_path = os.path.join(ftl_rel_path, file_name)
    # Add the path, avoid creating duplicates
    path_exists = False
    for path in toml_data["paths"]:
        if path["reference"] == file_path:
            path_exists = True
    if not path_exists:
        toml_data["paths"].append(
            {
                "reference": f"{file_path}",
                "l10n": f"{file_path}",
                "locales": recipe_locales,
            }
        )
    write_toml_content(toml_file, toml_data)

    # Check if an issue already exists, create a new one if needed
    gh_repo = args.repo
    issue_number = args.issue
    if not issue_exists(gh_repo, issue_number):
        # Create a new issue
        issue_number = create_issue(
            gh_repo, experiment_id, file_name, recipe_locales, args.token
        )

    # Write back info on the experiments in JSON file
    experiments[experiment_id] = {
        "file": file_path,
        "issue": issue_number,
        "locales": recipe_locales,
    }
    with open(experiments_json, "w") as f:
        json.dump(experiments, fp=f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
