#!/usr/bin/env python3
"""
Sovereign Memory System - CLI Demo
"""
import sys
import argparse
from .integration import SovereignMemoryIntegration

def main():
    parser = argparse.ArgumentParser(description="Sovereign Memory System CLI")
    parser.add_argument("--config", help="Path to MemGPT config file", default=None)
    args = parser.parse_args()

    print("Initializing Sovereign Memory System...")
    sms = SovereignMemoryIntegration(memgpt_config=args.config)
    print("System ready. Type your messages (Ctrl+C to exit).\n")

    user_id = "cli_user"
    try:
        while True:
            user_input = input("> ")
            if user_input.lower() in ("exit", "quit"):
                break
            result = sms.process_input(user_input, user_id=user_id)
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                print(f"SMS: {result['response']}")
                print(f"(Reservoir prediction: {result.get('reservoir_prediction', 'N/A')[:5]}...)")
                print(f"(VSA recalled: {list(result.get('vsa_similarity', {}).keys())[:3]})")
    except KeyboardInterrupt:
        print("\nExiting.")

if __name__ == "__main__":
    main()
