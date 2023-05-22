#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import os
import requests
import sys
from pathlib import Path


def add_comment(repo, issue_number, filename, translations, api_token):
    # Comment in the issue linked to the experiment, adding the translations

    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {"Authorization": f"token {api_token}"}

    comment_body = f"""
Translation has been completed for `{filename}`.

Here’s the data to copy in the Localization field in Experimenter:

```
{json.dumps(translations, indent=2, sort_keys=True, ensure_ascii=False)}
```

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
    parser.add_argument("--token", dest="token", help="API Token", required=True)
    parser.add_argument("--repo", dest="repo", help="GitHub repository", required=True)
    args = parser.parse_args()

    # Store paths
    script_path = os.path.dirname(__file__)
    root_path = os.path.abspath(os.path.join(script_path, os.pardir, os.pardir))
    storage_path = os.path.join(root_path, ".github", "storage")

    # Get experiments.json, which contains information about experiments that
    # were processed through this pipeline.
    experiments_json = os.path.join(storage_path, "experiments.json")
    if not os.path.exists(experiments_json):
        print("experiments.json not found")
        # We don't emit an error here, since it's still possible to create
        # experiments manually, and those are not tracked in experiments.json
        sys.exit()
    else:
        with open(experiments_json) as f:
            experiments = json.load(f)

    for exp_details in experiments.values():
        ftl_filename = Path(exp_details["file"]).stem
        json_filename = os.path.join(storage_path, f"{ftl_filename}.json")
        if os.path.exists(json_filename):
            with open(json_filename) as f:
                translation_data = json.load(f)

            # If the individual file is marked as complete, but the experiment
            # is not marked as complete yet in experiments.json, add a comment
            # to the issue.
            if translation_data["complete"] and not exp_details["complete"]:
                add_comment(
                    args.repo,
                    exp_details["issue"],
                    f"{ftl_filename}.ftl",
                    translation_data["translations"],
                    args.token,
                )
                exp_details["complete"] = True

    with open(experiments_json, "w") as f:
        json.dump(experiments, fp=f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
