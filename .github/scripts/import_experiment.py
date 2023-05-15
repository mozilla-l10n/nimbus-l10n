#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import urllib.request
import json
import sys
from jsonpath_ng.ext import parse

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

def generate_file(recipe):
    # Generate a FTL file from the recipe

    file_content = [
        "# This Source Code Form is subject to the terms of the Mozilla Public",
        "# License, v. 2.0. If a copy of the MPL was not distributed with this",
        "# file, You can obtain one at http://mozilla.org/MPL/2.0/.\n",
    ]
    parsed_ids = {}

    for branch in recipe["branches"]:
        file_content.append(f"\n## Branch: {branch['slug']}\n")
        for feature in branch["features"]:
            # Find all $l10n keys in the branch value
            branch_value = feature["value"]["content"]
            jsonpath_expression = parse("$..\"$l10n\"")
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

def main():
    # Read command line input parameters
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--id", dest="exp_id", help="Experiment ID", required="True"
    )
    parser.add_argument(
        "--issue", dest="issue", help="Issue number", default=0
    )
    args = parser.parse_args()

    # Get the experiment recipe (JSON)
    recipe = get_experiment_json(args.exp_id)
    file_content = generate_file(recipe)

if __name__ == "__main__":
    main()
