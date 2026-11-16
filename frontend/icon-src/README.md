# App icon sources

`icon.svg` (rounded, for the normal icons) and `icon-maskable.svg` (full-bleed, the mark inside
the central safe zone) are the originals. The PNGs in `../public/icons/` were rendered from them
in Chrome (drawn onto a canvas at the target size):

| File | Source | Size |
| --- | --- | --- |
| `icon-192.png` | `icon.svg` | 192 × 192 |
| `icon-512.png` | `icon.svg` | 512 × 512 |
| `icon-maskable-512.png` | `icon-maskable.svg` | 512 × 512 |
| `apple-touch-icon.png` | `icon-maskable.svg` | 180 × 180 |

After changing an SVG, render the PNGs again with any SVG rasteriser, for example
`rsvg-convert -w 512 -h 512 icon.svg -o ../public/icons/icon-512.png`.
