"""Send a local image to a vision-capable model through MultimodalPrompt."""

from __future__ import annotations

import argparse
import asyncio
import base64
import mimetypes
from pathlib import Path

from cody import AsyncCodyClient
from cody.core.prompt import ImageData, MultimodalPrompt


async def run(image_path: Path, workdir: Path, prompt: str) -> None:
    media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    image = ImageData(
        data=base64.b64encode(image_path.read_bytes()).decode("ascii"),
        media_type=media_type,
        filename=image_path.name,
    )
    async with AsyncCodyClient(workdir=str(workdir)) as client:
        result = await client.run(MultimodalPrompt(text=prompt, images=[image]))
        print(result.output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--prompt", default="描述图片内容并指出明显的界面可用性问题")
    args = parser.parse_args()
    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        parser.error(f"image does not exist: {image_path}")
    asyncio.run(run(image_path, args.workdir.resolve(), args.prompt))


if __name__ == "__main__":
    main()
