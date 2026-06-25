"""
AEGIS Policy Engine
The governance layer between RCA and autonomous healing.
Decides: auto-heal vs. human approval vs. block — based on confidence + risk.
This is the "safety net" that makes AEGIS production-trustworthy.
"""
from loguru import logger
from src.models import RCAResult, RiskLevel


class PolicyEngine:
    """
    Policy-based decision gate.
    Applies configurable rules to determine if auto-healing is safe.

    Rules:
      - confidence < 60%  → always escalate (not confident enough)
      - risk = high       → always escalate (too risky to auto-act)
      - risk = medium AND confidence >= 85% → auto-heal (confident + acceptable risk)
      - risk = low  AND confidence >= 60% → auto-heal (safe action)
    """

    def __init__(self, config: dict):
        self.min_confidence_auto = config.get("auto_heal_confidence_min", 85)
        self.low_risk_types = set(config.get("low_risk_types", []))
        self.medium_risk_types = set(config.get("medium_risk_types", []))
        self.high_risk_types = set(config.get("high_risk_types", []))

    def should_auto_heal(self, rca: RCAResult) -> tuple[bool, str]:
        """
        Returns (can_auto_heal: bool, reason: str)
        """
        # Rule 1: Never auto-heal if confidence too low
        if rca.confidence < 60:
            reason = f"Confidence {rca.confidence:.0f}% below minimum threshold (60%) — escalating"
            logger.warning(f"[POLICY] Block | {reason}")
            return False, reason

        # Rule 2: Never auto-heal high-risk actions
        if rca.risk_level == RiskLevel.HIGH:
            reason = f"Risk level HIGH — human approval required regardless of confidence"
            logger.warning(f"[POLICY] Block | {reason}")
            return False, reason

        # Rule 3: Medium risk — require high confidence
        if rca.risk_level == RiskLevel.MEDIUM:
            if rca.confidence >= self.min_confidence_auto:
                reason = f"Risk=MEDIUM, Confidence={rca.confidence:.0f}% >= {self.min_confidence_auto}% — auto-healing approved"
                logger.success(f"[POLICY] Approve | {reason}")
                return True, reason
            else:
                reason = f"Risk=MEDIUM, Confidence={rca.confidence:.0f}% below threshold — escalating"
                logger.warning(f"[POLICY] Block | {reason}")
                return False, reason

        # Rule 4: Low risk — auto-heal if confidence acceptable
        if rca.risk_level == RiskLevel.LOW:
            if rca.confidence >= 60:
                reason = f"Risk=LOW, Confidence={rca.confidence:.0f}% — auto-healing approved"
                logger.success(f"[POLICY] Approve | {reason}")
                return True, reason

        reason = "Default policy: escalate for human review"
        return False, reason
