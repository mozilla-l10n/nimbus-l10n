# Localization for Nimbus experiments

This repository is used to support out-of-train localization for [Nimbus experiments](https://experimenter.info/localization-process).

## Repository structure

This project is [localized through Pontoon](https://pontoon.mozilla.org/projects/nimbus-experiments/), and a project configuration file (`l10n.toml`) is used to define which locales are supported overall, and which locales are supported for specific files. For example:

```TOML
locales = [
    "de",
    "fr",
    "it"
]

[[paths]]
    reference = "en-US/*.ftl"
    l10n = "{locale}/*.ftl"

[[paths]]
    reference = "en-US/subset/import_bookmarks_onboarding_2023.ftl"
    l10n = "{locale}/subset/import_bookmarks_onboarding_2023.ftl"
    locales = [
        "de",
        "fr"
    ]
```

Based on this configuration, files living in the `en-US` folder will be automatically exposed to all locales defined in the top-level `locales` variable (`de`, `fr`, `it`).

Files that require a different set of locales can be stored in `en-US/subset`, with an additional `paths` entry to define the list of supported locales. In the example, `import_bookmarks_onboarding_2023.ftl` is only supported for `de` and `fr`.

## Automation to extract strings from experiment recipe

Starting with Firefox 113, Nimbus supports multi-locale experiment recipes. In the JSON representation of the recipe, a string would look like this:

```JSON
"$l10n": {
    "id": "button-label",
    "text": "OK",
    "comment": "A confirmation button"
}
```

Automation can be [manually triggered](https://github.com/flodolo/nimbus-l10n/actions/workflows/import_experiment.yaml) via GitHub actions, providing an experiment ID and an optional issue number. This will:
* Retrieve the experiment JSON via API (using the experiment ID).
* Extract the strings, create a FTL file for the experiment, and update `l10n.toml` accordingly (add new `path` for the file with the supported locales, amend the top-level list of locales if needed).
* Open a new issue if an issue number wasn't provided. Note that this is actively discouraged, as requesters should [file an issue](https://github.com/flodolo/nimbus-l10n/issues/new/choose) with additional information on the experiment.
* Open a pull request with a cross-reference to the issue.

## License

Translations in this repository are available under the terms of the [Mozilla Public License v2.0](http://www.mozilla.org/MPL/2.0/).
