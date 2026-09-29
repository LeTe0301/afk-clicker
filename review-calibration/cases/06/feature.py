# .github/workflows/nightly.yml
#
# Feature: a nightly build that publishes a pre-release so testers always have
# yesterday's code without waiting for a tagged release.
NIGHTLY_YML = r"""
name: Nightly

on:
  schedule:
    - cron: "0 3 * * *"
  workflow_dispatch:
    inputs:
      channel:
        description: "Pre-release channel name (e.g. nightly, beta)"
        required: false
        default: nightly

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: |
          python -m pip install --upgrade pip
          pip install pyinstaller pynput

      - name: Name the build
        id: name
        run: |
          STAMP=$(date -u +%Y%m%d)
          echo "tag=${{ inputs.channel }}-$STAMP" >> "$GITHUB_OUTPUT"

      - run: pyinstaller --noconfirm --clean --name "AFK Farm Clicker" --windowed afk_clicker.py

      - name: Package
        run: tar -czf nightly.tar.gz -C dist "AFK Farm Clicker"

      - uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.name.outputs.tag }}
          prerelease: true
          files: nightly.tar.gz
"""
