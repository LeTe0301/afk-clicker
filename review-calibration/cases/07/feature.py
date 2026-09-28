# .github/workflows/hotfix.yml
#
# Feature: a hotfix pipeline that can ship a patch without the full release
# ceremony, for the case where a released build is broken in the field.
HOTFIX_YML = r"""
name: Hotfix

on:
  push:
    branches: ["hotfix/**"]

permissions:
  contents: read

jobs:
  version:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.pick.outputs.version }}
    steps:
      - id: pick
        env:
          REF: ${{ github.ref_name }}
        run: |
          V="${REF##*/}"
          python3 - "$V" <<'CHECK'
          import re, sys
          if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", sys.argv[1]):
              print(f"::error::{sys.argv[1]!r} is not a version"); sys.exit(1)
          CHECK
          echo "version=$V" >> "$GITHUB_OUTPUT"

  test:
    needs: version
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install "pynput==1.7.7"
      - run: sudo apt-get update -qq && sudo apt-get install -y -qq xvfb
      - run: xvfb-run -a python -m unittest discover -s tests -t . -v

  publish:
    needs: [version, test]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
        with: {path: artifacts, merge-multiple: true}
      - uses: softprops/action-gh-release@v2.0.8
        with:
          tag_name: v${{ needs.version.outputs.version }}
          files: artifacts/*
"""
