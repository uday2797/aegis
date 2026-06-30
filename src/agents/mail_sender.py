"""
AEGIS MailSenderAgent
Non-blocking email notifications at each stage of the healing lifecycle.

Notification Stages:
1. initial_health_check: All jobs healthy ✅ or Failures detected ⚠️
2. failure_alert: Detailed failure notification with error traces
3. fix_in_progress: GPT-5.5 notebook repair started
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
_SMTP_PORT = 465  # Use SSL port instead of STARTTLS


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
        - final_confirmation
        - deployment_failed
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
        elif stage == "final_confirmation":
            return await self._send_final_confirmation(data)
        elif stage == "deployment_failed":
            return await self._send_deployment_failed(data)
        elif stage == "escalation":
            return await self._send_escalation(data)
        elif stage == "ml_drift_alert":
            return await self._send_ml_drift_alert(data)
        elif stage == "ml_healing_complete":
            return await self._send_ml_healing_complete(data)
        elif stage == "ml_healing_failed":
            return await self._send_ml_healing_failed(data)
        else:
            logger.warning(f"[MailSender] Unknown stage: {stage}")
            return False

    # ─── Stage 1: Initial Health Check ──────────────────────────────────────

    async def _send_initial_health_check(self, data: Dict) -> bool:
        """
        data: {
            "healthy_count": int,
            "failed_count": int,
            "job_health_reports": List[Dict],
            "model_health_reports": List[Dict]
        }
        """
        healthy = data.get("healthy_count", 0)
        failed = data.get("failed_count", 0)
        job_reports = data.get("job_health_reports", [])
        model_reports = data.get("model_health_reports", [])
        total = healthy + failed

        # ── Build job status table ───────────────────────────────────────
        job_lines = []
        for r in job_reports:
            icon = "✅" if r.get("status") == "healthy" else ("❌" if r.get("status") == "failed" else "⏳")
            name = r.get("job_name", r.get("job_id", "Unknown"))[:55]
            status = r.get("status", "unknown").upper()
            job_lines.append(f"  {icon}  {name:<55}  {status}")

        job_table = "\n".join(job_lines) if job_lines else "  (no jobs monitored)"

        # ── Build model health summary ───────────────────────────────────
        model_lines = []
        for m in model_reports:
            icon = "✅" if m.get("status") == "healthy" else "⚠️"
            name = m.get("model_name", "unknown")
            acc = m.get("current_accuracy", 0)
            psi = m.get("psi_score", 0)
            alert = m.get("alert") or f"accuracy={acc:.1%}, PSI={psi:.3f}"
            model_lines.append(f"  {icon}  {name}: {alert}")

        model_section = ""
        if model_lines:
            model_section = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🤖 ML MODEL HEALTH:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(model_lines)
            )

        if failed == 0:
            subject = f"[AEGIS] ✅ Health Check Complete | {total} Job(s) Healthy"
            body = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ AEGIS HEALTH CHECK — ALL CLEAR\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ {healthy} job(s) monitored — all healthy\n\n"
                f"JOB STATUS:\n"
                f"{job_table}"
                f"{model_section}\n\n"
                f"No action required. AEGIS continues monitoring."
            )
            html = self._build_html("✅ All Systems Healthy", body, "#2ecc71")
        else:
            failed_names = [r.get("job_name", r.get("job_id", "?")) for r in job_reports if r.get("status") == "failed"]
            subject = f"[AEGIS] ⚠️ {failed} Job(s) Failed — Auto-Healing Started"
            body = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️  AEGIS HEALTH CHECK — FAILURES DETECTED\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"❌ {failed} FAILED  |  ✅ {healthy} HEALTHY  |  📊 {total} TOTAL\n\n"
                f"FAILED JOB(S):\n"
                f"  {chr(10).join('  • ' + n for n in failed_names)}\n\n"
                f"ALL JOB STATUS:\n"
                f"{job_table}"
                f"{model_section}\n\n"
                f"🔧 AEGIS is now starting autonomous repair using GPT-5.5...\n"
                f"You will receive a failure analysis email shortly."
            )
            html = self._build_html("⚠️ Failures Detected — Auto-Healing Started", body, "#e74c3c")

        return await self._send_email(subject, body, html)

    # ─── Stage 2: Failure Alert ─────────────────────────────────────────────

    async def _send_failure_alert(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_id": str,
            "job_name": str,
            "error_summary": str,
            "root_cause": str,
            "confidence": float
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_id = data.get("job_id", "N/A")
        job_name = data.get("job_name", "Unknown Job")
        error = data.get("error_summary", "No error details")[:800]
        root_cause = data.get("root_cause", "Analyzing...")
        confidence = data.get("confidence", 0)
        
        subject = f"[AEGIS] ⚠️ Failure Detected | {incident_id} | {job_name}"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 FAILURE DETECTED\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 Incident ID: {incident_id}\n"
            f"🆔 Job ID: {job_id}\n"
            f"📦 Job Name: {job_name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ ERROR SUMMARY:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{error}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 ROOT CAUSE (GPT-5.5 Analysis):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{root_cause}\n"
            f"Confidence: {confidence:.0f}%\n\n"
            f"🔧 AEGIS is now attempting autonomous repair using GPT-5.5..."
        )
        html = self._build_html("⚠️ Failure Detected", body, "#e74c3c")
        return await self._send_email(subject, body, html)

    # ─── Stage 3: Fix in Progress ───────────────────────────────────────────

    async def _send_fix_in_progress(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_id": str,
            "job_name": str,
            "notebooks_to_fix": List[str]
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_id = data.get("job_id", "N/A")
        job_name = data.get("job_name", "Unknown Job")
        notebooks = data.get("notebooks_to_fix", [])
        
        subject = f"[AEGIS] 🔧 Fixing {incident_id} | {job_name}"
        body = (
            f"🔧 AEGIS is autonomously fixing the failure using GPT-5.5\n\n"
            f"📋 Incident: {incident_id}\n"
            f"🆔 Job ID: {job_id}\n"
            f"📦 Job: {job_name}\n\n"
            f"📓 Notebooks being analyzed and fixed by GPT-5.5:\n"
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

    # ─── Stage 7: Final Confirmation (Post-Deployment Verified) ─────────────

    async def _send_final_confirmation(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_id": str,
            "job_name": str,
            "pr_url": str,
            "workflow_run_url": str,
            "post_deployment_healthy": bool,
            "mttr_seconds": float
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_id = data.get("job_id", "N/A")
        job_name = data.get("job_name", "Unknown Job")
        pr_url = data.get("pr_url", "")
        workflow_url = data.get("workflow_run_url", "")
        mttr = data.get("mttr_seconds", 0)
        
        subject = f"[AEGIS] ✅ COMPLETE | {incident_id} | Job Verified Healthy"
        body = (
            f"═══════════════════════════════════════\n"
            f"✅ AUTONOMOUS HEALING COMPLETE\n"
            f"═══════════════════════════════════════\n\n"
            f"📋 Incident: {incident_id}\n"
            f"🆔 Job ID: {job_id}\n"
            f"📦 Job: {job_name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 FULL CYCLE COMPLETED:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"1. ✅ Error detected and analyzed (GPT-5.5)\n"
            f"2. ✅ Notebooks repaired autonomously\n"
            f"3. ✅ PR created and merged: {pr_url}\n"
            f"4. ✅ CD workflow deployed: {workflow_url}\n"
            f"5. ✅ Post-deployment verification: HEALTHY\n\n"
            f"⏱️ Total MTTR: {mttr:.0f} seconds ({mttr/60:.1f} minutes)\n\n"
            f"🎉 Your system is fully operational. No further action required.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"AEGIS - Autonomous Excellence Guardian & Intelligent System"
        )
        html = self._build_html("✅ Healing Complete — Verified Healthy", body, "#27ae60")
        return await self._send_email(subject, body, html)

    # ─── Stage 8: Deployment Failed (Post-Deployment Still Unhealthy) ───────

    async def _send_deployment_failed(self, data: Dict) -> bool:
        """
        data: {
            "incident_id": str,
            "job_id": str,
            "job_name": str,
            "pr_url": str,
            "workflow_run_url": str
        }
        """
        incident_id = data.get("incident_id", "UNKNOWN")
        job_id = data.get("job_id", "N/A")
        job_name = data.get("job_name", "Unknown Job")
        pr_url = data.get("pr_url", "")
        workflow_url = data.get("workflow_run_url", "")
        
        subject = f"[AEGIS] ⚠️ ESCALATION | {incident_id} | Post-Deployment Still Failing"
        body = (
            f"═══════════════════════════════════════\n"
            f"⚠️ MANUAL INTERVENTION REQUIRED\n"
            f"═══════════════════════════════════════\n\n"
            f"📋 Incident: {incident_id}\n"
            f"🆔 Job ID: {job_id}\n"
            f"📦 Job: {job_name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ POST-DEPLOYMENT VERIFICATION FAILED\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"AEGIS completed the autonomous healing cycle:\n"
            f"1. ✅ Error detected and analyzed\n"
            f"2. ✅ Notebooks repaired by GPT-5.5\n"
            f"3. ✅ PR merged: {pr_url}\n"
            f"4. ✅ CD deployed: {workflow_url}\n"
            f"5. ❌ Post-deployment health check: STILL FAILING\n\n"
            f"🚨 The automated fix was insufficient. The job is still unhealthy after redeployment.\n\n"
            f"📝 Recommended Actions:\n"
            f"  - Review the latest job run logs in Databricks\n"
            f"  - Verify the deployed notebooks match the fix\n"
            f"  - Check for environment/config issues\n"
            f"  - Manual debugging may be required\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"AEGIS - Escalating to human operators"
        )
        html = self._build_html("⚠️ Post-Deployment Failed — Manual Review Required", body, "#e74c3c")
        return await self._send_email(subject, body, html)

    # ─── Escalation: Low Confidence ─────────────────────────────────────────

    async def _send_escalation(self, data: Dict) -> bool:
        incident_id = data.get("incident_id", "UNKNOWN")
        job_name = data.get("job_name", "Unknown Job")
        confidence = data.get("confidence", 0)
        root_cause = data.get("root_cause", "Could not determine")
        threshold = data.get("threshold", 70)

        subject = f"[AEGIS] 🚨 ESCALATION | {incident_id} | Low Confidence — Human Required"
        body = (
            f"═══════════════════════════════════════\n"
            f"🚨 AEGIS ESCALATING TO HUMAN OPERATOR\n"
            f"═══════════════════════════════════════\n\n"
            f"📋 Incident: {incident_id}\n"
            f"📦 Job: {job_name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ WHY AEGIS IS NOT AUTO-FIXING:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"RCA Confidence: {confidence:.0f}% (threshold: {threshold}%)\n"
            f"AEGIS requires ≥{threshold}% confidence to auto-fix safely.\n\n"
            f"🔍 BEST GUESS ROOT CAUSE:\n"
            f"{root_cause}\n\n"
            f"📝 REQUIRED ACTION:\n"
            f"  - Review the Databricks job logs manually\n"
            f"  - Identify root cause and apply fix\n"
            f"  - Re-run the job once fixed\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"AEGIS — Prioritizing safety over speed"
        )
        html = self._build_html("🚨 Escalation — Human Intervention Required", body, "#e67e22")
        return await self._send_email(subject, body, html)

    # ─── ML Drift Alerts ────────────────────────────────────────────────────

    async def _send_ml_drift_alert(self, data: Dict) -> bool:
        incident_id = data.get("incident_id", "UNKNOWN")
        degraded_models = data.get("degraded_models", [])

        model_lines = []
        for m in degraded_models:
            model_lines.append(
                f"  ⚠️  {m.get('model_name')}: {m.get('alert', 'degraded')}"
            )

        subject = f"[AEGIS] 🤖 ML Drift Detected | {incident_id} | Auto-Retraining Started"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 AEGIS ML DRIFT DETECTION\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 Incident: {incident_id}\n"
            f"⚠️  {len(degraded_models)} model(s) showing drift/degradation:\n\n"
            + "\n".join(model_lines) +
            f"\n\n🔧 AEGIS is autonomously triggering model retraining on Databricks...\n"
            f"You will receive a notification when retraining completes."
        )
        html = self._build_html("🤖 ML Drift Detected — Retraining Started", body, "#9b59b6")
        return await self._send_email(subject, body, html)

    async def _send_ml_healing_complete(self, data: Dict) -> bool:
        incident_id = data.get("incident_id", "UNKNOWN")
        model_name = data.get("model_name", "Unknown")
        run_id = data.get("run_id")
        old_accuracy = data.get("old_accuracy", 0)
        new_accuracy = data.get("new_accuracy", 0)
        mttr = data.get("mttr_seconds", 0)

        subject = f"[AEGIS] ✅ ML Retraining Complete | {incident_id} | Model Healthy"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ AEGIS ML HEALING COMPLETE\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 Incident: {incident_id}\n"
            f"🤖 Model: {model_name}\n"
            f"🏃 Retraining Run: {run_id}\n\n"
            f"📊 ACCURACY IMPROVEMENT:\n"
            f"  Before: {old_accuracy:.1%}\n"
            f"  After:  {new_accuracy:.1%}\n"
            f"  Delta:  +{(new_accuracy - old_accuracy):.1%}\n\n"
            f"⏱️  MTTR: {mttr:.0f}s ({mttr/60:.1f} min)\n\n"
            f"✅ Model reregistered and healthy. No further action required."
        )
        html = self._build_html("✅ ML Healing Complete", body, "#27ae60")
        return await self._send_email(subject, body, html)

    async def _send_ml_healing_failed(self, data: Dict) -> bool:
        incident_id = data.get("incident_id", "UNKNOWN")
        model_name = data.get("model_name", "Unknown")
        reason = data.get("reason", "Retraining did not improve model accuracy")

        subject = f"[AEGIS] ⚠️ ML Healing Failed | {incident_id} | Manual Review Required"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ AEGIS ML HEALING ESCALATION\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 Incident: {incident_id}\n"
            f"🤖 Model: {model_name}\n\n"
            f"❌ AUTONOMOUS HEALING FAILED:\n"
            f"{reason}\n\n"
            f"📝 REQUIRED ACTION:\n"
            f"  - Review MLflow experiment runs\n"
            f"  - Check training data quality\n"
            f"  - Consider manual hyperparameter tuning\n"
            f"  - Review feature pipeline for data drift\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"AEGIS — Escalating ML incident to human operators"
        )
        html = self._build_html("⚠️ ML Healing Failed — Manual Review Required", body, "#e74c3c")
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
                # Use SMTP_SSL for port 465 (direct SSL connection)
                with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=30) as smtp:
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
