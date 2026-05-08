# Analytics Export Documentation

## Overview

The MR-Krabs analytics export functionality allows you to generate comprehensive cost and usage reports in CSV or JSON format. These exports include summary metrics, tier breakdowns, daily trends, and efficiency analysis.

## Features

- **CSV Export**: Tab-delimited format suitable for spreadsheet applications
- **JSON Export**: Structured data format ideal for programmatic consumption
- **In-Memory Mode**: Generate reports without writing to disk
- **File Mode**: Write reports to specified directories
- **Configurable Periods**: Export data for 1 to 90 days

## MCP Tools

### `mcp_mrkrabs_export_csv`

Export analytics data in CSV format.

**Endpoint**: `POST /tools/mcp_mrkrabs_export_csv`

**Request Schema**:
```json
{
  "period_days": 7,
  "session_id": null,
  "output_dir": "/tmp/reports",
  "output_file": "my_report.csv"
}
```

**Parameters**:
- `period_days` (int, optional, default: 7): Number of days to analyze (1-90)
- `session_id` (string, optional): Filter by specific session ID
- `output_dir` (string, optional): Directory to write the file
- `output_file` (string, optional): Output filename (default: "analytics_export.csv")

**Response Schema**:
```json
{
  "success": true,
  "format": "csv",
  "filename": "my_report.csv",
  "file_path": "/tmp/reports/my_report.csv",
  "data_preview": "=== MR-Krabs Analytics Export ===\n...",
  "message": "CSV export written to /tmp/reports/my_report.csv"
}
```

### `mcp_mrkrabs_export_json`

Export analytics data in JSON format.

**Endpoint**: `POST /tools/mcp_mrkrabs_export_json`

**Request Schema**:
```json
{
  "period_days": 30,
  "session_id": null,
  "output_dir": "/tmp/reports",
  "output_file": "my_report.json"
}
```

**Parameters**:
- `period_days` (int, optional, default: 7): Number of days to analyze (1-90)
- `session_id` (string, optional): Filter by specific session ID
- `output_dir` (string, optional): Directory to write the file
- `output_file` (string, optional): Output filename (default: "analytics_export.json")

**Response Schema**:
```json
{
  "success": true,
  "format": "json",
  "filename": "my_report.json",
  "file_path": "/tmp/reports/my_report.json",
  "data_preview": "{\"export_info\": {...}, ...}",
  "message": "JSON export written to /tmp/reports/my_report.json"
}
```

## CSV Format Details

The CSV export is organized into sections:

### Section 1: Export Metadata
```csv
=== MR-Krabs Analytics Export ===
Format,CSV
Export Date,2026-05-07 12:00:00
```

### Section 2: Summary Metrics
```csv
=== SUMMARY ===
Metric,Value
period,7 days
total_spent,17.62
task_count,70
avg_cost_per_task,0.25
budget_used_percent,35.2
trend_direction,stable
efficiency_score,79
```

### Section 3: Tier Breakdown
```csv
=== TIER BREAKDOWN ===
Tier,Task Count,Total Cost,Avg Cost Per Task,Percentage of Total,Success Rate,Efficiency Score
L0,45,2.89,0.06,37.0,98.5,94
L1,25,9.12,0.36,57.0,96.0,85
L2,8,3.45,0.43,12.0,94.0,78
```

### Section 4: Daily Trends
```csv
=== DAILY TRENDS ===
Date,Total Cost,Task Count,Avg Cost Per Task
2026-05-01,2.0,10,0.20
2026-05-02,1.51,6,0.25
2026-05-03,1.57,9,0.17
```

### Section 5: Efficiency Report
```csv
=== EFFICIENCY REPORT ===
Category,Value
Overall Efficiency Score,82
Total Tasks Analyzed,78
L0 Percentage,57.7%
L1 Percentage,34.6%
L2 Percentage,7.7%
Potential Monthly Savings,$0.26
```

## JSON Format Details

The JSON export provides structured data:

```json
{
  "export_info": {
    "format": "JSON",
    "exported_at": "2026-05-07T12:00:00.000000",
    "period": "7 days",
    "period_start": "2026-04-30",
    "period_end": "2026-05-07"
  },
  "summary": {
    "total_spent": 17.62,
    "task_count": 70,
    "avg_cost_per_task": 0.25,
    "budget_used_percent": 35.2,
    "trend_direction": "stable",
    "efficiency_score": 79
  },
  "tier_breakdown": {
    "L0": {
      "task_count": 45,
      "total_cost": 2.89,
      "avg_cost_per_task": 0.06,
      "percentage_of_total": 37.0,
      "success_rate": 98.5,
      "efficiency_score": 94
    },
    "L1": {
      "task_count": 25,
      "total_cost": 9.12,
      "avg_cost_per_task": 0.36,
      "percentage_of_total": 57.0,
      "success_rate": 96.0,
      "efficiency_score": 85
    },
    "L2": {
      "task_count": 8,
      "total_cost": 3.45,
      "avg_cost_per_task": 0.43,
      "percentage_of_total": 12.0,
      "success_rate": 94.0,
      "efficiency_score": 78
    },
    "L3": {
      "task_count": 2,
      "total_cost": 2.16,
      "avg_cost_per_task": 1.08,
      "percentage_of_total": 5.0,
      "success_rate": 99.0,
      "efficiency_score": 72
    }
  },
  "daily_trends": [
    {
      "date": "2026-05-01",
      "total_cost": 2.0,
      "task_count": 10,
      "avg_cost_per_task": 0.20
    },
    {
      "date": "2026-05-02",
      "total_cost": 1.51,
      "task_count": 6,
      "avg_cost_per_task": 0.25
    }
  ],
  "efficiency_report": {
    "overall_efficiency_score": 82,
    "tier_analysis": {
      "L0": {
        "efficiency_score": 94,
        "task_count": 45,
        "avg_cost_per_task": 0.06,
        "success_rate": 98.5,
        "status": "Excellent ✅"
      }
    },
    "optimization_suggestions": [
      "Shift 2 L2 tasks to L1 for simpler operations (potential savings: $0.04/month)"
    ],
    "potential_monthly_savings": 0.04
  }
}
```

## Usage Examples

### Python - File Export
```python
import requests

# CSV export to file
response = requests.post(
    'http://localhost:8000/tools/mcp_mrkrabs_export_csv',
    json={
        'period_days': 30,
        'output_dir': '/tmp/reports',
        'output_file': 'monthly_report.csv'
    }
)

result = response.json()
print(f"File saved to: {result['file_path']}")
```

### Python - In-Memory Export
```python
import requests

# JSON export in-memory
response = requests.post(
    'http://localhost:8000/tools/mcp_mrkrabs_export_json',
    json={'period_days': 7}
)

result = response.json()
data = result['full_data']  # Complete JSON string
print(data[:200])  # Preview
```

### Python - Filter by Session
```python
import requests

# Export data for specific session
response = requests.post(
    'http://localhost:8000/tools/mcp_mrkrabs_export_json',
    json={
        'session_id': 'abc123xyz',
        'period_days': 14,
        'output_dir': '/tmp/reports',
        'output_file': 'session_report.json'
    }
)

print(f"Export complete: {result['message']}")
```

### curl - CSV Export
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_export_csv \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7, "output_dir": "/tmp", "output_file": "report.csv"}'
```

### curl - JSON Export
```bash
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_export_json \
  -H "Content-Type: application/json" \
  -d '{"period_days": 30}' | jq '.'
```

## Integration with Analytics Service

The export functionality uses the `AnalyticsService` class:

```python
from src.mcp.analytics_tools import AnalyticsService, CSVExporter

service = AnalyticsService()

# Generate data
summary_data = service.generate_summary(period_days=7)
tier_data = service.generate_tier_breakdown(period_days=7)
trend_data = service.generate_cost_trends(period_days=7)
efficiency_data = service.generate_efficiency_report(period_days=7)

# Export to CSV
exporter = CSVExporter(output_dir='/tmp')
filepath = exporter.export_to_file(
    summary_data, tier_data, trend_data, efficiency_data,
    filename='custom_report.csv'
)

print(f"Exported to: {filepath}")
```

## Error Handling

### Common Errors

1. **Invalid Period Days**:
   ```json
   {
     "error": "period_days must be between 1 and 90"
   }
   ```

2. **Directory Write Failure**:
   ```json
   {
     "success": false,
     "error": "Permission denied: /protected/dir",
     "message": "Failed to generate CSV export"
   }
   ```

3. **Invalid Session ID** (if using real data):
   ```json
   {
     "success": true,
     "message": "No data found for session_id: invalid_id"
   }
   ```

## Performance Notes

- **Typical Export Time**: 50-200ms for 7 days of data
- **Large Exports**: 30-day exports may take 100-400ms
- **Memory Usage**: ~10MB for in-memory exports, negligible for file exports

## Testing

Run the export tests:
```bash
python -m pytest tests/mcp/test_exports.py -v
```

Expected output:
```
26 passed in 0.18s
```

## Troubleshooting

### Export returns empty data
- Verify that analytics data has been collected
- Check session_id parameter if filtering by session
- Ensure period_days is within valid range (1-90)

### File not created
- Check write permissions for output_dir
- Verify output_dir exists or can be created
- Check available disk space

### Invalid JSON/CSV format
- Use `data_preview` to check truncated content
- Access `full_data` or file at `file_path` for complete data
- Verify network transfer didn't truncate response

## Future Enhancements

Potential future features:
- [ ] PDF report generation
- [ ] Email delivery of exports
- [ ] Scheduled/automated exports
- [ ] Custom date ranges (start/end instead of period_days)
- [ ] Multi-session comparison reports
- [ ] Chart/image generation from trends
