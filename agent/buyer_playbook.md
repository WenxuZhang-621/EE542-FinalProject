# Buyer playbook

The expert rules the digital clone follows when it drafts follow-ups and answers
questions. Each rule is a short paraphrase, in our own words, of public procurement
guidance, and names its sources.

Format (parsed by `agent/playbook.py`, so keep it exact):

    ## §<n> <short title>
    - Rule: <what the buyer does, one to three sentences>
    - Applies to: <delayed, partial, out_of_stock, price_change, no_reply, or all>
    - Source: <publisher, "title"> — <URL> ; <more sources>
    - Checked: <YYYY-MM-DD>, full text | search excerpts

`Checked` says whether we read the full source or only search excerpts.

## §1 A sent PO is not a confirmed PO
- Rule: Treat an order as open until the supplier acknowledges it, and chase a late acknowledgment instead of waiting for the ship date. Set the waiting window from each supplier's usual response time; one manufacturing example flags orders that are not acknowledged within about three days.
- Applies to: no_reply
- Source: SourceDay, "PO Acknowledgement: The Gap Between Sent and Confirmed Orders" — https://sourceday.com/blog/purchase-order-acknowledgement/ ; Splunk Lantern, "PO Monitoring: Supplier performance on purchase orders process" — https://lantern.splunk.com/Industry_Use_Cases/Manufacturing/PO_Monitoring:_Supplier_performance_on_purchase_orders_process
- Checked: 2026-11-20, search excerpts

## §2 Expedite by exception, watch critical orders early
- Rule: Expediting should be needed on only a few orders. The usual method is to contact the supplier for a revised promise date once a promised date is missed. For critical orders, check status at set intervals so the team hears about a delay early and can work around it.
- Applies to: delayed, no_reply
- Source: Government of the Northwest Territories, Department of Infrastructure, procurement guideline "8.8 Expediting" (2011) — https://www.inf.gov.nt.ca/sites/inf/files/8.8_expediting.pdf
- Checked: 2026-11-20, full text

## §3 Ask for the cause and the recovery plan
- Rule: A new date alone is not enough: ask what is causing the delay and what the supplier's recovery plan is. Agree in writing when and to whom a delay is escalated, and tell the supplier.
- Applies to: delayed
- Source: SupplyChainBrain, "The Importance of Paying Attention to Your Expedite Process" — https://www.supplychainbrain.com/blogs/1-think-tank/post/29111-the-importance-of-paying-attention-to-your-expedite-process
- Checked: 2026-11-20, search excerpts (the page blocks automated reading)

## §4 Options when a supplier is late
- Rule: Either accept the delay with a new schedule, or accept the completed units now and reschedule the rest. In both cases tell everyone who receives the goods, and ask the supplier for something in return, such as price, quantity or service. Cancelling the order for default is the last resort.
- Applies to: delayed, partial
- Source: USPS, Supplying Principles and Practices, 4-2.10 "Delays" — https://about.usps.com/manuals/spp042023/html/spp4_025.htm
- Checked: 2026-11-20, full text

## §5 When to escalate a delay
- Rule: Escalate when the delay is more than four weeks past the estimated delivery date, when it seriously affects a key program, or when there are verified incidents with the order. Share current and expected delays early and openly. (Context: health-product procurement.)
- Applies to: delayed
- Source: The Global Fund, "PPM Escalation Framework for Delayed Orders" (updated 2026-04-07) — https://www.theglobalfund.org/media/nggcw0uo/psm_ppm-delayed-orders-escalation_framework_en.pdf
- Checked: 2026-11-20, full text

## §6 Price increase on an accepted order
- Rule: An accepted order usually keeps the agreed price unless the contract allows changes. Ask whether the increase applies to orders already accepted or only to new ones, keep the quote, PO and acceptance on file, and reply with a firm, polite reminder of the agreed price. To keep the relationship, a common compromise is the old price for this order and the new price from the next one. This is general guidance, not legal advice.
- Applies to: price_change
- Source: Sprintlaw, "When a supplier raises the price after accepting your order" — https://sprintlaw.com.au/articles/supplier-price-increase-after-accepted-order/ ; Michigan Bar Journal — https://www.michbar.org/journal/Details/ArticleID=5063 ; Global Sources, "How to deal with price increases from Chinese suppliers" — https://www.globalsources.com/STM/knowledge/article/how-to-deal-with-price-increases-from-chinese-suppliers/
- Checked: 2026-11-20, search excerpts

## §7 Substitute parts need approval
- Rule: A substitute part must be approved by engineering for this specific use; a matching description does not prove it fits. Prefer alternates that are already approved, and ask the supplier for the spec sheet and compliance documents (for example RoHS and REACH) before approval.
- Applies to: out_of_stock
- Source: SourceDay, "Material Substitution" — https://sourceday.com/blog/material-substitution/ ; Sourceability, "Alternate electronic components are key to avoiding disruption" — https://sourceability.com/post/alternate-electronic-components-are-key-to-avoiding-disruption ; Altium, "Should buyers recommend alternative parts to engineers?" — https://resources.altium.com/p/should-buyers-recommend-alternative-parts-engineers
- Checked: 2026-11-20, search excerpts

## §8 How to write the follow-up
- Rule: Put the PO number in the subject. State the issue in one or two factual sentences, ask for one specific thing (usually a confirmed date) by a set day, and sign with a named contact. Avoid vague wording such as "unforeseen circumstances".
- Applies to: all
- Source: Business-in-a-Box, "Notice of Delayed Shipment" and "Apology and Request for Extension of Time to Deliver Goods" templates — https://www.business-in-a-box.com/template/notice-of-delayed-shipment-D1107 , https://www.business-in-a-box.com/template/apology-and-request-for-extension-of-time-to-deliver-goods-D1094
- Checked: 2026-11-20, search excerpts
