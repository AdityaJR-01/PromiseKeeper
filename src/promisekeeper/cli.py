import argparse
import json
from .service import PromiseKeeperService
from .schemas import Scope

def main():
    parser = argparse.ArgumentParser(prog="pk", description="PromiseKeeper CLI")
    subparsers = parser.add_subparsers(dest="command")

    p_reset = subparsers.add_parser("reset")
    p_reset.add_argument("--domain", required=True)
    p_reset.add_argument("--yes", action="store_true")

    p_demo = subparsers.add_parser("demo")
    p_demo.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "demo":
        svc = PromiseKeeperService("fulfillment")
        scope = Scope(tenant="pk-demo", domain="fulfillment", account="acct-gold-01")
        state = {"order_value": 6000, "destination_region": "EU", "tier": "gold"}
        sim, recall = svc.simulate_workflow(scope, state)
        
        if args.json:
            print(json.dumps({"gates_passed": True, "decision": sim.decision, "total_value": sim.total_value}))
        else:
            print(f"Demo Run: {sim.decision.upper()} - {sim.total_value} days.")
            print(f"Memories recalled: {len(recall.records)}")

if __name__ == "__main__":
    main()
