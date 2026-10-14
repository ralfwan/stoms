#!/usr/bin/env bash
# Cut a fresh `public` branch from `main`'s current tip for the GitHub/PyPI
# release. Recreates `public` as an orphan branch (no shared history with
# `main`) containing a single commit: the current tree, minus internal-only
# content, with GitHub/PyPI-facing docs and metadata patched in.
#
# This script does NOT push anything. Review the result yourself
# (`git log -1`, `git show --stat`, `git diff main public`) before running
# `git push github public:main` by hand.
#
# Run from the repo root, on a clean `main`:
#   ./scripts/release/cut_public.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

GITHUB_USER="ralfwan"
GITHUB_REPO_URL="https://github.com/${GITHUB_USER}/stoms"
GITHUB_PAGES_URL="https://${GITHUB_USER}.github.io/stoms/"

# Internal-only content stripped from the public tree. Keep in sync with
# .claude/plans/we-were-discussing-making-swift-hummingbird.md's strip-list
# if that plan is revised.
STRIP_PATHS=(
  .scratch
  docs/quarantine
  docs/agents
  PUBLIC_API_CONTRADICTIONS.md
  stoms_immutable_aggregations_work_package.md
  AGENTS.md
  PUBLIC_API.md
  METHOD_IDENTIFIER_DESIGN.md
  reports
  benchmarks
  examples/my_first_attempts.py
  .gitlab-ci.yml
)

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is not clean. Commit or stash changes on main first." >&2
  exit 1
fi

CURRENT_BRANCH="$(git symbolic-ref --short HEAD)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "error: run this from 'main' (currently on '$CURRENT_BRANCH')." >&2
  exit 1
fi

# The orphan commit adds every file, so the pre-commit ruff-format hook checks
# the whole tree, not just recent changes. Fail early instead of mid-cut.
if ! uv run ruff format --check . >/dev/null; then
  echo "error: some files are not ruff-formatted (see 'uv run ruff format --check .')." >&2
  echo "       Run 'uv run ruff format .' on main, commit, push, and re-run." >&2
  exit 1
fi

MAIN_SHA="$(git rev-parse --short HEAD)"

echo "This will:"
echo "  - delete any existing local 'public' branch (main is untouched)"
echo "  - create a fresh orphan 'public' branch from main@${MAIN_SHA}"
echo "  - remove internal-only content from its working tree:"
for p in "${STRIP_PATHS[@]}"; do
  echo "      - $p"
done
echo "  - patch README/docs install snippets and pyproject.toml [project.urls]"
echo "    for GitHub/PyPI"
echo "  - create ONE commit on 'public' (nothing pushed)"
read -r -p "Proceed? [y/N] " REPLY
if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 1
fi

echo "==> Recreating local 'public' branch as an orphan from main@${MAIN_SHA}"
git branch -D public >/dev/null 2>&1 || true
git checkout --orphan public
git rm -rf --cached . >/dev/null

echo "==> Stripping internal-only content"
for p in "${STRIP_PATHS[@]}"; do
  rm -rf -- "$p"
done

echo "==> Patching GitHub/PyPI-facing docs and metadata"
GITHUB_REPO_URL="$GITHUB_REPO_URL" GITHUB_PAGES_URL="$GITHUB_PAGES_URL" \
  uv run python - <<'PYEOF'
import os
import pathlib

github_repo_url = os.environ["GITHUB_REPO_URL"]
github_pages_url = os.environ["GITHUB_PAGES_URL"]


def replace_exact(path, old, new):
    p = pathlib.Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(
            f"error: expected text not found in {path} - it has drifted "
            "since this script was written. Update the script's patch for "
            "this file, then re-run."
        )
    if text.count(old) > 1:
        raise SystemExit(
            f"error: expected text matched more than once in {path} - "
            "make the anchor more specific."
        )
    p.write_text(text.replace(old, new, 1))


# --- README.md: docs badge -> GitHub Pages; add pip/uv install section ---
replace_exact(
    "README.md",
    "https://e165-03-1_theoretische_materialchemie.git-pages.tuwien.ac.at"
    "/madsen-s-research-group/stoms/",
    github_pages_url,
)
replace_exact(
    "README.md",
    '## Install\n'
    '\n'
    '```bash\n'
    'uv sync --dev\n'
    'uv run pytest\n'
    '```\n'
    '\n'
    'Install the optional VASP parser with:\n'
    '\n'
    '```bash\n'
    'uv sync --extra vasp --dev\n'
    '```\n',
    '## Install\n'
    '\n'
    'Add STOMS as a dependency:\n'
    '\n'
    '```bash\n'
    'uv add stoms\n'
    '# or\n'
    'pip install stoms\n'
    '```\n'
    '\n'
    'Optional extras: `stoms[postgres]` and `stoms[vasp]`.\n'
    '\n'
    '### Development setup\n'
    '\n'
    'To work on STOMS itself:\n'
    '\n'
    '```bash\n'
    'uv sync --dev\n'
    'uv run pytest\n'
    '```\n'
    '\n'
    'Install the optional VASP parser with:\n'
    '\n'
    '```bash\n'
    'uv sync --extra vasp --dev\n'
    '```\n',
)

# --- docs/index.md: git+ssh install -> PyPI install ---
replace_exact(
    "docs/index.md",
    '```bash\n'
    'uv add "stoms @ git+ssh://git@gitlab.tuwien.ac.at/'
    'e165-03-1_theoretische_materialchemie/madsen-s-research-group/'
    'stoms.git"\n'
    '```\n'
    '\n'
    "This records STOMS in the project's `pyproject.toml`, updates its "
    "lockfile, and\n"
    'creates or updates its virtual environment. Your GitLab SSH key must '
    'have\n'
    'access to the repository.\n'
    '\n'
    'Add the optional VASP parser with:\n'
    '\n'
    '```bash\n'
    'uv add "stoms[vasp] @ git+ssh://git@gitlab.tuwien.ac.at/'
    'e165-03-1_theoretische_materialchemie/madsen-s-research-group/'
    'stoms.git"\n'
    '```\n',
    '```bash\n'
    'uv add stoms\n'
    '```\n'
    '\n'
    "This records STOMS in the project's `pyproject.toml`, updates its "
    "lockfile, and\n"
    'creates or updates its virtual environment.\n'
    '\n'
    'Add the optional VASP parser with:\n'
    '\n'
    '```bash\n'
    'uv add "stoms[vasp]"\n'
    '```\n',
)

# --- docs/researcher-guide.md: git+ssh install -> PyPI install ---
replace_exact(
    "docs/researcher-guide.md",
    '## One-time setup\n'
    '\n'
    'Currently, `stoms` is only available through GitLab. Using `uv` you '
    'can install it via\n'
    '\n'
    '```bash\n'
    'uv add "stoms @ git+ssh://git@gitlab.tuwien.ac.at/'
    'e165-03-1_theoretische_materialchemie/madsen-s-research-group/'
    'stoms.git"\n'
    '```\n',
    '## One-time setup\n'
    '\n'
    'Install `stoms` with `uv`:\n'
    '\n'
    '```bash\n'
    'uv add stoms\n'
    '```\n',
)

# --- docs/postgres.md: git+ssh install -> PyPI install ---
replace_exact(
    "docs/postgres.md",
    '```bash\n'
    'uv add "stoms[postgres] @ git+ssh://git@gitlab.tuwien.ac.at/'
    'e165-03-1_theoretische_materialchemie/madsen-s-research-group/'
    'stoms.git"\n'
    '```\n',
    '```bash\n'
    'uv add "stoms[postgres]"\n'
    '```\n',
)

# --- pyproject.toml: add [project.urls] before [project.scripts] ---
replace_exact(
    "pyproject.toml",
    "[project.scripts]\n",
    f'[project.urls]\n'
    f'Homepage = "{github_repo_url}"\n'
    f'Repository = "{github_repo_url}"\n'
    f'Documentation = "{github_pages_url}"\n'
    f'\n'
    f'[project.scripts]\n',
)

print("Patched README.md, docs/index.md, docs/researcher-guide.md, "
      "docs/postgres.md, pyproject.toml")
PYEOF

echo "==> Committing"
git add -A
VERSION="$(grep -m1 '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')"
git commit -q -m "Public release snapshot v${VERSION} (from main@${MAIN_SHA})"

echo
echo "Done. 'public' now has one commit, no shared history with 'main'."
echo "You are still on 'public' - review before pushing:"
echo "  git log -1"
echo "  git show --stat"
echo "  git diff main public          # full diff against main's tree"
echo "  git diff --stat main public   # summary only"
echo
echo "Before pushing: confirm GitLab CI is green for main@${MAIN_SHA} (the"
echo "only test gate - there is no GitHub Actions CI)."
echo
echo "When ready (first push):"
echo "  git push github public:main"
echo "Subsequent releases force-push:"
echo "  git push --force github public:main"
echo
echo "Return to the working branch with: git checkout main"
