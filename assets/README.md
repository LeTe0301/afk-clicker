# Icon assets

`icon.svg` (full design) and `icon-simplified.svg` (loop + arrow only, no
mouse -- used at 16/32 px where the mouse detail goes muddy) are the editable
sources. Everything else in this folder is a rasterized/packaged output of
one of those two SVGs and is regenerated, not hand-edited, whenever an SVG
changes:

- `icon-16.png`, `icon-32.png` -- from `icon-simplified.svg`
- `icon-48.png`, `icon-256.png` -- from `icon.svg`
- `icon.ico` -- Windows, multi-size (16/32 simplified, 48/256 full)
- `icon.icns` -- macOS bundle icon (16pt/32pt slots simplified, 128pt+ full)

Regenerate with any SVG rasterizer (Inkscape, `rsvg-convert`, a throwaway
Pillow+cairosvg script, an online converter -- not mandated, not part of CI
or this repo's dependencies). See `docs/implementation.md` for the exact
commands used to generate the committed copies.
