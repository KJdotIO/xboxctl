from pathlib import Path

from mcp.server.fastmcp.utilities.types import Image
from mcp.types import ImageContent, TextContent


def screenshot_content(path: Path) -> list[TextContent | ImageContent]:
    return [
        TextContent(
            type="text",
            text=f"Xbox screenshot captured: {path}",
        ),
        Image(path=path).to_image_content(),
    ]
