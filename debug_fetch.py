import os, sys, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'), override=True)
sys.path.insert(0, '.')

host  = os.getenv('DATABRICKS_HOST','')
token = os.getenv('DATABRICKS_TOKEN','')
print(f"HOST:  {host[:50]}")
print(f"TOKEN: ...{token[-6:]}" if token else "TOKEN: MISSING")

result = {'done': False, 'jobs': [], 'error': None}

from demo.streamlit_app import _fetch_jobs
t0 = time.time()
_fetch_jobs(host, token, result)
elapsed = time.time() - t0
print(f"done={result['done']}  error={result['error']}  jobs={len(result['jobs'])}  elapsed={elapsed:.1f}s")
for j in result['jobs']:
    print(f"  {j['job_id']} | {j['name'][:40]} | {j['latest_status']}")
