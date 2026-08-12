"""
Tests for the Look & Feel Registry module
(modules/look_and_feel/).

Covers:
  - Parser: single-module parse, multi-module file parse, line-ending
    normalization, FORMATS: slicing, separator detection, mood optional
  - Data model: dict round-trip
  - Registry: load/persist CRUD, upsert semantics, remove, search by tag
  - Module facade: lifecycle, seeding from bundled data, programmatic API,
    CLI, configure, platform factory
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine


# Make modules/ importable (same trick as the other module tests).
_MODULE_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_MODULE_PARENT) not in sys.path:
    sys.path.insert(0, str(_MODULE_PARENT))

from look_and_feel import (  # noqa: E402
    LookAndFeelCLI,
    LookAndFeelEntry,
    LookAndFeelParser,
    LookAndFeelRegistry,
    create_look_and_feel_module,
)

DATA_FILE = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "look_and_feel_modules.txt"
)

_ALL_NAMES = {
    "The Minimalist Muse",
    "The Ethereal Softness",
    "The Cyberpunk Dream",
    "The Dark Academia",
    "The Earthy Artisan",
    "The Neon Noir",
    "The Glassmorphism Gallery",
    "The Japandi Calm",
    "The Brutalist Edge",
    "The Biopunk Organism",
    "The Retro Wave",
    "The Golden Editorial",
}

_CYBERPUNK_TAGS = {"neon", "glitch", "tech", "dark", "futuristic"}


def _run(coro: Coroutine[Any, Any, Any]) -> object:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Parser ─────────────────────────────────────────────────────────────────


def test_parse_single_module() -> None:
    block = (
        "The Cyberpunk Dream\n"
        "Neon. Glitch. Future.\n"
        "__________________________________\n"
        "Design a cyberpunk-themed landing page.\n"
        "Use neon pink and electric blue accents.\n"
        "#neon\n#glitch\n#tech\n#dark\n#futuristic\n"
    )
    entry = LookAndFeelParser.parse_module(block)
    assert entry is not None
    assert entry.name == "The Cyberpunk Dream"
    assert entry.descriptor == "Neon. Glitch. Future."
    assert "cyberpunk" in entry.prompt.lower()
    assert "neon" in entry.prompt.lower()
    assert entry.hashtags == ["neon", "glitch", "tech", "dark", "futuristic"]


def test_parse_module_normalizes_windows_line_endings() -> None:
    block = (
        "The Retro Wave\r\n"
        "Synthwave. Nostalgia. Chrome.\r\n"
        "__________________________________\r\n"
        "Chrome and gradient.\r\n"
        "#retrowave\r\n#synthpop\r\n"
    )
    entry = LookAndFeelParser.parse_module(block)
    assert entry is not None
    assert entry.name == "The Retro Wave"
    assert "#no" not in entry.prompt


def test_parse_module_requires_separator_after_header() -> None:
    # Separator too early (only 1 header line) -> reject.
    bad = "The Minimalist Muse\n__________________________________\nhello\n"
    assert LookAndFeelParser.parse_module(bad) is None
    # No separator -> reject.
    assert LookAndFeelParser.parse_module("Foo\nbar\nbaz\n") is None


def test_parse_module_mood_optional() -> None:
    # 3 header lines -> mood captured.
    with_mood = (
        "The Japandi Calm\n"
        "Wabi-sabi. Stillness. Craft.\n"
        "Calm. Warm. Intentional.\n"
        "__________________________________\n"
        "Muted palette.\n"
        "#japandi\n"
    )
    entry = LookAndFeelParser.parse_module(with_mood)
    assert entry is not None
    assert entry.mood == "Calm. Warm. Intentional."

    # 2 header lines -> mood empty.
    no_mood = (
        "The Japandi Calm\n"
        "Wabi-sabi. Stillness. Craft.\n"
        "__________________________________\n"
        "Muted palette.\n"
        "#japandi\n"
    )
    entry2 = LookAndFeelParser.parse_module(no_mood)
    assert entry2 is not None
    assert entry2.mood == ""


def test_parse_modules_file_loads_all_12() -> None:
    content = DATA_FILE.read_text(encoding="utf-8")
    entries = LookAndFeelParser.parse_modules_file(content)
    names = {e.name for e in entries}
    assert names == _ALL_NAMES
    assert len(entries) == 12


def test_parse_via_load_then_registry() -> None:
    content = DATA_FILE.read_text(encoding="utf-8")
    entries = LookAndFeelParser.parse_modules_file(content)
    by_name = {e.name: e for e in entries}
    cp = by_name["The Cyberpunk Dream"]
    assert set(cp.hashtags) == _CYBERPUNK_TAGS
    assert "neon" in cp.prompt.lower()
    assert "cyberpunk" in cp.prompt.lower()
    glass = by_name["The Glassmorphism Gallery"]
    assert set(glass.hashtags) == {"glass", "gradient", "blur", "gallery", "translucent"}


# ── Data model ─────────────────────────────────────────────────────────────


def test_entry_dict_round_trip() -> None:
    e = LookAndFeelEntry(name="X", descriptor="d", mood="m", prompt="p", hashtags=["a", "b"])
    d = e.to_dict()
    e2 = LookAndFeelEntry.from_dict(d)
    assert e2.name == "X"
    assert e2.hashtags == ["a", "b"]
    assert e2.prompt == "p"


# ── Registry ───────────────────────────────────────────────────────────────


def test_registry_crud(tmp_path: Path) -> None:
    reg = LookAndFeelRegistry(tmp_path / "reg.json")
    assert len(reg) == 0
    e1 = LookAndFeelEntry(name="A", prompt="prompt-a", hashtags=["neon"])
    e2 = LookAndFeelEntry(name="B", prompt="prompt-b", hashtags=["glass"])

    assert reg.upsert(e1) is False  # new
    assert reg.upsert(e2) is False
    assert len(reg) == 2
    assert reg.upsert(e1) is True  # overwrite existing returns True
    assert len(reg) == 2

    assert reg.get("A").prompt == "prompt-a"
    assert reg.get("nope") is None

    assert reg.remove("A") is True
    assert reg.remove("A") is False
    assert len(reg) == 1

    reg.persist()
    reg2 = LookAndFeelRegistry(tmp_path / "reg.json")
    assert len(reg2) == 1
    assert reg2.get("B").prompt == "prompt-b"


def test_registry_search(tmp_path: Path) -> None:
    reg = LookAndFeelRegistry(tmp_path / "r.json")
    reg.upsert(LookAndFeelEntry(name="Cyberpunk", hashtags=["neon", "glitch"]))
    reg.upsert(LookAndFeelEntry(name="Neon Noir", hashtags=["noir", "neon"]))
    reg.upsert(LookAndFeelEntry(name="Glass", hashtags=["glass"]))

    assert {e.name for e in reg.search("#neon")} == {"Cyberpunk", "Neon Noir"}
    assert {e.name for e in reg.search("neon")} == {"Cyberpunk", "Neon Noir"}
    assert {e.name for e in reg.search("glass")} == {"Glass"}
    assert reg.search("nope") == []


def test_registry_missing_or_corrupt_file_is_handled(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    reg = LookAndFeelRegistry(bad)
    assert len(reg) == 0


# ── CLI ────────────────────────────────────────────────────────────────────


def test_cli_list_use_search(tmp_path: Path) -> None:
    reg = LookAndFeelRegistry(tmp_path / "c.json")
    reg.upsert(
        LookAndFeelEntry(
            name="The Cyberpunk Dream",
            prompt="neon prompt here",
            hashtags=["neon", "dark"],
        )
    )
    reg.upsert(
        LookAndFeelEntry(name="The Brutalist Edge", prompt="raw bold", hashtags=["brutalist"])
    )
    cli = LookAndFeelCLI(reg, LookAndFeelParser())

    listing = cli.run(["list"])
    assert "The Cyberpunk Dream" in listing
    assert "#neon" in listing

    assert "neon prompt here" in cli.run(["use", "The Cyberpunk Dream"])
    assert "The Brutalist Edge" in cli.run(["search", "brutalist"])
    assert "usage" in cli.run([])


# ── Module facade ──────────────────────────────────────────────────────────


def test_module_lifecycle_and_api(tmp_path: Path) -> None:
    reg_path = tmp_path / "module_registry.json"
    mod = create_look_and_feel_module(
        {
            "registry_path": str(reg_path),
            "default_modules_path": str(DATA_FILE),
        }
    )
    _run(mod.initialize())
    try:
        assert len(mod.list_modules()) == 12
        assert {m.name for m in mod.list_modules()} == _ALL_NAMES

        cp = mod.get_module("The Cyberpunk Dream")
        assert cp is not None
        assert "neon" in cp.prompt.lower()
        assert set(cp.hashtags) == _CYBERPUNK_TAGS

        neon = mod.search_by_tag("#neon")
        assert {m.name for m in neon} == {"The Cyberpunk Dream", "The Neon Noir", "The Retro Wave"}

        glass = mod.search_by_tag("#glass")
        assert [m.name for m in glass] == ["The Glassmorphism Gallery"]

        out = mod.run_cli(["list"])
        assert "The Minimalist Muse" in out
        assert "The Golden Editorial" in out
        assert "cyberpunk" in mod.run_cli(["use", "The Cyberpunk Dream"]).lower()
        assert "The Brutalist Edge" in mod.run_cli(["search", "brutalist"])
    finally:
        _run(mod.shutdown())

    # Shutdown persists -> reload sees modules.
    assert reg_path.exists()
    reg = LookAndFeelRegistry(reg_path)
    assert len(reg) >= 12


def test_module_health_check(tmp_path: Path) -> None:
    import enterprise.platform_kernel as pk

    mod = create_look_and_feel_module(
        {
            "registry_path": str(tmp_path / "h.json"),
            "default_modules_path": str(DATA_FILE),
        }
    )
    _run(mod.initialize())
    status = _run(mod.health_check())
    assert status == pk.HealthStatus.HEALTHY
    _run(mod.shutdown())
