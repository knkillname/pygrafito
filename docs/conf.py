# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Sphinx configuration for the pygrafito documentation site."""

import importlib.metadata
import pathlib
import re
import typing

release = importlib.metadata.version("pygrafito")
version = release
project = "pygrafito"
author = "Mario Abarca"
copyright = "2026-present Mario Abarca"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.githubpages",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinxcontrib.mermaid",
]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

mermaid_output_format = "svg"
mermaid_cmd = "npx --yes @mermaid-js/mermaid-cli@12.0.0"
mermaid_font = "Inter, 'Source Sans 3', 'Noto Sans', sans-serif"
mermaid_mono = "'JetBrains Mono', 'Source Code Pro', monospace"
mermaid_config = {
    "theme": "neutral",
    "fontFamily": mermaid_font,
    "themeVariables": {
        "background": "#f8f9fb",
    },
    "themeCSS": (f".cluster-label span, code, .mono {{ font-family: {mermaid_mono}; }}"),
}
mermaid_params = ["--puppeteerConfigFile", "docs/puppeteer-config.json"]

autodoc_member_order = "bysource"
autodoc_typehints = "signature"
autodoc_typehints_format = "short"
autodoc_type_aliases = {"FilePath": "pathlib.Path"}
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
}

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_rtype = False

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
nitpicky = True
nitpick_ignore = [
    ("py:class", "FilePath"),
    ("py:class", "QueryValue"),
    ("py:class", "Scalar"),
    ("py:class", "Value"),
    ("py:class", "collections.abc.Mapping[str"),
    ("py:class", "tuple[str"),
    ("py:class", "optional"),
    ("py:class", "pygrafito.engine.query.prepared.PreparedQuery"),
    ("py:class", "pygrafito.engine.query.values.QueryValue"),
    ("py:class", "pygrafito.engine.transaction.Transaction"),
    ("py:class", "pygrafito.model.Scalar"),
    ("py:class", "pygrafito.model.Value"),
]

html_theme = "furo"
html_title = f"{project} {release}"
html_baseurl = "https://knkillname.github.io/pygrafito/"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/knkillname/pygrafito/",
    "source_branch": "main",
    "source_directory": "docs/",
    "top_of_page_button": "edit",
}

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

SIGNATURELESS_CLASSES = frozenset(
    {
        "pygrafito.Direction",
        "pygrafito.ElementKind",
        "pygrafito.Graph",
        "pygrafito.Node",
        "pygrafito.PreparedQuery",
        "pygrafito.Relationship",
        "pygrafito.Transaction",
    }
)


class MermaidFonts:
    """Embed the bundled open fonts into every rendered Mermaid SVG."""

    STYLE: typing.ClassVar[str] = (
        "<style>"
        "@font-face{font-family:'Inter';"
        "src:url('../_static/fonts/Inter-latin.woff2') format('woff2');"
        "font-weight:100 900;font-style:normal;font-display:swap;}"
        "@font-face{font-family:'JetBrains Mono';"
        "src:url('../_static/fonts/JetBrainsMono-latin.woff2') format('woff2');"
        "font-weight:100 900;font-style:normal;font-display:swap;}"
        "</style>"
    )

    @staticmethod
    def embed(app: object, exception: BaseException | None) -> None:
        """Inject the font-face rules into each rendered diagram.

        Parameters
        ----------
        app : object
            Sphinx application with the output directory.
        exception : BaseException | None
            Build exception, if the build failed.
        """
        if exception is not None:
            return
        outdir = pathlib.Path(getattr(app, "outdir", ""))
        for svg in (outdir / "_images").glob("mermaid-*.svg"):
            text = svg.read_text(encoding="utf-8")
            if "@font-face" in text:
                continue
            text = re.sub(r"(<svg[^>]*>)", r"\1" + MermaidFonts.STYLE, text, count=1)
            svg.write_text(text, encoding="utf-8")


class AutodocHooks:
    """Sphinx event handlers that keep the public reference focused."""

    @staticmethod
    def hide_internal_signatures(
        app: object,
        what: str,
        name: str,
        obj: object,
        options: object,
        signature: str | None,
        return_annotation: str | None,
    ) -> tuple[str | None, str | None]:
        """Hide class signatures that repeat parameters or expose internal types."""
        del app, obj, options
        if what == "class" and name in SIGNATURELESS_CLASSES:
            return None, None
        return signature, return_annotation


def setup(app: object) -> None:
    """Register documentation event handlers."""
    app.connect("autodoc-process-signature", AutodocHooks.hide_internal_signatures)
    app.connect("build-finished", MermaidFonts.embed)
