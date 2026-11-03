# Business workspace — CAP-28 first slice

Open **Business** in the desktop footer, or say **“Show business”**. Choose
**New project**, enter name, currency, starting budget, context, goals and product
scenarios. Add products to compare, then **Save and evaluate**. Reopen Business
after restarting to see saved evaluations; **Edit and compare** revises a project.

Context is editable project data, not a global prompt. For the owner's current
exploration, enter Canada, low-inventory private-label technology accessories,
the desired fulfilment arrangement and the actual available budget. Cable kits
are a candidate, not an established business. No supplier agreement is assumed.

## Research and evidence

The bounded workflow defines constraints, organizes manually supplied evidence,
validates inputs, calculates economics, identifies gaps, compares scenarios and
saves the result. It does not run paid web searches. Describe customers/problems,
competitors, differentiation, supplier terms, fulfilment and operational risks.
Evidence records require a claim, provenance and status (assumption, supplied or
contradicted). A source URL is a label, never fetched or treated as an instruction.
Contradictions must be marked by the user; semantic contradiction detection is
not implemented. “Supplied” is not “independently verified.”

Missing costs remain unknown. Enter zero only with a justified assumption. All
figures are assumed to share the selected currency; no exchange conversion.
Quantity is a hypothetical procurement/sales scenario, not forecast demand.
Comparisons show each product independently, not a fabricated best-product score.

## Calculation definitions

Calculations use decimal arithmetic, with displayed amounts rounded half-up to
two decimal places. Inputs allow up to four places; intermediate arithmetic is
not rounded. All selling prices exclude collected sales tax.

- Revenue = price × scenario quantity.
- Gross profit = revenue minus product, inbound shipping, packaging and duties.
- Variable unit costs additionally include fulfilment, outbound shipping,
  transaction fixed/percentage fees, advertising and returns allowance.
- Contribution = revenue minus all modelled variable costs.
- Operating profit before tax = contribution minus fixed setup costs.
- Net profit remains **unknown**. Taxes and unmodelled overhead/regulatory
  obligations are not inferred or asserted to be zero.
- Break-even units = ceiling(fixed costs / positive unit contribution). A zero or
  negative contribution has no attainable break-even under this model.
- Conservative cash required = all scenario variable costs prepaid + fixed
  setup costs. This intentionally overstates upfront cash if fees are deducted
  later; deposits, MOQs, payment timing and working-capital cycles need real terms.
- Sensitivity shows unit contribution if price falls 10% or shipping rises 25%.

Positive contribution is only a reason for further research. Missing inputs,
negative contribution, budget gaps and contradictory evidence are disclosed.
This is scenario arithmetic, not tax advice, an investment recommendation or a
prediction of profitability. No competitor price, quote or demand figure is supplied.

## Boundaries, persistence and recovery

The authenticated local Save action authorizes only writing this project and its
evaluation. Same-origin/session checks apply; unknown action fields are rejected.
No model tool or phone permission is added. Local command replies stay outside
provider history. Privacy-safe history receipts record `business_evaluate`,
outcome and approval, without project names, costs, evidence or raw errors.
Returns are labelled unverified in history because source claims are unverified.

Projects use additive `business_projects` and `business_requests` tables in the
existing local memory database. They are not personal-memory facts, are not
retrieved into model context, and do not generate Task memory proposals. Existing
owner review decisions are untouched. Storage remains plaintext like the existing
memory database: do not enter credentials or sensitive customer/payment records.
Credential-like values are rejected. Keep the database out of Git and exports.

Limits: 100 projects, ten products each, twenty evidence entries per product,
60,000 serialized characters per project and 10,000 retained save request IDs.
At the request limit saves stop rather than evict idempotency protection. Retention
is indefinite in this first slice; project deletion/export UI is a priority follow-up.
SQLite transactions make saves atomic. Same request/input retries are idempotent;
changed inputs with reused IDs and stale edit revisions are rejected. If a response
is lost after saving, retry the same unchanged form. If another window edited it,
reopen Business. No automatic replay or external side effect exists.

Evaluation is bounded arithmetic over at most ten products, so it runs synchronously.
No competing background engine was added. Future network research must register
typed tools and use the established job/authority lifecycle before being enabled.
Shopify, accounting, fulfilment, supplier and customer-support connectors are
extension points only; none is connected. Automatic outreach, purchases, refunds,
advertising spend and storefront changes are explicitly excluded.

## Verification and rollback

```powershell
.venv\Scripts\python.exe -m unittest tests.test_business tests.test_desktop_business
node tests/desktop_business_check.cjs
.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/evaluation
```

Fixtures cover missing cable-kit quotes with a C$500 budget; shipping-destroyed
margin; contradicted evidence; exact arithmetic; malformed and injected inputs;
duplicates/stale edits; restart and SQLite backup/restore; origin/session guards;
private receipts and no provider history. UI uses text nodes and checks duplicate
clicks/retry IDs. These are automated checks, not live market validation.

Quit IRIS before backing up its database. Rolling back to `b4e5c96` ignores the
additive tables, preserving the data for a later upgrade; it does not erase them.
