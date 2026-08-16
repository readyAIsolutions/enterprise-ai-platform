#!/usr/bin/env python3
"""
Verification script for Creed Multiplayer stack.
Run after launching to confirm all components work end-to-end.
"""

import asyncio
import aiohttp
import sys
import json


async def verify_stack(base_url="http://localhost:8765", dash_url="http://localhost:8766"):
    """Run full verification suite."""
    
    async with aiohttp.ClientSession() as session:
        print("🔍 Verifying Creed Multiplayer Stack...")
        print("=" * 50)
        
        # 1. Server health
        print("\n1. Server Health")
        async with session.get(f"{base_url}/health") as resp:
            data = await resp.json()
            assert data["status"] == "ok", f"Health check failed: {data}"
            print(f"   ✓ Server healthy (uptime: {data['uptime']:.1f}s)")
        
        # 2. Clients endpoint
        print("\n2. Clients API")
        async with session.get(f"{base_url}/api/clients") as resp:
            data = await resp.json()
            clients = data.get("clients", [])
            print(f"   ✓ Clients endpoint: {len(clients)} connected")
            for c in clients:
                print(f"      - {c['name']} ({c['client_id']}): {c['status']}, {c['capabilities']['cpu_cores']} cores")
        
        # 3. Submit test task
        print("\n3. Task Submission")
        test_task = {
            "task_id": "verify-1",
            "name": "stack-verification",
            "description": "Verify stack by creating a simple Python script",
            "workdir": "~/creed_work",
            "prompt": "Create a Python script verify.py that prints 'VERIFIED' and the current timestamp. Update STATUS_STACK_VERIFY.md with [DONE] when complete.",
            "model": "free-router",
            "provider": "free-router",
            "required_providers": [],
            "required_tags": [],
            "timeout_seconds": 120,
            "artifacts_expected": ["*.py", "*.md"],
            "metadata": {}
        }
        
        async with session.post(f"{base_url}/api/tasks", json=test_task) as resp:
            data = await resp.json()
            task_id = data.get("task_id")
            assert task_id == "verify-1", f"Task submission failed: {data}"
            print(f"   ✓ Task submitted: {task_id}")
        
        # 4. Wait for completion
        print("\n4. Task Execution (waiting up to 60s)...")
        for _ in range(30):
            await asyncio.sleep(2)
            async with session.get(f"{base_url}/api/tasks") as resp:
                data = await resp.json()
                completed = data.get("completed", [])
                for t in completed:
                    if t.get("task_id") == "verify-1":
                        if t.get("success"):
                            print(f"   ✓ Task completed in {t['duration_seconds']:.1f}s")
                            print(f"      stdout: {t['stdout'][:100]}...")
                        else:
                            print(f"   ✗ Task failed: {t['error']}")
                            return False
                        break
                else:
                    continue
                break
        else:
            print("   ⚠ Task did not complete in time")
            return False
        
        # 5. Dashboard accessibility
        print("\n5. Dashboard")
        async with session.get(dash_url) as resp:
            assert resp.status == 200, "Dashboard not accessible"
            text = await resp.text()
            assert "Demiurge Creed" in text, "Dashboard HTML incorrect"
            print("   ✓ Dashboard serving HTML")
        
        # 6. Dashboard API proxy
        print("\n6. Dashboard API Proxy")
        async with session.get(f"{dash_url}/api/clients") as resp:
            data = await resp.json()
            assert "clients" in data, "Proxy failed"
            print("   ✓ API proxy working")
        
        print("\n" + "=" * 50)
        print("✅ ALL VERIFICATIONS PASSED")
        print("   Stack is fully operational!")
        return True


if __name__ == "__main__":
    try:
        result = asyncio.run(verify_stack())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)