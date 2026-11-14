"""MkDocs hooks for the documentation site.

mkdocs-static-i18n builds the Persian site after the English one, into the same output folder, with the
Persian pages under fa/. Two files at the root are written by both builds; these hooks sort them out.
"""

from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_LANGUAGE = 'en'

_english_404: bytes | None = None


def on_post_build(config, **kwargs) -> None:  # type: ignore[no-untyped-def]
    global _english_404
    site = Path(config.site_dir)
    language = config.theme['language']
    not_found = site / '404.html'

    if language == DEFAULT_LANGUAGE:
        # This runs before the i18n plugin starts the Persian build, which writes its own 404.html here.
        if not_found.is_file():
            _english_404 = not_found.read_bytes()
        return

    target = site / language
    if not target.is_dir():
        return
    # The root keeps the English 404 page; the Persian one goes into its own folder.
    if not_found.is_file():
        shutil.copyfile(not_found, target / '404.html')
        if _english_404 is not None:
            not_found.write_bytes(_english_404)
    # The theme's language selector loads sitemap.xml from the root of every language to send the reader to
    # the same page in the other language; the i18n plugin writes a single sitemap, listing both languages.
    sitemap = site / 'sitemap.xml'
    if sitemap.is_file():
        shutil.copyfile(sitemap, target / 'sitemap.xml')
