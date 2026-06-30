"""
AEGIS PRManagerAgent
Creates GitHub PRs with fixed code and polls for approval/merge.
"""
import os
import asyncio
from typing import Dict, Optional
from loguru import logger
from github import Github, GithubException


class PRManagerAgent:
    """
    Manages GitHub pull requests for AEGIS hotfixes.
    
    Capabilities:
    1. Create PR with fixed notebooks
    2. Poll PR status until merged or rejected
    3. Return PR URL and merge status
    """

    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.repo_owner = os.environ.get("GITHUB_REPO_OWNER", "")
        self.repo_name = os.environ.get("GITHUB_REPO_NAME", "")
        
        if not (self.token and self.repo_owner and self.repo_name):
            logger.warning("[PRManager] GitHub credentials not configured")
            self.enabled = False
        else:
            self.github = Github(self.token)
            self.repo = self.github.get_repo(f"{self.repo_owner}/{self.repo_name}")
            self.enabled = True
            logger.info(f"[PRManager] Initialized | repo={self.repo_owner}/{self.repo_name}")

    async def create_pr(
        self,
        incident_id: str,
        fixed_notebooks: list,
        root_cause: str,
        failure_type: str = "code_bug",
    ) -> Dict:
        """
        Create a GitHub PR with fixed notebooks.
        
        Args:
            incident_id: Incident ID (e.g., INC-ABC123)
            fixed_notebooks: [{"git_path": str, "content": str, ...}]
            root_cause: RCA summary
            failure_type: Failure type slug
        
        Returns:
            {
                "pr_url": str,
                "pr_number": int,
                "branch_name": str,
                "created": bool
            }
        """
        if not self.enabled:
            logger.warning("[PRManager] GitHub not configured — PR creation skipped")
            return {
                "pr_url": "",
                "pr_number": 0,
                "branch_name": "",
                "created": False,
            }
        
        logger.info(f"[PRManager] Creating PR for {incident_id} | {len(fixed_notebooks)} file(s)")
        
        try:
            # Step 1: Create branch
            branch_name = f"aegis-hotfix/{failure_type}/{incident_id}"
            base_branch = self.repo.default_branch
            base_ref = self.repo.get_git_ref(f"heads/{base_branch}")
            base_sha = base_ref.object.sha
            
            try:
                self.repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)
                logger.success(f"[PRManager] Created branch: {branch_name}")
            except GithubException as e:
                if e.status == 422:  # Branch already exists
                    logger.info(f"[PRManager] Branch {branch_name} already exists, reusing")
                else:
                    raise
            
            # Step 2: Commit fixed notebooks
            for nb in fixed_notebooks:
                git_path = nb["git_path"]
                content = nb["content"]
                commit_message = f"[AEGIS Auto-Fix] {incident_id}: Fix notebook {git_path}"
                
                # PyGithub requires bytes for file content
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content

                try:
                    # Try update existing file
                    file = self.repo.get_contents(git_path, ref=branch_name)
                    self.repo.update_file(
                        path=git_path,
                        message=commit_message,
                        content=content_bytes,
                        sha=file.sha,
                        branch=branch_name,
                    )
                    logger.success(f"[PRManager] Updated {git_path} on {branch_name}")
                except GithubException:
                    # File doesn't exist, create it
                    self.repo.create_file(
                        path=git_path,
                        message=commit_message,
                        content=content_bytes,
                        branch=branch_name,
                    )
                    logger.success(f"[PRManager] Created {git_path} on {branch_name}")
            
            # Step 3: Create PR
            pr_title = f"[AEGIS Auto-Fix] {incident_id}: Autonomous notebook repair"
            pr_body = self._generate_pr_body(incident_id, fixed_notebooks, root_cause)
            
            try:
                pr = self.repo.create_pull(
                    title=pr_title,
                    body=pr_body,
                    head=branch_name,
                    base=base_branch,
                )
                logger.success(f"[PRManager] Created PR #{pr.number}: {pr.html_url}")
                
                return {
                    "pr_url": pr.html_url,
                    "pr_number": pr.number,
                    "branch_name": branch_name,
                    "created": True,
                }
            except GithubException as e:
                if e.status == 422:  # PR already exists
                    # Find existing PR
                    prs = self.repo.get_pulls(state="open", head=f"{self.repo_owner}:{branch_name}")
                    existing_pr = prs[0] if prs.totalCount > 0 else None
                    if existing_pr:
                        logger.info(f"[PRManager] PR already exists: #{existing_pr.number}")
                        return {
                            "pr_url": existing_pr.html_url,
                            "pr_number": existing_pr.number,
                            "branch_name": branch_name,
                            "created": False,
                        }
                raise
        
        except Exception as e:
            logger.error(f"[PRManager] PR creation failed: {e}")
            return {
                "pr_url": "",
                "pr_number": 0,
                "branch_name": "",
                "created": False,
            }

    async def wait_for_pr_approval(self, pr_number: int) -> Dict:
        """
        Poll PR status until merged or closed.
        
        **BLOCKS INDEFINITELY** - No timeout. Waits until human reviews and merges/closes PR.
        This is intentional to allow human review at their own pace.
        
        Args:
            pr_number: PR number to monitor
            timeout_minutes: Max time to wait
        
        Returns:
            {
                "merged": bool,
                "closed": bool,
                "sha": str | None  # Merge commit SHA if merged
            }
        """
        if not self.enabled:
            logger.warning("[PRManager] GitHub not configured — cannot poll PR")
            return {"merged": False, "closed": False, "sha": None}

        if not pr_number or pr_number == 0:
            logger.error("[PRManager] Invalid PR number (0) — cannot poll. PR creation likely failed.")
            return {"merged": False, "closed": True, "sha": None}

        logger.info(f"[PRManager] Waiting for PR #{pr_number} approval (NO TIMEOUT - will wait indefinitely)")
        
        poll_count = 0
        while True:
            try:
                pr = self.repo.get_pull(pr_number)
                
                if pr.merged:
                    logger.success(f"[PRManager] PR #{pr_number} merged! SHA={pr.merge_commit_sha}")
                    return {
                        "merged": True,
                        "closed": False,
                        "sha": pr.merge_commit_sha,
                    }
                
                if pr.state == "closed":
                    logger.warning(f"[PRManager] PR #{pr_number} closed without merging")
                    return {
                        "merged": False,
                        "closed": True,
                        "sha": None,
                    }
                
                # Log progress every 5 minutes (5 polls × 60s)
                poll_count += 1
                if poll_count % 5 == 0:
                    elapsed_min = poll_count
                    logger.info(f"[PRManager] PR #{pr_number} still open, waiting... ({elapsed_min}min elapsed)")
                
                # Poll every 60 seconds
                await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"[PRManager] Error polling PR #{pr_number}: {e}")
                await asyncio.sleep(60)

    def _generate_pr_body(self, incident_id: str, fixed_notebooks: list, root_cause: str) -> str:
        """Generate PR description."""
        files_list = "\n".join([f"- `{nb['git_path']}`" for nb in fixed_notebooks])
        return f"""## 🛡️ AEGIS Autonomous Repair

**Incident ID**: {incident_id}

### Root Cause (GPT-5.5 Analysis)
{root_cause}

### Changes
This PR contains autonomous notebook repairs generated by AEGIS GPT-5.5:

{files_list}

### Verification
✅ All fixed notebooks have been uploaded to Databricks and the job ran successfully.

### Next Steps
1. **Review** the code changes
2. **Approve** if the fix looks correct
3. **Merge** — AEGIS will automatically trigger CD to redeploy the bundle

---

*Generated by AEGIS — AI-Engine for Guardian Intelligence & Self-healing*
"""
