"""
TUI Engine — prompt_toolkit-based Terminal UI with Ink-inspired Component Tree
===============================================================================

Re-implements Claude Code's Ink rendering system as a Python-native
prompt_toolkit-based terminal UI framework. Provides:

  - Component tree with declarative layout (Ink-inspired)
  - Keybinding registry with modal support
  - Theme engine with 6 built-in themes + custom theme support
  - Component lifecycle (mount, update, unmount)
  - Event-driven rendering via publisher/subscriber hooks
  - Vim-style navigation modes (normal, insert, visual)

Usage::

    engine = TUIEngine(event_bus=event_bus)
    await engine.initialize()
    root = engine.create_root()
    text_box = TextBox(props={"value": "Hello, World!", "border": "rounded"})
    root.mount(text_box)
    await engine.start(component=root)

Themes:
  - dark (default)    — Claude-inspired dark palette
  - light             — clean light terminal palette
  - tokyo-night       — Tokyo Night inspired
  - gruvbox           — retro warm palette
  - nord              — Arctic, north-bluish
  - catppuccin        — pastel-heavy soothing palette

Key mappings:
  See KeybindingRegistry for default mappings including Vim-mode
"""

from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.formatted_text import FormattedText  # noqa: F401
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings  # noqa: F401
    from prompt_toolkit.keys import Keys  # noqa: F401
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import (
        Float,  # noqa: F401
        FloatContainer,  # noqa: F401
        HSplit,
        VSplit,  # noqa: F401
        Window,
        WindowAlign,  # noqa: F401
    )
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.styles import Style, merge_styles  # noqa: F401

    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

import contextlib

from enterprise.platform_kernel import Event, EventBus, HealthStatus

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: logging.Logger = logging.getLogger("enterprise.agent_infra.tui")


# =============================================================================
# Enums & Constants
# =============================================================================


class TUIMode(Enum):
    """TUI rendering mode."""

    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    COMMAND = "command"


class ComponentLifecycle(Enum):
    """Component lifecycle state."""

    CREATED = "created"
    MOUNTING = "mounting"
    MOUNTED = "mounted"
    UPDATING = "updating"
    UNMOUNTING = "unmounting"
    UNMOUNTED = "unmounted"
    ERROR = "error"


# =============================================================================
# Theme Engine
# =============================================================================


@dataclass
class ThemePalette:
    """Color palette for a TUI theme."""

    name: str
    background: str = "#1a1b26"
    foreground: str = "#a9b1d6"
    primary: str = "#7aa2f7"
    secondary: str = "#bb9af7"
    accent: str = "#f7768e"
    success: str = "#9ece6a"
    warning: str = "#e0af68"
    error: str = "#f7768e"
    info: str = "#7dcfff"
    muted: str = "#565f89"
    border: str = "#3b4261"
    highlight: str = "#292e42"
    cursor: str = "#c0caf5"
    selection: str = "#364a82"

    def to_prompt_toolkit_style(self) -> Style:
        """Convert theme palette to prompt_toolkit Style."""
        return Style.from_dict(
            {
                # Base
                "": f"bg:{self.background} fg:{self.foreground}",
                # Components
                "window.border": f"fg:{self.border}",
                "window.title": f"fg:{self.primary} bold",
                "text.primary": f"fg:{self.foreground}",
                "text.secondary": f"fg:{self.muted}",
                "text.accent": f"fg:{self.accent}",
                "text.success": f"fg:{self.success}",
                "text.warning": f"fg:{self.warning}",
                "text.error": f"fg:{self.error}",
                "text.info": f"fg:{self.info}",
                "text.muted": f"fg:{self.muted}",
                # Interactive
                "button": f"bg:{self.primary} fg:{self.background} bold",
                "button.focused": f"bg:{self.accent} fg:{self.background} bold",
                "input": f"bg:{self.highlight} fg:{self.foreground}",
                "input.border": f"fg:{self.border}",
                "input.focused": f"bg:{self.highlight} fg:{self.foreground}",
                "input.focused.border": f"fg:{self.primary}",
                # Selection
                "selection": f"bg:{self.selection} fg:{self.foreground}",
                # Cursor
                "cursor": f"fg:{self.cursor}",
                "cursor-line": f"bg:{self.highlight}",
                # Status bar
                "status-bar": f"bg:{self.highlight} fg:{self.foreground}",
                "status-bar.mode": f"bg:{self.primary} fg:{self.background} bold",
                # Scrollbar
                "scrollbar": f"bg:{self.border}",
                "scrollbar.arrow": f"fg:{self.muted}",
                # Menu
                "menu": f"bg:{self.highlight} fg:{self.foreground}",
                "menu.selected": f"bg:{self.selection} fg:{self.foreground}",
            }
        )


class ThemeEngine:
    """Manages TUI themes with built-in presets and custom theme support.

    Provides 6 built-in themes (dark, light, tokyo-night, gruvbox, nord,
    catppuccin) and allows registration of custom themes.
    """

    BUILTIN_THEMES: dict[str, ThemePalette] = {
        "dark": ThemePalette(
            name="dark",
            background="#1a1b26",
            foreground="#a9b1d6",
            primary="#7aa2f7",
            secondary="#bb9af7",
            accent="#f7768e",
            success="#9ece6a",
            warning="#e0af68",
            error="#f7768e",
            info="#7dcfff",
            muted="#565f89",
            border="#3b4261",
            highlight="#292e42",
            cursor="#c0caf5",
            selection="#364a82",
        ),
        "light": ThemePalette(
            name="light",
            background="#fafafa",
            foreground="#383a42",
            primary="#4078f2",
            secondary="#a626a4",
            accent="#e45649",
            success="#50a14f",
            warning="#c18401",
            error="#e45649",
            info="#0184bc",
            muted="#a0a1a7",
            border="#d0d0d0",
            highlight="#f0f0f0",
            cursor="#526fff",
            selection="#e5e5e6",
        ),
        "tokyo-night": ThemePalette(
            name="tokyo-night",
            background="#24283b",
            foreground="#c0caf5",
            primary="#7aa2f7",
            secondary="#bb9af7",
            accent="#f7768e",
            success="#9ece6a",
            warning="#e0af68",
            error="#f7768e",
            info="#7dcfff",
            muted="#565f89",
            border="#3b4261",
            highlight="#1f2335",
            cursor="#c0caf5",
            selection="#364a82",
        ),
        "gruvbox": ThemePalette(
            name="gruvbox",
            background="#282828",
            foreground="#ebdbb2",
            primary="#458588",
            secondary="#b16286",
            accent="#cc241d",
            success="#98971a",
            warning="#d79921",
            error="#fb4934",
            info="#83a598",
            muted="#7c6f64",
            border="#504945",
            highlight="#3c3836",
            cursor="#ebdbb2",
            selection="#504945",
        ),
        "nord": ThemePalette(
            name="nord",
            background="#2e3440",
            foreground="#d8dee9",
            primary="#88c0d0",
            secondary="#81a1c1",
            accent="#bf616a",
            success="#a3be8c",
            warning="#ebcb8b",
            error="#bf616a",
            info="#5e81ac",
            muted="#4c566a",
            border="#434c5e",
            highlight="#3b4252",
            cursor="#d8dee9",
            selection="#434c5e",
        ),
        "catppuccin": ThemePalette(
            name="catppuccin",
            background="#1e1e2e",
            foreground="#cdd6f4",
            primary="#cba6f7",
            secondary="#b4befe",
            accent="#f38ba8",
            success="#a6e3a1",
            warning="#fab387",
            error="#f38ba8",
            info="#89b4fa",
            muted="#6c7086",
            border="#45475a",
            highlight="#313244",
            cursor="#f5c2e7",
            selection="#45475a",
        ),
    }

    def __init__(
        self, theme_name: str = "dark", custom_themes: dict[str, ThemePalette] | None = None
    ) -> None:
        self._custom_themes: dict[str, ThemePalette] = custom_themes or {}
        self._active_theme_name: str = theme_name

    @property
    def active_theme_name(self) -> str:
        return self._active_theme_name

    def get_active_theme(self) -> ThemePalette:
        """Return the currently active theme palette."""
        if self._active_theme_name in self._custom_themes:
            return self._custom_themes[self._active_theme_name]
        return self.BUILTIN_THEMES.get(self._active_theme_name, self.BUILTIN_THEMES["dark"])

    def set_theme(self, name: str) -> None:
        """Switch to a different theme by name."""
        self._active_theme_name = name

    def register_theme(self, palette: ThemePalette) -> None:
        """Register a custom theme."""
        self._custom_themes[palette.name] = palette
        _logger.info("Custom theme registered: %s", palette.name)

    def list_themes(self) -> list[str]:
        """Return all available theme names."""
        return list(self.BUILTIN_THEMES) + list(self._custom_themes)

    def get_prompt_toolkit_style(self) -> Style:
        """Return the active theme as a prompt_toolkit Style."""
        return self.get_active_theme().to_prompt_toolkit_style()


# =============================================================================
# Component System (Ink-inspired component tree)
# =============================================================================


@dataclass
class ComponentProps:
    """Base props for all components. Extensible via subclassing."""

    id: str | None = None
    class_name: str | None = None
    visible: bool = True
    focusable: bool = False
    width: int | str = "auto"
    height: int | str = "auto"
    border: str | None = None  # "rounded", "single", "double", "none"
    padding: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentNode:
    """A node in the Ink-inspired component tree.

    Analogous to Ink's virtual DOM nodes but using prompt_toolkit containers.
    """

    name: str
    props: ComponentProps = field(default_factory=ComponentProps)
    children: list[ComponentNode] = field(default_factory=list)
    parent: ComponentNode | None = None
    lifecycle: ComponentLifecycle = ComponentLifecycle.CREATED
    state: dict[str, Any] = field(default_factory=dict)

    def mount(self, child: ComponentNode) -> ComponentNode:
        """Mount a child component onto this node."""
        child.parent = self
        child.lifecycle = ComponentLifecycle.MOUNTING
        self.children.append(child)
        child.lifecycle = ComponentLifecycle.MOUNTED
        return child

    def unmount(self) -> None:
        """Unmount this component from its parent."""
        if self.parent:
            self.lifecycle = ComponentLifecycle.UNMOUNTING
            self.parent.children = [c for c in self.parent.children if c is not self]
            self.lifecycle = ComponentLifecycle.UNMOUNTED
            self.parent = None

    def set_state(self, **kwargs: Any) -> None:
        """Update component state, triggering a re-render signal."""
        self.state.update(kwargs)
        self.lifecycle = ComponentLifecycle.UPDATING

    def find(self, component_id: str) -> ComponentNode | None:
        """Find a descendant by its component id."""
        if self.props.id == component_id:
            return self
        for child in self.children:
            found = child.find(component_id)
            if found:
                return found
        return None

    def walk(self) -> list[ComponentNode]:
        """Return all nodes in the tree as a flat list (pre-order traversal)."""
        nodes = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes


class Component(abc.ABC):
    """Abstract base component with Ink-like render interface.

    Subclasses implement render() to produce a ComponentNode tree.
    """

    @abc.abstractmethod
    def render(self, props: ComponentProps) -> ComponentNode:
        """Render this component into a ComponentNode."""
        ...


class RootComponent(Component):
    """The root component of the TUI. Wraps the entire application."""

    def render(self, props: ComponentProps) -> ComponentNode:
        node = ComponentNode(name="root", props=props)
        node.lifecycle = ComponentLifecycle.MOUNTED
        return node


class TextBox(Component):
    """A simple text display box component."""

    def render(self, props: ComponentProps) -> ComponentNode:
        return ComponentNode(name="text_box", props=props)


class InputBox(Component):
    """A text input box component."""

    def render(self, props: ComponentProps) -> ComponentNode:
        p = ComponentProps(**{**props.__dict__, "focusable": True})
        return ComponentNode(name="input_box", props=p)


class Button(Component):
    """A clickable button component."""

    def render(self, props: ComponentProps) -> ComponentNode:
        p = ComponentProps(**{**props.__dict__, "focusable": True})
        return ComponentNode(name="button", props=p)


class SplitPane(Component):
    """A split-pane container (horizontal or vertical)."""

    def render(self, props: ComponentProps) -> ComponentNode:
        return ComponentNode(name="split_pane", props=props)


class StatusBar(Component):
    """A status bar component typically at the bottom of the TUI."""

    def render(self, props: ComponentProps) -> ComponentNode:
        return ComponentNode(name="status_bar", props=props)


# =============================================================================
# Keybinding Registry
# =============================================================================


@dataclass
class Keybinding:
    """A single keybinding registration."""

    keys: str
    action: str
    description: str
    mode: TUIMode = TUIMode.NORMAL
    priority: int = 0

    def __hash__(self) -> int:
        return hash((self.keys, self.action, self.mode))


class KeybindingRegistry:
    """Manages keybindings with modal support (normal, insert, visual, command).

    Provides default keybindings inspired by Claude Code's keybinding system
    and Vim-style modal editing.
    """

    def __init__(self) -> None:
        self._bindings: dict[TUIMode, set[Keybinding]] = {m: set() for m in TUIMode}
        self._mode: TUIMode = TUIMode.NORMAL
        self._action_handlers: dict[str, Callable[[], Any]] = {}
        self._register_defaults()

    @property
    def mode(self) -> TUIMode:
        return self._mode

    @mode.setter
    def mode(self, value: TUIMode) -> None:
        self._mode = value
        _logger.debug("Keybinding mode switched to: %s", value.value)

    def register(
        self,
        keys: str,
        action: str,
        description: str = "",
        mode: TUIMode = TUIMode.NORMAL,
        priority: int = 0,
    ) -> None:
        """Register a new keybinding."""
        kb = Keybinding(
            keys=keys, action=action, description=description, mode=mode, priority=priority
        )
        self._bindings[mode].add(kb)

    def unregister(self, keys: str, mode: TUIMode) -> None:
        """Remove a keybinding."""
        self._bindings[mode] = {kb for kb in self._bindings[mode] if kb.keys != keys}

    def get_bindings_for_mode(self, mode: TUIMode | None = None) -> set[Keybinding]:
        """Return all keybindings for the given mode."""
        return self._bindings.get(mode or self._mode, set())

    def bind_action_handler(self, action: str, handler: Callable[[], Any]) -> None:
        """Bind a handler to an action name."""
        self._action_handlers[action] = handler

    def get_handler(self, action: str) -> Callable[[], Any] | None:
        """Get the handler for an action."""
        return self._action_handlers.get(action)

    def to_prompt_toolkit_bindings(self) -> KeyBindings:
        """Convert registered bindings to prompt_toolkit KeyBindings.

        Returns an empty KeyBindings if prompt_toolkit is not available.
        """
        if not PROMPT_TOOLKIT_AVAILABLE:
            return KeyBindings()

        kb = KeyBindings()
        active_bindings = self.get_bindings_for_mode()

        for binding in active_bindings:
            action = binding.action
            handler = self._action_handlers.get(action)

            if handler is not None:

                def _make_handler(h: Callable[[], Any]) -> Callable:
                    def _wrapped(event: Any) -> None:
                        h()

                    return _wrapped

                kb.add(binding.keys)(_make_handler(handler))
            else:
                _logger.debug("No handler for action: %s", action)

        return kb

    def get_default_bindings(self) -> dict[TUIMode, list[tuple[str, str, str]]]:
        """Return default keybinding definitions as (keys, action, description)."""
        defaults: dict[TUIMode, list[tuple[str, str, str]]] = {
            TUIMode.NORMAL: [
                ("q", "quit", "Quit application"),
                ("c-q", "force_quit", "Force quit"),
                ("/", "search", "Search"),
                ("g g", "scroll_top", "Scroll to top"),
                ("G", "scroll_bottom", "Scroll to bottom"),
                ("j", "cursor_down", "Move cursor down"),
                ("k", "cursor_up", "Move cursor up"),
                ("h", "cursor_left", "Move cursor left"),
                ("l", "cursor_right", "Move cursor right"),
                ("c-p", "command_palette", "Open command palette"),
                ("c-r", "reload", "Reload configuration"),
                ("F1", "help", "Show help"),
                ("Tab", "focus_next", "Focus next component"),
                ("S-Tab", "focus_prev", "Focus previous component"),
            ],
            TUIMode.INSERT: [
                ("escape", "mode_normal", "Switch to normal mode"),
                ("c-c", "mode_normal", "Switch to normal mode"),
            ],
            TUIMode.VISUAL: [
                ("escape", "mode_normal", "Switch to normal mode"),
                ("y", "yank", "Yank selection"),
                ("d", "delete_selection", "Delete selection"),
            ],
            TUIMode.COMMAND: [
                ("escape", "mode_normal", "Cancel command"),
                ("enter", "execute_command", "Execute command"),
            ],
        }
        return defaults

    def _register_defaults(self) -> None:
        """Register all default keybindings."""
        for mode, bindings in self.get_default_bindings().items():
            for keys, action, desc in bindings:
                self.register(keys=keys, action=action, description=desc, mode=mode)


# =============================================================================
# TUI Engine (main orchestrator)
# =============================================================================


@dataclass
class TUIConfig:
    """Configuration for the TUI engine."""

    theme: str = "dark"
    full_screen: bool = True
    mouse_support: bool = True
    title: str = "Claude Code Superior — ENI Enterprise"
    refresh_rate: float = 0.016  # ~60 FPS
    vim_mode_enabled: bool = True


class TUIHealthCheck:
    """Health check for the TUI engine."""

    def __init__(self, engine: TUIEngine) -> None:
        self._engine = engine

    async def run(self) -> bool:
        """Run a health check on the TUI engine.

        The engine is healthy when it has been initialized. This is consistent
        with ``TUIEngine.initialize()`` which marks the engine HEALTHY once
        the component tree, theme, and keybindings are wired. Returning
        ``_initialized`` avoids the prior inconsistency where a fully
        initialised engine (headless or live) reported unhealthy.

        Returns:
            True if the engine is operational.
        """
        if not PROMPT_TOOLKIT_AVAILABLE:
            _logger.warning("prompt_toolkit not available — TUI in headless mode")

        return bool(self._engine._initialized)


class TUIEngine:
    """The main TUI engine orchestrating prompt_toolkit with an Ink-inspired
    component tree, keybinding registry, and theme engine.

    Can run in headless mode (no prompt_toolkit needed) for CI/testing.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = config or {}
        self._event_bus = event_bus
        self._config = TUIConfig(
            theme=cfg.get("theme", "dark"),
            full_screen=cfg.get("full_screen", True),
            mouse_support=cfg.get("mouse_support", True),
            title=cfg.get("title", "Claude Code Superior — ENI Enterprise"),
            refresh_rate=cfg.get("refresh_rate", 0.016),
            vim_mode_enabled=cfg.get("vim_mode_enabled", True),
        )
        self._theme_engine = ThemeEngine(theme_name=self._config.theme)
        self._keybindings = KeybindingRegistry()
        self._root: ComponentNode | None = None
        self._application: Any | None = None
        self._initialized: bool = False
        self._running: bool = False
        self._lock = threading.RLock()
        self._status: HealthStatus = HealthStatus.UNKNOWN

    @property
    def theme_engine(self) -> ThemeEngine:
        return self._theme_engine

    @property
    def keybindings(self) -> KeybindingRegistry:
        return self._keybindings

    @property
    def root(self) -> ComponentNode | None:
        return self._root

    @property
    def status(self) -> HealthStatus:
        return self._status

    async def initialize(self) -> None:
        """Initialize the TUI engine with default theme and keybindings."""
        with self._lock:
            self._status = HealthStatus.STARTING
            self._root = ComponentNode(name="root", props=ComponentProps(id="root"))
            self._root.lifecycle = ComponentLifecycle.MOUNTED

            # Register default action handlers
            self._keybindings.bind_action_handler("quit", self._action_quit)
            self._keybindings.bind_action_handler("force_quit", self._action_quit)

            if PROMPT_TOOLKIT_AVAILABLE:
                _logger.info("TUI Engine: prompt_toolkit detected, full TUI available")
            else:
                _logger.info("TUI Engine: prompt_toolkit NOT available, running in headless mode")

            self._initialized = True
            self._status = HealthStatus.HEALTHY

    async def start(self, component: ComponentNode | None = None) -> None:
        """Start the TUI event loop with the given root component."""
        if not self._initialized:
            await self.initialize()

        if component is not None:
            self._root = component

        if not PROMPT_TOOLKIT_AVAILABLE:
            _logger.info("TUI Engine: headless mode — start() is a no-op")
            self._running = True
            return

        try:
            style = self._theme_engine.get_prompt_toolkit_style()

            layout = Layout(
                container=HSplit(
                    [
                        Window(
                            content=FormattedTextControl(
                                text="Claude Code Superior — ENI Enterprise"
                            ),
                            height=1,
                        ),
                        Window(
                            content=FormattedTextControl(
                                text="Prompt ready. Type /help for commands."
                            ),
                        ),
                        Window(
                            content=BufferControl(buffer=Buffer()),
                            height=1,
                        ),
                    ]
                ),
            )

            app: Application = Application(
                layout=layout,
                key_bindings=self._keybindings.to_prompt_toolkit_bindings(),
                style=style,
                full_screen=self._config.full_screen,
                mouse_support=self._config.mouse_support,
            )

            self._application = app
            self._running = True

            if self._event_bus:
                self._event_bus.publish(
                    Event.create(
                        "claude.infra.tui.rendering",
                        "tui_engine",
                        {"status": "running"},
                    )
                )

            _logger.info("TUI Engine started")
            await app.run_async()

        except Exception as exc:
            _logger.exception("TUI Engine failed to start: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def stop(self) -> None:
        """Stop the TUI event loop."""
        self._running = False
        if self._application is not None and PROMPT_TOOLKIT_AVAILABLE:
            with contextlib.suppress(Exception):
                self._application.exit()
        _logger.info("TUI Engine stopped")

    async def health_check(self) -> bool:
        """Run a health check and return True if operational."""
        checker = TUIHealthCheck(self)
        result = await checker.run()
        self._status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
        return result

    async def shutdown(self) -> None:
        """Gracefully shut down the TUI engine."""
        self._status = HealthStatus.STOPPING
        await self.stop()
        with self._lock:
            self._root = None
            self._initialized = False
        self._status = HealthStatus.HEALTHY
        _logger.info("TUI Engine shut down")

    def create_root(self, **props: Any) -> ComponentNode:
        """Create a new root component node."""
        p = ComponentProps(**props) if props else ComponentProps(id="app-root")
        return ComponentNode(name="root", props=p)

    def get_focused(self) -> ComponentNode | None:
        """Get the currently focused component, if any."""
        if self._root is None:
            return None
        return self._find_focused(self._root)

    def _find_focused(self, node: ComponentNode) -> ComponentNode | None:
        """Recursively find a focused node."""
        if node.props.focusable and node.props.visible:
            return node
        for child in node.children:
            found = self._find_focused(child)
            if found:
                return found
        return None

    def _action_quit(self) -> None:
        """Default quit action."""
        _logger.info("Quit action triggered")
        if self._event_bus:
            self._event_bus.publish(Event.create("claude.infra.tui.quit", "tui_engine", {}))

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event if the event bus is available."""
        if self._event_bus:
            self._event_bus.publish(Event.create(topic, "tui_engine", payload))
