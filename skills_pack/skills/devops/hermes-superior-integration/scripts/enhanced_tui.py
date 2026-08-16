#!/usr/bin/env python3
"""
Enhanced TUI for Hermes - Superior to Claude Code's Ink TUI
Features: Multi-line editing, autocomplete, history, interrupt, streaming, sessions
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import asynccontextmanager

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
from prompt_toolkit.widgets import TextArea, Frame, Label
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
import json


# =============================================================================
# COMPLETION ENGINE
# =============================================================================

class HermesCompleter(Completer):
    """Smart completer for slash commands, model names, file paths, skills."""
    
    SLASH_COMMANDS = [
        "/help", "/model", "/new", "/reset", "/continue", "/resume",
        "/compress", "/usage", "/insights", "/skills", "/personality",
        "/retry", "/undo", "/stop", "/platforms", "/sethome",
        "/agent", "/background", "/parallel", "/voice", "/search",
        "/read", "/write", "/edit", "/bash", "/task", "/delegate"
    ]
    
    MODEL_ALIASES = [
        "free-router", "nemotron", "deepseek", "solar", "glm",
        "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
        "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo",
        "llama-3.1-70b", "llama-3.1-8b", "mistral-large",
        "local", "ollama", "nous"
    ]
    
    def __init__(self, session_manager=None):
        self.session_manager = session_manager
        self._skill_names = []
    
    def set_skills(self, skills: List[str]):
        self._skill_names = skills
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # Slash commands
        if text.startswith("/"):
            for cmd in self.SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
            return
        
        # Model names after /model
        if "/model " in text or text.startswith("model "):
            prefix = text.split()[-1] if " " in text else ""
            for model in self.MODEL_ALIASES:
                if model.startswith(prefix):
                    yield Completion(model, start_position=-len(prefix))
            return
        
        # Skills
        if text.startswith("@") or text.startswith("skill "):
            prefix = text[1:] if text.startswith("@") else text.split()[-1]
            for skill in self._skill_names:
                if skill.startswith(prefix):
                    yield Completion(skill, start_position=-len(prefix))
            return
        
        # File paths
        if any(c in text for c in ["/", "~", "."]) and " " not in text[-20:]:
            # Simple path completion
            pass


# =============================================================================
# MULTI-LINE INPUT AREA
# =============================================================================

class MultiLineInput(TextArea):
    """Multi-line input with syntax highlighting and history."""
    
    def __init__(self, **kwargs):
        super().__init__(
            multiline=True,
            wrap_lines=True,
            scrollbar=True,
            line_numbers=False,
            **kwargs
        )


# =============================================================================
# MESSAGE DISPLAY AREA
# =============================================================================

class MessageDisplay(TextArea):
    """Display conversation with formatting."""
    
    def __init__(self, **kwargs):
        super().__init__(
            multiline=True,
            wrap_lines=True,
            scrollbar=True,
            read_only=True,
            **kwargs
        )
    
    def add_message(self, role: str, content: str, timestamp: str = None):
        ts = timestamp or datetime.now().strftime("%H:%M")
        
        if role == "user":
            prefix = f"<ansicyan>[{ts}] You:</ansicyan> "
        elif role == "assistant":
            prefix = f"<ansigreen>[{ts}] Hermes:</ansigreen> "
        elif role == "tool":
            prefix = f"<ansiyellow>[{ts}] Tool:</ansiyellow> "
        elif role == "system":
            prefix = f"<ansimagenta>[{ts}] System:</ansimagenta> "
        else:
            prefix = f"[{ts}] {role}: "
        
        # Append to existing text
        current = self.text
        new_text = current + ("\n" if current else "") + prefix + content
        self.text = new_text
        # Auto-scroll to bottom
        self.buffer.cursor_position = len(self.text)


# =============================================================================
# STATUS BAR
# =============================================================================

class StatusBar:
    """Bottom status bar with model, tokens, mode."""
    
    def __init__(self):
        self.model = "free-router"
        self.provider = "openrouter"
        self.tokens_used = 0
        self.tokens_limit = 100000
        self.mode = "chat"
        self.background_tasks = 0
    
    def get_tokens_html(self):
        pct = self.tokens_used / self.tokens_limit if self.tokens_limit else 0
        color = "ansired" if pct > 0.8 else "ansiyellow" if pct > 0.5 else "ansigreen"
        return f"<{color}>{self.tokens_used:,}/{self.tokens_limit:,}</{color}>"
    
    def get_html(self):
        bg = "ansiblue" if self.background_tasks == 0 else "ansiyellow"
        return HTML(
            f"<ansicyan>{self.model}</ansicyan> | "
            f"Tokens: {self.get_tokens_html()} | "
            f"<{bg}>● {self.background_tasks} bg</{bg}> | "
            f"<ansimagenta>{self.mode}</ansimagenta>"
        )


# =============================================================================
# MAIN TUI APPLICATION
# =============================================================================

class HermesTUI:
    """Full-featured TUI superior to Claude Code's Ink TUI."""
    
    def __init__(self):
        self.session_id = None
        self.messages = []
        self.running = False
        self.current_input = ""
        self.completer = HermesCompleter()
        self.status_bar = StatusBar()
        self.history_file = Path.home() / ".hermes" / "tui_history.txt"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # UI Components
        self.message_display = MessageDisplay()
        self.input_area = MultiLineInput()
        self.status_bar_widget = self.status_bar
        
        # Key bindings
        self.kb = KeyBindings()
        self._setup_keybindings()
        
        # Layout
        self.layout = self._create_layout()
        
        # Application
        self.app = Application(
            layout=self.layout,
            key_bindings=self.kb,
            style=self._get_style(),
            full_screen=True,
            mouse_support=True
        )
        
        # Session
        self.session = PromptSession(
            history=FileHistory(str(self.history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self.completer,
            complete_while_typing=True
        )
    
    def _get_style(self):
        return Style.from_dict({
            "frame.border": "ansicyan",
            "frame.label": "ansicyan bold",
            "scrollbar": "ansicyan",
            "scrollbar.button": "ansicyan",
            "scrollbar.arrow": "ansicyan",
        })
    
    def _create_layout(self):
        from prompt_toolkit.layout.containers import HSplit, VSplit, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        
        # Status bar at bottom
        status_control = FormattedTextControl(
            lambda: self.status_bar.get_html(),
            show_cursor=False
        )
        
        return HSplit([
            Frame(
                Window(self.message_display.buffer, wrap_lines=True),
                title="Hermes Agent",
                style="class:frame"
            ),
            Window(height=1, char="─", style="ansicyan"),
            Frame(
                Window(self.input_area.buffer, wrap_lines=True),
                title="Input (Enter=send, Alt+Enter=newline, Ctrl+C=interrupt)",
                style="class:frame"
            ),
            Window(height=1, char="─", style="ansicyan"),
            Window(height=1, content=FormattedTextControl(
                lambda: self.status_bar.get_html()
            )),
        ])
    
    def _setup_keybindings(self):
        @self.kb.add("enter")
        def _(event):
            """Send message on Enter."""
            if event.app.current_buffer.name == "input":
                text = event.app.current_buffer.text.strip()
                if text:
                    asyncio.create_task(self.send_message(text))
                    event.app.current_buffer.text = ""
        
        @self.kb.add("escape", "enter")
        def _(event):
            """Newline on Alt+Enter."""
            if event.app.current_buffer.name == "input":
                event.app.current_buffer.insert_text("\n")
        
        @self.kb.add("c-c")
        def _(event):
            """Interrupt current operation."""
            asyncio.create_task(self.interrupt())
        
        @self.kb.add("c-l")
        def _(event):
            """Clear screen."""
            self.message_display.text = ""
            event.app.current_buffer.text = ""
        
        @self.kb.add("c-u")
        def _(event):
            """Clear input."""
            event.app.current_buffer.text = ""
        
        @self.kb.add("c-r")
        def _(event):
            """Search history."""
            # Implement reverse history search
            pass
        
        @self.kb.add("f1")
        def _(event):
            """Show help."""
            self.show_help()
        
        @self.kb.add("c-t")
        def _(event):
            """Toggle mode."""
            self.toggle_mode()
    
    async def send_message(self, text: str):
        """Send message to agent."""
        # Add to display
        self.message_display.add_message("user", text)
        
        # Add to history
        self.messages.append({"role": "user", "content": text})
        
        # Send to agent (implement actual agent call)
        await self.call_agent(text)
    
    async def call_agent(self, prompt: str):
        """Call the Hermes agent."""
        # This would integrate with the actual agent loop
        # For now, show placeholder
        self.message_display.add_message("assistant", f"[Processing: {prompt}]")
        
        # Simulate streaming response
        response = await self.stream_agent_response(prompt)
        
        # Update with full response
        self.message_display.add_message("assistant", response)
        self.messages.append({"role": "assistant", "content": response})
    
    async def stream_agent_response(self, prompt: str) -> str:
        """Stream response from agent."""
        # Integrate with actual agent loop
        # This is where you'd call the Hermes agent
        return f"Response to: {prompt}"
    
    async def interrupt(self):
        """Interrupt current agent operation."""
        self.message_display.add_message("system", "[Interrupted]")
        # Send interrupt signal to agent
    
    def show_help(self):
        help_text = """
Hermes TUI - Keyboard Shortcuts:
  Enter          - Send message
  Alt+Enter      - New line
  Ctrl+C         - Interrupt
  Ctrl+L         - Clear screen
  Ctrl+U         - Clear input
  Ctrl+R         - Search history
  F1             - This help
  Ctrl+T         - Toggle mode
  
Commands:
  /help          - Show help
  /model <name>  - Change model
  /new           - New conversation
  /reset         - Reset session
  /compress      - Compress context
  /usage         - Show token usage
  /skills        - List skills
  /agent <name>  - Use specific agent
  /parallel <n>  - Run N agents in parallel
  /voice         - Voice mode
        """
        self.message_display.add_message("system", help_text)
    
    def toggle_mode(self):
        modes = ["chat", "code", "voice", "search"]
        current_idx = modes.index(self.status_bar.mode) if self.status_bar.mode in modes else 0
        self.status_bar.mode = modes[(current_idx + 1) % len(modes)]
    
    def run(self):
        """Run the TUI application."""
        self.running = True
        self.app.run()
    
    async def run_async(self):
        """Run as async task."""
        self.running = True
        await self.app.run_async()


# =============================================================================
# SIMPLER RUNNER
# =============================================================================

async def run_hermes_tui():
    """Run the enhanced TUI."""
    tui = HermesTUI()
    await tui.run_async()


if __name__ == "__main__":
    asyncio.run(run_hermes_tui())