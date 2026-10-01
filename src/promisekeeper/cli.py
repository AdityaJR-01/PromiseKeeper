import argparse
import json
from datetime import date

from .errors import PromiseKeeperError
from .memory import store as local_store
from .schemas import Scope
from .seed import seed_demo
from .service import PromiseKeeperService

def main(argv=None):
    parser = argparse.ArgumentParser(prog="pk", description="PromiseKeeper CLI")
    sub = parser.add_subparsers(dest="command")

    p_reset = sub.add_parser("reset", help="delete local demo memory for one account")
    p_reset.add_argument("--domain", required=True)
    p_reset.add_argument("--tenant", default="pk-demo")
    p_reset.add_argument("--account", default="acct-gold-01")
    p_reset.add_argument("--all-accounts", action="store_true", help="wipe every account in this tenant+domain")
    p_reset.add_argument("--yes", action="store_true")

    p_seed = sub.add_parser("seed", help="load deterministic demo evidence (idempotent)")
    p_seed.add_argument("--tenant", default="pk-demo")
    p_seed.add_argument("--account", default="acct-gold-01")

    p_demo = sub.add_parser("demo", help="simulate a gold EU order against retained memory")
    p_demo.add_argument("--tenant", default="pk-demo")
    p_demo.add_argument("--account", default="acct-gold-01")
    p_demo.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.command == "reset":
            if not args.yes:
                print("Refusing to reset without --yes")
                return 1
            scope = Scope(tenant=args.tenant, domain=args.domain, account=args.account)
            cleared = local_store.reset_scope(scope, all_accounts=args.all_accounts)
            who = "ALL accounts" if args.all_accounts else f"account={args.account}"
            print(f"Cleared local scope '{scope.bank_key()}' ({who}): {cleared}")
            print("Note: Hindsight memories are not deleted; they stop being recalled because "
                  "recall hydrates only from the local store.")
            return 0

        if args.command == "seed":
            scope = Scope(tenant=args.tenant, domain="fulfillment", account=args.account)
            n = seed_demo(scope)
            print(f"Seeded {n} evidence records for {scope.bank_key()} / {args.account} (idempotent).")
            return 0

        if args.command == "demo":
            svc = PromiseKeeperService("fulfillment")
            scope = Scope(tenant=args.tenant, domain="fulfillment", account=args.account)
            state = {"order_value": 6000, "destination_region": "EU", "tier": "gold",
                     "placed_at": date.today().isoformat()}
            sim, recall = svc.simulate_workflow(scope, state)
            payload = {
                "decision": sim.decision, "reachable": sim.reachable, "total_value": sim.total_value,
                "metric_unit": sim.metric_unit, "model_confidence": sim.model_confidence,
                "projected_date": sim.projected_date.isoformat() if sim.projected_date else None,
                "memories_used": len(recall.records), "degraded_recall": recall.degraded,
                "reasons": sim.reasons, "alternatives": sim.alternatives,
            }
            if args.json:
                print(json.dumps(payload))
            else:
                print(f"Demo Run: {sim.decision.upper()} -- {sim.total_value} {sim.metric_unit}")
                for r in sim.reasons:
                    print(f"  reason: {r}")
                for a in sim.alternatives:
                    print(f"  alternative: {a['intervention']} -> {a['total_value']} {sim.metric_unit} ({a['decision']})")
                print(f"Memories recalled: {len(recall.records)} (degraded_recall={recall.degraded})")
                if sim.decision == "insufficient_evidence":
                    print("Hint: run `pk seed` first to load demo evidence.")
            return 0
    except PromiseKeeperError as e:
        print(f"error: {e}")
        return 2

    parser.print_help()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
