# Building the documentation

The documentation site is built with MkDocs from the repository root.

## Install documentation dependencies

```bash
uv sync --group docs
```

## Serve locally

```bash
uv run --group docs mkdocs serve
```

Open the local URL printed by MkDocs. It rebuilds the site when documentation
or configuration files change.

## Build and validate

```bash
uv run --group docs mkdocs build --strict
```

The generated static site is written to `site/`. The `--strict` flag turns
MkDocs warnings, including broken internal links, into errors.

## Publish on GitHub Pages

`.github/workflows/docs.yml` builds and deploys the site on pushes to `main`.
Enable GitHub Pages for the repository with **GitHub Actions** as its source.
