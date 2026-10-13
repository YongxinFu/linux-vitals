#!/bin/sh
# Regenerate every generated asset from a linux-vitals checkout:
#   tools/build.sh /path/to/linux-vitals
# Needs python3 with PyYAML, and ansible-core for the demo dashboard.
set -eu
collection=${1:?usage: tools/build.sh /path/to/linux-vitals}
here=$(dirname "$0")
python3 "$here/build_variables.py" "$collection"
python3 "$here/build_changelog.py" "$collection"
python3 "$here/build_demo.py" "$collection"
