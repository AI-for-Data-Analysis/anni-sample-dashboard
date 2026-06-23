#!/usr/bin/env python3
"""Create the workshop Codex LiteLLM configuration."""

from __future__ import annotations

import getpass
import shutil
import stat
import sys
from pathlib import Path


CONFIG_TEMPLATE = """#:schema https://developers.openai.com/codex/config-schema.json

# Workshop LiteLLM configuration for Codex.
model = "gpt-5.3-codex"
model_provider = "litellm"

[analytics]
enabled = false

[shell_environment_policy]
exclude = ["VAULT_*", "OP*"]

[model_providers.litellm]
name = "litellm"
base_url = "https://litellm.oit.duke.edu/v1"
wire_api = "responses"
experimental_bearer_token = "{api_key}"
"""

def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def check_command(command: str) -> None:
    if shutil.which(command) is None:
        fail(
            f"`{command}` was not found. Install Codex first with "
            "`npm install -g @openai/codex`, then rerun this script."
        )


def write_private_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main() -> None:
    print("Workshop Codex LiteLLM setup")
    print()

    check_command("codex")
    check_command("codex-acp")

    api_key = getpass.getpass("Paste your workshop LiteLLM API key: ").strip()
    if not api_key:
        fail("No API key was entered.")

    home = Path.home()
    codex_home = home / ".codex-litellm"
    config_path = codex_home / "config.toml"

    write_private_file(config_path, CONFIG_TEMPLATE.format(api_key=api_key))

    print()
    print(f"Wrote Codex config: {config_path}")
    print()
    print("To test the API key, run:")
    print(
        'CODEX_HOME="$HOME/.codex-litellm" codex exec '
        '"Reply with only: Codex LiteLLM is working" --skip-git-repo-check'
    )

if __name__ == "__main__":
    main()
