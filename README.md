# py-scripts

Some tools I use. Scripts located under [packages](packages/).

## Development

Install every workspace member into `.venv` (a bare `uv sync` only installs the virtual root, which has no dependencies):

```bash
uv sync --all-packages
uv run steam-ungarbage
```

Build or publish all tools at once:

```bash
uv build --all-packages
uv publish dist/*
```

Installing an unreleased tool straight from this repo:

```bash
uv tool install "git+https://github.com/hexadecimal233/py-scripts#subdirectory=packages/steam-ungarbage"
```

## Adding a tool

1. Create `packages/<tool>/pyproject.toml` with its own `[project]`, `[project.scripts]` and `[build-system]`, plus `packages/<tool>/<module>/`.
2. `uv sync --all-packages` to install it into the shared `.venv`.
3. Document it in the table above.

Each package keeps its own version and PyPI name. Cross-tool code goes into its own `packages/<lib>/` member and is referenced with `[tool.uv.sources] <lib> = { workspace = true }`.
