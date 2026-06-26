# AEGIS Live Dashboard - Quick Start Guide

## 🚀 How to Run

### Option 1: Direct Command
```powershell
$env:PYTHONPATH="C:\Users\uday_nagisetti\aegis"
streamlit run app_aegis_live.py
```

### Option 2: Using Batch Script
```powershell
.\run_dashboard.ps1
```

---

## 📊 Dashboard Features

### ✅ 5 Comprehensive Tabs

#### 1. **📊 Live Dashboard**
- Real-time system status monitoring
- Current job information
- Live progress bar
- Latest activity feed (last 5 logs)
- Elapsed time tracking
- Email count

#### 2. **🔄 Workflow Progress**
- Visual progress through all 15 nodes
- Color-coded stages:
  - 🟢 **Green**: Completed
  - 🟡 **Purple (animated)**: In Progress
  - ⚪ **Gray**: Pending
- Gauge chart showing completion percentage
- Real-time node tracking

#### 3. **📝 Live Logs**
- Real-time log streaming
- Filter by level (info, success, warning, error)
- Color-coded log entries
- Auto-scrolling container
- Clear logs button
- Timestamp for each entry

#### 4. **📈 Analytics**
- Total incidents tracked
- Auto-heal success rate
- Average MTTR (Mean Time To Recovery)
- MTTR trend line chart
- Success rate pie chart
- Full incident history table
- Historical statistics

#### 5. **🔗 Resources**
- Quick links to:
  - Databricks workspace
  - Current job page
  - GitHub repository
  - Active PR (when created)
  - GitHub Actions workflow (CD)
- Full workflow state viewer (JSON)
- Quick stats summary

---

## 🎛️ Sidebar Controls

### Job Selection
- **Refresh Jobs** button to fetch latest Databricks jobs
- Dropdown to select specific job ID or "all"
- Shows job name, ID, and current status

### Workflow Control
- **🚀 Start AEGIS** button
  - Launches full 15-node autonomous workflow
  - Runs in background thread
  - Real-time updates every 2 seconds
- **⏹️ Stop** button (when running)
  - Graceful shutdown
  - Preserves logs and state

### Configuration Display
- Databricks host
- Model (GPT-5.5)
- GitHub repository

---

## 🎨 Visual Design

### Light Theme
- Gradient background (blue-gray tones)
- White cards with shadows
- Purple gradient branding
- Smooth animations
- Hover effects on buttons

### Status Indicators
- 🟢 **Green**: Healthy/Success
- 🟡 **Yellow**: Running/In Progress
- 🔴 **Red**: Failed/Error
- ⚪ **Gray**: Pending/Idle

### Color Coding
- **Info logs**: Blue left border
- **Success logs**: Green left border
- **Warning logs**: Orange left border
- **Error logs**: Red left border

---

## 🔄 15-Node Workflow

```
START
  ↓
1. job_selector ← User selects job(s)
  ↓
2. status_check → Monitor job health
  ↓
3. initial_email → Send status report
  ↓
4. failure_alert → RCA analysis (GPT-5.5)
  ↓
5. fix_in_progress_email → Notify fixing
  ↓
6. job_fixer → Auto-repair notebooks
  ↓
7. fix_complete_email → Confirm fix
  ↓
8. pr_create → Create GitHub PR
  ↓
9. pr_raised_email → Notify PR created
  ↓
10. pr_wait_approval → Wait indefinitely
  ↓
11. deployment → Trigger GitHub Actions CD
  ↓
12. post_deployment_verification → Re-check health
  ↓
13. final_confirmation_email → Success notification
  OR
14. deployment_failed_email → Escalation
  ↓
END
```

---

## 📊 Real-Time Updates

### Auto-Refresh (Every 2 seconds when running)
- Current node updates
- Progress bar advances
- Logs stream in real-time
- Metrics update live
- URLs appear when available

### Thread-Based Execution
- Workflow runs in background thread
- UI remains responsive
- No blocking operations
- Graceful error handling

---

## 🔗 External Resources

### Databricks Links
- **Workspace**: Opens your Databricks environment
- **Job Page**: Direct link to selected job (with runs, tasks, logs)

### GitHub Links
- **Repository**: Your aegis repo
- **PR**: Auto-generated PR link when created
- **Actions**: CD workflow run page

### Auto-Generated URLs
- PR URL appears after `pr_create` node
- Deployment URL appears after `deployment` node
- Job run URL available from status check

---

## 📈 Analytics & Metrics

### Real-Time Metrics (Top Bar)
- **System Status**: 🟢 Idle / 🟡 Running
- **Elapsed Time**: Since workflow start
- **Current Node**: Active processing node
- **Progress**: Percentage complete (nodes/15)
- **Emails Sent**: Count of notifications

### Historical Analytics
- **Total Incidents**: All workflow runs
- **Auto-Healed**: Successful autonomous fixes
- **Avg MTTR**: Average time to recovery
- **Success Rate**: Heal rate percentage
- **MTTR Trend**: Line chart over time
- **Success Pie**: Visual breakdown

---

## 🛠️ Troubleshooting

### Dashboard won't start
```powershell
# Check Python path
$env:PYTHONPATH="C:\Users\uday_nagisetti\aegis"

# Install dependencies
pip install -r requirements.txt

# Check Streamlit version
streamlit --version
```

### No jobs appearing
- Click "🔄 Refresh Jobs" in sidebar
- Check Databricks credentials in `.env`
- Verify VPN connection to EPAM

### Workflow not starting
- Ensure a job is selected
- Check "Start AEGIS" button is not disabled
- Verify all environment variables in `.env`
- Check logs tab for error messages

### Real-time updates stopped
- Workflow may have completed
- Check "System Status" (should be 🟢 Idle when done)
- Review "Analytics" tab for results
- Check "Live Logs" for completion message

---

## 🎯 Usage Flow

1. **Open Dashboard**
   ```powershell
   streamlit run app_aegis_live.py
   ```

2. **Wait for Load**
   - Dashboard initializes
   - Jobs are fetched automatically

3. **Select Job**
   - Use sidebar dropdown
   - Choose specific job ID or "all"

4. **Start AEGIS**
   - Click "🚀 Start AEGIS"
   - Workflow begins immediately

5. **Monitor Progress**
   - Watch "Workflow Progress" tab for stages
   - See "Live Logs" for detailed activity
   - Check "Live Dashboard" for quick status

6. **Review Results**
   - PR link appears in "Resources" tab
   - Analytics updated in "Analytics" tab
   - Full state available in "Resources" > "View Full State"

7. **Access External Resources**
   - Click links in "Resources" tab
   - View PRs, deployments, job runs
   - Verify fixes in Databricks

---

## 💡 Tips

### Best Practices
- ✅ Always refresh jobs before starting
- ✅ Monitor "Live Logs" for detailed tracking
- ✅ Use "Resources" tab for quick access to PRs
- ✅ Check "Analytics" after each run for trends

### Performance
- Dashboard auto-refreshes every 2 seconds when running
- Logs limited to last 100 entries for performance
- Thread-based execution prevents UI freezing

### Monitoring
- "Workflow Progress" tab shows exact stage
- Waiting indicators show which node is processing
- Color coding makes status instantly visible

---

## 🎉 What to Expect

### Full Autonomous Cycle (End-to-End)

**Typical Timeline:**
- Status check: 5-10s
- RCA analysis: 10-15s
- Auto-fix: 15-20s
- PR creation: 5s
- PR approval: Variable (human review)
- Deployment: 60-90s
- Verification: 65s
- **Total MTTR: ~220-240s** (excluding PR review time)

### Email Notifications (8 Stages)
1. ✉️ Initial health status
2. ✉️ Failure alert (RCA results)
3. ✉️ Fix in progress
4. ✉️ Fix complete
5. ✉️ PR raised
6. ✉️ (No email for PR wait)
7. ✉️ (No email for deployment)
8. ✉️ Final confirmation OR Deployment failed

### Real-Time Visibility
- Every node updates within 2 seconds
- Logs stream live
- Progress bar advances automatically
- Metrics update continuously
- URLs appear as soon as available

---

## 🚀 Ready to Use!

Just run:
```powershell
streamlit run app_aegis_live.py
```

**Then sit back and watch AEGIS autonomously heal your infrastructure!** 🛡️✨
