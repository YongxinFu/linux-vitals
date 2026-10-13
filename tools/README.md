# Site tooling

Every file under `assets/` except `site.css`, `site.js` and `command-builder.*`
is generated from a checkout of the collection's `main` branch:

```sh
pip install pyyaml 'ansible-core>=2.16'
tools/build.sh /path/to/linux-vitals
```

| Script | Writes | From |
| --- | --- | --- |
| `build_variables.py` | `assets/variables.js` | every role's `meta/argument_specs.yml` |
| `build_changelog.py` | `assets/changelog.js` | `CHANGELOG.md` |
| `build_demo.py` | `assets/demo-dashboard.html`, `assets/fleet.js` | `tests/golden/*.json`, rendered by the real `vitals_report` role (baseline, then postcheck) |

Re-run it after a release so the builder, the demo dashboard, the triage
playground and the release timeline match what shipped. Live data (latest
release, CI, stars, commits, milestones) comes from the GitHub API at view time
and falls back to the generated copies when the API is unreachable.
