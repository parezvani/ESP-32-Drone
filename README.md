# ESP-32-Drone / FireFly
FireFly is a student-built drone and ground-station project for fire-risk monitoring in areas without existing sensor coverage. The repository currently contains ESP-IDF firmware prototypes, a simple telemetry server, a Flask/Leaflet map UI, fire-detection experiments, hardware documentation, and a LiteWing reference submodule.

## Repository Layout
- `main/scripts/`: ESP-NOW control prototypes and the shared `ESPNowEasy` helper.
- `main/base-server/fire-server/`: Rust TCP server and test client for the FireFly telemetry payload.
- `main/base-server/espnow_drone_sender/`: ESP-IDF drone-side telemetry sender.
- `main/base-server/espnow_drone_base_server/`: ESP-IDF base-station ESP-NOW receiver and LiteWing command test bridge.
- `main/map-ui/`: Flask/Leaflet map UI plus a drone/fire simulator.
- `main/fire_detect/`: camera/video fire-detection prototypes.
- `main/read_pos_data/`: ESP-IDF GPS reader that broadcasts position JSON over UDP.
- `main/testing/`: hardware test firmware, including motor/PWM testing.
- `main/lab4_1/` and `main/scrapped/`: older lab/reference code and discarded experiments.
- `docs/`: design documents, CAD/frame work, schematics, bills of materials, status reports, research notes, and meeting notes.
- `esp/esp-idf/`: local ESP-IDF checkout, when present in the working tree.
- `litewing/LiteWing/`: LiteWing firmware/hardware reference project submodule.

## Documentation
- `docs/design-document/`: design-document source and exported PDFs.
- `docs/drone-designs/`: frame dimensions, CAD, STL, G-code, and design images.
- `docs/circuit-design/`: schematics, wiring diagrams, and circuit images.
- `docs/bill-of-materials/`: bill-of-materials revisions.
- `docs/status-reports/`: weekly reports and project planning artifacts.
- `docs/research-notes/project_review_findings.md`: source review notes and known integration risks.
