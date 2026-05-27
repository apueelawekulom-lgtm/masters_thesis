---
output:
  pdf_document: default
  html_document: default
---
# GVC Chain Position Measure — Project Plan

## 1. Research Objective

Construct a product-level GVC chain position measure at the HS6 level using natural language processing and a layered enrichment architecture. The measure captures **downstreamness** — how much industrial transformation a product has already undergone — recoverable from product description text alone. Upstreamness signal (how many further production steps remain) is added through successive data layers.

**Output:** A scored dataset of HS6 products with a chain position class, continuous score, and uncertainty measure — covering the full HS6 universe across all major revisions (1992–2022).

**Primary contribution:** Recovering within-sector heterogeneity in chain position that sector-level I-O approaches cannot see by construction. All existing measures (Antràs-Fally, Mancini et al.) operate at the ISIC sector level. A single sector can contain products at very different chain positions. This measure differentiates them.

---

## 2. Key Design Decisions

### 2.1 Unit of Analysis
**Product level (HS6)**, not sector level. Sector-level upstreamness measures already exist (Antràs-Fally; Mancini et al. 2024). Moving to product level recovers within-sector heterogeneity that sector aggregation masks — this is the primary contribution.

### 2.2 What the Measure Captures
- **Primary dimension: Downstreamness.** How much transformation has already occurred, inferred from the semantic content of HS6 descriptions. Recoverable from text alone.
- **Secondary dimension: Upstreamness.** How many further production steps remain before reaching final demand. Requires trade pattern data and/or product-level input-output links. Added through layers 4–6.
- These two dimensions are not inverses in complex production networks. A product can be high on both (specialty chemicals, semiconductors) — a mid-chain complex intermediate. A highly processed chemical correctly scores high on downstreamness even though it may still feed many further production stages. The text captures what has happened to a product; trade patterns are needed to infer what will happen.

### 2.3 Scope
**Full HS6 universe scored.** All products across all HS6 codes receive a chain position class and continuous score, including final goods (Class 5). BEC classification (PLAID) is used as a Layer 3 feature rather than a scope gate. This means:

- Final goods are classified as Class 5 — the measure assigns chain position to all products, not only intermediates.
- Downstream users can filter by class or BEC flag themselves rather than being locked out at the pipeline level.
- Class 5 final goods serve as validation anchors (passenger cars, smartphones, bottled wine are unambiguous Class 5 products).
- PLAID BEC remains a signal in the model — the intermediate/final/capital distinction is informative for classification — but it does not gate which products enter the scored dataset.

### 2.4 Double-Dipping — Acknowledged Limitation
A single HS6 code feeds into multiple sectors simultaneously. Steel rods flow into automotive, construction, machinery, and shipbuilding. The score is a **product-level central tendency** across all realistic uses — it represents the modal or expected chain position of the product, not its position in any specific supply chain. The uncertainty score captures how ambiguous this averaging is: products with high ensemble disagreement are likely high double-dipping candidates. This is an honest limitation of working at the product level without I-O allocation data.

### 2.5 Classification Method
Zero-shot Natural Language Inference (NLI) as the primary engine. No labelled training data required. Open-weight models (BART-MNLI, DeBERTa-NLI), locally runnable, fully owned. A thin classifier is distilled from high-confidence NLI predictions for deployment. No LLM ensemble API dependency.

### 2.6 Output Scale
Five-class ordinal label:
- **Class 1** — Raw / Primary
- **Class 2** — Processed Material
- **Class 3** — Component / Part
- **Class 4** — Intermediate Assembly / Capital
- **Class 5** — Final Good

All five classes are active in the scored output. Class 5 is not a residual or out-of-scope label — it is a substantive classification assigned to products the NLI identifies as complete finished goods intended for direct use. PLAID BEC provides an independent cross-check on Class 5 assignments but does not override the NLI score.

Plus a continuous score [1–5] (probability-weighted average across classes) and an uncertainty score [0–1] (entropy of the class probability distribution).

---

## 3. Motivating Questions and Design Responses

| Question | Response | Status |
|---|---|---|
| Should the measure live at sector or product level? Sector-level upstreamness already exists. | Product level — within-sector heterogeneity is large and policy-relevant. Descriptions recover variation that aggregation masks. | Resolved |
| Are we measuring GVC intensity or supply chain risk? Are these the same thing? | Distinct concepts. Chain position is the intensity signal; concentration (HHI) is the risk signal. Kept separate — concentration is not addressed in this measure. | Resolved |
| Do all products belong in scope, or only products that feed further production? | Full HS6 universe scored. Final goods receive Class 5. BEC classification is a Layer 3 feature, not a scope gate. Downstream users filter by class. | Resolved |
| A single HS6 product feeds into multiple sectors simultaneously — whose GVC does it belong to? (double-dipping) | Acknowledged limitation. Score is a product-level central tendency; use-specific variation surfaces in the uncertainty score. Not formally resolved without I-O allocation data. | Acknowledged limitation |
| Can text alone tell us where a product sits in a production chain? | Yes, for downstreamness — how much transformation has occurred. HS descriptions contain systematic linguistic gradients. Upstreamness requires trade pattern data added in later layers. | Resolved (partial) |
| How do you validate a score with no single ground truth? | Convergent multi-layer strategy: face validity on anchor products, correlation with sector-level upstreamness (Mancini et al.), within-chain ordering tests, Rauch classification consistency. | Resolved |

---

## 4. Layered Architecture

Each layer is a testable improvement over the previous. The key empirical question at each transition: does adding this source improve classification accuracy on the validation set?

---

### Layer 0 — HS2 Chapter Prior

**What it is:** A lookup table mapping HS2 chapters to a single coarse chain position class, derived from the known organisational logic of the HS schedule.

**Logic:**

| Chapter range | Contents | Prior class |
|---|---|---|
| 01–27 | Live animals, food, raw materials, minerals, fuels | Class 1 — Raw/Primary |
| 28–40 | Chemicals, plastics, rubber | Class 2 — Processed Material |
| 41–60 | Leather, wood, paper, textiles (fabrics/yarns) | Class 3 — Component/Part |
| 61–63 | Apparel and clothing accessories | Class 5 — Final Good |
| 64–67 | Footwear, headgear | Class 5 — Final Good |
| 68–83 | Stone, glass, ceramics, base metals, metal articles | Class 3 — Component/Part |
| 84–92 | Machinery, electrical equipment, instruments | Class 4 — Intermediate Assembly/Capital |
| 93 | Arms and ammunition | Class 4 — Intermediate Assembly/Capital |
| 94–96 | Furniture, toys, miscellaneous manufactures | Class 5 — Final Good |
| 97 | Art, antiques | Class 5 — Final Good |

**Design:** Single class per chapter range (Option A). No within-chapter resolution at Layer 0 — that is Layer 1's job. The prior is a fully transparent, zero-text baseline that every subsequent layer must improve on.

**Data required:** HS schedule chapter list. No external databases.

**Limitation:** All within-chapter variation invisible. Chapter 84 contains both industrial boilers and household microwaves. The prior assigns both to Class 4; Layer 1 NLI differentiates them from description text.

---

### Layer 1 — Zero-Shot NLI on HS6 Descriptions

**What it is:** The primary classification engine. NLI model reads each HS6 short description as a premise and evaluates entailment probability against a hypothesis for each of the five chain position classes.

**Models:** BART-MNLI, DeBERTa-NLI. Open weights, locally runnable.

**NLI hypothesis phrasings:**
- Class 1: *"This product is a raw or primary material that has been extracted, harvested, or produced in its natural state and has undergone little or no industrial transformation."*
- Class 2: *"This product is an industrial material that has been refined, processed, or transformed from a raw input into a standardised form, but is not yet a discrete component or assembled part of anything."*
- Class 3: *"This product is a discrete manufactured part or component that is designed to be incorporated into a larger assembly or system and cannot function independently."*
- Class 4: *"This product is either a complex sub-assembly incorporated into final goods during manufacturing, or a capital good used as equipment in a production process rather than consumed directly."*
- Class 5: *"This product is a complete, finished good intended for direct use by a household, business, or government without further industrial transformation."*

**Data required:** WCO HS6 short descriptions. Freely available across all revisions (HS 1992–2022).

**What it gives:** Downstreamness signal — how much transformation has occurred. Probability distribution over five classes for every HS6 code. Covers full universe (~5,000 codes per revision). No training data needed — classification is driven by the semantic relationship between the description and the explicitly stated hypothesis.

**Limitation:** No semantic understanding of interactions. Cannot distinguish "parts of a raw material processing machine" from "parts of a consumer appliance" — both trigger the "parts of" signal equally. Cannot recover upstreamness — descriptions tell you what has been done to a product, not what will be done with it.

---

### Layer 2 — Enriched Text (WCO Explanatory Notes)

**What it is:** Same NLI approach applied to longer, richer text. HS6 short description concatenated with the relevant WCO Explanatory Note for that heading.

**Data required:** WCO Explanatory Notes. Publicly available from the WCO.

**What it adds:** Disambiguation of borderline cases. Explanatory Notes contain explicit information about processing stage, intended use, and what distinguishes a product from related headings. Handles the "parts of" ambiguity better because Notes often specify what the parts are parts of. Improves performance on products with terse or ambiguous short descriptions.

**Coverage:** Full HS6 universe.

---

### Layer 3 — PLAID Attributes as Additional Features

**What it is:** PLAID-derived product characteristics added as features alongside the NLI probability distribution.

**Data required:** PLAID database (Brockhaus, Hinz, Iodice 2026). Open access, covers HS 1992–2022.

**Key features:**
- **BEC end-use flag:** Independent signal for intermediate/final/capital classification. Used as a feature, not a gate. Intermediate flag pulls toward classes 1–4; final consumption flag pulls toward class 5; capital goods flag pulls toward class 4. Cross-checks and refines NLI class 5 assignments.
- **Rauch classification (w/r/n):** Independent substitutability signal orthogonal to text. Exchange-traded goods (w) pull toward class 1–2. Differentiated goods (n) pull toward class 3–5. Derived from price-setting mechanisms, entirely independent of the description text.
- **Perishability class:** Correlated with upstream/downstream position — perishable goods tend to be agricultural or food products, often upstream.

**What it adds:** Independent corroboration from a different information source. Better handling of products whose descriptions are terse or ambiguous. Allows the model to learn interactions between text signals and categorical attributes.

**Note on BEC as validation:** BEC intermediate/final classifications and NLI chain position scores should correlate predictably. If a product receives Class 5 from the NLI but BEC flags it as an intermediate, that disagreement is informative — it surfaces in the uncertainty score and warrants inspection. BEC is a cross-check and enrichment signal, not an override.

**Note on Rauch as validation:** Rauch classification and chain position should correlate predictably — upstream products should skew toward w and r, downstream toward n. If NLI scores and Rauch labels are uncorrelated, something is wrong with one of them. This is a core validation check as well as a feature.

---

### Layer 4 — Trade Pattern Features (Comtrade)

**What it is:** Comtrade-derived behavioural features added to the classification. These add upstreamness signal — what happens to a product after it is traded reveals how many further steps remain.

**Data required:** UN Comtrade bilateral HS6 trade flows. Freely available at country level.

**Features:**
- **Exporter complexity profile:** Average Economic Complexity Index (ECI) of top exporters, weighted by export share. Products exported predominantly by low-complexity resource economies tend to be upstream. Products exported by high-complexity manufacturing economies tend to be mid-to-downstream.
- **Unit value (price per kg):** Very low unit values suggest bulk upstream commodities. Very high unit values suggest complex differentiated downstream goods.
- **Number of trading country pairs:** Upstream commodities tend to have many buyers and few sellers. Differentiated downstream goods have more bilateral variation.
- **HHI-MSX:** Global export market share concentration. Highly concentrated global supply is associated with upstream resource products.
- **Re-export ratio of importing countries:** Average ratio of exports to imports among top importers, weighted by import value. If major importers are themselves major exporters of related downstream products, the product is upstream.

**What it adds:** Grounds the linguistic signal in observed trade behaviour. Begins to recover upstreamness signal that text cannot provide. Substantially improves performance on products where the description alone is ambiguous.

**Limitation:** Country-level Comtrade gives weaker specialisation signals than subnational regional data. Trade features provide correlated upstreamness signals but not direct product-level input-output links. Products lightly traded in available data will have sparse features.

---

### Layer 5 — Sector-Level Upstreamness as Weak Supervision (Mancini et al.)

**What it is:** Sector-level upstreamness scores crosswalked to HS6 and used as weak training labels for the distilled classifier.

**Data required:** Mancini et al. (2024) GVC positioning dataset. Freely available at tradeconomics.com.

**Method:** Products that crosswalk exclusively to sectors with upstreamness above 3.5 → class 1–2 training labels. Products crosswalking exclusively to sectors with upstreamness below 1.3 → class 4–5 training labels. Only products with clean single-sector mappings used — double-dipping products excluded from the training signal to keep labels clean.

**What it adds:** Formal grounding in the Antràs-Fally framework. Makes product-level scores comparable to and interpretable alongside the established sector-level upstreamness literature. Provides empirical anchor for the distilled classifier.

**Limitation:** Sector-level crosswalk is noisy. Within-sector variation is exactly what this layer cannot recover — it uses sector averages as product labels. Used carefully only for the extremes of the distribution.

---

### Layer 6 — Product-Level Input-Output Links (Karbevska and Hidalgo 2025)

**What it is:** Published product-level input-output L matrix from Karbevska and Hidalgo (2025), providing directed links between HS4 product headings inferred from regional trade specialisation patterns using their Backward & Forward method.

**Data required:** Published HS4 results (open access, available as CSV). Their code is open source.

**What it adds:** Partial upstreamness enrichment. For products where the L matrix provides reliable links, the number of downstream products a heading feeds into gives a directed chain depth signal — the closest available approximation to product-level upstreamness without running their model on regional data.

**Coverage and limitations:**
- HS4-level only (~1,200 headings). HS6 codes within the same heading inherit identical upstreamness signal — within-heading variation not recovered.
- Reliable for manufactured goods traded heavily among their eight countries (Brazil, Canada, Chile, China, Japan, Russia, Spain, US). Coverage weaker for agricultural products and goods whose main trade corridors run through uncovered countries.
- Estimated meaningful coverage: ~40–50% of HS6 codes, at HS4 granularity.
- False positive rate non-trivial (~40% accuracy on full HS6, 70% for machinery). Used as enrichment signal with uncertainty weighting, not as ground truth.

**Future extension:** Run their open-source model on freely available subnational regional trade data (US Census state-level, Eurostat NUTS2, Japan Customs prefecture-level) to produce own HS6-level L matrix with better coverage and granularity.

---

## 5. Distillation Step

Once NLI produces labels across the full HS schedule:

1. Take high-confidence NLI predictions (entailment probability > 0.95 for one class, < 0.05 for all others) as pseudo-labels
2. Cross-check against Layer 0 chapter prior and PLAID BEC — only promote to training label if at least two independent sources agree
3. Fine-tune a lightweight classifier (DistilBERT or small sentence transformer) on the resulting training corpus
4. Deployed model is fast, cheap, fully owned, and traceable back to the explicit NLI hypotheses
5. NLI is the teacher; the thin classifier is the student

---

## 6. Anchor Products for Validation

A gold standard set of hand-labelled unambiguous products, held out from training and used only for evaluation.

**Class 1 anchors (Raw/Primary):**
Crude petroleum (HS 2709), iron ore (HS 2601), raw cotton (HS 5201), unrefined copper (HS 7402), natural gas (HS 2711), raw hides (HS 4101), coal (HS 2701), bauxite (HS 2606)

**Class 2 anchors (Processed Material):**
Refined copper cathodes (HS 7408), cold-rolled steel sheet (HS 7209), refined petroleum products (HS 2710), polyethylene (HS 3901), cotton yarn (HS 5205), aluminium ingots (HS 7601)

**Class 3 anchors (Component/Part):**
Ball bearings (HS 8482), semiconductor wafers (HS 3818), printed circuit boards (HS 8534), electric motors (HS 8501), valves (HS 8481), lenses (HS 9001)

**Class 4 anchors (Intermediate Assembly/Capital):**
Diesel engines (HS 8408), CNC machine tools (HS 8457), industrial robots (HS 8479), transmission shafts (HS 8483), compressors (HS 8414)

**Class 5 anchors (Final Good):**
Passenger cars (HS 8703), smartphones (HS 8517), washing machines (HS 8450), bottled wine (HS 2204), woven suits (HS 6203), refrigerators (HS 8418)

---

## 7. Validation Strategy

No single ground truth exists for HS6-level chain position. Validation is convergent across multiple independent sources.

**V1 — Face validity on anchor products**
Score the gold standard anchor set. Unambiguous products (crude petroleum = class 1, passenger cars = class 5) must be classified correctly. Any failure here is a hard problem, not a borderline case.

**V2 — Within-chain ordering tests**
Construct 10–15 known supply chains. Verify that the score recovers the correct ordering of products along each chain. Test is ordinal — correct ordering matters, not cardinal distances.

Example chains:
- Textile: raw cotton → cotton yarn → woven fabric → finished apparel (1 → 2 → 3 → 5)
- Steel: iron ore → pig iron → steel billet → cold-rolled sheet → stamped automotive part (1 → 2 → 2 → 2 → 3)
- Electronics: silicon → wafers → chips → PCBs → assembled devices (1 → 2 → 3 → 3 → 5)

**V3 — Correlation with sector-level upstreamness (Mancini et al.)**
Average NLI continuous scores for products crosswalked to each ISIC sector. Correlate with sector-level upstreamness values from Mancini et al. At the sector aggregate level, mean product scores should recover the sector ordering. Mining sector products should average near class 1. Motor vehicles sector products should average near class 4–5.

**V4 — Rauch classification consistency**
Class 1 and 2 products should skew toward Rauch w (organised exchange) and r (reference priced). Class 4 and 5 products should skew toward Rauch n (differentiated). If chain position scores and Rauch labels are uncorrelated, something is wrong with one of them.

**V5 — BEC cross-check**
Class 5 NLI assignments should correlate strongly with PLAID BEC final consumption flag. Disagreements (NLI says Class 5, BEC says intermediate) are flagged for inspection and surface in the uncertainty score. This replaces the old scope gate role of BEC with a more informative diagnostic role.

**V6 — Layer-by-layer improvement**
Each layer transition is a testable hypothesis. Does adding Explanatory Note text improve over description text alone? Does adding Rauch as a feature improve over text alone? Does adding trade pattern features improve over text alone? Measure improvement on the anchor validation set at each step.

---

## 8. Data Sources Summary

| Source | What it provides | Role in pipeline | Level | Access |
|---|---|---|---|---|
| WCO HS descriptions | Product description text | Layer 1 input | HS6 | Free |
| WCO Explanatory Notes | Richer official text | Layer 2 input | HS heading | Free |
| PLAID (Brockhaus et al. 2026) | BEC feature, Rauch, perishability | Layer 3 features + Class 5 cross-check | HS6 | Open access |
| UN Comtrade | Bilateral trade flows | Layer 4 features | HS6, country | Free |
| Mancini et al. (2024) | Sector-level upstreamness / downstreamness | Layer 5 weak supervision + validation V3 | Country × ISIC | Free |
| Karbevska & Hidalgo (2025) | Product-level I-O links | Layer 6 upstreamness enrichment | HS4 | Open access |
| BART-MNLI / DeBERTa-NLI | NLI classification models | Layer 1–2 engine | — | Open weights |

---

## 9. Key Literature

| Paper | Contribution to this project |
|---|---|
| Johnson (2018) — *Measuring Global Value Chains* | Conceptual foundation. Leontief/Ghosh framework. Upstreamness/downstreamness definitions. Motivates moving to product level. |
| Antràs & Fally (2012) | Original sector-level upstreamness measure. Theoretical benchmark this measure attempts to replicate at product level. |
| Mancini et al. (2024) — *Positioning in GVC* | Ready-to-use sector-level U and D scores across five ICIO datasets. Layer 5 weak supervision and validation V3. |
| OECD (2024) — *Product Level Vulnerabilities* | Documents within-sector heterogeneity that sector-level allocation misses. Motivates the product-level approach. Shows sector-uniform allocation underestimates concentration. |
| Brockhaus, Hinz & Iodice (2026) — *PLAID* | HS6-level product attribute database. BEC feature. Rauch classification. Methodological template for NLI classification architecture. Demonstrates feasibility of text-based HS6 classification. |
| Karbevska & Hidalgo (2025) — *Mapping GVCs at product level* | Product-level input-output L matrix at HS4. Backward & Forward method. Layer 6 partial upstreamness enrichment. Future extension: run their model on free regional data. |
| Rauch (1999) | w/r/n classification of traded goods by price-setting mechanism. Layer 3 feature and validation V4 consistency check. |

---

## 10. Acknowledged Limitations

**Double-dipping:** The measure assigns a single score per HS6 product representing a central tendency across all its realistic uses. Use-specific chain position variation is not resolved. The uncertainty score flags products where this ambiguity is largest.

**Downstreamness not full chain position:** The text-based layers primarily recover how much transformation has already occurred. How many steps remain to final demand (upstreamness) is only partially recovered through trade pattern layers and the L matrix.

**Layer 6 coverage gap:** Karbevska and Hidalgo cover ~40–50% of HS6 codes at HS4 granularity. The remaining products rely on Layers 4 and 5 for upstreamness signal only.

**HS4 granularity in Layer 6:** Within-HS4-heading variation in upstreamness is not recovered from the L matrix. Products within the same heading receive identical upstreamness signal from this layer.

**Country-level trade data:** Layer 4 trade pattern features use country-level Comtrade rather than subnational regional data. Specialisation signals are weaker than what subnational data would provide, limiting precision of upstreamness inference from trade patterns.

**BEC-NLI disagreement:** Class 5 assignments from the NLI are cross-checked against PLAID BEC but not overridden by it. Cases where the two disagree are flagged in the uncertainty score. The absence of a hard gate means some borderline products near the intermediate/final boundary may receive ambiguous scores — these surface as high-entropy cases and should be interpreted with caution.

---

## 11. Future Extensions

- **Run Karbevska & Hidalgo model on free regional data:** US Census state-level, Eurostat NUTS2, Japan Customs prefecture-level data are freely available. Running their open-source model on this data would produce an own HS6-level L matrix with better coverage and granularity than their published HS4 results.
- **Sector interdependencies:** Some sectors function as mini-GVCs with a final good residing in a different sector entirely. Treating sectors as nodes in a larger production network — rather than independent units — is a natural extension once the product-level measure is established.
- **Sector × product combination:** Allocating HS6 product flows across ISIC sectors using the ICIO Z-matrix would formally resolve double-dipping and enable vulnerability analysis at the country × sector × product × source level. Deferred given the data engineering complexity and the aggregation problems this inherits from sector-level I-O structure.

---

## 12. Open Design Questions

- **Hypothesis phrasing:** Exact wording of NLI hypotheses for each class to be tested empirically. Performance is sensitive to phrasing quality. Multiple phrasings per class should be tested and validated against anchor products before finalising.
- **NLI ensemble vs. single model:** Whether to run multiple NLI models and take majority vote (adds robustness, higher uncertainty signal) or run one strong model and distil directly (simpler). To be decided based on empirical performance.
- **HS revision harmonisation:** HS codes change across revisions (1992, 1996, 2002, 2007, 2012, 2017, 2022). Scores need to be mapped consistently across revisions for time-series analysis. Concordance tables exist but introduce their own alignment challenges.
- **Validation sample size:** How many anchor products per class are needed for statistically meaningful layer-by-layer comparison?
- **BEC-NLI disagreement threshold:** At what level of BEC-NLI disagreement should a product be flagged as high-uncertainty? To be calibrated empirically against the anchor validation set.
