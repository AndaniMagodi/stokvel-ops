# Treasurer contribution workflow

This is the next product workflow to implement in the existing backend.
The ledger package remains responsible for immutable money postings.
The date-window, amount-allocation, and manual preview/confirmation code live in
`services/ledger/app/contributions/`. POP file upload and extraction remain future work.

## Flow

1. Proof review: receive a PDF, photo, screenshot, or payment link. Extract a
   proposed payment date, amount, and reference; suggest a member. Keep the
   original proof and require treasurer review. Confirm receipt against the
   group bank account before accepting the payment.
2. Contribution window: August runs from 8 August through 7 September,
   inclusive. A payment on 8 September is in September's window. Store the
   actual payment date separately from the contribution month.
3. Allocation preview: show the proposed breakdown: payment received, carried
   fines paid, current-month fine (if applicable), contribution credited, and
   fines still outstanding. Apply old fines to missed months oldest first; a
   month becomes green only when its fine is fully cleared. Let the treasurer
   confirm the preview before ledger posting.
4. The ledger records the approved allocation and its proof key. The member
   grid is a view of those records: normal for an ordinary recorded month, red
   for a missed month, and green only when a previously red month is cleared.

The current API supports one confirmed payment per member per contribution
month. Split payments require another rule before they can be safely automated.

## Confirmed rules

- The contribution window for month M is the 8th of M through the 7th of M+1.
- An unpaid month becomes missed after its window closes.
- Each missed month adds R100. Unpaid fines carry forward.
- Fines are deducted before the remaining amount is credited as a contribution.
- If that remaining amount is below the R300 minimum, another R100 is deducted
  as a fine. The treasurer's example: R600 paid with four missed months gives
  R400 in carried fines, R100 in the minimum-rule fine, and R100 credited.

Before implementing edge cases, confirm how to handle a remaining amount below
R100 and whether partial settlement changes a missed month's colour.

Do not place real member details, bank account numbers, or uploaded POPs in the
repository or test fixtures.
