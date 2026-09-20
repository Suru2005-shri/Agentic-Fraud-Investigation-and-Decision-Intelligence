"""Sample policy and typology content used for retrieval.

This is demonstration text, not a real institution's policy. Replace it with the
challenge policy dataset (see docs/INTEGRATION.md).
"""

POLICIES = [
    ("4.2", "Customer validation before intervention",
     "Where a payment above 50,000 rupees originates from a device linked to more than one unrelated account, "
     "the investigator must establish customer authorization before the payment is blocked. Authorization may be "
     "established by direct customer validation, step-up authentication, or a documented analyst information request."),
    ("4.3", "Step-up authentication",
     "Step-up authentication should be requested when the customer cannot be reached directly or when the device is "
     "not recognised, for example after a login from an unseen device. A failed challenge is treated as adverse evidence."),
    ("5.1", "Low-risk release",
     "Payments assessed as low risk, with no linked accounts, no similar prior cases and no first-time high-value "
     "merchant, may be released with monitoring without customer validation."),
    ("5.2", "Velocity and card testing",
     "A burst of small payments to new payees or merchants followed by a large payment indicates card testing. Hold the "
     "sequence and request customer validation before releasing further payments."),
    ("6.1", "Human approval",
     "Blocking a payment, escalating a case to the fraud team, or filing a report requires approval from a human "
     "approver. Monitoring, warning the customer, and release with monitoring may be applied by the agent."),
    ("6.4", "Escalation criteria",
     "Escalate to a fraud analyst when risk is 75 or higher and the customer denies the transaction, or when evidence "
     "remains insufficient after every evidence request has been used."),
    ("7.3", "Case memory",
     "Every resolved case is recorded with its evidence, decision, action, approval and outcome so that it can inform "
     "later investigations."),
    ("8.2", "Mule accounts and shared devices",
     "Several unrelated accounts sharing one device, especially with rapid cash-out to gift card, forex or prepaid "
     "merchants, indicates a mule ring. Review every linked account and the cases already recorded against them."),
]

# fraud pattern -> (typology id, related policy sections)
TYPOLOGIES = {
    "Shared-device mule ring": ("T-07", ["4.2", "8.2", "6.1"]),
    "Account takeover": ("T-02", ["4.3", "4.2"]),
    "Card-testing burst": ("T-04", ["5.2", "4.2"]),
    "Synthetic identity": ("T-05", ["8.2", "6.4"]),
    "Rapid cash-out": ("T-06", ["8.2", "4.2"]),
    "Social-engineering payment": ("T-03", ["4.2", "4.3"]),
    "Velocity spike": ("T-08", ["5.2"]),
    "First-time high-value merchant": ("T-09", ["4.2", "5.1"]),
    "Shared-device false positive": ("T-10", ["5.1", "4.2"]),
    "Travel anomaly": ("T-11", ["4.3", "5.1"]),
    "Chargeback cluster": ("T-12", ["6.4"]),
}
