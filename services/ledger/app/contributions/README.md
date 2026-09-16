# Contribution workflow scaffold

This package belongs in the existing `ledger` backend. It will handle the
treasurer's monthly workflow; `app/ledger/` remains responsible for immutable
money postings. These files define places for the next implementation step,
not working endpoints yet.

## Flow

1. `proofs.py`: receive a PDF, photo, screenshot, or payment link. Extract a
   proposed payment date, amount, and reference; suggest a member. Keep the
   original proof and require treasurer review. Confirm receipt against the
   group bank account before accepting the payment.
2. `periods.py`: determine the contribution window. For example, August runs
   from 8 August through 7 September, inclusive. A payment on 8 September is
   in September's window. Store the actual payment date separately from the
   contribution month.
3. `allocation.py`: show the proposed breakdown: payment received, carried
   fines paid, current-month fine (if applicable), contribution credited, and
   fines still outstanding. Let the treasurer confirm it before ledger posting.
4. The ledger records the approved allocation and its source proof. The member
   grid is a view of those records: normal for an ordinary recorded month, red
   for a missed month, and green only when a previously red month is cleared.

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
