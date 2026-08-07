# TUYA IoT — Deep-Dive for Agroverse Farm Monitoring

**Prepared for TrueSight DAO / Agroverse** — partner research following the office visit with Erica.

> **Name note:** "Tuyao" (as heard) maps to **Tuya Inc. (Tuya Smart)** — tuya.com. No company spelled exactly "Tuyao" exists; Tuya is the only IoT-sensor + application-platform match. Confirm spelling with Erica at first touch.

---

## 1. Executive Summary

- **Tuya** is a global **AI + IoT developer platform** (founded 2014, Hangzhou; NYSE: TUYA / HKEX: 2391; ~US$302M revenue 2021; 1,000–5,000 employees).
- It provides **IoT Core** (connect & manage hundreds of millions of devices), **TuyaOS** (device firmware), **App SDK / OEM App** (build your own app), and cloud services: **data analytics, data visualization, SaaS development framework, device logs**.
- Sensor ecosystem spans **soil moisture/temperature, weather, water quality, pest sensors, cameras, gateways** — with **LoRa / Sub-1GHz** long-range options for remote fields.
- Agriculture line: **"M0L0, powered by Tuya"** smart-agriculture solution (LoRa soil/water/pest monitoring, edge gateway, cloud backend).
- **Relevance to Agroverse:** continuous **soil-quality time-series** on partner farms and **biodiversity monitoring** as we restore forest — both map cleanly onto Tuya's sensor + cloud + app platform.
- **Mission tie-back:** every hectare monitored with real data strengthens the path to **10,000 hectares of restored Amazon rainforest**.

---

## 2. Who Is Tuya?

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

Tuya is **not an agtech company** — it is an **IoT PaaS** that powers thousands of brands and OEMs. That means Agroverse would use Tuya's platform + third-party Tuya-compatible sensors, rather than buying a finished farm system. That is an advantage (open ecosystem) and a caveat (you assemble the stack).

---

## 3. The Application Programming Platform

- **IoT Core (PaaS):** full-lifecycle device management at scale — onboarding, OTA updates, real-time monitoring, remote control.
- **TuyaOS / TuyaOpen:** open device SDK (C/C++), MCU & SoC targets (Tuya T-series, ESP32, Raspberry Pi, Rockchip) — build custom sensor firmware.
- **App SDK / OEM App / Smart MiniApp:** ship your own branded farmer app without building one from scratch.
- **Cloud development:** device logs, data analytics, data visualization, real-time voice/video, SaaS development framework, open API reference.
- **Protocols:** Wi-Fi, Zigbee, Bluetooth, Thread, Sub-1GHz, LoRa (via gateway), NB-IoT, LTE, GPRS.

**Bottom line:** Agroverse can connect sensors → Tuya cloud → custom dashboards/app with very little infra to build ourselves.

---

## 4. Sensor Ecosystem (relevant classes)

| Sensor class | What it measures | Relevance |
|---|---|---|
| Soil moisture + temperature | Water content, soil temp | Core soil-quality time series |
| Soil NPK / EC / pH probes | Nutrients, conductivity, acidity | Soil fertility over seasons |
| Weather stations | Temp, humidity, rainfall, wind | Microclimate per zone |
| Water quality / level | Tanks, wells, reservoirs | Farm water security |
| Cameras / visual | Visual monitoring, timelapse | Canopy growth, wildlife |
| Pest / smart-agriculture sensors | Pest pressure, irrigation | Crop health |

Long-range **LoRa / Sub-1GHz** variants matter for the Amazon: low power, several km per node, works far from cellular coverage.

---

## 5. Smart Agriculture Line (M0L0, Powered by Tuya)

- Collects & analyzes **field data in real time**; deploy command mechanisms (irrigation, etc.).
- **Digital monitoring** via wireless sensors: **soil moisture, water quality, pests**.
- **Edge gateway** — local device management, reduced cloud traffic & latency (important in remote areas).
- **Cloud-based backend** for production planning, park inspection, supervision.
- **One-stop open APIs** to integrate with internal systems.

---

## 6. Relevance to Agroverse — Three Use Cases

### 6.1 Soil quality over time (farm monitoring)
- Deploy soil moisture/temp + NPK/pH probes at Oscar's Farm (Bahia) & Paulo's Farm (Pará).
- Log continuous time series to Tuya cloud; build a dashboard tracking recovery of degraded pasture → cacao agroforestry.
- LoRa nodes + gateway where cellular is weak; solar/battery powered for multi-year unattended operation.

### 6.2 Biodiversity monitoring as we restore the forest
- As land is repopulated with trees, track **canopy/timelapse cameras**, **acoustic sensors** (birds/mammals), **weather stations**, **soil recovery**.
- Tuya's platform handles device fleets + data pipelines; species-identification analytics sits on top (we can build or integrate with the data layer).
- Baseline today → measurable biodiversity uplift year-over-year = credible proof for partners, funders, and the DAO ledger.

### 6.3 Reforestation / tree-planting traceability
- Per-zone sensor data links to our **QR lineage** and **TrueChain** records — sensor-verified planting conditions per tree/bag.
- Strengthens the mission story: "every bag sold plants a tree, and we measure the land recovering."

---

## 7. Fit with Agroverse Stack

- **QR lineage (lineage-credentials / lineage-assets):** sensor data adds an environmental evidence layer to each provenance record.
- **TrueChain (PoA notarization):** anchor periodic soil/biodiversity snapshots as notarized records.
- **DApp / truesight.me dashboard:** farm monitoring charts enrich the public "origin & restoration" surface.
- **Attention surfaces:** turns "Origin & Restoration" from narrative into **measured data** — the strongest possible mission signal.

---

## 8. Gaps, Risks & Considerations

| Area | Consideration |
|---|---|
| Name/spelling | Confirm "Tuya" vs "Tuyao" with Erica; verify what her company actually resells/builds |
| Assembly needed | Tuya = platform, not turnkey ag solution — we pick sensors/gateways, possibly via a local partner (e.g. M0L0, Landatel, Nova Digital in Brazil) |
| Connectivity | Amazon farms may lack cellular — plan LoRa + edge gateway + periodic data sync |
| Biodiversity sensors | Bioacoustic (AudioMoth-class) & camera traps are niche; likely need custom firmware via TuyaOS or a companion stack |
| Data ownership | Confirm data export, on-prem/private-cloud option (Cube Private Cloud) for sovereignty |
| Cost | Per-hectare cost is low (~BRL 1/ha for some platforms) but hardware + gateways are the real budget line |
| Security | ISO 27001 + SOC 3 present; still review data residency for Brazilian farm data |

---

## 9. Recommended Pilot + Next Steps

1. **Confirm identity & scope with Erica** — name spelling, what her company sells (reseller? integrator? platform?), Brazil presence, reference ag deployments.
2. **Pick 1 pilot farm** (suggest Oscar's Farm, Bahia) and deploy: 3–5 soil probes + 1 weather station + 1 gateway (LoRa) + solar/battery.
3. **Define 12-month data plan:** soil moisture/temp/pH/NPK, rainfall, timelapse, acoustic sampling.
4. **Build the dashboard** on Tuya cloud; export snapshots to DAO ledger (QR lineage + TrueChain notarization).
5. **Baseline biodiversity index** at year 0, measure annually → publish as mission proof.
6. **Cost the pilot** (hardware + gateway + platform fees) and bring to DAO for budget approval.

---

## 10. Questions to Ask Erica's Company

- Is the platform **Tuya** (tuya.com) and what is your exact role — OEM, reseller, integrator, or solution provider?
- Do you have **deployed agriculture/IoT references in Brazil** (especially Amazon/Bahia/Pará)?
- Sensor price list & lead times for: soil moisture/temp, NPK/pH, weather station, LoRa gateway, camera.
- Connectivity options for **off-grid farms** (LoRa range, solar power, data sync frequency).
- Data ownership, export, and **private-cloud option**.
- Timeline & minimum order to pilot on one farm.

---

## 11. Sources

- tuya.com — platform pages (IoT Core, TuyaOS, App SDK, SaaS framework, Cube Private Cloud)
- Gartner Peer Insights — Tuya IoT Platform
- Alibaba Cloud marketplace — Tuya IoT
- Wikipedia — Tuya Inc.
- Landatel — "M0L0, powered by Tuya" Smart Agriculture (LoRaWAN)
- CSA STAR Registry — Tuya IoT Platform
- Tuya SOC 3 Report (FY22)

---

*Prepared by Sophia Truesight (TrueSight DAO Autopilot) — research deliverable for governor review. Mission: restore 10,000 hectares of Amazon rainforest.*
