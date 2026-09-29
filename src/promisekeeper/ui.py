import streamlit as st
from datetime import datetime
from promisekeeper.service import PromiseKeeperService
from promisekeeper.schemas import Scope

st.set_page_config(page_title="PromiseKeeper Hindsight Simulator", layout="wide")
st.title("PromiseKeeper: Delivery-Promise Risk Simulator")

domain_name = st.sidebar.selectbox("Domain", ["fulfillment", "deployment"])
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
    
    with st.spinner("Compiling Reality Engine & Recalling Memories..."):
        sim, recall = svc.simulate_workflow(scope, state)
        
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Decision Output")
        if sim.decision == "allow":
            st.success("✅ Promise Feasible (Allow)")
        elif sim.decision == "review":
            st.warning("⚠️ Review Required")
        else:
            st.error(f"🛑 Blocked: {', '.join(sim.reasons)}")
            
        st.metric(label=f"Predicted {sim.metric_name}", value=f"{sim.total_value} {sim.metric_unit}")
            
    with col2:
        st.subheader("Hindsight Memory Panel")
        st.caption("G3/G4 Requirement: Visible Memories Used")
        if recall.records:
            for rec in recall.records:
                st.info(f"**[{rec.kind}] {rec.id}**: {rec.note}")
        else:
            st.write("No prior memories found for this scope.")
            
        st.subheader("Saved to Memory")
        st.caption("Status: Waiting for trace...")
