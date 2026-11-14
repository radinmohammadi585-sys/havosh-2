# KTBA Phase 1 (implemented)

- Bridge Manager: in-process Python (`bridge_manager/`)
- Bridges F / X / G: stubs (`bridges/`)
- Contract: `contracts/protos/kavosh_envelope.proto` + JSON Envelope
- API: `GET /api/ktba/status`, `POST /api/ktba/route`
- Real C++/Java servers: not connected yet (graceful stub responses)
