"""
AEGIS DeploymentAgent
Triggers GitHub Actions CD workflow and monitors deployment completion.
"""
import os
import asyncio
from typing import Dict
from loguru import logger
from github import Github, GithubException


class DeploymentAgent:
    """
    Triggers GitHub Actions CD workflow after PR merge.
    Monitors workflow run until completion.
    """

    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.repo_owner = os.environ.get("GITHUB_REPO_OWNER", "")
        self.repo_name = os.environ.get("GITHUB_REPO_NAME", "")
        
        if not (self.token and self.repo_owner and self.repo_name):
            logger.warning("[Deployment] GitHub credentials not configured")
            self.enabled = False
        else:
            self.github = Github(self.token)
            try:
                self.repo = self.github.get_repo(f"{self.repo_owner}/{self.repo_name}")
                self.enabled = True
                logger.info(f"[Deployment] Initialized | repo={self.repo_owner}/{self.repo_name}")
            except GithubException as e:
                logger.error(f"[Deployment] Cannot access repo {self.repo_owner}/{self.repo_name}: {e}")
                self.enabled = False

    async def trigger_cd(self, merge_sha: str) -> Dict:
        """
        Trigger CD workflow after PR merge.
        
        The CD workflow (.github/workflows/cd.yml) should be configured with:
        - trigger: push to main branch
        - OR workflow_dispatch for manual trigger
        
        This method waits for the workflow run triggered by the merge commit.
        
        Returns:
            {
                "workflow_run_url": str,
                "status": "success" | "failure" | "timeout",
                "conclusion": str
            }
        """
        if not self.enabled:
            logger.warning("[Deployment] GitHub not configured — CD not triggered")
            return {
                "workflow_run_url": "",
                "status": "failure",
                "conclusion": "GitHub not configured",
            }
        
        logger.info(f"[Deployment] Waiting for CD workflow triggered by merge {merge_sha[:7]}")
        
        try:
            # Wait longer for GitHub Actions to register the workflow run
            # GitHub can take 20-30 seconds to create the workflow run after merge
            logger.info("[Deployment] Waiting 30s for GitHub Actions to start workflow...")
            await asyncio.sleep(30)
            
            # Find workflow runs for the merge commit
            workflow_runs = self.repo.get_workflow_runs(
                event="push",
                branch=self.repo.default_branch,
            )
            
            # Check last 20 runs to find the one triggered by our merge
            target_run = None
            for run in list(workflow_runs)[:20]:
                if run.head_sha == merge_sha:
                    target_run = run
                    break
            
            if not target_run:
                logger.warning(f"[Deployment] No workflow run found for SHA {merge_sha[:7]} after 30s wait")
                logger.info("[Deployment] This may be normal if:")
                logger.info("  1. GitHub Actions is delayed")
                logger.info("  2. No workflows trigger on this branch")
                logger.info("  3. Workflow filters exclude the changed files")
                return {
                    "workflow_run_url": "",
                    "status": "not_found",
                    "conclusion": "No workflow run found (may still be queued or not configured)",
                }
            
            logger.info(f"[Deployment] Found workflow run #{target_run.id}: {target_run.html_url}")
            
            # Poll until completion (max 10 min)
            for _ in range(120):  # 120 × 5s = 10 min
                await asyncio.sleep(5)
                run = self.repo.get_workflow_run(target_run.id)
                
                logger.info(f"[Deployment] Workflow run #{run.id} status={run.status} conclusion={run.conclusion}")
                
                if run.status == "completed":
                    if run.conclusion == "success":
                        logger.success(f"[Deployment] CD workflow completed successfully: {run.html_url}")
                        return {
                            "workflow_run_url": run.html_url,
                            "status": "success",
                            "conclusion": run.conclusion,
                        }
                    else:
                        logger.error(f"[Deployment] CD workflow failed: {run.conclusion}")
                        return {
                            "workflow_run_url": run.html_url,
                            "status": "failure",
                            "conclusion": run.conclusion,
                        }
            
            # Timeout
            logger.warning(f"[Deployment] Workflow run #{target_run.id} timed out after 10 min")
            return {
                "workflow_run_url": target_run.html_url,
                "status": "timeout",
                "conclusion": "Timed out after 10 minutes",
            }
        
        except Exception as e:
            logger.error(f"[Deployment] CD trigger failed: {e}")
            return {
                "workflow_run_url": "",
                "status": "failure",
                "conclusion": str(e),
            }

    async def trigger_cd_manual(self, workflow_name: str = "cd.yml") -> Dict:
        """
        Manually trigger CD workflow via workflow_dispatch.
        
        Requires the CD workflow to have:
        ```yaml
        on:
          workflow_dispatch:
        ```
        """
        if not self.enabled:
            logger.warning("[Deployment] GitHub not configured")
            return {
                "workflow_run_url": "",
                "status": "failure",
                "conclusion": "GitHub not configured",
            }
        
        logger.info(f"[Deployment] Manually triggering workflow: {workflow_name}")
        
        try:
            workflow = self.repo.get_workflow(workflow_name)
            success = workflow.create_dispatch(
                ref=self.repo.default_branch,
                inputs={},
            )
            
            if success:
                logger.success(f"[Deployment] Workflow {workflow_name} dispatch triggered")
                # Wait for run to appear
                await asyncio.sleep(5)
                runs = list(workflow.get_runs(branch=self.repo.default_branch))
                if runs:
                    latest_run = runs[0]
                    return {
                        "workflow_run_url": latest_run.html_url,
                        "status": "triggered",
                        "conclusion": "Manual dispatch triggered",
                    }
            
            return {
                "workflow_run_url": "",
                "status": "failure",
                "conclusion": "Dispatch failed",
            }
        
        except Exception as e:
            logger.error(f"[Deployment] Manual trigger failed: {e}")
            return {
                "workflow_run_url": "",
                "status": "failure",
                "conclusion": str(e),
            }
