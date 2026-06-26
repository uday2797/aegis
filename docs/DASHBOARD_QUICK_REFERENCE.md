# 🎯 AEGIS Live Dashboard - Quick Reference

## 🚀 Launch Command

```powershell
python -m streamlit run app_aegis_live.py
```

**Dashboard URL:** http://localhost:8501

---

## 📊 5 Tabs Overview

### Tab 1: 📊 Live Dashboard
**Purpose:** Real-time monitoring at a glance

**Top Metrics Bar:**
- System Status (🟢 Idle / 🟡 Running)
- Elapsed Time (since workflow start)
- Current Node (which stage is active)
- Progress % (completed nodes / 15)
- Emails Sent (notification count)

**Current Job Info:**
- Job ID
- Job Name
- Latest Status (✅ SUCCESS / ❌ FAILED)

**Real-Time Progress:**
- Animated progress bar
- Current node spinner
- Waiting indicator

**Latest Activity:**
- Last 5 log entries
- Color-coded by level
- Timestamps

---

### Tab 2: 🔄 Workflow Progress
**Purpose:** Visual tracking through all 15 nodes

**Node Status Colors:**
- 🟢 **Green** = Completed
- 🟡 **Purple (pulsing)** = In Progress
- ⚪ **Gray** = Pending

**15 Nodes Tracked:**
1. job_selector
2. status_check
3. initial_email
4. failure_alert
5. fix_in_progress_email
6. job_fixer
7. fix_complete_email
8. pr_create
9. pr_raised_email
10. pr_wait_approval
11. deployment
12. post_deployment_verification
13. final_confirmation_email
14. deployment_failed_email

**Gauge Chart:**
- Visual completion percentage
- Color gradient progress indicator

---

### Tab 3: 📝 Live Logs
**Purpose:** Real-time log streaming with filtering

**Features:**
- Multi-select filter (info, success, warning, error)
- Scrollable container (600px height)
- Color-coded entries:
  - 🔵 **Blue** = Info
  - 🟢 **Green** = Success
  - 🟠 **Orange** = Warning
  - 🔴 **Red** = Error
- Timestamp on each entry
- Auto-scroll to latest
- Clear logs button

**Log Format:**
```
[HH:MM:SS] Message text
```

---

### Tab 4: 📈 Analytics
**Purpose:** Historical trends and statistics

**Top Metrics:**
- Total Incidents
- Auto-Healed Count (with %)
- Average MTTR
- Success Rate

**MTTR Trend Chart:**
- Line chart showing MTTR over time
- X-axis: Incident number
- Y-axis: MTTR in seconds
- Markers on each data point

**Success Rate Pie Chart:**
- 🟢 Green slice: Healed
- 🔴 Red slice: Failed
- Percentage breakdown

**Incident History Table:**
| # | Timestamp | Job ID | Status | MTTR | PR |
|---|---|---|---|---|---|
| 1 | 2026-06-26 10:33:32 | 470575380114552 | ✅ Healed | 218s | github.com/... |

---

### Tab 5: 🔗 Resources
**Purpose:** Quick access to external systems

**Databricks Links:**
- 🔗 Open Databricks Workspace
- 📊 View Current Job (specific job page)

**GitHub Links:**
- 🔗 Open Repository
- 🔀 View Active PR (when created)

**GitHub Actions:**
- 🚀 View Deployment Workflow (CD run)

**Full State Viewer:**
- Expandable JSON view of complete workflow state
- All state fields visible

**Quick Stats:**
- Available Jobs count
- Logs Captured count
- Incident History count

---

## 🎛️ Sidebar Controls

### Job Selection Section
1. **🔄 Refresh Jobs** button
   - Fetches latest jobs from Databricks
   - Updates dropdown list

2. **Select Job to Monitor** dropdown
   - Shows all available jobs
   - Format: `{job_id} - {job_name}`
   - Plus "all" option to monitor all jobs

### Workflow Control Section
**When Idle:**
- **🚀 Start AEGIS** button (primary, purple gradient)
  - Launches full autonomous workflow
  - Disabled if no job selected
  - Starts background thread

**When Running:**
- Success message: "🟢 AEGIS is running..."
- **⏹️ Stop** button (secondary)
  - Graceful shutdown
  - Logs stop message

### Configuration Display
**Info box showing:**
- Databricks host
- Model: GPT-5.5 (EPAM DIAL)
- GitHub repo

**Footer:**
- AEGIS v2.0 | 15-Node Workflow

---

## ⏱️ Real-Time Updates

### Auto-Refresh Behavior
- **Refresh Interval:** 2 seconds (when workflow running)
- **What Updates:**
  - Current node indicator
  - Progress bar
  - Logs stream
  - Completed nodes list
  - Elapsed time
  - All metrics
  - External URLs (as they become available)

### URL Population Timeline
| When | URL | Where It Appears |
|---|---|---|
| After `pr_create` | PR URL | Tab 5: Resources → View Active PR |
| After `deployment` | Workflow Run URL | Tab 5: Resources → View Deployment |
| During `status_check` | Job Run URL | Available in state |

---

## 🎨 Visual Design Elements

### Color Palette
- **Primary Gradient:** Purple (#667eea to #764ba2)
- **Success:** Green (#11998e to #38ef7d)
- **Error:** Red (#eb3349 to #f45c43)
- **Background:** Blue-gray gradient (#f0f4f8 to #bcccdc)
- **Cards:** White with subtle shadows

### Animations
- **Pulse:** Active stage cards (2s infinite)
- **Fade In:** Title and headers (1s ease-in)
- **Hover:** Buttons lift 2px with increased shadow

### Typography
- **Titles:** 3.5rem, bold 900, gradient text
- **Subtitles:** 1.2rem, weight 500
- **Body:** Default, color #334e68
- **Logs:** Courier New, monospace, 0.9rem

---

## 🔧 Technical Details

### Thread Architecture
```
┌─────────────────────────────────────┐
│  Streamlit Main Thread (UI)         │
│  - Renders dashboard                │
│  - Handles user interactions        │
│  - Auto-refreshes every 2s          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Background Thread (Workflow)       │
│  - Runs LangGraph workflow          │
│  - Updates session_state            │
│  - Executes all 15 nodes            │
└─────────────────────────────────────┘
```

### Session State Variables
```python
st.session_state.workflow_running      # bool
st.session_state.workflow_logs         # list[dict]
st.session_state.current_node          # str | None
st.session_state.completed_nodes       # list[str]
st.session_state.start_time            # float | None
st.session_state.available_jobs        # list[dict]
st.session_state.selected_job_id       # str | None
st.session_state.pr_url                # str | None
st.session_state.workflow_run_url      # str | None
st.session_state.mttr_seconds          # float
st.session_state.email_count           # int
st.session_state.incidents_history     # list[dict]
```

### Performance Optimizations
- **Log Limit:** Keep only last 100 entries
- **Conditional Refresh:** Only auto-refresh when workflow running
- **Cached Config:** @st.cache_resource for config loading
- **Thread Daemon:** Background thread auto-terminates with main

---

## 📋 Typical Workflow Timeline

```
00:00 - User clicks "Start AEGIS"
00:01 - job_selector: Fetch & display jobs (2s)
00:03 - status_check: Monitor job health (5-10s)
00:13 - initial_email: Send status report (2s)
00:15 - failure_alert: GPT-5.5 RCA (10-15s)
00:30 - fix_in_progress_email: Notify (2s)
00:32 - job_fixer: Auto-repair notebooks (15-20s)
00:52 - fix_complete_email: Confirm fix (2s)
00:54 - pr_create: Create GitHub PR (5s) ← PR URL appears
00:59 - pr_raised_email: Notify PR (2s)
01:01 - pr_wait_approval: Indefinite wait
XX:XX - (User merges PR manually)
XX:XX - deployment: Trigger GitHub Actions (30-90s) ← Deployment URL appears
XX:XX - post_deployment_verification: Re-check (65s)
XX:XX - final_confirmation_email: Success (2s)
XX:XX - END (Total MTTR: ~220-240s excluding PR review)
```

---

## 🎯 User Interaction Flow

```
1. Dashboard loads
   └─> Jobs auto-fetch from Databricks
   
2. User selects job from dropdown
   └─> "Start AEGIS" button enabled
   
3. User clicks "Start AEGIS"
   └─> Workflow thread starts
   └─> UI begins auto-refreshing (2s interval)
   └─> Current node updates live
   └─> Logs stream in real-time
   
4. Monitor progress
   └─> Switch between tabs to view different aspects
   └─> Watch "Workflow Progress" for visual flow
   └─> Check "Live Logs" for detailed tracking
   └─> See "Resources" for external links
   
5. Workflow completes
   └─> Auto-refresh stops
   └─> System status returns to 🟢 Idle
   └─> Analytics updated with new incident
   └─> All URLs available in Resources tab
   
6. Review results
   └─> Check Analytics tab for MTTR
   └─> View incident history table
   └─> Click PR link to see code changes
   └─> Verify job health in Databricks
```

---

## 💡 Pro Tips

### 🎯 Monitoring Tips
1. Keep "Workflow Progress" tab open to see visual flow
2. Switch to "Live Logs" if you need detailed troubleshooting
3. Use "Analytics" to track improvement over time
4. Bookmark external links from "Resources" for quick access

### ⚡ Performance Tips
1. Clear logs periodically if dashboard feels slow
2. Use job filters to monitor specific jobs only
3. Let PR approval happen in GitHub (don't close dashboard)

### 🔍 Debugging Tips
1. If workflow stalls, check "Live Logs" for errors
2. Red log entries indicate failures requiring attention
3. Check "Resources" → "View Full State" for complete context
4. Verify Databricks/GitHub credentials in `.env` if connection fails

---

## 🚨 Common Issues & Solutions

### Issue: Dashboard won't start
**Solution:**
```powershell
pip install streamlit
python -m streamlit run app_aegis_live.py
```

### Issue: No jobs appearing
**Solution:**
1. Click "🔄 Refresh Jobs"
2. Check `.env` for correct Databricks credentials
3. Verify VPN connection (if required)

### Issue: Workflow stops unexpectedly
**Solution:**
1. Check "Live Logs" → filter for "error" level
2. Verify all environment variables in `.env`
3. Check Databricks job permissions
4. Ensure GitHub token has repo scope

### Issue: Auto-refresh stopped
**Solution:**
- This is normal when workflow completes
- Status changes to 🟢 Idle
- Results available in Analytics tab

---

## 📊 Dashboard Metrics Explained

### System Status
- 🟢 **Idle** = Ready to start, no workflow running
- 🟡 **Running** = Workflow active, processing nodes

### Progress %
- Calculated as: (completed_nodes / 15) × 100
- Updates after each node completes

### MTTR (Mean Time To Recovery)
- Time from failure detection to verified fix
- Measured in seconds
- Lower is better
- Typical range: 200-250s (excluding human PR review)

### Success Rate
- (Healed incidents / Total incidents) × 100
- Target: >95%

---

## 🎉 Success Indicators

**Workflow completed successfully when you see:**
1. ✅ Status: 🟢 Idle
2. ✅ Progress: 100%
3. ✅ Current Node: None
4. ✅ Analytics: New incident added with "✅ Healed" status
5. ✅ Resources: PR URL and Deployment URL both populated
6. ✅ Logs: "✅ Workflow completed in XXXs"

---

## 📚 Additional Resources

- **Complete Guide:** [docs/DASHBOARD_GUIDE.md](../DASHBOARD_GUIDE.md)
- **Agent Architecture:** [docs/AGENT_ARCHITECTURE.md](../AGENT_ARCHITECTURE.md)
- **Enhancements Summary:** [docs/ENHANCEMENTS_SUMMARY.md](../ENHANCEMENTS_SUMMARY.md)
- **Dynamic Job Selection:** [docs/DYNAMIC_JOB_SELECTION.md](../DYNAMIC_JOB_SELECTION.md)

---

**🛡️ AEGIS v2.0 - Autonomous Excellence Guardian & Intelligent System**
