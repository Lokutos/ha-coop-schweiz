# Contributing

Thanks for helping. This is a small spare-time project; issues and pull
requests are welcome.

## Before you start

- Open an issue first for larger changes, so we can agree on the approach.
- Never post tokens, the sign-in address containing `code=`, user ids,
  list ids or the contents of a real shopping list in issues, logs, tests
  or commits.
- Do not use the bot-protected website addresses of coop.ch and do not work
  around any bot protection. The integration only uses the interfaces of the
  Coop app (see [docs/protocol.md](docs/protocol.md)).
- Write tests and examples with neutral products, not with items of a real
  list.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

`tests/test_api.py` and `tests/test_util.py` run without Home Assistant and
without network access. `tests/test_ha.py` needs
`pytest-homeassistant-custom-component` (installed by `requirements_test.txt`)
and runs on Linux, macOS or WSL. All tests must pass before a pull request is
merged; the GitHub checks (hassfest, HACS validation, tests) run
automatically.

## Conventions

- The version lives in `manifest.json` and in `const.py` (`VERSION`); a test
  checks that both match. Releases are tagged `vX.Y.Z` with the same number.
- Changes to the dashboard card need a new version number, otherwise browsers
  keep the old file.
- If the data stored in the config entry changes, raise the config flow
  version and add a migration in `async_migrate_entry`.
- Write operations on the list follow what the Coop app does (fields,
  `activity` timestamps, `status`). Deviations need evidence from the app's
  behaviour.
- Log messages, errors and diagnostics never contain response bodies,
  tokens, ids or product names.

## Maintainers

The repository is maintained by the people listed in
[.github/CODEOWNERS](.github/CODEOWNERS). If you would like to help maintain
it, open an issue. The project may move to a GitHub organisation later;
GitHub redirects the old address, so existing HACS installations keep
working.
