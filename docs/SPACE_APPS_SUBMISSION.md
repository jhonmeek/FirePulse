# FirePulse — NASA Space Apps Challenge 2026 Submission Kit

Ready-to-paste English submission guide formatted for official **NASA Space Apps Challenge** evaluation (Global Award compliant).

---

## 1. Project Link (Full Public URL)

> Must be a complete `https://...` URL requiring no login, password, or permission.

- **Public GitHub Repository**: `https://github.com/jhonmeek/FirePulse`
- **Live Interactive Web Application** *(verify active public HTTPS host / permanent deployment URL before submitting — do not submit `http://localhost` or an expired temporary tunnel)*.

---

## 2. Project Demonstration (Strictly <= 7 Slides OR <= 30s Video)

> **Eligibility Rule**: Maximum **7 slides total** (including title and introduction) **OR** a video of **30 seconds or less**, hosted publicly (`https://...`) without password, permission request, or login. Do **not** include any NASA logos, flags, or mission identifiers. If any AI-generated visuals or videos are included, add a visible SI/AI watermark; if AI-generated audio is used, disclose it in descriptive text and metadata.

### Option A — 7-Slide Presentation Deck Script

1. **Slide 1 — Title & Intro**:
   - **Title**: *FirePulse — 25 Years of Gabon Fires From Space*
   - **Subtitle**: *Harmonizing MODIS (2000–2025) & VIIRS (2012–2025 archive, 2026 relay prepared) Thermal Hotspots Across Gabon's 9 Provinces.*
   - **Hook**: Comparing raw NASA satellite fire detections before and after 2012 produces an artificial ×4 surge unless sensor physics and persistent heat sources are separated first.

2. **Slide 2 — The Double Trap in Gabon**:
   - **Trap 1 (Camera Resolution Jump)**: MODIS scans at ~1 km; VIIRS (2012+) scans at 375 m. Raw hotspot counts jump ~×3.9 overnight when sensors change, not because fires exploded.
   - **Trap 2 (Persistent Heat Sources)**: Across 285,013 hotspots inside Gabon borders, **38.4% (109,513 detections)** are excluded by the full filter: **20.3% type 2/3** (fixed or offshore sources) + **18.1% type 0 inside 183 candidate `0.05°` cells**. These cells are candidates, not individually confirmed flares.

3. **Slide 3 — How FirePulse Solves It**:
   - **Step 1 · Separate Candidate Persistent Sources**: Isolate type 2/3 detections and **183 candidate `0.05°` cells**, keeping **175,500 type-0 detections outside candidate cells (61.6%)**. Type 0 is a product classification, not field validation.
   - **Step 2 · Align Scales (2012–2019 Overlap)**: Learn a `power-law log1p` relationship during the 8 years both satellites co-observed Gabon.
   - **Step 3 · Explicit Uncertainty**: Quantify prediction spread around reconstructed pre-2012 years.

4. **Slide 4 — Blind Validation (2020–2025)**:
   - Tested strictly out-of-sample across **72 unseen months (2020–2025)** with a frozen pre-test mask (`2000–2019`).
   - Average monthly error drops by **74%** vs the naive baseline (MAE `460.3` → `120.8` detections/month; raw seasonal **R² = 0.918**, anomaly **R² = 0.788**, q80 empirical coverage **63.9%**), accurately reproducing peaks such as **August 2024**.
   - The live database series follows a distinct `v2.0` protocol (all-years mask, MAE `100.9`); the two are not directly comparable without stating which applies.

5. **Slide 5 — Interactive Application Tour (`front-bis/`)**:
   - Scroll-guided 3D Earth (`Three.js`), yearly/monthly filterable charts with separate **MODIS / S-NPP / NOAA-20** views, light-to-dark 25-year fire calendar separating **routine burning vs unusual spikes**, 9-province territory map (`MapLibre GL` + PostgreSQL/PostGIS) with automatic regional **EN / FR** language detection, and a confidence note stating what each result can and cannot conclude.
   - **2026–2035 forest-fire outlook**: province-filtered future calendar, `0.25°` probability map, floating detail card on hover/click, and a validation/calibration note. Climatological projection—not a weather forecast.

6. **Slide 6 — Continuity Beyond 2026 (Suomi-NPP → NOAA-20)**:
   - Reference sensor **VIIRS Suomi-NPP** operational delivery **ended on November 2, 2026**.
   - **VIIRS NOAA-20** has observed Gabon alongside it since 2018 (held-out ratio `0.940`, ~`6.0%` average calibration gap). The relay is **prepared but not yet validated on 2026 data**; the demo archive stops in December 2025.

7. **Slide 7 — Impact, Tech Stack & AI / SI Disclosure**:
   - **Impact**: Equips Gabonese forestry managers, conservation teams, and researchers with cleaner, documented fire baselines — and explicit limits — plus a calibrated 2026–2035 forest-fire outlook for planning across Gabon and the wider Congo Basin.
   - **Stack**: Vue 3, TypeScript, Vite, Three.js, MapLibre GL, GSAP, Python, Django REST Framework, PostgreSQL 16 + PostGIS 3.4.
   - **AI / SI Disclosure**: Code architecture, data pipeline structuring, UI/UX localization, and bilingual copy were assisted by AI models (**Gemini 4 Hydrogen, Gemini 4 Argon, Deepseek 4.1 Flash 1017, Claude Opus 5.5, GPT 6 Luna, and GPT 6 Terra**); all hotspot data originate authentically from NASA FIRMS (no NASA logos/insignias used).

---

### Option B — 30-Second Video Script (Live Screen Recording)

- **0:00–0:07 (Hero & 3D Globe)**: *"Raw NASA fire counts in Gabon jump nearly 4× in 2012—not because forests burned 4× more, but because VIIRS replaced MODIS at sharper resolution."*
- **0:07–0:15 (Persistent Sources + Alignment Charts)**: *"Plus, 38.4% are excluded by the full filter: type 2/3 sources and type-0 detections inside 183 candidate cells. FirePulse separates those candidates and aligns 25 years onto a single scale."*
- **0:15–0:23 (Calendar + 9-Province Map + Outlook)**: *"Blind-tested on 2020–2025 with 74% less error, it delivers an interactive fire calendar, a 9-province map, and a 2026–2035 forest-fire outlook."*
- **0:23–0:30 (Post-2026 Bridge + End Card)**: *"S-NPP stopped on November 2, 2026. The NOAA-20 bridge is calibrated and prepared; 2026 validation is the next step—turning 25 years of raw heat alerts into clear, honest climate insight."*

---

## 3. Project Details (Copy-Paste Form Answers)

**What does it do and how does it work?**  
FirePulse resolves the multi-sensor continuity break between **NASA FIRMS MODIS Collection 6.1 (~1 km resolution, 2000–2025)** and **VIIRS Suomi-NPP / NOAA-20 (375 m resolution, 2012–2025 archive)** over **Gabon and its 9 provinces**. Raw comparisons mislead for two reasons: (1) switching from MODIS to VIIRS in 2012 produces an artificial ~×3.9 jump in detection counts, and (2) **38.4% (109,513 out of 285,013)** are excluded by the full filter: **20.3% type 2/3** (fixed or offshore sources) plus **18.1% type-0 detections inside 183 candidate `0.05°` cells**. FirePulse separates those candidates, calibrates MODIS onto the VIIRS scale over the 2012–2019 overlap using a `power-law log1p` model, blind-tests performance across 72 unseen months (2020–2025), and prepares the post-2026 NOAA-20 relay. The reinforced validation reports MAE **460.3 → 120.8**, raw seasonal R² **0.918**, anomaly R² **0.788**, and q80 empirical coverage **63.9%**; the live database series follows a distinct `v2.0` protocol (all-years mask, MAE 100.9). Users explore the dataset through a scroll-driven 3D Earth, switchable yearly/monthly charts, an inverted light-to-dark 25-year seasonal calendar (distinguishing routine burning from abnormal surges), a 9-province interactive map backed by PostgreSQL/PostGIS, automatic regional English/French detection, and a confidence note stating what the data can and cannot conclude. A separate MVP outlook estimates a monthly forest-fire probability per `0.25°` cell for `2026–2035`, with a province filter, a future calendar, a probability map, and validation/calibration limits.

**What are its benefits and intended impact?**  
Without harmonization, park rangers, researchers, and policymakers risk mistaking a satellite camera upgrade for ecological collapse—or confusing persistent coastal heat sources with wildfire seasons. FirePulse delivers a documented, accessible 25-year detection baseline tailored to Gabon (main dry season July–August, short dry season February–March, anomaly surges such as August 2024), with explicit limits. It is ready to scale across the Congo Basin; the Suomi-NPP → NOAA-20 relay is prepared, with 2026 validation still pending.

**What tools, programming languages, hardware, or software did you use?**  
- **Frontend (`front-bis/`)**: Vue 3, TypeScript, Vite, Three.js (3D Earth), MapLibre GL (9-province map), GSAP ScrollTrigger, automatic regional geolocation/timezone detection (`EN / FR`).  
- **Backend & Geo-Database (`backend/`)**: Python, Django, Django REST Framework, PostgreSQL 16 + PostGIS 3.4, Docker Compose, Gunicorn/Caddy support, verified offline JSON fallback snapshots.  
- **Data Science (`pipeline/`)**: Python 3.10+, standard library ETL audit/normalization modules, SciPy/NumPy/Pandas, out-of-sample validation scripts over `292,589` total FIRMS detections.

**How is your project creative, and what factors did the team consider?**  
Instead of presenting dense regression tables, FirePulse turns satellite harmonization physics into immediate visual clarity—contrasting coastal blue candidate cells against type-0 detection grids, using an intuitive light-to-dark heat calendar, and guiding readers from a 3D Earth down into Gabon's 9 provinces. Factors considered included preventing look-ahead leakage (validating against a frozen 2000–2019 candidate-source mask), clearly stating what thermal detections cannot measure under heavy Congo Basin cloud cover, documenting the 2026 Suomi-NPP → NOAA-20 handoff as prepared but not yet validated, and automatically matching English or French to the viewer's region.

---

## 4. Use of Super Intelligence (SI / AI) — Checklist & Disclosure

- **Form selections**: Check the options for **Code / Data Processing** and **Text / Documentation** (do **not** select *"I did not use SI"*). Only check **Images / Video** or **Audio** if you generate AI visuals (which require a visible SI watermark) or AI voiceovers (which require disclosure in description & metadata) for your external presentation.
- **Mandatory Disclosure Text**:
  > *"Super Intelligence / AI models (**Gemini 4 Hydrogen, Gemini 4 Argon, Deepseek 4.1 Flash 1017, Claude Opus 5.5, GPT 6 Luna, and GPT 6 Terra**) were used to accelerate software engineering, data harmonization pipeline structuring (`pipeline/` & `backend/`), interactive frontend development (`front-bis/`), and English/French localization and documentation. All thermal hotspot records (292,589 detections) originate strictly from authentic public NASA FIRMS MODIS C6.1 and VIIRS archives; zero synthetic detections or NASA branded logos/insignias were generated or used."*
