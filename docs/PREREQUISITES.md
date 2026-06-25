# AEGIS — Prerequisites & Setup Guide

## Minimum Requirements (Demo Mode)

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| pip | latest | Package manager |
| Git | any | Clone repo |

No cloud account needed to run the simulation demo.

---

## Python Dependencies

```bash
pip install -r requirements.txt
```

Key packages installed:
- `langchain`, `langchain-openai` — LLM agent framework
- `chromadb` — vector store for incident knowledge base
- `evidently` — ML model drift detection
- `great-expectations` — data quality checks
- `rich` — beautiful terminal output for demo
- `loguru` — structured logging
- `httpx` — async HTTP for Teams webhook
- `PyGithub` — GitHub PR creation
- `pyyaml`, `python-dotenv` — config management

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

### Minimum (Simulation Mode — no cloud needed)
```
SIMULATION_MODE=true
AEGIS_ENV=demo
```

### Enable LLM-Powered RCA (Azure OpenAI)
```
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-01
```
> Cost estimate: ~$2–5 for a full hackathon demo session

### Enable Teams Notifications
```
TEAMS_WEBHOOK_URL=https://your-org.webhook.office.com/webhookb2/...
```
> How to get: Teams channel → Connectors → Incoming Webhook → Create

### Enable GitHub Auto-PR
```
GITHUB_TOKEN=ghp_your_token
GITHUB_REPO_OWNER=your-org
GITHUB_REPO_NAME=your-repo
```
> GitHub token needs `repo` scope

### Enable Real Databricks Monitoring (Production)
```
SIMULATION_MODE=false
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=dapi_your_token
DATABRICKS_JOB_ID=123456
```

---

## Running the Project

### Validate Everything Works
```bash
python demo/quick_test.py
```
Expected: All 5 failure types processed, each shows PASS

### Live Demo (Hackathon Presentation)
```bash
python demo/run_demo.py
```
Interactive — press Enter between each scenario

### Continuous Production Monitoring
```bash
python -m src.main
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `ChromaDB import error` | Run `pip install chromadb` separately |
| LLM returns error | Check `.env` Azure OpenAI keys; system falls back to rule-based RCA automatically |
| Teams card not showing | Verify webhook URL format includes `webhookb2` |
| GitHub PR fails | Ensure token has `repo` scope and repo exists |

---

## Folder Permissions (Windows)

If ChromaDB fails to write:
```powershell
mkdir aegis\data\knowledge_store -Force
```
