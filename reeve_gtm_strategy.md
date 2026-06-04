
reeve_gtm_strategy.md


raw
# Reeve — Marketing & Sales Strategy
 
> **Status:** Living document · **Version:** 0.1 · **Last updated:** 2026-06-04
> **Owner:** Reid (product/eng) · **Sales/strategy:** brother
> **Purpose:** The single source of truth for how we position, message, and sell Reeve.
> Update it when the market teaches us something. Don't let it go stale — a strategy doc
> that isn't edited monthly is a strategy nobody is using.
 
**How to use this doc.** Sections 1–2 are the thesis and rarely change. Sections 3–8 are the
working playbook and should churn. Section 9 (Open Questions) is the to-validate list that
drives the next edit. Section 10 is the changelog — append, never overwrite, so we can see how
our thinking moved.
 
---
 
## 1. Positioning thesis (the north star)
 
**Reeve gives a small real-estate operator the full white-collar org chart of an institutional
firm — for less than the cost of one part-time bookkeeper.**
 
We do not sell software, and we do not primarily sell "cheaper property management." We sell
**autonomous labor**: a chief-of-staff agent that triages everything and routes to specialist
desks — Acquisition, Asset Management, Finance & Tax — that do the analyst, underwriter, asset
manager, bookkeeper, and tax-strategist work a 10–100 unit owner could never justify hiring for.
 
The owner keeps the boots (a handyman, a super, the existing maintenance vendor). We replace the
org chart and the overhead above them. For anything that spends money, creates a legal
obligation, or touches a tenant, the agent proposes and the owner approves — autonomy grows as
trust builds.
 
**Pricing:** ~$1,000/mo. **Near-term goal:** 5 paying customers by end of 2026, then raise.
 
---
 
## 2. The market structure (why the wedge exists)
 
There are two worlds, and our buyer lives in the gap between them.
 
**The institutional world** (REPE firms, REITs) organizes the exact labor our agents do into a
clean structure: an **Acquisitions** team that sources, underwrites, negotiates, and closes; an
**Asset Management** team that executes the post-close business plan (leasing, capital projects,
refi/disposition); a **Portfolio Management** layer that rolls performance up to the fund; and
**Capital Markets** for financing. This is our three-desk model almost exactly, with Reeve as the
chief-of-staff/portfolio-manager that stitches it together.
 
**The SMB world** (our buyer, 10–100 units) has none of it. They have themselves, maybe a
sibling, and a property-management (PM) company. They get the org chart's *bottom half*
(operations) from the PM and the *top half* (acquisitions, underwriting, tax strategy, portfolio
analysis) from nobody — they do it on nights and weekends, or not at all.
 
**That gap is the product.** The PM industry covers only the Asset Management desk. Our entire
Acquisition desk and most of our Finance & Tax desk have **no incumbent at all** for this buyer.
Our differentiation is strongest exactly where the PM is absent — which is why we lead with the
investor-side value, not "we'll do tenant comms cheaper."
 
### What the PM company actually covers (and doesn't)
 
The PM fee — nationally ~8.5% of collected rent for small multifamily, practically 8–12%
(ClearLead / MRI, 2026) — buys *operations only*: rent collection, tenant comms, maintenance
coordination, lease enforcement, basic reporting. Leasing and major repairs are typically billed
separately. Acquisition, underwriting, tax strategy, and portfolio-level analysis are out of
scope entirely.
 
| Agent | Real-world role | Who does this for an SMB today? |
|---|---|---|
| Sam (sourcing) | Acquisitions analyst | Nobody — owner, ad hoc |
| Ana (underwriting) | Acquisitions associate | Nobody — owner, in a spreadsheet |
| Cole (LOI/diligence) | Acquisitions VP/Director | Nobody — owner + broker |
| Cara (tenant comms) | Resident-relations / community mgr | **PM** |
| Manny (work orders) | Maintenance coordinator | **PM** (coordinates; vendor executes) |
| Leo (leasing) | Leasing agent | **PM**, often à la carte |
| Bea (bookkeeping) | Property bookkeeper | Owner or fractional bookkeeper |
| Reed (reporting/KPIs) | Asset manager / controller | Nobody |
| Tess (tax) | Tax strategist | Outsourced CPA, reactive |
| Reeve (orchestrator) | Chief of staff / portfolio mgr | Owner's own head |
 
**Takeaway:** sell the empty rows first.
 
---
 
## 3. ICP & wedge
 
**Beachhead ICP:** small-multifamily owner-operators, 10–100 units, who think of themselves as
*investors* (want to grow the portfolio), not just landlords (want to stop the phone ringing).
 
Why this segment:
- Big enough to feel the white-collar gap (they're underwriting deals, watching cash flow, owing
  taxes) but too small to fund any of the institutional roles — even one.
- Too small to build their own centralized back office the way a REIT does (see §6).
- Decision-maker is the buyer, the user, and the budget owner — one person, fast cycle.
**Disqualifiers / not-yet:** passive owners with 1–4 doors (too little pain, will use software);
large operators 250+ units (already have staff and enterprise tooling — later, not the wedge).
 
**Open ICP question → §9:** what % of 10–100-unit owners self-manage vs. use a third-party PM?
This changes who we're really displacing.
 
---
 
## 4. Competitive landscape & framing
 
We sit in a category that doesn't quite exist yet, which is both the opportunity and the messaging
problem. We're compared to four things; here's how we frame against each.
 
**1. The PM company.** Their real moat for a small owner was never the back office — it's the
*truck*: someone who physically shows up, turns a unit, meets the plumber, takes the 2am call.
We can't do that and shouldn't claim to. Frame: *we replace the firm's org chart and overhead,
not its boots.* Keep a cheap local maintenance vendor; let Reeve be the entire white-collar
function above them — the expensive third the PM does worst.
 
**2. Self-managing (the owner's nights and weekends).** If most of our ICP self-manages, *this*
is the real competitor, and the pitch shifts from "cheaper than your PM" to "gives you your
evenings back AND does the acquisition/tax work you keep skipping." Likely our strongest emotional
wedge. Validate the self-manage rate before betting the narrative on it.
 
**3. PropTech software (AppFolio, Buildium, RealPage, Yardi).** They sell *tools the owner still
operates*. We sell *labor that operates the tools*. The line: "Software gives you a dashboard.
Reeve does the work and hands you the decision." Don't position as a better dashboard — that's a
losing, feature-comparison fight against incumbents with 20-year head starts.
 
**4. Horizontal AI (ChatGPT, generic agents) + future RE-specific copycats.** Our moat is the
**safety architecture**, not raw model capability: least-privilege data access, propose-don't-
execute on anything touching money/legal/tenants, a separate execution layer the agent can't
reach, and an immutable audit log. For a buyer whose assets are their net worth, "the AI cannot
unilaterally spend, sign, or message a tenant" is the feature that closes the deal. Lead with
containment, not cleverness.
 
---
 
## 5. Value & ROI argument
 
### The staffing reality we're priced against
Industry rule of thumb: historically ~1 FTE per 100 units; modern benchmark ~1 FTE per 50–75
units, with leaner staffing treated as understaffing (ThePropertyCEO, 2026; D2 Demand). Real
check: post-merger Bryten runs ~1,150 staff over ~47,000 units ≈ 1:41 (BDC Network). But that
ratio only counts *operations* — the investor-side roles aren't in it because SMBs never staff
them.
 
### The honest dollar math (illustrative — refine per real customer)
For a ~50-unit operator the comparison is **not** "$1K/mo vs. the full ~8.5% PM fee," because the
PM also provides physical execution. The credible ROI stack is:
 
- **Replaces** the part-time bookkeeper / admin they'd otherwise hire (~$52K/yr loaded;
  ZipRecruiter, 2026).
- **Provides** acquisitions, asset-management, and tax-strategy capability they currently can't
  afford to hire even one person for (institutional equivalents run $60K–$140K+ each;
  SalaryCube / Quora-illustrative, 2026).
- **Potentially lets them** renegotiate the PM down to a leaner maintenance-only arrangement once
  the back office is covered.
At ~$12K/yr, Reeve undercuts a single fractional hire while doing the work of several. **Frame the
ROI as "the team you can't afford," not "a cheaper version of one role."**
 
### Headline numbers worth memorizing for sales
- PM fee: 8–12% of collected rent, ~8.5% avg small multifamily.
- Bookkeeper: ~$52K/yr. Single-asset PM: ~$60–70K. Portfolio manager: $100K+.
- Staffing ratio: ~1 FTE per 50–75 units (modern), 1:100 (legacy).
- PM turnover ran ~34% in 2025 (BLS via HH Staffing) — the human team they'd build is also
  unstable; Reeve doesn't quit.
---
 
## 6. The tailwind: centralization is already happening
 
Our strongest macro story. Multifamily is mid-wave on **centralization** — pulling work off the
property into specialized offsite teams. Crucially, the functions being centralized are *admin*
(accounting, payments, deposits, collections), while operators are explicitly **not**
centralizing leasing or maintenance (NAA, 2024). And the REITs leading on automation (AvalonBay,
UDR, Equity) can do it only because they're big enough to fund enterprise tech and dense enough to
share staff across nearby properties — conditions almost no non-REIT meets (D2 Demand).
 
Two implications:
1. **We're riding a secular trend, not fighting one.** The industry already agrees the back office
   should leave the property. Reeve is the version a sub-REIT operator can actually buy:
   *centralization-as-a-service for owners too small to build their own.*
2. **The centralization line is our gated/internal line.** What resists going offsite (showing
   units, turning a unit, meeting a vendor) is exactly what our agents *propose* rather than
   execute. What centralizes cleanly (bookkeeping, reporting, underwriting) is our read-heavy,
   ship-early, ACT-INTERNAL surface. The industry's own behavior validates our capability model.
---
 
## 7. Messaging pillars & objection handling
 
### Narrative spine (the one-liner ladder)
- **One line:** "An AI team that runs your portfolio. You approve; it does the work."
- **One paragraph:** the §1 thesis.
- **The reframe that lands:** "You don't have a team to replace — that's the point. Reeve is the
  acquisitions analyst, asset manager, bookkeeper, and tax strategist a 50-unit owner could never
  hire."
### Three pillars
1. **The team you can't afford.** Institutional capability at SMB scale.
2. **Safe with your money by design.** Propose → approve → a separate layer executes. The agent
   has no credentials. Every action is logged. (This is the trust close.)
3. **Grows with you.** Autonomy expands as trust builds; read-only agents ship first, gated
   actions unlock deliberately.
### Objection handling
| Objection | Response |
|---|---|
| "Who fixes the toilet?" | We don't replace your maintenance vendor — we replace the office above them. Keep your handyman; Reeve dispatches and tracks, you approve the spend. |
| "Can I trust AI with my money?" | It can't move money. It proposes; you approve; a separate system executes. No credentials, full audit log. |
| "I already use AppFolio / a PM." | Those are tools and operations. Reeve does the *investor* work neither touches — sourcing, underwriting, tax strategy, portfolio analysis. |
| "What if it's wrong?" | Every output shows its assumptions and flags low confidence. On money/legal/tax it surfaces uncertainty rather than smoothing it. You see the work, not just a verdict. |
| "$1,000/mo is a lot." | It's less than a part-time bookkeeper, and it also does the acquisitions and tax work you're doing at 11pm for free. |
 
---
 
## 8. Go-to-market motion (path to 5 by end of 2026)
 
> Draft — this is the section most likely to change as we learn. Sales owns it.
 
- **Motion:** founder-led, high-touch. We're selling a new category to a skeptical, money-anxious
  buyer — that's demo-and-trust, not self-serve, for the first 5.
- **Channel hypotheses (rank after testing):** investor communities (BiggerPockets, local REIA
  groups, small-multifamily owner forums); Reid's own operator network + the family company as
  reference; X content as top-of-funnel (see x-post voice).
- **Proof asset:** a live underwrite of a *prospect's actual deal* in the first call. Ana's
  deal-analysis artifact is the demo — it shows the work, the assumptions, and a number, on a
  property they care about. Nothing sells the category faster than watching it work on your own
  building.
- **Land:** start a customer on the read-only desks (Ana, Sam, Reed) — no approval infra needed,
  zero risk to them, immediate value. Earn the right to unlock gated actions.
- **First-5 success criteria:** define what "paying and retained" means (not a pilot that
  churns). → §9.
---
 
## 9. Open questions to validate (drives the next edit)
 
- [ ] **Self-manage vs. PM split** among 10–100-unit owners. Determines our real competitor and
      whether the lead message is "cheaper than your PM" or "get your time back." *(Highest
      priority — the GTM narrative hinges on it.)*
- [ ] Which empty-row desk (Acquisition vs. Finance/Tax) is the sharpest *first* hook in a demo?
- [ ] Willingness to pay at $1,000/mo by portfolio size — does it break above/below a unit count?
- [ ] What's the actual trust threshold to unlock the first gated action? Days? One clean
      proposal? A dollar cap?
- [ ] Does "autonomous labor, not software" land with buyers, or do they pattern-match us to
      PropTech anyway and we have to fight on features?
- [ ] Reference-ability: will early customers go on record / give us their deal as a case study?
---
 
## 10. Changelog
 
- **0.1 — 2026-06-04.** Initial draft. Established positioning thesis (§1), two-worlds market
  structure and PM-scope gap (§2), ICP/wedge (§3), competitive framing (§4), ROI stack and
  staffing benchmarks (§5), centralization tailwind (§6), messaging/objections (§7), GTM v0 (§8),
  open-questions list (§9). Sourced from external research on REPE/REIT org structure, multifamily
  staffing ratios, PM fee structures, and the industry centralization trend.
---
 
*Sources behind the figures: WallStreetPrep / M&I / Umbrex (REPE structure); ThePropertyCEO, D2
Demand, NAA, BDC Network (staffing ratios & centralization); MRI, ClearLead, AllPropertyMgmt,
PropRise (PM fees & scope); ZipRecruiter, SalaryCube, Multifamily Dive (compensation). Figures are
benchmarks for argument-building, not audited inputs — verify against a real customer's P&L before
putting a number in a contract.*
