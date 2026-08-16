#!/usr/bin/env python3
"""ENI Hermes Controller - Interactive Chat Client"""
import sys
import requests
import json

CONTROLLER_URL = "http://localhost:8940"

def chat(message: str) -> str:
    """Send message to controller /chat endpoint"""
    try:
        resp = requests.post(
            f"{CONTROLLER_URL}/chat",
            json={"message": message},
            timeout=300  # 5 min for long hermes -z runs
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "[ERROR] Controller not reachable at localhost:8940. Is eni-controller.service running?"
    except requests.exceptions.Timeout:
        return "[ERROR] Request timed out (5 min). The hermes -z execution may still be running."
    except Exception as e:
        return f"[ERROR] {e}"

def main():
    print("═══════════════════════════════════════════")
    print("  ENI Hermes Controller — Interactive Chat")
    print("  Type 'exit' or 'quit' to leave")
    print("  Type 'status' for controller status")
    print("═══════════════════════════════════════════\n")
    
    # Quick health check
    try:
        h = requests.get(f"{CONTROLLER_URL}/health", timeout=3)
        if h.json().get("status") != "ok":
            print("[WARN] Controller health check failed")
    except:
        print("[WARN] Could not reach controller at localhost:8940")
    
    print()
    
    while True:
        try:
            user_input = input("LO > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[bye]")
            break
        
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("[bye]")
            break
        if user_input.lower() == "status":
            try:
                s = requests.get(f"{CONTROLLER_URL}/status", timeout=5).json()
                print(f"\n[STATUS] Queue: {s['queue']['pending']} pending | Router: {s['router']['free_router']} | Enterprise: {s['enterprise']['total']} modules\n")
            except Exception as e:
                print(f"[ERROR] {e}\n")
            continue
        
        print("ENI > ", end="", flush=True)
        response = chat(user_input)
        print(response)
        print()

if __name__ == "__main__":
    main()