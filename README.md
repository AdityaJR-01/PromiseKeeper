# PromiseKeeper
Delivery-promise risk simulator built on the Reality Compiler engine, with Hindsight agent memory. 

## Architecture & Hindsight's Role
PromiseKeeper predicts B2B fulfillment timelines. Instead of static rules, it uses Hindsight to recall past fulfillment traces, learning dynamically from SLA breaches, delays, and successful interventions.

## Quick Start
1. Install dependencies: `make install`
2. Start Hindsight local server: `docker run -d -p 8888:8888 ghcr.io/vectorize-io/hindsight:latest`
3. Launch UI: `make ui`
