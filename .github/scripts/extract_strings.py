#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
import argparse
import json
import os
import sys

try:
    from compare_locales import paths
    from compare_locales import parser
except ImportError as e:
    print("FATAL: make sure that dependencies are installed")
    print(e)
    sys.exit(1)


class StringExtraction:
    def __init__(self, l10n_path, reference_locale, experiments_metadata):
        """Initialize object."""

        self.translations = defaultdict(dict)

        self.l10n_path = l10n_path
        self.reference_locale = reference_locale
        self.experiments_metadata = experiments_metadata

    def extractStrings(self):
        """Extract strings from TOML file."""

        def extractLocale(locale):
            """Extract strings for single locale"""

            print(f"Extracting strings for locale: {locale}.")
            if locale != self.reference_locale:
                files = paths.ProjectFiles(locale, [project_config])
            else:
                files = paths.ProjectFiles(None, [project_config])

            for l10n_file, reference_file, _, _ in files:
                if not os.path.exists(l10n_file):
                    # File not available in localization
                    continue

                if not os.path.exists(reference_file):
                    # File not available in reference
                    continue

                key_path = os.path.relpath(reference_file, basedir)
                experiment_id = os.path.basename(os.path.splitext(key_path)[0])
                try:
                    p = parser.getParser(reference_file)
                except UserWarning:
                    continue

                p.readFile(l10n_file)
                self.translations[locale].update(
                    (
                        f"{experiment_id}:{entity.key}",
                        entity.raw_val if entity.raw_val is not None else "",
                    )
                    for entity in p.parse()
                )

            # Remove obsolete strings not available in the reference locale
            if locale != self.reference_locale:
                self.translations[locale] = {
                    k: v
                    for (k, v) in self.translations[locale].items()
                    if k in self.translations[self.reference_locale]
                }
            print(f"  {len(self.translations[locale])} strings extracted")

        basedir = os.path.dirname(self.l10n_path)
        project_config = paths.TOMLParser().parse(self.l10n_path, env={"l10n_base": ""})
        basedir = os.path.join(basedir, project_config.root)

        if not project_config.all_locales:
            print("No locales defined in the project configuration.")

        # Extract reference locale first
        extractLocale(self.reference_locale)

        for locale in project_config.all_locales:
            extractLocale(locale)

    def getTranslations(self):
        """Return translations and stats"""

        json_output = {}
        for locale, messages in self.translations.items():
            for full_id, translation in messages.items():
                experiment_id, message_id = full_id.split(":")
                if experiment_id not in json_output:
                    json_output[experiment_id] = {
                        "complete": False,
                        "complete_locales": [],
                        "translations": defaultdict(dict),
                    }
                json_output[experiment_id]["translations"][locale][message_id] = (
                    translation
                )

        # Identify complete locales for each experiment, and remove
        # translations for partially translated locales.
        print("\nAnalyzing project completion...")
        for experiment_id, exp_data in json_output.items():
            locales = list(exp_data["translations"].keys())
            locales.sort()
            reference_ids = list(exp_data["translations"][self.reference_locale].keys())

            incomplete_locales = []
            for loc in locales:
                l10n_ids = list(exp_data["translations"][loc].keys())
                if len(set(reference_ids) - set(l10n_ids)) == 0:
                    exp_data["complete_locales"].append(loc)
                else:
                    incomplete_locales.append(loc)
            exp_data["complete_locales"].sort()

            # Remove partially translated locales
            for loc in incomplete_locales:
                del exp_data["translations"][loc]

            if incomplete_locales:
                print(
                    f"\nExperiment {experiment_id} incomplete. "
                    f"Missing locales: {','.join(incomplete_locales)}"
                )
            else:
                # Check if there are locales that don't have yet an FTL file
                # by looking at all requested locales in experiments.json

                # Find the Nimbus experiment ID from metadata
                nimbus_id = ""
                for id, data in self.experiments_metadata.items():
                    if experiment_id in data["file"]:
                        nimbus_id = id
                        break

                all_locales = self.experiments_metadata.get(nimbus_id, {}).get(
                    "locales", []
                )
                all_locales.append(self.reference_locale)
                all_locales.sort()
                if nimbus_id == "":
                    # Old type experiment, not defined in experiments.json
                    print(
                        f"Warning: '{experiment_id}' not available in experiments.json."
                    )
                    exp_data["complete"] = True
                else:
                    if exp_data["complete_locales"] == all_locales:
                        exp_data["complete"] = True

        return json_output


def main():
    # Read command line input parameters
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--toml", dest="toml_path", help="Path to l10n.toml file", required="True"
    )
    parser.add_argument(
        "--ref", dest="reference_code", help="Reference language code", default="en-US"
    )
    parser.add_argument(
        "--dest", dest="dest_path", help="Path used to output files", required="True"
    )
    args = parser.parse_args()

    # Read experiments metadata from experiments.json. We assume its path
    # as fixed, relatively to the script (../storage/experiments.json)
    experiments_json = os.path.join(
        os.path.dirname(__file__), os.pardir, "storage", "experiments.json"
    )
    if not os.path.exists(experiments_json):
        print("experiments.json not found")
        # We don't emit an error here, since it's still possible to create
        # experiments manually, and those are not tracked in experiments.json
        experiments_metadata = {}
    else:
        with open(experiments_json) as f:
            experiments_metadata = json.load(f)

    # Extract translations from FTL files, update statistics for each experiment
    extracted_strings = StringExtraction(
        l10n_path=args.toml_path,
        reference_locale=args.reference_code,
        experiments_metadata=experiments_metadata,
    )
    extracted_strings.extractStrings()
    translations = extracted_strings.getTranslations()

    # Store the JSON file for each experiment
    for exp_id, exp_data in translations.items():
        filename = os.path.join(args.dest_path, f"{exp_id}.json")
        with open(filename, "w", encoding="utf8") as f:
            json.dump(exp_data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
