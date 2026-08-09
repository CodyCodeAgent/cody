"""Create and inspect a project Skill without calling a model."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from cody import AsyncCodyClient


SKILL = """---
name: release-check
description: Check tests, version metadata, changelog, and secrets before release.
---

# Release check

1. Compare package versions.
2. Run repository tests and linters.
3. Confirm the changelog contains the release.
4. Search staged changes for credentials.
5. Report evidence; do not publish automatically.
"""


async def run() -> None:
    with TemporaryDirectory(prefix="cody-skill-demo-") as temporary:
        workdir = Path(temporary)
        skill_dir = workdir / ".cody" / "skills" / "release-check"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL, encoding="utf-8")

        async with AsyncCodyClient(workdir=str(workdir)) as client:
            skills = await client.list_skills()
            detail = await client.get_skill("release-check")
            print("Discovered:", [item["name"] for item in skills])
            print("Source:", detail["source"])
            print(detail["documentation"])


if __name__ == "__main__":
    asyncio.run(run())
