import streamlit as st
from datetime import datetime
from pathlib import Path
from promisekeeper.errors import PromiseKeeperError
from promisekeeper.service import DOMAINS_DIR, PromiseKeeperService
from promisekeeper.schemas import Scope

st.set_page_config(page_title="PromiseKeeper Hindsight Simulator", layout="wide")
st.title("PromiseKeeper: Delivery-Promise Risk Simulator")

domain_name = st.sidebar.selectbox("Domain", sorted(p.stem for p in Path(DOMAINS_DIR).glob("*.yaml")))
tenant = st.sidebar.text_input("Tenant ID", "pk-demo")
account = st.sidebar.text_input("Account ID", "acct-gold-01")

st.sidebar.markdown("---")
st.sidebar.header("Current Order State")
order_value = st.sidebar.number_input("Order Value ($)", value=6000)
region = st.sidebar.selectbox("Destination Region", ["EU", "US", "APAC"])
tier = st.sidebar.selectbox("Service Tier", ["gold", "silver", "bronze"])

if st.sidebar.button("Run Simulation"):
    svc = PromiseKeeperService(domain_name)
    scope = Scope(tenant=tenant, domain=domain_name, account=account)
    state = {
        "order_value": order_value, 
        "destination_region": region, 
        "tier": tier,
        "payment_method": "card",
        "placed_at": datetime.now().strftime("%Y-%m-%d")
    }
    
    try:
        with st.spinner("Compiling Reality Engine & Recalling Memories..."):
            sim, recall = svc.simulate_workflow(scope, state)
    except (PromiseKeeperError, ValueError) as e:
        st.error(f"Invalid request: {e}")
        st.stop()
        
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Decision Output")
        if sim.decision == "allow":
            st.success("✅ Promise Feasible (Allow)")
        elif sim.decision == "review":
            st.warning("⚠️ Review Required: " + " ".join(sim.reasons))
        elif sim.decision == "insufficient_evidence":
            st.info("ℹ️ Not enough retained evidence to promise a date yet. " + " ".join(sim.reasons))
        else:
            st.error(f"🛑 Blocked: {', '.join(sim.reasons)}")

        if sim.reachable:
            st.metric(label=f"Predicted {sim.metric_name}", value=f"{sim.total_value} {sim.metric_unit}")
            if sim.projected_date:
                st.caption(f"Projected delivery: {sim.projected_date} (buffered: {sim.projected_date_buffered})")
        for alt in sim.alternatives:
            st.success(f"Alternative: **{alt['intervention']}** -> {alt['total_value']} {sim.metric_unit} ({alt['decision']})")
            
    with col2:
        st.subheader("Hindsight Memory Panel")
        st.caption("G3/G4 Requirement: Visible Memories Used")
        if recall.records:
            for rec in recall.records:
                st.info(f"**[{rec.kind}] {rec.id}** ({rec.occurred_at}): {rec.note or ', '.join(f'{t.from_state}->{t.to_state} {t.value}' for t in rec.transitions)}")
        else:
            st.write("No prior memories found for this scope. Run `python -m promisekeeper.cli seed` to load demo evidence.")
        if recall.degraded:
            st.warning("Degraded recall: Hindsight was requested but unavailable/empty; using the local store.")
            
        st.subheader("Saved to Memory")
        st.caption(f"Simulation id: {sim.simulation_id} (POST /observe with this id to reconcile the real outcome)")
