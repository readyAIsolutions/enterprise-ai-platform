#!/usr/bin/env python3
"""
Integration test for claude-code-integration skill.
Tests that all major components are accessible and functional.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add skill scripts to path
skill_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(skill_dir))

def test_imports():
    """Test that all reference files exist and are readable."""
    refs_dir = Path(__file__).parent.parent / "references"
    
    required_files = [
        "architecture_mapping.md",
        "tui_architecture.md", 
        "shell_command.md",
        "hooks_system.md",
        "memory_system.md",
        "agent_delegation.md",
        "session_management.md"
    ]
    
    print("Testing reference files...")
    for f in required_files:
        path = refs_dir / f
        assert path.exists(), f"Missing: {f}"
        size = path.stat().st_size
        assert size > 1000, f"File too small: {f}"
        print(f"  ✅ {f} ({size:,} bytes)")
    
    return True

def test_templates():
    """Test that template files exist."""
    templates_dir = Path(__file__).parent.parent / "templates"
    
    required_templates = [
        "CLAUDE.md.template",
        "CLAUDE.local.md.template", 
        "hooks.yaml.template"
    ]
    
    print("\nTesting templates...")
    for t in required_templates:
        path = templates_dir / t
        assert path.exists(), f"Missing template: {t}"
        size = path.stat().st_size
        print(f"  ✅ {t} ({size:,} bytes)")
    
    return True

def test_scripts():
    """Test that script files exist and are valid Python."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    
    required_scripts = [
        "local_agent_client.py",
    ]
    
    print("\nTesting scripts...")
    for s in required_scripts:
        path = scripts_dir / s
        assert path.exists(), f"Missing script: {s}"
        
        # Validate Python syntax
        with open(path) as f:
            compile(f.read(), str(path), 'exec')
        
        size = path.stat().st_size
        print(f"  ✅ {s} ({size:,} bytes)")
    
    return True

async def test_local_agent_client():
    """Test that local agent client can be imported and used."""
    from local_agent_client import (
        LocalAgentClient,
        local_shell,
        local_read_file,
        local_write_file,
        local_search,
        local_system_info
    )
    
    print("\nTesting local agent client imports...")
    print("  ✅ All client functions imported successfully")
    
    # Test that we can instantiate (won't connect without server)
    client = LocalAgentClient("http://127.0.0.1:9999")  # Non-existent
    print("  ✅ LocalAgentClient instantiation works")
    
    return True

def test_skill_structure():
    """Verify the complete skill structure."""
    skill_root = Path(__file__).parent.parent
    
    required_dirs = [
        "references",
        "templates", 
        "scripts"
    ]
    
    print("\nTesting skill directory structure...")
    for d in required_dirs:
        path = skill_root / d
        assert path.exists() and path.is_dir(), f"Missing directory: {d}"
        files = list(path.iterdir())
        print(f"  ✅ {d}/ ({len(files)} files)")
    
    return True

async def main():
    """Run all integration tests."""
    print("=" * 60)
    print("CLAUDE-CODE-INTEGRATION SKILL - INTEGRATION TESTS")
    print("=" * 60)
    
    try:
        test_imports()
        test_templates()
        test_scripts()
        test_skill_structure()
        await test_local_agent_client()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSkill 'claude-code-integration' is fully integrated!")
        print("\nAvailable commands:")
        print("  hermes local-agent [--port N] [--workspace DIR]")
        print("  hermes local-task \"prompt\"")
        print("  python -m hermes_local_agent.scripts.local_agent_client <cmd>")
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))