"""Direct tool usage example for Cody SDK.

Shows how to call tools directly without going through the AI agent.
"""

import asyncio

from cody.sdk import AsyncCodyClient, CodyClient


async def async_tools_example():
    """Call tools directly using the async client."""
    async with AsyncCodyClient(workdir=".") as client:
        # Read a file
        content = await client.read_file("README.md")
        print(f"README.md ({len(content)} chars):")
        print(content[:200])
        print("...")

        # Search for files
        files = await client.glob("**/*.py")
        print(f"\nPython files:\n{files}")

        # Search file contents
        matches = await client.grep("def main", include="*.py")
        print(f"\nFunctions named 'main':\n{matches}")

        # List directory
        listing = await client.list_directory(".")
        print(f"\nDirectory listing:\n{listing}")


def sync_tools_example():
    """Call tools using the synchronous client."""
    with CodyClient(workdir=".") as client:
        result = client.tool("read_file", {"path": "README.md"})
        print(f"README.md: {result.result[:100]}...")


if __name__ == "__main__":
    asyncio.run(async_tools_example())
