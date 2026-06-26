"""
AEGIS MailSenderAgent
Non-blocking email notifications at each stage of the healing lifecycle.

Notification Stages:
1. initial_health_check: All jobs healthy ✅ or Failures detected ⚠️
2. failure_alert: Detailed failure notification with error traces
3. fix_in_progress: GPT-4o notebook repair started
4. fix_complete: Job fixed and running successfully
5. pr_raised: PR created, awaiting manual approval
6. deployment_complete: CD pipeline finished, all good
"""
import os
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from loguru import logger
from typing import Dict, List, Optional


_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


class MailSenderAgent:
    """
    Non-blocking email notification agent.
    Fires asyncio tasks so emails don't block critical healing.
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
            logger.warning("[MailSender] Gmail not configured — emails will be logged only")
        else:
            logger.info(f"[MailSender] Initialized | recipients={self.recipients}")

    async def send_stage(self, stage: str, data: Dict) -> bool:
        """
        Send notification for a specific stage (non-blocking).
        
        Stages:
        - initial_health_check
        - failure_alert
        - fix_in_progress
        - fix_complete
        - pr_raised
        - deployment_complete
        """
        logger.info(f"[MailSender] Sending stage: {stage}")
        
        if stage == "initial_health_check":
            return await self._send_initial_health_check(data)
        elif stage == "failure_alert":
            return await self._send_failure_alert(data)
        elif stage == "fix_in_progress":
            return await self._send_fix_in_progress(data)
        elif stage == "fix_complete":
            return await self._send_fix_complete(data)
        elif stage == "pr_raised":
            return await self._send_pr_raised(data)
        elif stage == "deployment_complete":
            return await self._send_deployment_complete(data)
        else:
            logger.warning(f"[MailSender] Unknown stage: {stage}")
            return False

    # ─── Stage 1: Initial Health Check ──────────────────────────────────────

    async def _send_initial_health_check(self, data: Dict) -> bool:
        """
        data: {
            "healthy_count": int,
            "failed_count": int,
            "job_health_reports": List[Dict]
        }
        """
        healthy = data.get("healthy_count", 0)
        failed = data.get("failed_count", 0)
        
        if failed == 0:
            subject = "[AEGIS] ✅ All Jobs Healthy"
            body = f"AEGIS Health Check:\n\n✅ All {healthy} monitored jobs are healthy.\n\nNo action required."
            html = self._build_html("✅ All Jobs Healthy", body, "#2ecc71")
        else:
            subject = f"[AEGIS] ⚠️ {failed} Job(s) Failed"
            body = f"AEGIS Health Check:\n\n⚠️ {failed} job(s) failed out of {healthy + failed} monitored.\n\nAEGIS will now attempt auto-healing..."
            html = self._build_html("⚠️ Failures Detected", body, "#e74c3c")
        
        return await self._send_email(subject, body, html)

    # ─── Stage 2: Failure Alert ─────────────────────────────────────────────

    async def _send_failure_alert(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_name": str,
            "error_summary": str,
            "root_cause": str,
            "confidence": float
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_name = data.get("job_name", "Unknown Job")
        error = data.get("error_summary", "No error details")[:500]
        root_cause = data.get("root_cause", "Analyzing...")
        confidence = data.get("confidence", 0)
        
        subject = f"[AEGIS] ⚠️ Failure Detected | {incident_id} | {job_name}"
        body = (
            f"Incident ID: {incident_id}\n"
            f"Job: {job_name}\n\n"
            f"Error:\n{error}\n\n"
            f"Root Cause (GPT-4o analysis):\n{root_cause}\n"
            f"Confidence: {confidence:.0f}%\n\n"
            f"AEGIS is now attempting autonomous repair..."
        )
        html = self._build_html("⚠️ Failure Detected", body, "#e74c3c")
        return await self._send_email(subject, body, html)

    # ─── Stage 3: Fix in Progress ───────────────────────────────────────────

    async def _send_fix_in_progress(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_name": str,
            "notebooks_to_fix": List[str]
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_name = data.get("job_name", "Unknown Job")
        notebooks = data.get("notebooks_to_fix", [])
        
        subject = f"[AEGIS] 🔧 Fixing {incident_id} | {job_name}"
        body = (
            f"AEGIS is autonomously fixing the failure.\n\n"
            f"Incident: {incident_id}\n"
            f"Job: {job_name}\n"
            f"Notebooks being fixed by GPT-4o:\n"
        )
        for nb in notebooks:
            body += f"  - {nb}\n"
        body += "\nYou will receive another email when the fix is complete."
        
        html = self._build_html("🔧 Fix in Progress", body, "#3498db")
        return await self._send_email(subject, body, html)

    # ─── Stage 4: Fix Complete ──────────────────────────────────────────────

    async def _send_fix_complete(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_name": str,
            "post_fix_run_id": int,
            "mttr_seconds": float
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_name = data.get("job_name", "Unknown Job")
        run_id = data.get("post_fix_run_id", 0)
        mttr = data.get("mttr_seconds", 0)
        
        mttr_str = f"{mttr:.0f}s" if mttr < 120 else f"{mttr / 60:.1f} min"
        
        subject = f"[AEGIS] ✅ Fixed {incident_id} | {job_name}"
        body = (
            f"AEGIS successfully fixed the failure.\n\n"
            f"Incident: {incident_id}\n"
            f"Job: {job_name}\n"
            f"Post-fix run ID: {run_id}\n"
            f"MTTR: {mttr_str}\n\n"
            f"✅ Job is now running successfully.\n\n"
            f"Next: AEGIS will create a PR with the fix for your review."
        )
        html = self._build_html("✅ Fix Complete", body, "#2ecc71")
        return await self._send_email(subject, body, html)

    # ─── Stage 5: PR Raised ─────────────────────────────────────────────────

    async def _send_pr_raised(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "pr_url": str,
            "pr_number": int
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        pr_url = data.get("pr_url", "")
        pr_number = data.get("pr_number", 0)
        
        subject = f"[AEGIS] 📝 PR #{pr_number} Raised | {incident_id} | Awaiting Manual Approval"
        body = (
            f"AEGIS has created a pull request with the fix.\n\n"
            f"Incident: {incident_id}\n"
            f"PR: #{pr_number}\n"
            f"URL: {pr_url}\n\n"
            f"⏳ Please review and approve the PR.\n\n"
            f"Once merged, AEGIS will trigger CD to redeploy the bundle.\n"
            f"You will receive a final email when redeployment is complete."
        )
        html = self._build_html("📝 PR Raised — Awaiting Approval", body, "#f39c12")
        return await self._send_email(subject, body, html)

    # ─── Stage 6: Deployment Complete ───────────────────────────────────────

    async def _send_deployment_complete(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "workflow_run_url": str,
            "healthy_count": int
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        workflow_url = data.get("workflow_run_url", "")
        healthy = data.get("healthy_count", 0)
        
        subject = f"[AEGIS] 🎉 Deployment Complete | {incident_id} | All Good"
        body = (
            f"AEGIS has successfully redeployed your DAB bundle.\n\n"
            f"Incident: {incident_id}\n"
            f"Workflow: {workflow_url}\n"
            f"Status: ✅ All {healthy} jobs are now healthy.\n\n"
            f"🎉 Your system is fully recovered and in sync with GitOps."
        )
        html = self._build_html("🎉 Deployment Complete — All Good", body, "#2ecc71")
        return await self._send_email(subject, body, html)

    # ─── Helper: Send Email ─────────────────────────────────────────────────

    async def _send_email(self, subject: str, body: str, html: str) -> bool:
        """Non-blocking email send via asyncio.to_thread()."""
        if not self.enabled:
            logger.info(f"[MailSender] Email not sent (not configured): {subject}")
            logger.info(f"[MailSender] Body:\n{body}")
            return False
        
        # Fire email in background thread (non-blocking)
        try:
            await asyncio.to_thread(self._send_smtp, subject, body, html)
            logger.success(f"[MailSender] Email sent: {subject}")
            return True
        except Exception as e:
            logger.error(f"[MailSender] Email failed: {e}")
            return False

    def _send_smtp(self, subject: str, body: str, html: str):
        """Synchronous SMTP send (runs in thread pool)."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"AEGIS Reliability Agent <{self.sender}>"
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html, "html"))
        
        import time
        for attempt in range(1, 3):
            try:
                with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(self.sender, self.app_password)
                    smtp.sendmail(self.sender, self.recipients, msg.as_string())
                return
            except smtplib.SMTPAuthenticationError:
                logger.error("[MailSender] SMTP auth failed")
                raise
            except (smtplib.SMTPException, OSError) as e:
                logger.warning(f"[MailSender] SMTP attempt {attempt}/2 failed: {e}")
                if attempt < 2:
                    time.sleep(3)
            except Exception as e:
                logger.error(f"[MailSender] SMTP unexpected error: {e}")
                raise
        raise Exception("All SMTP attempts failed")

    def _build_html(self, title: str, body: str, color: str) -> str:
        """Build HTML email body."""
        body_escaped = body.replace("<", "&lt;").replace(">", "&gt;")
        return f"""
<!DOCTYPE html><html><body style="background:#0e1117;font-family:Arial,sans-serif;color:#e0e0e0;padding:30px;">
<div style="max-width:620px;margin:auto;background:#1c1f26;border-radius:12px;padding:28px;border:3px solid {color};">
  <h2 style="color:{color};margin-top:0;">🛡️ {title}</h2>
  <pre style="background:#0e1117;color:#a0cfff;padding:16px;border-radius:8px;white-space:pre-wrap;font-size:13px;">{body_escaped}</pre>
  <p style="color:#555;font-size:11px;margin-bottom:0;">AI-Engine for Guardian Intelligence &amp; Self-healing</p>
</div></body></html>"""
