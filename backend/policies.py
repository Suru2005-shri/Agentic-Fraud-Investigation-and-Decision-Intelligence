"""Hacker House Goa Fraud Policy 1.0, copied into the agent's policy store."""

POLICIES=[
("R1","Verify before you block on a weak signal",
 "If the case rests on a single signal, including a risk score alone, and assessed fraud probability is below 0.70, recommend VERIFY_WITH_CUSTOMER or STEP_UP_AUTH before any block. Blocking on one signal is prohibited."),
("R2","Customer denies the transaction",
 "Recommend BLOCK_CARD and CREATE_CASE. Add FILE_REPORT when exposure exceeds $1,000 or the case connects to a shared device profile or another customer's fraud."),
("R3","Customer confirms the transaction",
 "Recommend CLOSE_NO_FRAUD and record the confirmation."),
("R4","No reply within 24 hours",
 "Recommend MONITOR_CARD and DECLINE_TRANSACTION for pending authorizations. Escalate if exposure exceeds $500."),
("R5","Card testing",
 "Three or more small online authorizations on one card within one hour followed by a larger purchase: recommend DECLINE_TRANSACTION and STEP_UP_AUTH. If a purchase over $100 has already cleared, recommend BLOCK_CARD."),
("R6","Shared origin",
 "When several cards show fraud from the same device profile, billing region, or recipient email in one window, name the shared element, recommend CREATE_CASE and FILE_REPORT, and MONITOR_CONNECTED_CARDS for every connected card."),
("R7","Disputed but legitimate",
 "When the customer disputes a charge that matches their own recurring pattern, recommend CREATE_CASE, VERIFY_WITH_CUSTOMER and WARN_CUSTOMER. Do not block."),
("R8","Escalate when uncertain and exposed",
 "If the verdict is uncertain and exposure exceeds $500, or evidence conflicts, recommend ESCALATE_TO_ANALYST."),
("R9","Undocumented patterns",
 "When activity fits none of the known patterns but evidence shows coordinated or repeated abuse across customers, recommend CREATE_CASE, FILE_REPORT and ESCALATE_TO_ANALYST. Do not force it into a known category."),
("R10","Never block all cards",
 "Never recommend BLOCK_ALL_CARDS unless at least two of the customer's cards show confirmed fraud or the customer's credentials are confirmed compromised.")
]

TYPOLOGIES={
"card_testing":("T-01",["R5"]),
"card_not_present_fraud":("T-02",["R1","R2"]),
"card_not_present_new_device":("T-03",["R1","R2"]),
"out_of_region_use":("T-04",["R2","R3"]),
"account_takeover":("T-05",["R2","R8"]),
"undocumented":("T-06",["R6","R9"]),
"none":("T-00",["R1","R3"]),
}
