# Visual asset provenance and licensing

Unless noted below, SVG and PNG files in this directory are original fan-art-like geometric illustrations created specifically for `astrbot_plugin_Helldivers` in July 2026.

## Provenance

- The artwork was constructed from original vector primitives: polygons, ellipses, lines, rings, stars, shields, and abstract mechanical or biological silhouettes.
- Unless noted below, no Helldivers 2 game screenshot, Galactic War Web (GWW) screenshot, Discord/Steam image, extracted game texture, official logo file, or traced third-party artwork was used.
- The designs use broad fictional concepts and color associations to make Super Earth, the Democracy Space Station (DSS), Automatons, Terminids, Illuminate, defense operations, major orders, and DSS tactical actions recognizable in plugin interfaces.
- Every original runtime PNG was rendered locally from the corresponding SVG design and retains an alpha channel. Pillow is the only runtime image dependency; the SVG files are editable source masters.
- `global_events/super_earth_flag.*` is an original stylized flag illustration and is not a copy of an in-game or promotional image.
- `tactical/eagle_storm.*`, `tactical/orbital_blockade.*`, and `tactical/heavy_ordnance.*` are user-provided DSS tactical icons. Their SVG source credits Dogo314; the bundled PNGs are direct local rasterizations of those sources.
- `user/dss.png` is the user-provided DSS reference image used by the DSS report renderer.
- `user/super_earth_flag.png` is the user-provided Super Earth flag reference used for major-order and global-event artwork.
- `user/*_template.png` files are user-provided visual references used as darkened cockpit backplates beneath dynamic report data.
- `user/steam_hero.png` is the official Helldivers 2 "Devoid of Liberty" key art (store banner, downscaled crop, obtained via helldivers.wiki.gg). © Arrowhead Game Studios; bundled as the /steam card hero for the current warbond. Replace this file (and its manifest sha256) when the warbond rotates.

## License

The project author makes the original assets available under the same MIT License as the repository root `LICENSE` file. User-provided tactical icons retain the attribution and license recorded in `manifest.json`.

> Copyright (c) 2026 fiatlux2333
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, subject to the conditions in the repository's MIT License.

Helldivers and related names and fictional concepts are trademarks or intellectual property of their respective owners. This is unofficial fan work and is not endorsed by Arrowhead Game Studios or Sony Interactive Entertainment.

## Asset inventory

- `emblems/super_earth.svg` and `.png`
- `emblems/dss.svg` and `.png`
- `emblems/automaton.svg` and `.png`
- `emblems/terminids.svg` and `.png`
- `emblems/illuminate.svg` and `.png`
- `emblems/defense.svg` and `.png`
- `emblems/major_order.svg` and `.png`
- `dss/dss_wireframe.svg` and `.png`
- `tactical/eagle_storm.svg` and `.png`
- `tactical/orbital_blockade.svg` and `.png`
- `tactical/heavy_ordnance.svg` and `.png`
- `tactical/orbital_napalm.svg` and `.png`
- `global_events/super_earth_flag.svg` and `.png`
