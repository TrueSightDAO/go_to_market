# Agroverse Farm Monitoring — Deep-Dive (Radio Data Acquisition)

**Prepared for TrueSight DAO / Agroverse** — field research with Erica & Gianluca (office visit) and SunMint farmer partners.

> **Name note:** the platform we discussed (heard as “Tuyao”) is **Tuya Inc. (Tuya Smart)** — tuya.com, confirmed by the office photo. This report is vendor-neutral: it leads with the radio data-acquisition architecture and treats Tuya as one reference platform option.

---

## 1. Executive Summary

- **The problem:** partner farms in the Amazon (Bahia, Pará) are off-grid — no reliable internet at the edge, and cellular/satellite links degrade first in storms. Internet-dependent IoT is the wrong model.
- **The architecture:** **radio data acquisition** — sensors log locally on RF dataloggers (LoRa / sub-GHz / VHF-UHF); a **car or drone data mule** harvests the data store-and-forward; solar + battery powers nodes for years. Storm-resilient, zero data loss, no internet required.
- **The data we get:** continuous **soil-quality time-series**, **weather**, **biodiversity** (as we restore forest), **bean quality × environment** correlation, and **tree health/survival** for the SunMint planting program.
- **The platform layer:** storage, dashboards and analytics can run on **Tuya** (a reference option — strong app platform, M0L0 agriculture line) or on our own open stack. The radio edge works with either.
- **Mission tie-back:** every hectare measured with real data strengthens the path to **10,000 hectares of restored Amazon rainforest**.

---

## 2. The Problem — Off-Grid Farms in the Amazon

- Partner farms (Oscar's, Bahia; Paulo's, Pará) have **no reliable internet**. IoT as commonly understood assumes cloud connectivity at the edge.
- Storms are the worst case: heavy rain and wind degrade **cellular and satellite links first** — exactly when you need data.
- We need **continuous environmental data** — soil, weather, biodiversity, tree health — to prove restoration and premium quality.
- Conclusion: adopt **radio data acquisition** (RF telemetry + local dataloggers + data mules), not IoT. Install it in the car or on drones to acquire data in the field.

---

## 3. Radio Data Acquisition Architecture (the right transport)

*Contribution from Gianluca (office visit): radio transmission works well on the farm.*

- **Sensors stay local.** Soil moisture/temp, NPK/pH, weather, and water-quality probes connect by wire or short-range RF to a **field datalogger / RF node** (LoRa, sub-GHz, or VHF/UHF telemetry).
- **Radio is the backbone.** RF links (LoRa/sub-GHz: several km per hop, low power; VHF/UHF: long range, more storm-tolerant than cellular) carry data from nodes to a **local gateway/base station** at the farm house or village. No internet required at any hop.
- **Data mules for collection.** Where no fixed gateway covers a zone:
  - **Car mule** — a vehicle-mounted radio/gateway (or laptop + SDR) drives through or near the farm and automatically harvests data from nodes in range (store-and-forward).
  - **Drone mule** — a drone with a LoRa/RF transceiver flies a route over the farm and downloads data from ground nodes (validated for remote no-infrastructure areas; LoRa-UAV data collection is an active, well-documented field).
- **Store-and-forward sync.** Nodes buffer data locally (SD card / flash); when a mule or an uplink appears (village Wi-Fi, satellite terminal, periodic 4G), data syncs to the cloud — our analytics or a platform — with gaps preserved and timestamped.
- **Storm resilience.** Radio links (especially VHF/UHF and LoRa spread-spectrum) hold up through heavy rain and storms far better than cellular/satellite; local storage means zero data loss even if links drop for days.
- **Energy.** Nodes run solar + battery, multi-year unattended; radio + low-power MCU keeps the power budget tiny.

**Where a platform fits:** the cloud/analytics/App layer ingests data only when a mule or uplink syncs it. The radio edge is vendor-neutral and works with any platform.

---

## 4. Sensor Classes We Need

| Sensor class | What it measures | Relevance |
|---|---|---|
| Soil moisture + temperature | Water content, soil temp | Core soil-quality time series |
| Soil NPK / EC / pH probes | Nutrients, conductivity, acidity | Soil fertility over seasons |
| Weather stations | Temp, humidity, rainfall, wind | Microclimate per zone |
| Water quality / level | Tanks, wells, reservoirs | Farm water security |
| Cameras / visual | Visual monitoring, timelapse | Canopy growth, wildlife |
| Bioacoustic / camera traps | Species presence, activity | Biodiversity index |
| Pest sensors | Pest pressure, irrigation | Crop health |

Long-range **LoRa / Sub-1GHz** variants matter for the Amazon: low power, several km per node, works far from cellular coverage. **VHF/UHF telemetry** is the strongest in heavy-rain conditions.

---

## 5. Data Platform Layer — Options

**Requirements:** time-series storage, dashboards, APIs/webhooks to join sensor data to QC records, data export and ownership.

- **Option A — Tuya (reference platform):** fast to start, huge open ecosystem of Tuya-compatible sensors, App SDK to ship a branded farmer app, M0L0 smart-agriculture line, LoRa edge gateway. Caveat: it is a platform, not a turnkey farm system — we assemble the stack.
- **Option B — Open stack:** InfluxDB/PostgreSQL time-series + Grafana dashboards + our own APIs. Full control, data sovereignty, no vendor lock-in; we build more.
- **Option C — Local integrator:** a Brazilian ag-tech partner (e.g. Landatel, Nova Digital) assembles sensors + gateways + data mule, possibly powered by a platform like Tuya.

**Recommendation:** pick the option that lets us pilot fastest on one farm (likely Tuya or a local integrator); keep data export open so we can switch or run our own analytics.

---
## 6. Reference Platform Option — Tuya

### 6.1 Who is Tuya

| Attribute | Detail |
|---|---|
| Legal name | Tuya Inc. (Hangzhou Tuya Information Technology Co., Ltd.) |
| Founded | June 16, 2014 — Hangzhou, China |
| Founder | Xueji (Jerry) Wan |
| Listing | NYSE: TUYA; SEHK: 2391 |
| Scale | ~1.97M+ registered developers, 3,000+ product categories, 200+ countries |
| Revenue | US$302M (2021) |
| Certifications | ISO/IEC 27001, ISO 27017/27701, SOC 3, CSA STAR Level 1 |
| Cloud | AWS, Azure, Tencent Cloud — 6 global clusters |

Tuya is **not an agtech company** — it is an **IoT PaaS** powering thousands of brands and OEMs. We would use the platform + third-party Tuya-compatible sensors rather than a finished farm system. Advantage: open ecosystem. Caveat: we assemble the stack.

### 6.2 Application platform

- **IoT Core (PaaS):** full-lifecycle device management at scale — onboarding, OTA updates, real-time monitoring, remote control.
- **TuyaOS / TuyaOpen:** open device SDK (C/C++), MCU & SoC targets (Tuya T-series, ESP32, Raspberry Pi, Rockchip) — build custom sensor firmware.
- **App SDK / OEM App / Smart MiniApp:** ship a branded farmer app without building from scratch.
- **Cloud development:** device logs, data analytics, data visualization, real-time voice/video, SaaS development framework, open API reference.
- **Protocols:** Wi-Fi, Zigbee, Bluetooth, Thread, Sub-1GHz, LoRa (via gateway), NB-IoT, LTE, GPRS.

**Bottom line:** we can connect sensors → a platform cloud → custom dashboards/app with very little infra built ourselves.

### 6.3 M0L0 smart-agriculture line (powered by Tuya)

- Collects & analyzes **field data in real time**; deploy command mechanisms (irrigation, etc.).
- **Digital monitoring** via wireless sensors: **soil moisture, water quality, pests**.
- **Edge gateway** — local device management, reduced cloud traffic & latency (important in remote areas).
- **Cloud-based backend** for production planning, park inspection, supervision.
- **One-stop open APIs** to integrate with internal systems.

---

## 7. Agroverse Use Cases

### 7.1 Soil quality over time (farm monitoring)

- Deploy soil moisture/temp + NPK/pH probes at Oscar's Farm (Bahia) & Paulo's Farm (Pará).
- Log continuous time series **locally on RF dataloggers**; sync to a platform cloud **store-and-forward via car/drone data mules**; build a dashboard tracking recovery of degraded pasture → cacao agroforestry.
- RF nodes (LoRa/sub-GHz) + local gateway + **car/drone data-mule collection** where cellular is weak or absent; solar/battery powered for multi-year unattended operation. No on-farm internet required.

### 7.2 Biodiversity monitoring as we restore the forest

- Baseline at year 0, measure annually: tree species diversity, animal/bird presence via bioacoustic + camera traps.
- Acoustic monitoring (AudioMoth-class) is proven in rainforest settings; log audio locally, harvest by data mule, analyze offline.
- Publish a **biodiversity index** per plot over time — the restoration story, measured.

### 7.3 Bean Quality × Environment interface

- The science: rainfall, max temperature and wind during the season measurably affect fermentation and flavor (PMC11353615 — nine agroclimatic clusters; nuttiness rises with higher max temp/wind; fruitiness drops after ~120h fermentation).
- Fermentation outcome is temperature- and humidity-sensitive (ideal ~45–50°C, high humidity) — so ambient + soil data directly inform when to stop fermentation (96h vs 120h).
- Cut-test grade (slaty/violet/brown) predicts free amino acid + polyphenol profiles — i.e. the chemistry that drives chocolate flavor (PMC6525676).

### 7.4 Agroverse application of bean quality

- Per-zone environmental fingerprint + per-batch quality grade attached to each bag's **QR lineage** → TrueChain notarization. “This bag's beans: zone B, soil moisture X, rain Y, fermented 96h, 85% brown — premium.”
- Seasonal learning: “zone with soil moisture < threshold during pod-fill yields +15% brown ratio” → guide irrigation/planting.
- Premium justification with data; identify microzones that command premium pricing on Oscar's (Bahia) and Paulo's (Pará) farms.
- QC workflow: farmer/post-harvest team photographs cut-test beans via a lightweight app (or lab form); batch QR links photos + scores to the sensor window. A platform cloud holds the time-series; our ledger holds the joined record.

### 7.5 Data schema (per batch)

| Field | Source |
|---|---|
| batch_id / QR | ledger |
| farm / zone | ledger |
| harvest date | QC form |
| fermentation duration | QC form (h) |
| cut-test % brown / violet / slaty | QC photo + form |
| fermentation index | computed |
| bean count / 100g, moisture % | QC form |
| flavor notes | taster |
| soil window (moisture/temp/pH/NPK means) | platform cloud (auto) |
| weather window (rain/temp/hum/wind) | platform cloud (auto) |
| quality grade (A/B/C) | computed |

---
### 7.6 Tree Health & Survival Monitoring (SunMint tie-in)

The same store-and-forward philosophy already powers the **SunMint farmer app** (offline queue + flush). Tree health monitoring layers on top of both — manual check-ins today, sensor-backed cross-checks as the RF layer deploys.

**Tier 1 — simple offline interface (ship first, no new hardware):**
- The farmer app already captures plantings offline (sign at capture, queue in IndexedDB, flush when signal returns).
- **Extend it with periodic health check-ins:** photo of the tree + survival status (healthy / struggling / dead) + optional GPS. Same offline queue, one tap in the field.
- Manual baseline: cheap, human-verified, starts this season.

**Tier 2 — radio/RF + data-mule (autonomous layer, Gianluca's approach):**
- Low-cost sensors co-located with trees or per plot: soil moisture/temp, a few weather nodes, time-lapse/acoustic for canopy + biodiversity.
- Data logs locally on RF dataloggers; a car or drone data mule harvests it store-and-forward.
- Sensors cross-check the farmer's check-ins: “healthy” + sensor agreement = strong proof; “healthy” + collapsed soil moisture = flag for a visit. That is credible MRV, not self-report.

**Tier 3 — the ledger link (the payoff):**
- Each tree already has a QR / lineage record. Attach survival events (check-in, sensor snapshot) to that tree's lineage → TrueChain notarization.
- Survival rate per cohort/plot becomes a measurable, auditable metric — exactly what carbon methodology (Verra VM0017 / ARR) requires: survival thresholds, 30-year monitoring.

**Recommendation:** do not wait for sensors. The offline check-in extension reuses the existing IndexedDB queue pattern and yields survival data this season; the RF layer adds autonomous cross-validation when hardware deploys.

---

## 8. Fit with Agroverse Stack

- **QR lineage (lineage-credentials / lineage-assets):** sensor data adds an environmental evidence layer to each provenance record.
- **TrueChain (PoA notarization):** anchor periodic soil/biodiversity/quality snapshots as notarized records.
- **DApp / truesight.me dashboard:** farm monitoring charts enrich the public “origin & restoration” surface.
- **Attention surfaces:** turns “Origin & Restoration” from narrative into **measured data** — the strongest possible mission signal.

---

## 9. Gaps, Risks & Considerations

| Area | Consideration |
|---|---|
| Name/spelling | Confirmed Tuya via office photo; verify what Erica's company actually resells/builds |
| Assembly needed | Platform = not turnkey ag solution — we pick sensors/gateways, possibly via a local partner (e.g. M0L0, Landatel, Nova Digital in Brazil) |
| Connectivity | Amazon farms may lack cellular — plan LoRa + edge gateway + periodic data sync (data mule) |
| Biodiversity sensors | Bioacoustic (AudioMoth-class) & camera traps are niche; likely need custom firmware or a companion stack |
| Data ownership | Confirm data export, on-prem/private-cloud option for sovereignty |
| Cost | Per-hectare cost is low (~BRL 1/ha for some platforms) but hardware + gateways are the real budget line |
| Security | Review data residency for Brazilian farm data |
| QC consistency | Cut-test scoring needs a standard protocol + photo record so batch grades are comparable across farms and seasons |

---

## 10. Recommended Pilot + Next Steps

1. **Confirm scope with Erica** — what her company sells (reseller? integrator? platform?), Brazil presence, reference ag deployments.
2. **Pick 1 pilot farm** (suggest Oscar's Farm, Bahia) and deploy: 3–5 soil probes + 1 weather station + 1 RF datalogger/gateway (LoRa/sub-GHz) + solar/battery + **car/drone data-mule pickup**.
3. **Define 12-month data plan:** soil moisture/temp/pH/NPK, rainfall, timelapse, acoustic sampling + **cut-test QC per batch**.
4. **Build the dashboard** (on a platform or our own stack); export snapshots to DAO ledger (QR lineage + TrueChain notarization).
5. **Baseline biodiversity index** at year 0, measure annually → publish as mission proof.
6. **Cost the pilot** (hardware + gateway + platform fees) and bring to DAO for budget approval.
7. **Hand to Jerry (team):** review the bean-quality × environment schema (§7.5) and decide the QC app / data pipeline approach.

---

## 11. Questions to Ask Erica's Company

- Is the platform **Tuya** (tuya.com) and what is your exact role — OEM, reseller, integrator, or solution provider?
- Do you have **deployed agriculture/IoT references in Brazil** (especially Amazon/Bahia/Pará)?
- Sensor price list & lead times for: soil moisture/temp, NPK/pH, weather station, LoRa gateway, camera.
- Connectivity options for **off-grid farms** (LoRa range, solar power, data sync frequency).
- **Offline / data-mule compatibility:** can your sensors log locally and sync via car or drone pickup with no internet at the farm?
- **Storm resilience:** which radio links (LoRa/sub-GHz/VHF-UHF) are proven in heavy-rain Amazon conditions?
- Data ownership, export, and **private-cloud option**.
- Timeline & minimum order to pilot on one farm.
- Can the platform expose **time-series APIs / webhooks** so we can join sensor data to our QC records?

---

## 12. Sources

- tuya.com — platform pages (IoT Core, TuyaOS, App SDK, SaaS framework, Cube Private Cloud)
- Gartner Peer Insights — Tuya IoT Platform
- Alibaba Cloud marketplace — Tuya IoT
- Wikipedia — Tuya Inc.
- Landatel — “M0L0, powered by Tuya” Smart Agriculture (LoRaWAN)
- CSA STAR Registry — Tuya IoT Platform
- Tuya SOC 3 Report (FY22)
- PMC11353615 — Fermentation time & climate vs quality (sensorial profile, volatilome)
- PMC6525676 — Cut-test grade vs amino acids & polyphenols
- MDPI Future Internet — Data Collection in Area Coverage (UAV/drone data mule for remote sensing)
