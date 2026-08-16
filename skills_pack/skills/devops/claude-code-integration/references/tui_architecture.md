#!/usr/bin/env python3
"""
TUI Architecture: Ink (React) → Python Mapping

This document explains how the Ink-based React TUI architecture from Claude Code
maps to Python implementation patterns.
"""

# =============================================================================
# INK REACT PATTERNS → PYTHON EQUIVALENTS
# =============================================================================

"""
Ink (React for CLI)                    Python Equivalent
─────────────────────────────────────────────────────────────────────────────
Component (class)                      Class with render() method
Component (function)                   Function returning string/dict
Props                                  **kwargs or dataclass
State (useState)                       Instance attributes + dirty flag
Context (React.Context)                contextvars.ContextVar / ContextManager
useEffect                              __aenter__ / __aexit__ + callbacks
useRef                                 Instance attribute
useMemo/useCallback                    @cached_property / lru_cache
Fragment                               List/string concatenation
Portal                                 Not directly applicable (single terminal)
"""

# =============================================================================
# KEY APP.TXS PATTERNS MAPPED
# =============================================================================

# 1. RAW MODE HANDLING
# ─────────────────────────────────────────────────────────────────────────────
# App.tsx:
#   handleSetRawMode(enabled) {
#     stdin.setRawMode(enabled)
#     stdin.addListener('readable', handleReadable)
#   }
#
# Python:
import termios, tty, sys, os

class RawModeManager:
    def __init__(self, fd=sys.stdin.fileno()):
        self.fd = fd
        self.old_attrs = None
    
    def __enter__(self):
        self.old_attrs = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        return self
    
    def __exit__(self, *args):
        if self.old_attrs:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_attrs)

# 2. KEY PARSING STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────
# App.tsx uses parseMultipleKeypresses with state tracking for:
# - Normal keys
# - Escape sequences (CSI, OSC, DCS)
# - CSI u / Kitty keyboard protocol
# - Bracketed paste mode
# - Mouse events (SGR 1006, X10)
#
# Python: KeyParser class in hermes_cli/key_parser.py

# 3. MOUSE TRACKING
# ─────────────────────────────────────────────────────────────────────────────
# App.tsx enables:
#   - DECSET 1000 (X10 compatibility)
#   - DECSET 1002 (button-event tracking)
#   - DECSET 1003 (any-event tracking)
#   - DECSET 1006 (SGR 1006 extended coordinates)
#   - DECSET 1004 (focus reporting)
#
# Python: MouseTracker class with same escape sequences

# 4. STDIN RESUME GAP DETECTION
# ─────────────────────────────────────────────────────────────────────────────
# App.tsx detects tmux attach, ssh reconnect, laptop wake:
#   STDIN_RESUME_GAP_MS = 5000
#   lastStdinTime = Date.now()
#   if (now - lastStdinTime > gap): re-assert terminal modes
#
# Python: Same pattern in StdinManager

# 5. CONTEXT PROVIDERS → CONTEXT MANAGERS
# ─────────────────────────────────────────────────────────────────────────────
# App.tsx wraps children in:
#   TerminalSizeContext, AppContext, StdinContext, TerminalFocusProvider,
#   ClockProvider, CursorDeclarationContext
#
# Python: Use @contextmanager or contextvars.ContextVar

# =============================================================================
# RENDERING ARCHITECTURE
# =============================================================================

"""
Ink uses Yoga layout engine for flexbox in terminal.
Python options:
  1. textual (has built-in layout) - RECOMMENDED
  2. prompt_toolkit (has layout)
  3. Custom Yoga bindings (pyyoga)
  4. Manual ANSI positioning (simplest)

For Hermes, we use prompt_toolkit with custom layout for compatibility.
"""

# =============================================================================
# EVENT HANDLING
# =============================================================================

"""
React: onKeyDown, onMouseDown, onFocus
Python: callbacks in KeyParser, MouseTracker, FocusTracker

App.tsx internal_eventEmitter → asyncio.Event + callback registry
"""

# =============================================================================
# SUSPEND/RESUME (Ctrl+Z)
# =============================================================================

"""
App.tsx handleSuspend():
  1. Disable raw mode completely
  2. Show cursor, disable focus/mouse tracking
  3. Emit 'suspend' event
  4. SIGSTOP process
  5. On SIGCONT: restore raw mode, hide cursor, re-enable tracking
  6. Emit 'resume' event

Python: signal.signal(signal.SIGTSTP, handler) + SIGCONT handling
"""

# =============================================================================
# TERMINAL QUERIES (DA1, XTVERSION)
# =============================================================================

"""
App.tsx uses TerminalQuerier:
  - Sends CSI queries (DA1 for terminal ID, XTVERSION for name)
  - Receives responses on stdin (parsed by parse-keypress)
  - Promise-based response handling

Python: TerminalQuerier class with asyncio.Future for responses
"""

# =============================================================================
# RECONCILER / DISCRETE UPDATES
# =============================================================================

"""
Ink uses reconciler.discreteUpdates() to batch state updates
from multiple key events in single event loop tick.

Python: Collect all parsed keys, process in single batch,
then trigger single render.
"""

# =============================================================================
# RECOMMENDED PYTHON STACK FOR HERMES TUI
# =============================================================================

"""
Base: prompt_toolkit 3.x
  - Full ANSI support
  - Key binding system
  - Layout engine (flexbox-like)
  - Mouse support
  - Raw mode handling
  - Async event loop integration

Add-ons:
  - pyyoga (if Yoga layout needed)
  - rich (for rendering components)
  - textual (higher-level, but more opinionated)

Current Hermes uses: prompt_toolkit + custom components
"""

# =============================================================================
# FILE STRUCTURE FOR TUI
# =============================================================================

"""
hermes_cli/tui/
├── __init__.py
├── app.py              # Main App class (App.tsx equivalent)
├── key_parser.py       # parseMultipleKeypresses equivalent
├── mouse_tracker.py    # SGR 1006, X10, focus events
├── stdin_manager.py    # Raw mode, resume gap detection
├── terminal_querier.py # DA1, XTVERSION, cursor position
├── components/
│   ├── __init__.py
│   ├── base.py         # Component base class
│   ├── input.py        # Text input with history
│   ├── message_list.py # Scrollable message display
│   ├── status_bar.py   # Bottom status line
│   ├── toolbar.py      # Slash command palette
│   └── dialog.py       # Modal dialogs
├── layout.py           # Yoga/manual layout
├── theme.py            # Color/theme system
└── hooks.py            # useEffect-like lifecycle
"""