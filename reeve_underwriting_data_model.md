# Reeve — Underwriting Data Model (Value-Add / Distressed Multifamily)

Companion to `reeve_agent_specs.md` (Ana, §4) and `contracts/deal_analysis.schema.json`
(the v1 stabilized contract). This document is the **data model and computation spec for
the v2 underwriter**: an Ana that can handle partial occupancy, mid-renovation assets with
mixed unit conditions, two-phase financing that doesn't fit agency boxes, and deals where
most of the value is unrealized.

Status: **specification**. Nothing in this file is implemented yet; §9 maps each piece to
the existing code and gives a build order.

---

## 0. Why v1 is not enough

The v1 underwriter (`reeve/underwriting/model.py` + the `deal_analysis` contract) assumes a
stabilized asset. Its specific failures on a value-add deal, called out honestly:

| v1 behavior | Why it breaks on value-add |
|---|---|
| One rent roll with `in_place` / `market` per unit | No condition tiers. Can't distinguish a renovated-occupied unit's **achieved** rent from a broker's **asking** rent — the single most load-bearing number in a value-add underwrite. |
| OpEx modeled as `% of EGI` | At 64% occupancy, EGI is depressed but taxes, insurance, and most fixed costs are not. A % ratio **understates expenses exactly when the deal is riskiest.** v2 holds OpEx in fixed dollars across occupancy states. |
| One NOI, one cap, one value | A value-add deal has at least three NOI states (in-place, stabilized, stabilized + ancillary) and the valuation is a **floor/ceiling band**, not a point. |
| Single financing block (rate/term/LTV) | No concept of bridge-to-perm, no agency occupancy gate. A 64%-occupied building cannot take Freddie SBL debt (90% for 90 days); v1 would happily model it. |
| Taxes inside a blended `other_expense_rate` | No reassessment-at-trade-price. Carrying the seller's tax basis is one of the classic naive-underwriter errors. |
| `confidence` + `unverified[]` as flat lists | No per-input provenance. v2 attaches `verified / broker_claimed / assumed` to every material input and ranks them by valuation swing. |

---

## 1. Design principles

1. **Provenance on every input.** Every material number carries a verification status:
   `verified` (document in hand / third-party quote) → `broker_claimed` (came from the OM
   or the listing; treat as adversarial) → `assumed` (the agent or investor supplied it).
   The output's risk register is generated from these tags, ranked by how much each
   unverified input moves the max offer.
2. **Asking ≠ achieved.** They are different fields, never interchangeable. `achieved_rent`
   exists only on a renovated, occupied unit with a signed lease. The sample size of
   achieved-renovated observations is itself a tracked datum.
3. **Three NOI states + one adversarial input.** In-place, stabilized base, stabilized +
   ancillary are computed by Reeve's engine. The broker pro-forma is **stored but never
   trusted** — it is rebuilt from primitives and the deltas are reported.
4. **The offer never pays for value the buyer creates.** Ancillary income and rent upside
   set the *ceiling*; the offer anchors on *in-place* economics. The spread is the
   investor's to capture. (This maps directly onto the existing propose-don't-execute
   model: Ana presents the disciplined bid and shows the upside separately.)
5. **Assumptions are data.** Target rent, exit cap, required margin live in a
   `DealAssumptions` record — editable, versioned with the analysis artifact, and always
   labeled as levers rather than facts.
6. **Ingestion is the riskiest layer.** Rent rolls and T-12s arrive as inconsistent
   PDFs/Excel. Extracted documents land in *staging* records with validation checks and a
   `human_confirmed` gate; Ana refuses to emit a confident verdict on unconfirmed
   extractions (confidence is capped at `low` and the flag is blocking). See §8.

---

## 2. Entity map

```
deal (existing, extended)
 ├── profile: stabilized | value_add | distressed        ← routing flag for Ana
 ├── property_profile        1:1   physical truth (structures, mix, condition, site)
 ├── rent_roll               1:0..n  STAGED ingest; one "active" per deal   ← keystone
 │     └── leases[]                per-lease rows (the actual data)
 ├── operating_statement     1:0..n  STAGED ingest (T-12); one "active"
 ├── renovation_budget       1:0..1  scope + costs to the target standard
 ├── market_context          1:0..1  comps (by condition), caps, vacancy norms
 ├── financing_scenario      1:0..n  bridge + perm pairs (compare scenarios)
 ├── deal_assumptions        1:0..n  levers; versioned with each analysis
 └── artifact (existing)     value_add_analysis payload (§7) — immutable, versioned
```

Storage: `property_profile`, `renovation_budget`, `market_context`,
`financing_scenario`, `deal_assumptions` are **embedded documents on the deal** (they are
small and always read together). `rent_roll` and `operating_statement` are **separate
staged collections** (`rent_rolls`, `operating_statements`) because they are large,
ingested from files, carry their own confirmation lifecycle, and are superseded by
re-ingests the same way artifacts are versioned.

---

## 3. Entities in detail

Conventions: `prov` column = does the field carry a per-field provenance tag
(`verified | broker_claimed | assumed`). Money in dollars, rates/percentages as decimals
(0.07 = 7%), dates ISO-8601.

### 3.1 `deal` extensions

| Field | Type | Why |
|---|---|---|
| `profile` | enum `stabilized \| value_add \| distressed` | Routes Ana to the right engine + the right contract. Default `stabilized` keeps v1 deals working. |
| `active_rent_roll_id` | str? | The confirmed rent roll this analysis reads. |
| `active_operating_statement_id` | str? | The confirmed T-12 this analysis reads. |
| `broker_proforma` | object? | The OM's claimed NOI/rents, stored verbatim. Adversarial input: the engine rebuilds NOI from primitives and reports deltas line by line. Never feeds a computation. |

### 3.2 `property_profile` (embedded on deal)

The physical truth of the asset. Everything here is cheap to collect and expensive to skip.

| Field | Type | Prov | Why |
|---|---|---|---|
| `structures[]` | `{label, type: apartments\|clubhouse\|garage\|other, year_built, units_count, notes}` | ✓ | **Per-structure year built** — a 1940 clubhouse and 1960 apartments age, depreciate, and carry abatement risk differently. `year_built` drives the pre-1980 abatement presumption (§3.5) and the contingency scaling rule. |
| `unit_mix[]` | `{beds, baths, count, avg_sqft?}` | ✓ | Comps must be segmented by mix; a blended average hides the spread. |
| `physical_occupancy` | decimal | ✓ | Units physically occupied ÷ total. Distinct from economic occupancy (which the rent roll derives). **This is the number checked against the agency gate.** |
| `condition_inventory` | `{renovated: int, rent_ready: int, down: int}` | ✓ | Tier counts; the per-unit detail lives on rent-roll rows. Drives the renovation budget shape and the lease-up timeline. |
| `completed_capital[]` | `{item, year, cost?, verified}` | ✓ | Roofs, HVAC, etc. already done. Lowers the reno budget and the contingency, but only if verified — "new roof" in an OM is a claim, not a fact. |
| `site` | `{parking_spaces, parking_scarce: bool, storage_dead_space: bool, standalone_structures[]}` | ✓ | Ancillary-income raw material (paid parking, storage). Scarce parking is a lever; abundant parking is nothing. |
| `submarket` | str |  | Comp segmentation key. |
| `demand_drivers[]` | str[] |  | Employers, transit, university — context for rent-growth and vacancy assumptions. |

### 3.3 `rent_roll` (staged collection) — **the keystone**

A lease-by-lease snapshot, never an average. One deal may have several (re-ingests as
diligence progresses); exactly one is `active`.

**Envelope:**

| Field | Type | Why |
|---|---|---|
| `deal_id`, `as_of` | str, date | Which deal, what snapshot date. Staleness >60 days is a flag. |
| `source` | `{file_name, format: pdf\|xlsx\|csv\|manual, ingested_at, extraction_method}` | Audit trail back to the original document. |
| `human_confirmed` | bool | **The ingestion gate (§8).** Ana caps confidence at `low` and raises a blocking flag while false. |
| `validation` | `{checks: [{name, passed, detail}]}` | Machine checks run at ingest: row count vs claimed unit count, occupancy consistency, rent column sums, date parses. |
| `supersedes` | str? | Prior rent_roll id — same immutable-versioning convention as artifacts. |

**`leases[]` rows:**

| Field | Type | Prov | Why |
|---|---|---|---|
| `unit_label` | str |  | Joins to the unit record. |
| `condition_tier` | enum `renovated \| rent_ready \| down` | ✓ | The unit-level renovated-vs-not flag. Splits every income stat by tier. |
| `occupied` | bool | ✓ | Drives physical occupancy. |
| `in_place_rent` | number? | ✓ | Contract rent on the current lease. Null for vacant. |
| `achieved_rent` | number? | ✓ | **The load-bearing number.** Only populated when `condition_tier=renovated` AND `occupied=true` — a signed lease at the post-reno standard. This, not the OM's "renovated units getting $X," is what the stabilized rent assumption must be reconciled against. |
| `asking_rent` | number? | broker_claimed by definition | What the listing/OM asks for this unit type. Stored so the gap to achieved is computable; **never used in NOI math.** |
| `lease_start`, `lease_end` | date? | ✓ | Rollover schedule; near-term expiries during a reno program are lease-up capacity. |
| `concessions` | number? | ✓ | Free rent / discounts. Effective rent = contract − amortized concessions; ignoring this overstates in-place NOI. |
| `delinquent_balance` | number? | ✓ | Credit-loss reality check on the economic-occupancy assumption. |
| `notes` | str? |  | Free text from the source document. |

**Derived (computed at confirm time, stored on the envelope):**
`physical_occupancy`, `economic_occupancy`, `avg_in_place_by_tier`,
`achieved_renovated: {mean, median, n}` — **`n` matters**: two achieved-renovated leases
is an anecdote, twelve is evidence; the risk register reports the sample size.

### 3.4 `operating_statement` (staged collection — the T-12)

Same envelope as the rent roll (`source`, `human_confirmed`, `validation`, `supersedes`).

| Field | Type | Prov | Why |
|---|---|---|---|
| `period` | `{start, end}` |  | Must actually be trailing-12; partial-year annualization is a flag. |
| `lines[]` | `{category, annual, monthly[]?}` | ✓ | Line-by-line: `taxes, insurance, utilities_water, utilities_electric, utilities_gas, mgmt_fee, repairs_maintenance, turns, payroll, admin, marketing, other`. Monthly detail when extractable — seasonality and one-time spikes are visible there. |
| `tax` | `{current_assessed, current_annual_bill, reassessment_estimate_at_price, reassessment_method, verified}` | ✓ | **Never carry the seller's basis.** `reassessment_estimate_at_price` is a function of trade price (county millage × price, or local rule); the engine recomputes it per bid level in the sensitivity grid. |
| `insurance` | `{current_annual, commercial_quote, quote_source, quote_date}` | ✓ | A residential-rate proxy on a 5+ unit asset is invalid. The stabilized NOI uses the commercial quote; absence of one is a flag. |
| `utilities` | `{master_metered[], sub_metered[], owner_paid_annual, rubs_candidate: bool}` | ✓ | Owner-paid water on a master meter is the classic RUBS (ratio utility billback) opportunity — ancillary income, therefore ceiling-only (§1.4). |
| `reserves_per_door` | number | assumed | Replacement reserves. **Below the NOI line** (§5 rule 1) but inside DSCR math per lender convention — stored once, applied correctly in both places. |

### 3.5 `renovation_budget` (embedded on deal)

| Field | Type | Prov | Why |
|---|---|---|---|
| `tiers[]` | `{condition_tier, scope_description, cost_per_unit, units_count}` | ✓ | Cost to bring each tier to the target standard. `down` units cost full reno; `rent_ready` only make-ready. |
| `make_ready_per_unit` | number | ✓ | Turn cost on rent-ready units — cheaper than reno but not free. |
| `systems[]` | `{item: electrical_panel \| plumbing_supply \| hvac \| roof \| other, structure_label, cost, status: required \| contingent}` | ✓ | Old structures get **explicit systems line items**, not a blended per-unit number. A 1960 building with original panels is a known cost, not a contingency. |
| `abatement_allowance` | `{amount, basis, tested: bool}` | ✓ | Asbestos/lead is **near-certain pre-1980**. Untested → carried as an allowance with `assumed` provenance and a blocking flag; tested → verified line item. |
| `contingency_pct` | decimal | assumed | **Mandatory, scales with age**: suggested floor 10%, +5 pts for any structure pre-1980, +5 pts if systems are untested. The engine refuses a budget with contingency below floor. |
| `total` | computed | | `Σ(tier costs) + Σ(systems) + abatement + contingency`. |

### 3.6 `market_context` (embedded on deal)

| Field | Type | Prov | Why |
|---|---|---|---|
| `rent_comps[]` | `{address, condition: renovated \| classic, beds, baths, rent, sqft?, source, observed_at}` | ✓ | **Segmented by condition.** A renovated comp set supports the target rent; classic comps support in-place sanity checks. Mixing them is how target rents get inflated. |
| `cap_rates` | `{market_cap_by_class: {a?, b?, c?}, source, as_of}` | ✓ | Floor valuation uses the class-appropriate market cap; the exit cap is an *assumption* (§3.8) tested against this. |
| `vacancy_norm` | decimal | ✓ | Submarket stabilized vacancy — the floor for the stabilized-vacancy assumption. |
| `rent_growth_trend` | decimal | broker/assumed | Used only in IRR projection, never in the stabilized NOI. |

### 3.7 `financing_scenario` (embedded on deal; repeatable)

Two phases, explicitly. Multiple scenarios per deal so bridge-to-agency can be compared
against bank debt or all-cash.

| Field | Type | Why |
|---|---|---|
| `label` | str | "Bridge→Freddie SBL", "Bank mini-perm", … |
| `bridge` | `{ltc, rate, interest_only: true, term_months, origination_pts, expected_hold_months}` | Sized off **loan-to-cost** (price + reno), not LTV. IO during the reno/lease-up period. `expected_hold_months` drives the net-carry computation (§4.3). |
| `perm` | `{program, rate, amort_years, min_dscr, max_ltv, occupancy_gate: {occupancy: 0.90, days: 90}, refi_costs_pct}` | The takeout. `occupancy_gate` encodes the agency rule (e.g. **Freddie SBL: 90% for 90 days**) — the engine checks in-place occupancy against it and *hard-disqualifies* perm-first structures below the gate. |
| `sponsor` | `{liquidity_required, net_worth_required}` | Lender sponsor covenants — surfaced so the investor knows the gate before falling in love with the deal. |

### 3.8 `deal_assumptions` (embedded on deal; versioned with each analysis)

Everything here is a **lever, not a fact** — provenance is `assumed` by construction, and
the output contract reprints these next to every number they touch.

| Field | Type | Why |
|---|---|---|
| `target_rents[]` | `{condition_tier or mix, monthly_rent}` | Post-reno rent standard. Must be reconciled against `achieved_renovated.mean` and the renovated comp set; a target above both is a flag. |
| `exit_cap` | decimal | Stabilized valuation divisor. Tested against `market_context.cap_rates`; an exit cap *below* market (value appreciation baked in) is a flag. |
| `required_margin` | `{type: pct_of_cost \| dollars, value}` | The profit the deal must clear. Subtracted in the max-offer formula — this is "don't pay for value you create" made arithmetic. |
| `stabilized_vacancy` | decimal | Floor = `market_context.vacancy_norm`. |
| `credit_loss` | decimal | Informed by rent-roll delinquency. |
| `rent_growth` | decimal | IRR projection only. |
| `lease_up_months` | int | Reno + absorption timeline; drives net carry. |
| `ancillary[]` | `{item: rubs \| storage \| parking \| clubhouse_conversion \| other, monthly, basis, confidence}` | Upside inventory. Feeds NOI state 3 and the ceiling — **never the offer basis.** `clubhouse_conversion` carries its own highest-and-best-use flag (§6). |

### 3.9 Provenance (cross-cutting)

```
provenance: verified | broker_claimed | assumed
```

Attached per-field (the `prov` columns above). Rules:

- Anything sourced from the OM/listing/broker enters as `broker_claimed` — including the
  rent roll itself until `human_confirmed` flips and spot-checks pass.
- The engine computes every output twice where it matters: once with all inputs, once with
  `broker_claimed` inputs haircut to conservative defaults. The gap is reported.
- The **assumption-risk register** (§7) is generated by perturbing each non-`verified`
  input ±X% and recording the swing in max offer — that is how the agent *names the
  load-bearing assumption* instead of hand-waving.

---

## 4. Computation spec

Pure functions, extending `reeve/underwriting/`. Inputs are the entities above; no IO.

### 4.1 Three NOI states (plus the adversarial fourth)

| State | Income side | Expense side |
|---|---|---|
| **In-place** | Σ effective contract rents (occupied units only, concessions amortized, delinquency haircut) | **Actual T-12 dollars**, with two corrections only: taxes → reassessed-at-bid, insurance → commercial quote. **Never % of EGI** — fixed costs don't shrink with vacancy. |
| **Stabilized base** | `target_rents` × all units × (1 − stabilized_vacancy − credit_loss) | T-12 dollars + variable lines (turns, mgmt) scaled to stabilized occupancy; taxes reassessed; insurance quoted; reserves stated separately below the line. |
| **Stabilized + ancillary** | Stabilized base + Σ `ancillary[].monthly × 12` | Same as stabilized base + any opex the ancillary item adds. |
| *Broker pro-forma* | *Stored, rebuilt, diffed. Reported as `broker_delta` per line. Never feeds math.* | |

NOI is **before** CapEx, reserves, and debt service in all states (rule 1, §5).

### 4.2 Valuation — a band, not a point

```
floor_value        = NOI_in_place   ÷ market_cap          (what it earns today)
stabilized_value   = NOI_stabilized ÷ exit_cap            (what it earns fixed)
ceiling_max_offer  = stabilized_value
                     − cost_to_stabilize                  (§4.3)
                     − required_margin
                     all grossed up for closing costs
bid ladder:
  walk_away  = ceiling_max_offer                          (breakeven on required margin)
  target_bid = between floor and walk_away, set by competitive read
  opening    = anchored at/near floor (in-place economics — rule 4, §5)
```

### 4.3 Cost-to-stabilize stack

```
cost_to_stabilize = renovation_budget.total
                  + make_ready + lease_up_costs (marketing, turns at velocity)
                  + NET CARRY
                  + closing_costs (acquisition + refi)

NET CARRY = Σ over lease_up_months of
            (bridge interest accrued − partial in-place NOI collected that month)
```

Net carry is called out as its own line because it is the term most often silently
omitted, and on a 12–18 month program it materially moves the answer.

### 4.4 Two-stage financing

```
bridge_proceeds   = ltc × (price + renovation_budget.total)
debt_constant     = annual P&I per $1 at (perm.rate, perm.amort_years)
perm_by_ltv       = perm.max_ltv × stabilized_value
perm_by_dscr      = NOI_stabilized ÷ (perm.min_dscr × debt_constant)
perm_loan         = min(perm_by_ltv, perm_by_dscr)        ← lesser-of, always

occupancy gate    : if physical_occupancy < perm.occupancy_gate.occupancy
                    → perm-first structures DISQUALIFIED; bridge-to-perm is the path,
                      and the gate timeline feeds lease_up_months.

refi_proceeds     = perm_loan − refi costs
equity_recapture  = refi_proceeds − bridge payoff
residual_equity   = total equity in − equity_recapture
stabilized_coc    = (NOI_stabilized − perm debt service) ÷ residual_equity
hold_irr          = optional: monthly cash flows through reno → lease-up → refi → hold → exit at exit_cap
```

### 4.5 Cross-check panel (cheap error-catchers, always computed)

| Check | Formula | Catches |
|---|---|---|
| Price per door | bid ÷ units | Fat-finger and comp-set errors |
| Untrended yield-on-cost | NOI_stabilized ÷ (price + cost_to_stabilize) | The core value-add return |
| **YoC spread vs exit cap** | YoC − exit_cap | **Negative-leverage test**: spread ≤ 0 means paying retail for wholesale work |
| In-place cap at bid | NOI_in_place ÷ bid | How much pro-forma the bid is paying for |
| Stabilized cap at bid | NOI_stabilized ÷ bid | Sanity vs market cap |
| DSCR at perm | NOI_stabilized ÷ perm debt service | Refi feasibility |
| GRM | bid ÷ gross scheduled income | Cross-era comparable |

### 4.6 Sensitivity

Minimum: **rent × cap grid** — target rent ±10% (or ± the achieved-vs-target gap,
whichever is larger) crossed with exit cap ±50–100 bps, reporting max offer in each cell.
Taxes are re-derived per cell (reassessment is bid-dependent). The output **must state the
swing** ("max offer moves $412k across the grid"), not just the center value.

---

## 5. Judgment rules and where each is enforced

Prompt language alone does not survive contact with an LLM. Each rule gets a home in code.

| # | Rule | Enforced in |
|---|---|---|
| 1 | NOI is before CapEx, reserves, and debt service | Engine: reserves and debt are separate fields; no code path adds them into NOI. |
| 2 | Never model OpEx as % of EGI at low occupancy; hold fixed costs in dollars | Engine: in-place state consumes T-12 dollars. The v1 `% of EGI` path is reserved for `profile=stabilized` only. |
| 3 | Reassess taxes at trade price; commercial insurance quote, not residential proxy | Engine substitutes both in every state; **flags** (§6) if estimate/quote missing. |
| 4 | Don't pay for value you create — ancillary and upside set the ceiling, never the offer | Engine: `ancillary` is structurally absent from the floor/opening computation; offer anchors on in-place. |
| 5 | Match financing to asset state — no residential math on 5+ units; agency gated by occupancy | Engine: occupancy-gate hard check; tool schema has no residential-loan path. |
| 6 | Name the load-bearing assumption; refuse false precision | Risk register generated by perturbation (§3.9); confidence capped at `low` while any blocking flag is open. |
| 7 | Broker pro-forma is adversarial input | Schema: `broker_proforma` is stored verbatim, type-isolated from engine inputs; only the diff report reads it. |

---

## 6. Blocking diligence flags (auto-raised)

Each is `{flag, trigger, severity: blocking, what_unblocks}` on the artifact. While any
blocking flag is open, Ana's verdict is `conditional` at most and confidence ≤ `low`.

| Flag | Trigger | Unblocked by |
|---|---|---|
| `unconfirmed_extraction` | `rent_roll.human_confirmed == false` or T-12 unconfirmed | Human confirms the staged ingest (§8) |
| `achieved_rent_unverified` | target rent leans on `broker_claimed` asking rents, or `achieved_renovated.n` < 3 | Lease audit on renovated-occupied units |
| `below_agency_gate` | `physical_occupancy < perm.occupancy_gate.occupancy` | Acknowledge bridge-to-perm path (informational once financing matches) |
| `pre_1980_structure` | any `structures[].year_built < 1980` | Abatement test results + systems inspection, or tested allowance in budget |
| `tax_reassessment_missing` | no `reassessment_estimate_at_price` | County estimate at bid price |
| `insurance_below_commercial` | no commercial quote, or current annual < quote × 0.8 | Bound commercial quote |
| `valued_on_unachieved_proforma` | any structure/unit valued on income it has never produced | Achieved comps or reclassification as upside |
| `stale_rent_roll` | `as_of` > 60 days old | Re-ingest current roll |
| `hbu_question` | non-standard space with competing uses (clubhouse → unit vs amenity) | Investor decision recorded in assumptions |

---

## 7. Output contract: `value_add_analysis` (artifact payload)

A superset of `deal_analysis`, rendered by a new UI card. Panels:

1. **NOI panel** — in-place / stabilized / stabilized+ancillary, line-by-line, with the
   broker-pro-forma diff column.
2. **Valuation panel** — floor, stabilized value, ceiling; bid ladder (opening / target /
   walk-away) with the formula trace for each.
3. **Sources & uses** — acquisition + reno + carry + closing vs bridge + equity; then the
   refi event: perm proceeds, bridge payoff, equity recapture, residual equity.
4. **Returns** — stabilized cash-on-cash, equity recapture %, optional hold-period IRR.
5. **Cross-check panel** — §4.5 table with pass/warn coloring (YoC spread ≤ 0 renders red).
6. **Sensitivity grid** — rent × cap with the stated swing.
7. **Assumption-risk register** — ranked: `{input, provenance, value_used, swing_on_max_offer,
   verification_action}`. The top entry is, definitionally, the load-bearing assumption.
8. **Flags** — open blocking flags (§6) with unblock actions.
9. `confidence` + `verdict {decision, max_price, headline}` — same shape as v1, but
   `max_price` is the ceiling from §4.2 and `decision` is forced to `conditional` while
   blocking flags are open.

Contract files to create at build time: `contracts/value_add_analysis.schema.json` +
`reeve/contracts/value_add_analysis.py` (Pydantic mirror), per the established convention.

---

## 8. Ingestion & normalization layer

**This is where the engineering and reliability risk actually lives.** Rent rolls and
T-12s arrive as messy PDFs and Excel in wildly inconsistent formats, and a generic LLM
extraction will silently transpose a column or skip a page.

Pipeline (per document):

```
upload → extract (LLM/parser) → STAGED record (rent_rolls / operating_statements)
       → machine validation     (checks stored on the record):
           • row count == claimed unit count
           • occupancy from rows ≈ stated occupancy
           • rent column sums == stated totals (where the doc states them)
           • dates parse; lease_end ≥ lease_start
           • T-12 line sums == stated annual totals
       → HUMAN CONFIRMATION     (investor or operator reviews a rendered table next to
                                 the source; edits land on the staged record with
                                 provenance=verified)
       → active                 (deal.active_rent_roll_id flips; prior roll superseded)
```

Hard rules:

- Ana **cannot** promote a staged document to active; only a human confirmation can
  (mechanically: the confirm endpoint is investor-authenticated, same pattern as
  proposal approval).
- While the active document is missing or unconfirmed, `unconfirmed_extraction` blocks.
- Every machine-validation failure is visible in the confirmation UI — the human is
  checking the extractor's work, not re-keying the document.

---

## 9. Mapping to the current implementation + build order

What exists today and what changes:

| Piece | Today | v2 change |
|---|---|---|
| `Deal` model | address/units/ask/status | + `profile`, `active_*_id` refs, `broker_proforma`, embedded entities (§3.2, 3.5–3.8) |
| `underwrite()` | stabilized, % of EGI | New `underwrite_value_add()` alongside it; v1 path kept for `profile=stabilized` |
| `deal_analysis` contract | v1, point estimate | New `value_add_analysis` contract (§7); v1 untouched |
| `pull_comps` | one blended market rent | Comp records segmented by condition (§3.6) |
| Ana spec (`agents/ana.md`) | stabilized prose | Routing on `deal.profile`; §5 judgment rules and §6 flags added to Failure & Uncertainty |
| Ingestion | none | `rent_rolls` + `operating_statements` staged collections, extraction tool, confirm endpoint + UI (§8) |
| Mongo | — | 2 new collections + indexes (`deal_id`, `human_confirmed`) |

Suggested build order (each step independently shippable, same pattern as the original
§8 plan):

1. **Models + contracts** — embedded entities on Deal, the two staged collections, the
   `value_add_analysis` schema. No behavior change.
2. **Engine** — `underwrite_value_add()`: NOI states, valuation band, cost-to-stabilize,
   two-stage financing, cross-checks, sensitivity. Pure functions, smoke-tested against a
   hand-computed reference deal (the deal that motivated this spec is the test fixture).
3. **Ingestion** — extraction into staging, machine validation, the confirm endpoint +
   UI table. This is the long pole; build it third so the engine can be validated with
   hand-entered data first.
4. **Ana v2** — routing, tools (`get_rent_roll`, `get_operating_statement`,
   `run_value_add_analysis`, `submit_value_add_analysis`), prompt update, flags.
5. **UI** — the `value_add_analysis` renderer (panels 1–8).

---

*Spec derived from a worked underwrite of a partially-occupied, mid-renovation multifamily
asset (mixed 1940/1960 structures, 64% occupancy, bridge-to-agency financing path). The
test for v2 is simple: it must refuse to give that deal a confident single number, and it
must name achieved-renovated rent as the assumption the whole answer hangs on.*
