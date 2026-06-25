"""
AEGIS Gmail Notifier
Sends HTML incident report emails via Gmail SMTP.
Uses Python stdlib smtplib — no extra packages required.

Setup:
  1. Enable 2-Step Verification on your Google account.
  2. Go to Google Account → Security → App Passwords → create one for "AEGIS".
  3. Set GMAIL_SENDER, GMAIL_APP_PASSWORD, GMAIL_RECIPIENTS in .env
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from loguru import logger

from src.models import IncidentReport

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def _risk_color(risk: str) -> str:
    return {"low": "#2ecc71", "medium": "#f39c12", "high": "#e74c3c"}.get(risk.lower(), "#7f8c8d")


def _status_badge(auto_healed: bool) -> str:
    if auto_healed:
        return '<span style="background:#2ecc71;color:#fff;padding:3px 10px;border-radius:12px;font-weight:bold;">✅ AUTO-HEALED</span>'
    return '<span style="background:#e74c3c;color:#fff;padding:3px 10px;border-radius:12px;font-weight:bold;">⚠️ ESCALATED</span>'


def _build_html(report: IncidentReport) -> str:
    risk_color = _risk_color(report.risk_level)
    mttr = f"{report.mttr_seconds:.0f}s" if report.mttr_seconds < 120 else f"{report.mttr_seconds / 60:.1f} min"
    pr_row = (
        f'<tr><td style="color:#888;">Hotfix PR</td>'
        f'<td><a href="{report.pr_url}" style="color:#3498db;">{report.pr_url}</a></td></tr>'
        if report.pr_url else ""
    )
    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0e1117;font-family:Arial,sans-serif;color:#e0e0e0;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0e1117;">
  <tr><td align="center" style="padding:30px 0;">
    <table width="620" cellpadding="0" cellspacing="0"
           style="background:#1c1f26;border-radius:12px;overflow:hidden;border:1px solid #2d3139;">

      <!-- Header -->
      <tr>
        <td style="background:#1a1d27;padding:24px 30px;border-bottom:3px solid {risk_color};">
          <h1 style="margin:0;font-size:22px;color:#fff;">
            🛡️ AEGIS Incident Report
          </h1>
          <p style="margin:6px 0 0;color:#888;font-size:13px;">
            AI-Engine for Guardian Intelligence &amp; Self-healing
          </p>
        </td>
      </tr>

      <!-- Status bar -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;">
          <table width="100%">
            <tr>
              <td>{_status_badge(report.auto_healed)}</td>
              <td align="right" style="color:#aaa;font-size:13px;">
                {report.timestamp.strftime("%Y-%m-%d %H:%M UTC")}
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Key metrics -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;">
          <table width="100%" cellspacing="0">
            <tr>
              <td style="width:25%;text-align:center;padding:12px;background:#0e1117;border-radius:8px;">
                <div style="font-size:22px;font-weight:bold;color:#fff;">{mttr}</div>
                <div style="font-size:11px;color:#888;margin-top:4px;">MTTR</div>
              </td>
              <td style="width:4%;"></td>
              <td style="width:25%;text-align:center;padding:12px;background:#0e1117;border-radius:8px;">
                <div style="font-size:22px;font-weight:bold;color:{risk_color};">
                  {report.risk_level.upper()}
                </div>
                <div style="font-size:11px;color:#888;margin-top:4px;">Risk Level</div>
              </td>
              <td style="width:4%;"></td>
              <td style="width:25%;text-align:center;padding:12px;background:#0e1117;border-radius:8px;">
                <div style="font-size:22px;font-weight:bold;color:#3498db;">
                  {report.confidence:.0f}%
                </div>
                <div style="font-size:11px;color:#888;margin-top:4px;">RCA Confidence</div>
              </td>
              <td style="width:4%;"></td>
              <td style="width:25%;text-align:center;padding:12px;background:#0e1117;border-radius:8px;">
                <div style="font-size:22px;font-weight:bold;color:#9b59b6;">
                  {'AUTO' if report.auto_healed else 'HUMAN'}
                </div>
                <div style="font-size:11px;color:#888;margin-top:4px;">Resolution</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Details table -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;">
          <table width="100%" style="font-size:13px;border-collapse:collapse;">
            <tr>
              <td style="color:#888;padding:7px 0;width:140px;">Incident ID</td>
              <td style="color:#fff;font-family:monospace;">{report.incident_id}</td>
            </tr>
            <tr>
              <td style="color:#888;padding:7px 0;">Job</td>
              <td style="color:#fff;font-family:monospace;">{report.job_name}</td>
            </tr>
            {pr_row}
          </table>
        </td>
      </tr>

      <!-- RCA -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;">
          <p style="margin:0 0 8px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;">
            Root Cause
          </p>
          <p style="margin:0;color:#fff;font-size:14px;line-height:1.6;">{report.root_cause}</p>
        </td>
      </tr>

      <!-- Action -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;">
          <p style="margin:0 0 8px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;">
            Action Taken
          </p>
          <p style="margin:0;color:#fff;font-size:14px;line-height:1.6;">{report.action_taken}</p>
        </td>
      </tr>

      <!-- Outcome -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;">
          <p style="margin:0 0 8px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;">
            Outcome
          </p>
          <p style="margin:0;color:#fff;font-size:14px;line-height:1.6;">{report.outcome}</p>
        </td>
      </tr>

      <!-- Prevention -->
      <tr>
        <td style="padding:20px 30px;border-bottom:1px solid #2d3139;
                   background:linear-gradient(135deg,#0d2b1a,#1c1f26);">
          <p style="margin:0 0 8px;font-size:12px;color:#2ecc71;text-transform:uppercase;letter-spacing:1px;">
            🔒 Prevention Recommendation
          </p>
          <p style="margin:0;color:#c8f7d8;font-size:14px;line-height:1.6;">
            {report.prevention_recommendation}
          </p>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="padding:16px 30px;text-align:center;">
          <p style="margin:0;font-size:11px;color:#555;">
            This report was generated autonomously by AEGIS &nbsp;·&nbsp;
            Governed AI Reliability Agent &nbsp;·&nbsp;
            {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>
"""


class GmailNotifier:
    """
    Sends HTML incident report emails via Gmail SMTP (TLS on port 587).
    Requires a Gmail App Password — NOT the account password.

    Env vars:
        GMAIL_SENDER        — from address, e.g. aegis-alerts@gmail.com
        GMAIL_APP_PASSWORD  — 16-char App Password from Google Account settings
        GMAIL_RECIPIENTS    — comma-separated to addresses
    """

    def __init__(self):
        self.sender = os.environ.get("GMAIL_SENDER", "")
        self.app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        self.recipients = [
            r.strip()
            for r in os.environ.get("GMAIL_RECIPIENTS", "").split(",")
            if r.strip()
        ]
        self.enabled = bool(self.sender and self.app_password and self.recipients)
        if not self.enabled:
            logger.info("[GMAIL] Credentials not set — email notifications disabled")

    async def send(self, report: IncidentReport) -> bool:
        """Send HTML incident email. Returns True on success."""
        if not self.enabled:
            return False

        subject = (
            f"[AEGIS] {'✅ Auto-Healed' if report.auto_healed else '⚠️ Escalated'} "
            f"| {report.incident_id} | {report.job_name} | MTTR {report.mttr_seconds:.0f}s"
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"AEGIS Reliability Agent <{self.sender}>"
        msg["To"] = ", ".join(self.recipients)

        # Plain-text fallback
        plain = (
            f"AEGIS Incident Report\n"
            f"{'='*50}\n"
            f"Incident  : {report.incident_id}\n"
            f"Job       : {report.job_name}\n"
            f"Status    : {'Auto-Healed' if report.auto_healed else 'Escalated'}\n"
            f"MTTR      : {report.mttr_seconds:.0f}s\n"
            f"Risk      : {report.risk_level.upper()}\n"
            f"Confidence: {report.confidence:.0f}%\n\n"
            f"Root Cause:\n{report.root_cause}\n\n"
            f"Action Taken:\n{report.action_taken}\n\n"
            f"Outcome:\n{report.outcome}\n\n"
            f"Prevention:\n{report.prevention_recommendation}\n"
        )

        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(_build_html(report), "html"))

        import time
        for attempt in range(1, 3):
            try:
                with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(self.sender, self.app_password)
                    smtp.sendmail(self.sender, self.recipients, msg.as_string())
                logger.success(f"[GMAIL] Email sent to {self.recipients}")
                return True
            except smtplib.SMTPAuthenticationError:
                logger.error(
                    "[GMAIL] Authentication failed — ensure GMAIL_APP_PASSWORD is a valid "
                    "App Password (not your account password). "
                    "Generate one at: Google Account → Security → App Passwords"
                )
                return False
            except (smtplib.SMTPException, OSError) as e:
                logger.warning(f"[GMAIL] Attempt {attempt}/2 failed: {e}")
                if attempt < 2:
                    time.sleep(3)
            except Exception as e:
                logger.error(f"[GMAIL] Unexpected error: {e}")
                return False
        logger.error("[GMAIL] All send attempts failed")
        return False
