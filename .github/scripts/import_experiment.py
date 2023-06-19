#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import date
from jsonpath_ng.ext import parse
import argparse
import json
import os
import re
import requests
import sys
import toml
import urllib.request


def get_experiment_json(exp_id):
    # Get recipe of draft experiment in JSON format from the Nimbus API

    host = "https://experimenter.services.mozilla.com"
    url = f"{host}/api/v6/draft-experiments/{exp_id}/"
    try:
        data = urllib.request.urlopen(url)
    except urllib.error.HTTPError as e:
        print(f"Experiment with ID {exp_id} not found.")
        sys.exit(e)

    return json.load(data)


def generate_ftl_file(recipe, experiment_id):
    # Generate a FTL file from the strings in the recipe

    file_content = [
        "# This Source Code Form is subject to the terms of the Mozilla Public",
        "# License, v. 2.0. If a copy of the MPL was not distributed with this",
        "# file, You can obtain one at http://mozilla.org/MPL/2.0/.\n",
    ]
    parsed_ids = {}
    warnings = []
    for branch in recipe["branches"]:
        branch_strings = []
        for feature in branch["features"]:
            # Find all $l10n keys in the branch value
            if "content" not in feature["value"]:
                continue
            branch_value = feature["value"]["content"]
            jsonpath_expression = parse('$.."$l10n"')
            for match in jsonpath_expression.find(branch_value):
                # Check if $l10n is an object
                if type(match.value) != dict:
                    warnings.append(
                        "\n---\n\n"
                        f"$l10n definition is not an object (found `{type(match.value).__name__}` instead).\n"
                        f"\n```\n{match.value}\n```\n"
                    )
                    continue

                # Get the id attribute, store a warning if not available
                if "id" not in match.value:
                    warnings.append(
                        "\n---\n\n"
                        f"$l10n object defined without an `id` attribute.\n"
                        f"\n```\n{json.dumps(match.value, indent=2)}\n```\n"
                    )
                    continue
                id = match.value["id"]

                # Get the text attribute, store a warning if not available
                if "text" not in match.value:
                    warnings.append(
                        "\n---\n\n"
                        f"$l10n object defined without a `text` attribute.\n"
                        f"\n```\n{json.dumps(match.value, indent=2)}\n```\n"
                    )
                    continue
                text = match.value["text"]

                # Get the comment attribute, use an empty string if not available
                comment = match.value.get("comment", "")

                if id in parsed_ids:
                    # We already parsed a string with this ID. Verify that the
                    # text is the same. If not, store a warning.
                    if parsed_ids[id] != text:
                        warnings.append(
                            "\n---\n\n"
                            f"The string with ID `{id}` is defined with different values throughout the recipe.\n"
                            f"Initial value: `{parsed_ids[id]}`\n"
                            f"Different value (ignored): `{text}`\n"
                        )

                else:
                    if comment:
                        branch_strings.append(f"# {comment}")
                    branch_strings.append(f"{id} = {text}")
                    parsed_ids[id] = text
        if branch_strings:
            branch_strings.append("")
            file_content.append(f"## Branch: {branch['slug']}\n")
            file_content.extend(branch_strings)
            (f"## Branch: {branch['slug']}\n")

    # If there are no strings defined, exit with an error
    if not parsed_ids:
        sys.exit(
            f"There are no strings defined in the experiment recipe ({experiment_id})"
        )

    return "\n".join(file_content), warnings


def print_toml_file(toml_data):
    # Format the TOML file to minimize differences with the manual format
    # typically used

    def print_locales(locales, indent=0):
        # Order and format the list of locales
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
    # Read project configuration file (TOML) content

    if not os.path.exists(toml_file):
        sys.exit(f"TOML file does not exist ({toml_file})")
    with open(toml_file) as f:
        toml_data = toml.load(f)

    return toml_data


def issue_exists(repo, issue_number):
    # Verify if the provided issue number is available in the repository

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


def add_comment_warnings(repo, issue_number, warnings, api_token):
    # Comment in the issue linked to the experiment with the warnings

    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {"Authorization": f"token {api_token}"}

    warnings_body = "\n".join(warnings)
    comment_body = f"""
Automation has detected issues in the experiment recipe.

{warnings_body}
    """
    payload = {
        "body": comment_body,
    }

    r = requests.post(url=url, headers=headers, data=json.dumps(payload))
    if r.status_code != 201:
        print(f"Error adding comment to issue {issue_number} in {repo}")


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
    ref_folder_path = os.path.join(root_path, "en-US", "subset")

    # Get experiments.json, which contains information about experiments that
    # were processed through this pipeline.
    experiments_json = os.path.join(root_path, ".github", "storage", "experiments.json")
    if not os.path.exists(experiments_json):
        experiments = {}
    else:
        with open(experiments_json) as f:
            experiments = json.load(f)

    # Get the experiment recipe (JSON), generate the FTL file and store it in
    # the repository
    experiment_id = args.exp_id
    recipe = get_experiment_json(experiment_id)
    ftl_filename = f"{experiment_id.replace('-', '_')}_{date.today().year}.ftl"
    ref_ftl_fullname = os.path.join(ref_folder_path, ftl_filename)
    ref_ftl_relname = os.path.relpath(ref_ftl_fullname, root_path)
    # Exit with an error if the file already exists
    if os.path.exists(ref_ftl_fullname):
        sys.exit(
            f"Error: there is already a file called `{ref_ftl_relname}`. Import stopped."
        )
    ref_ftl_content, warnings = generate_ftl_file(recipe, experiment_id)
    with open(ref_ftl_fullname, "w") as f:
        f.write(ref_ftl_content)

    # Extract the list of locales from the recipe, remove en-US
    recipe_locales = recipe["locales"]
    recipe_locales.remove("en-US")
    recipe_locales.sort()

    # en-CA and en-GB are special cases, as we use the same content as en-US.
    # If they're part of the request, store the same file also for these locales.
    for loc in ["en-CA", "en-GB"]:
        if loc not in recipe_locales:
            continue
        loc_folder = os.path.join(root_path, loc, "subset")
        os.makedirs(loc_folder, exist_ok=True)
        with open(os.path.join(loc_folder, ftl_filename), "w") as f:
            f.write(ref_ftl_content)

    # Parse and update the existing TOML file:
    # - Make sure that the top-level list of locales includes all locales
    #   requested in the recipe
    # - Add the new file to [[paths]]
    toml_file = args.toml_path
    toml_data = read_toml_content(toml_file)
    toml_locales = list(set(toml_data["locales"] + recipe_locales))
    toml_locales.sort()
    toml_data["locales"] = toml_locales
    l10n_file_path = os.path.join("{locale}", "subset", ftl_filename)

    # Add the path, making sure not to create duplicates
    path_exists = False
    for path in toml_data["paths"]:
        if path["reference"] == ref_ftl_relname:
            path_exists = True
    if not path_exists:
        toml_data["paths"].append(
            {
                "reference": f"{ref_ftl_relname}",
                "l10n": f"{l10n_file_path}",
                "locales": recipe_locales,
            }
        )

    # Write back the project configuration file
    with open(toml_file, "w") as f:
        f.write(print_toml_file(toml_data))

    # Check if an issue already exists, otherwise create a new one
    gh_repo = args.repo
    api_token = args.token
    issue_number = args.issue
    if not issue_exists(gh_repo, issue_number):
        issue_number = create_issue(
            gh_repo, experiment_id, ftl_filename, recipe_locales, api_token
        )
    # If there are warnings, print them and add an additional comment
    if warnings:
        print("".join(warnings))
        add_comment_warnings(gh_repo, issue_number, warnings, api_token)

    # Write back info on the experiment in experiments.json
    experiments[experiment_id] = {
        "complete": False,
        "file": ref_ftl_relname,
        "issue": issue_number,
        "locales": recipe_locales,
    }
    with open(experiments_json, "w") as f:
        json.dump(experiments, fp=f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
