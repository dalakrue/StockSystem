"""Local AI Assistant safety question patterns.
No external API. Existing answer logic can import this helper optionally.
"""
SAFETY_QUESTIONS = [
    "Why is this trade unsafe?",
    "What is the main hidden danger now?",
    "Should I trust this prediction?",
    "Why did safety guard change decision?",
    "Is regime becoming old?",
    "Is prediction drift high?",
    "Is this a false confidence situation?",
    "What is the no-trade reason?",
    "What should I check before entry?",
    "Which hour has lowest hidden danger?",
]

def match_safety_question(text: str) -> bool:
    t = str(text or "").lower()
    return any(k in t for k in ["hidden danger", "unsafe", "safety", "no trade", "prediction drift", "false confidence", "regime old", "trust prediction", "danger now"])
