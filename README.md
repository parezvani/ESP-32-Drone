# ESP-32-Drone / FireFly

FireFly is a student-built drone and ground-station project for fire-risk monitoring in areas without existing sensor coverage. The repository currently contains ESP-IDF firmware prototypes, a simple telemetry server, a Flask/Leaflet map UI, fire-detection experiments, hardware documentation, and a LiteWing reference submodule.

## Repository Layout

- `main/`: source code, firmware experiments, and hardware tests.
  - `groundstation/`: Python Flask base-station — receives GPS telemetry, hosts the Leaflet map UI, proxies the camera feed, and ingests fire detections.
  - `firmware/`: ESP-IDF projects flashed to the on-drone microcontrollers.
    - `gps_telemetry/`: GPS UART reader + WiFi UDP broadcaster.
  - `fire_detect/`: YOLOv8 fire/smoke detection, bearing math, and synthetic drone simulator for offline testing.
  - `scripts/`: ESP-NOW communication and control prototypes.
  - `testing/`: hardware test firmware (motor/PWM, range tests).
  - `lab4_1/`: earlier lab firmware kept for reference.
  - `scrapped/`: older discarded experiments and scratch files (includes the deprecated Rust fire-server and ESP-NOW prototypes).
- `docs/`: project documentation and design artifacts.
  - `design-document/`: design-document source and exported PDFs.
  - `drone-designs/`: frame dimensions, CAD, STL, G-code, and design images.
  - `circuit-design/`: schematics, wiring diagrams, and circuit images.
  - `bill-of-materials/`: bill-of-materials revisions.
  - `status-reports/`: weekly reports and project planning artifacts.
  - `meeting-notes/`: team notes, decisions, and action items.
  - `research-notes/`: reference material gathered during development, including `project_review_findings.md`.
  - `testing_logs/`: prototype testing logs and PDFs.
- `esp/esp-idf/`: local ESP-IDF checkout, when present in the working tree.
- `litewing/LiteWing/`: LiteWing firmware/hardware reference project submodule.
