import json
import struct
from pathlib import Path

STATIC = Path(__file__).parent.parent / "audiobook_notifier" / "static"


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the IHDR chunk, which always comes first."""
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", header[16:24])


def test_manifest_icons_exist_with_declared_size():
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone"
    sizes = set()
    for icon in manifest["icons"]:
        path = STATIC / icon["src"].lstrip("/")
        width, height = (int(n) for n in icon["sizes"].split("x"))
        assert png_size(path) == (width, height), icon["src"]
        sizes.add(width)
    # Chrome requires both for installability.
    assert {192, 512} <= sizes


def test_apple_touch_icon_size():
    assert png_size(STATIC / "icon-180.png") == (180, 180)
