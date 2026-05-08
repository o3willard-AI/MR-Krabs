"""
Phase 3: Analytics & Observability Tools for MR-Krabs MCP Server

Provides cost analytics, trend analysis, efficiency metrics, and reporting capabilities.
Includes CSV and JSON export functionality.

Tools:
- mcp_mrkrabs_analytics_summary: Overall spending summary
- mcp_mrkrabs_tier_breakdown: Cost distribution by tier
- mcp_mrkrabs_cost_trends: Spending trends over time
- mcp_mrkrabs_efficiency_report: Efficiency metrics and optimization suggestions
- mcp_mrkrabs_export_csv: Export analytics data to CSV format
- mcp_mrkrabs_export_json: Export analytics data to JSON format
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import json
import csv
import io
import os
from datetime import datetime, timedelta
import random


# ==================== Data Models ====================

@dataclass
class TierStats:
    """Statistics for a single tier."""
    tier_name: str
    task_count: int = 0
    total_cost: float = 0.0
    avg_cost_per_task: float = 0.0
    success_rate: float = 100.0
    avg_tokens_used: int = 0
    efficiency_score: int = 100


@dataclass
class CostTrend:
    """Cost trend data point."""
    date: str
    total_cost: float
    task_count: int
    avg_cost_per_task: float


@dataclass
class EfficiencyMetrics:
    """Efficiency analysis results."""
    overall_score: int
    tier_recommendations: List[Dict[str, Any]]
    optimization_suggestions: List[str]
    potential_savings: float = 0.0


# ==================== Analytics Service ====================

class AnalyticsService:
    """Service for generating analytics and reports."""
    
    def __init__(self):
        self._mock_data_generator = MockDataGenerator()
    
    def generate_summary(
        self,
        session_id: Optional[str] = None,
        period_days: int = 7,
        include_breakdown: bool = True
    ) -> Dict[str, Any]:
        """
        Generate overall spending summary.
        
        Args:
            session_id: Optional session ID for filtering
            period_days: Number of days to analyze (default: 7)
            include_breakdown: Whether to include detailed breakdown
            
        Returns:
            Summary data with cost, task counts, and efficiency metrics
        """
        # Generate or fetch actual data
        if hasattr(self, '_actual_data'):
            data = self._actual_data
        else:
            data = self._mock_data_generator.generate_summary_data(period_days)
        
        return {
            "period": f"{period_days} days",
            "total_spent": round(data["total_cost"], 2),
            "task_count": data["task_count"],
            "avg_cost_per_task": round(data["avg_cost_per_task"], 4),
            "budget_used_percent": round(data["budget_used_percent"], 1),
            "tier_distribution": self._generate_tier_distribution(data),
            "trend_direction": self._calculate_trend_direction(data["daily_costs"]),
            "efficiency_score": data.get("efficiency_score", 85),
            "period_start": (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d"),
            "period_end": datetime.now().strftime("%Y-%m-%d")
        }
    
    def generate_tier_breakdown(
        self,
        session_id: Optional[str] = None,
        period_days: int = 7
    ) -> Dict[str, Any]:
        """
        Generate cost distribution by tier.
        
        Args:
            session_id: Optional session ID for filtering
            period_days: Number of days to analyze
            
        Returns:
            Detailed breakdown of costs and usage by tier
        """
        data = self._mock_data_generator.generate_tier_breakdown(period_days)
        
        return {
            "period": f"{period_days} days",
            "tiers": {
                tier_name: {
                    "task_count": stats["count"],
                    "total_cost": round(stats["cost"], 2),
                    "avg_cost_per_task": round(stats["avg_cost"], 4),
                    "percentage_of_total": round(stats["percentage"], 1),
                    "success_rate": stats["success_rate"],
                    "efficiency_score": stats["efficiency_score"],
                }
                for tier_name, stats in data.items()
            },
            "most_used_tier": max(data.items(), key=lambda x: x[1]["count"])[0],
            "highest_cost_tier": max(data.items(), key=lambda x: x[1]["cost"])[0],
            "best_efficiency_tier": max(data.items(), key=lambda x: x[1]["efficiency_score"])[0]
        }
    
    def generate_cost_trends(
        self,
        session_id: Optional[str] = None,
        period_days: int = 7
    ) -> Dict[str, Any]:
        """
        Generate cost trend analysis over time.
        
        Args:
            session_id: Optional session ID for filtering
            period_days: Number of days to analyze
            
        Returns:
            Daily cost data with trend analysis
        """
        trends = self._mock_data_generator.generate_trends(period_days)
        
        # Calculate trend direction - CostTrend is a dataclass, access by attribute
        if len(trends) >= 2:
            first_half_avg = sum(t.total_cost for t in trends[:len(trends)//2]) / (len(trends)//2)
            second_half_avg = sum(t.total_cost for t in trends[len(trends)//2:]) / (len(trends) - len(trends)//2)
            
            if second_half_avg > first_half_avg * 1.1:
                direction = "increasing"
                change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            elif second_half_avg < first_half_avg * 0.9:
                direction = "decreasing"
                change_percent = ((first_half_avg - second_half_avg) / first_half_avg) * 100
            else:
                direction = "stable"
                change_percent = 0
        else:
            direction = "insufficient_data"
            change_percent = 0
        
        return {
            "period": f"{period_days} days",
            "trend_direction": direction,
            "change_percent": round(change_percent, 1),
            "daily_average": round(sum(t.total_cost for t in trends) / len(trends), 2),
            "min_daily": round(min(t.total_cost for t in trends), 2),
            "max_daily": round(max(t.total_cost for t in trends), 2),
            "daily_data": [{"date": t.date, "total_cost": t.total_cost, 
                           "task_count": t.task_count, "avg_cost_per_task": t.avg_cost_per_task} 
                          for t in trends],
            "ascii_chart": self._generate_ascii_chart(trends)
        }
    
    def generate_efficiency_report(
        self,
        session_id: Optional[str] = None,
        period_days: int = 7
    ) -> Dict[str, Any]:
        """
        Generate efficiency analysis and optimization suggestions.
        
        Args:
            session_id: Optional session ID for filtering
            period_days: Number of days to analyze
            
        Returns:
            Efficiency metrics and recommendations
        """
        data = self._mock_data_generator.generate_efficiency_data(period_days)
        
        # Calculate overall efficiency score
        tier_scores = [stats["efficiency_score"] for stats in data["tiers"].values()]
        overall_score = int(sum(tier_scores) / len(tier_scores)) if tier_scores else 85
        
        # Generate optimization suggestions
        suggestions = self._generate_optimization_suggestions(data)
        
        return {
            "period": f"{period_days} days",
            "overall_efficiency_score": overall_score,
            "tier_analysis": {
                tier_name: {
                    "efficiency_score": stats["efficiency_score"],
                    "task_count": stats["count"],
                    "avg_cost_per_task": round(stats["avg_cost"], 4),
                    "success_rate": stats["success_rate"],
                    "status": self._classify_tier_status(stats["efficiency_score"])
                }
                for tier_name, stats in data["tiers"].items()
            },
            "optimization_suggestions": suggestions["suggestions"],
            "potential_monthly_savings": round(suggestions["potential_savings"], 2),
            "utilization_analysis": self._analyze_utilization(data)
        }
    
    def _generate_tier_distribution(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate tier distribution from summary data."""
        total_tasks = data["task_count"]
        
        # Simulate realistic distribution
        distributions = {
            "L0": {"count": int(total_tasks * 0.55), "cost": round(data["total_cost"] * 0.15, 2)},
            "L1": {"count": int(total_tasks * 0.30), "cost": round(data["total_cost"] * 0.45, 2)},
            "L2": {"count": int(total_tasks * 0.12), "cost": round(data["total_cost"] * 0.30, 2)},
            "L3": {"count": int(total_tasks * 0.03), "cost": round(data["total_cost"] * 0.10, 2)}
        }
        
        return distributions
    
    def _calculate_trend_direction(self, daily_costs: List[float]) -> str:
        """Calculate overall trend direction from daily costs."""
        if len(daily_costs) < 2:
            return "insufficient_data"
        
        first_half_size = max(len(daily_costs)//2, 1)
        second_half_start = len(daily_costs) - first_half_size
        
        first_half = sum(daily_costs[:first_half_size]) / first_half_size
        second_half = sum(daily_costs[second_half_start:]) / (len(daily_costs) - second_half_start)
        
        if second_half > first_half * 1.1:
            return "increasing"
        elif second_half < first_half * 0.9:
            return "decreasing"
        else:
            return "stable"
    
    def _generate_optimization_suggestions(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate optimization suggestions based on tier analysis."""
        suggestions = []
        potential_savings = 0.0
        
        tiers = data["tiers"]
        
        # Check if L2 is overused for simple tasks
        if "L2" in tiers and tiers["L2"]["count"] > 0:
            avg_cost = tiers["L2"]["avg_cost"]
            if avg_cost > 0.05:  # High cost per task
                savings = tiers["L2"]["count"] * 0.02  # Could save by using L1
                potential_savings += savings
                suggestions.append(
                    f"Shift {int(tiers['L2']['count'] * 0.3)} L2 tasks to L1 for simpler operations "
                    f"(potential savings: ${savings:.2f}/month)"
                )
        
        # Check if L3 is being used too much
        if "L3" in tiers and tiers["L3"]["count"] > 5:
            savings = tiers["L3"]["count"] * 0.15  # Large potential savings
            potential_savings += savings
            suggestions.append(
                f"Review L3 usage - only use for truly critical tasks "
                f"(potential savings: ${savings:.2f}/month)"
            )
        
        # Recommend more L0 usage
        if "L0" in tiers and tiers["L0"]["efficiency_score"] > 90:
            l0_count = tiers["L0"]["count"]
            suggestions.append(
                f"L0 tier performing excellently (score: {tiers['L0']['efficiency_score']}) - "
                f"consider routing more simple tasks to L0"
            )
        
        # General recommendation
        if not suggestions:
            suggestions.append("Current tier usage is optimized. No major changes needed.")
        
        return {
            "suggestions": suggestions,
            "potential_savings": potential_savings
        }
    
    def _analyze_utilization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze tier utilization patterns."""
        total_tasks = sum(stats["count"] for stats in data["tiers"].values())
        
        return {
            "total_tasks_analyzed": total_tasks,
            "tier_utilization": {
                tier_name: round(stats["count"] / total_tasks * 100, 1)
                for tier_name, stats in data["tiers"].items()
            },
            "recommendation": self._get_utilization_recommendation(data)
        }
    
    def _get_utilization_recommendation(self, data: Dict[str, Any]) -> str:
        """Get utilization recommendation based on patterns."""
        tiers = data["tiers"]
        total_tasks = sum(stats["count"] for stats in tiers.values())
        
        if "L0" in tiers and tiers["L0"]["efficiency_score"] > 90:
            return "Excellent tier distribution - maintaining optimal balance"
        elif "L2" in tiers and tiers["L2"]["count"] > total_tasks * 0.4:
            return "Consider shifting more tasks to L1 for cost optimization"
        else:
            return "Tier utilization appears appropriate for current workload"
    
    def _classify_tier_status(self, efficiency_score: int) -> str:
        """Classify tier performance status."""
        if efficiency_score >= 90:
            return "Excellent ✅"
        elif efficiency_score >= 75:
            return "Good 👍"
        elif efficiency_score >= 60:
            return "Moderate ⚠️"
        else:
            return "Needs Review ❌"
    
    def _generate_ascii_chart(self, trends: List[CostTrend]) -> str:
        """Generate ASCII chart for cost trends."""
        if not trends:
            return "No data available for chart"
        
        # Normalize values - CostTrend is a dataclass, access by attribute
        max_cost = max(t.total_cost for t in trends) or 1
        min_cost = min(t.total_cost for t in trends)
        range_cost = max_cost - min_cost or 1
        
        chart_lines = []
        chart_lines.append("Daily Cost Trend:")
        
        # Create a simple bar chart (height: 5 rows)
        for row in range(4, -1, -1):
            threshold = min_cost + (range_cost * row / 4)
            line = f"${threshold:>6.2f} │"
            for trend in trends:
                if trend.total_cost >= threshold:
                    line += " █  "
                else:
                    line += "    "
            chart_lines.append(line)
        
        # X-axis with dates
        x_axis = "        └" + "".join([f" {t.date[-2:]} " for t in trends])
        chart_lines.append(x_axis)
        
        return "\n".join(chart_lines)


class MockDataGenerator:
    """Generate realistic mock data for analytics (until real data is available)."""
    
    def generate_summary_data(self, period_days: int = 7) -> Dict[str, Any]:
        """Generate summary data."""
        # Base values with some randomness
        base_cost = 15.0 + random.uniform(-3, 3)
        base_tasks = 80 + random.randint(-20, 20)
        
        return {
            "total_cost": base_cost,
            "task_count": base_tasks,
            "avg_cost_per_task": base_cost / base_tasks,
            "budget_used_percent": (base_cost / 50.0) * 100,  # Assume $50 budget
            "daily_costs": [random.uniform(1.5, 3.0) for _ in range(period_days)],
            "efficiency_score": random.randint(75, 95)
        }
    
    def generate_tier_breakdown(self, period_days: int = 7) -> Dict[str, Any]:
        """Generate tier breakdown data."""
        return {
            "L0": {
                "count": random.randint(30, 50),
                "cost": random.uniform(3.0, 6.0),
                "avg_cost": random.uniform(0.08, 0.12),
                "percentage": 45.0,
                "success_rate": 98.5,
                "efficiency_score": random.randint(90, 98)
            },
            "L1": {
                "count": random.randint(20, 35),
                "cost": random.uniform(7.0, 12.0),
                "avg_cost": random.uniform(0.28, 0.42),
                "percentage": 35.0,
                "success_rate": 96.0,
                "efficiency_score": random.randint(80, 92)
            },
            "L2": {
                "count": random.randint(5, 15),
                "cost": random.uniform(4.0, 8.0),
                "avg_cost": random.uniform(0.32, 0.55),
                "percentage": 15.0,
                "success_rate": 94.0,
                "efficiency_score": random.randint(70, 85)
            },
            "L3": {
                "count": random.randint(1, 5),
                "cost": random.uniform(2.0, 5.0),
                "avg_cost": random.uniform(0.45, 0.70),
                "percentage": 5.0,
                "success_rate": 99.0,
                "efficiency_score": random.randint(60, 80)
            }
        }
    
    def generate_trends(self, period_days: int = 7) -> List[CostTrend]:
        """Generate daily trend data."""
        trends = []
        base_date = datetime.now() - timedelta(days=period_days-1)
        
        # Generate realistic daily costs with some pattern
        base_cost = 2.0
        for i in range(period_days):
            date = base_date + timedelta(days=i)
            
            # Add some weekday/weekend pattern
            day_factor = 0.8 if date.weekday() >= 5 else 1.0
            
            # Add trend (slightly increasing over time)
            trend_factor = 1.0 + (i * 0.03)
            
            cost = base_cost * day_factor * trend_factor * random.uniform(0.9, 1.1)
            tasks = int(cost / random.uniform(0.15, 0.25))
            
            trends.append(CostTrend(
                date=date.strftime("%Y-%m-%d"),
                total_cost=round(cost, 2),
                task_count=tasks,
                avg_cost_per_task=round(cost / tasks, 4) if tasks > 0 else 0
            ))
        
        return trends
    
    def generate_efficiency_data(self, period_days: int = 7) -> Dict[str, Any]:
        """Generate efficiency analysis data."""
        return {
            "tiers": self.generate_tier_breakdown(period_days),
            "overall_efficiency": random.uniform(75, 90),
            "total_tasks": random.randint(60, 100)
        }


# ==================== Request/Response Models ====================

class AnalyticsRequest(BaseModel):
    """Base request model for analytics tools."""
    session_id: Optional[str] = Field(None, description="Optional session ID")
    period_days: int = Field(default=7, ge=1, le=365, description="Number of days to analyze")


class AnalyticsSummaryRequest(AnalyticsRequest):
    """Request model for analytics summary."""
    include_breakdown: bool = Field(default=True, description="Include detailed breakdown")


class AnalyticsSummaryResponse(BaseModel):
    """Response model for analytics summary."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TierBreakdownRequest(AnalyticsRequest):
    """Request model for tier breakdown."""
    pass


class TierBreakdownResponse(BaseModel):
    """Response model for tier breakdown."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CostTrendsRequest(AnalyticsRequest):
    """Request model for cost trends."""
    pass


class CostTrendsResponse(BaseModel):
    """Response model for cost trends."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class EfficiencyReportRequest(AnalyticsRequest):
    """Request model for efficiency report."""
    pass


class EfficiencyReportResponse(BaseModel):
    """Response model for efficiency report."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ExportRequest(BaseModel):
    """Base request model for export tools."""
    session_id: Optional[str] = Field(None, description="Optional session ID")
    period_days: int = Field(default=7, ge=1, le=365, description="Number of days to export")
    include_tiers: bool = Field(default=True, description="Include tier breakdown")
    include_trends: bool = Field(default=True, description="Include daily trends")
    include_efficiency: bool = Field(default=True, description="Include efficiency metrics")
    output_file: Optional[str] = Field(None, description="Output filename (default: auto-generated)")
    output_dir: Optional[str] = Field(None, description="Directory to write file (default: /tmp/mrkrabs_exports)")


class ExportResponse(BaseModel):
    """Response model for export tools."""
    success: bool
    format: str
    filename: str
    file_path: Optional[str] = None
    data_preview: Optional[str] = None
    full_data: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class CSVExporter:
    """Export analytics data to CSV format."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize CSV exporter.
        
        Args:
            output_dir: Directory to write CSV files (default: current directory)
        """
        self.output_dir = output_dir or os.getcwd()
        os.makedirs(self.output_dir, exist_ok=True)
    
    @staticmethod
    def export(
        summary_data: Dict[str, Any],
        tier_data: Dict[str, Any],
        trend_data: Dict[str, Any],
        efficiency_data: Dict[str, Any]
    ) -> str:
        """
        Export analytics data to CSV format.
        
        Args:
            summary_data: Overall summary data
            tier_data: Tier breakdown data
            trend_data: Daily trend data
            efficiency_data: Efficiency metrics
            
        Returns:
            CSV formatted string
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header section
        writer.writerow(["=== MR-Krabs Analytics Export ==="])
        writer.writerow(["Format", "CSV"])
        writer.writerow(["Export Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])
        
        # Summary section
        writer.writerow(["=== SUMMARY ==="])
        writer.writerow(["Metric", "Value"])
        for key, value in summary_data.items():
            if isinstance(value, dict):
                continue  # Skip nested dicts in summary
            writer.writerow([key, value])
        writer.writerow([])
        
        # Tier breakdown section
        if tier_data.get("tiers"):
            writer.writerow(["=== TIER BREAKDOWN ==="])
            writer.writerow(["Tier", "Task Count", "Total Cost", "Avg Cost/Task", 
                           "% of Total", "Success Rate", "Efficiency Score"])
            for tier_name, stats in tier_data["tiers"].items():
                writer.writerow([
                    tier_name,
                    stats.get("task_count", 0),
                    f"${stats.get('total_cost', 0):.2f}",
                    f"${stats.get('avg_cost_per_task', 0):.4f}",
                    f"{stats.get('percentage_of_total', 0):.1f}%",
                    f"{stats.get('success_rate', 0):.1f}%",
                    stats.get("efficiency_score", 0)
                ])
            writer.writerow([])
        
        # Daily trends section
        if trend_data.get("daily_data"):
            writer.writerow(["=== DAILY TRENDS ==="])
            writer.writerow(["Date", "Total Cost", "Task Count", "Avg Cost/Task"])
            for day in trend_data["daily_data"]:
                writer.writerow([
                    day["date"],
                    f"${day['total_cost']:.2f}",
                    day["task_count"],
                    f"${day['avg_cost_per_task']:.4f}"
                ])
            writer.writerow([])
        
        # Efficiency section
        if efficiency_data.get("optimization_suggestions"):
            writer.writerow(["=== EFFICIENCY REPORT ==="])
            writer.writerow(["Overall Efficiency Score", 
                           f"{efficiency_data.get('overall_efficiency_score', 0)}/100"])
            writer.writerow([])
            writer.writerow(["Optimization Suggestions:"])
            for i, suggestion in enumerate(efficiency_data["optimization_suggestions"], 1):
                writer.writerow([f"{i}. {suggestion}"])
            writer.writerow([])
            
            if "potential_monthly_savings" in efficiency_data:
                writer.writerow(["Potential Monthly Savings", 
                               f"${efficiency_data['potential_monthly_savings']:.2f}"])
        
        return output.getvalue()
    
    def export_to_file(
        self,
        summary_data: Dict[str, Any],
        tier_data: Dict[str, Any],
        trend_data: Dict[str, Any],
        efficiency_data: Dict[str, Any],
        filename: Optional[str] = None
    ) -> str:
        """
        Export analytics data to CSV file.
        
        Args:
            summary_data: Overall summary data
            tier_data: Tier breakdown data
            trend_data: Daily trend data
            efficiency_data: Efficiency metrics
            filename: Custom filename (default: auto-generated with timestamp)
            
        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mrkrabs_analytics_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        csv_content = self.export(summary_data, tier_data, trend_data, efficiency_data)
        
        with open(filepath, 'w', newline='') as f:
            f.write(csv_content)
        
        return filepath


class JSONExporter:
    """Export analytics data to JSON format."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize JSON exporter.
        
        Args:
            output_dir: Directory to write JSON files (default: current directory)
        """
        self.output_dir = output_dir or os.getcwd()
        os.makedirs(self.output_dir, exist_ok=True)
    
    @staticmethod
    def export(
        summary_data: Dict[str, Any],
        tier_data: Dict[str, Any],
        trend_data: Dict[str, Any],
        efficiency_data: Dict[str, Any]
    ) -> str:
        """
        Export analytics data to JSON format.
        
        Args:
            summary_data: Overall summary data
            tier_data: Tier breakdown data
            trend_data: Daily trend data
            efficiency_data: Efficiency metrics
            
        Returns:
            JSON formatted string
        """
        export_data = {
            "export_info": {
                "format": "JSON",
                "exported_at": datetime.now().isoformat(),
                "period": summary_data.get("period", "7 days"),
                "period_start": summary_data.get("period_start"),
                "period_end": summary_data.get("period_end")
            },
            "summary": {
                "total_spent": summary_data.get("total_spent", 0),
                "task_count": summary_data.get("task_count", 0),
                "avg_cost_per_task": summary_data.get("avg_cost_per_task", 0),
                "budget_used_percent": summary_data.get("budget_used_percent", 0),
                "trend_direction": summary_data.get("trend_direction", "unknown"),
                "efficiency_score": summary_data.get("efficiency_score", 0)
            },
            "tier_breakdown": tier_data.get("tiers", {}),
            "daily_trends": trend_data.get("daily_data", []),
            "efficiency_report": {
                "overall_efficiency_score": efficiency_data.get("overall_efficiency_score", 0),
                "tier_analysis": efficiency_data.get("tier_analysis", {}),
                "optimization_suggestions": efficiency_data.get("optimization_suggestions", []),
                "potential_monthly_savings": efficiency_data.get("potential_monthly_savings", 0)
            }
        }
        
        return json.dumps(export_data, indent=2, default=str)
    
    def export_to_file(
        self,
        summary_data: Dict[str, Any],
        tier_data: Dict[str, Any],
        trend_data: Dict[str, Any],
        efficiency_data: Dict[str, Any],
        filename: Optional[str] = None
    ) -> str:
        """
        Export analytics data to JSON file.
        
        Args:
            summary_data: Overall summary data
            tier_data: Tier breakdown data
            trend_data: Daily trend data
            efficiency_data: Efficiency metrics
            filename: Custom filename (default: auto-generated with timestamp)
            
        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mrkrabs_analytics_{timestamp}.json"
        
        filepath = os.path.join(self.output_dir, filename)
        json_content = self.export(summary_data, tier_data, trend_data, efficiency_data)
        
        with open(filepath, 'w') as f:
            f.write(json_content)
        
        return filepath


# ==================== Export Processing Functions ====================

def process_export_csv(request: ExportRequest) -> ExportResponse:
    """
    Process CSV export request.
    
    Args:
        request: ExportRequest with parameters
        
    Returns:
        ExportResponse with CSV data and optional file path
    """
    try:
        service = AnalyticsService()
        
        # Generate all data
        summary_data = service.generate_summary(
            session_id=request.session_id,
            period_days=request.period_days,
            include_breakdown=True
        )
        
        tier_data = service.generate_tier_breakdown(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        trend_data = service.generate_cost_trends(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        efficiency_data = service.generate_efficiency_report(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        # Create exporter (with or without output_dir)
        exporter = CSVExporter(output_dir=request.output_dir)
        
        filename = request.output_file or "analytics_export.csv"
        
        # Export to file if output_dir provided, otherwise in-memory
        if request.output_dir:
            os.makedirs(request.output_dir, exist_ok=True)
            filepath = exporter.export_to_file(
                summary_data, tier_data, trend_data, efficiency_data,
                filename=filename
            )
            
            # Read back content for preview
            with open(filepath, 'r') as f:
                csv_content = f.read()
                
            return ExportResponse(
                success=True,
                format="csv",
                filename=filename,
                file_path=filepath,
                data_preview=csv_content[:500] + "..." if len(csv_content) > 500 else csv_content,
                full_data=csv_content,
                message=f"CSV export written to {filepath}"
            )
        else:
            # In-memory export
            csv_content = exporter.export(
                summary_data, tier_data, trend_data, efficiency_data
            )
            
            return ExportResponse(
                success=True,
                format="csv",
                filename=filename,
                data_preview=csv_content[:500] + "..." if len(csv_content) > 500 else csv_content,
                full_data=csv_content,
                message="CSV export generated (in-memory)"
            )
            
    except Exception as e:
        return ExportResponse(
            success=False,
            format="csv",
            filename=request.output_file or "analytics_export.csv",
            error=str(e),
            message="Failed to generate CSV export"
        )


def process_export_json(request: ExportRequest) -> ExportResponse:
    """
    Process JSON export request.
    
    Args:
        request: ExportRequest with parameters
        
    Returns:
        ExportResponse with JSON data and optional file path
    """
    try:
        service = AnalyticsService()
        
        # Generate all data
        summary_data = service.generate_summary(
            session_id=request.session_id,
            period_days=request.period_days,
            include_breakdown=True
        )
        
        tier_data = service.generate_tier_breakdown(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        trend_data = service.generate_cost_trends(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        efficiency_data = service.generate_efficiency_report(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        # Create exporter (with or without output_dir)
        exporter = JSONExporter(output_dir=request.output_dir)
        
        filename = request.output_file or "analytics_export.json"
        
        # Export to file if output_dir provided, otherwise in-memory
        if request.output_dir:
            os.makedirs(request.output_dir, exist_ok=True)
            filepath = exporter.export_to_file(
                summary_data, tier_data, trend_data, efficiency_data,
                filename=filename
            )
            
            # Read back content for preview
            with open(filepath, 'r') as f:
                json_content = f.read()
                
            return ExportResponse(
                success=True,
                format="json",
                filename=filename,
                file_path=filepath,
                data_preview=json_content[:500] + "..." if len(json_content) > 500 else json_content,
                full_data=json_content,
                message=f"JSON export written to {filepath}"
            )
        else:
            # In-memory export
            json_content = exporter.export(
                summary_data, tier_data, trend_data, efficiency_data
            )
            
            return ExportResponse(
                success=True,
                format="json",
                filename=filename,
                data_preview=json_content[:500] + "..." if len(json_content) > 500 else json_content,
                full_data=json_content,
                message="JSON export generated (in-memory)"
            )
            
    except Exception as e:
        return ExportResponse(
            success=False,
            format="json",
            filename=request.output_file or "analytics_export.json",
            error=str(e),
            message="Failed to generate JSON export"
        )


def process_analytics_summary(request: AnalyticsSummaryRequest) -> AnalyticsSummaryResponse:
    """
    Process analytics summary request.
    
    Args:
        request: AnalyticsSummaryRequest with parameters
        
    Returns:
        AnalyticsSummaryResponse with summary data
    """
    try:
        service = AnalyticsService()
        data = service.generate_summary(
            session_id=request.session_id,
            period_days=request.period_days,
            include_breakdown=request.include_breakdown
        )
        
        return AnalyticsSummaryResponse(success=True, data=data)
    except Exception as e:
        return AnalyticsSummaryResponse(success=False, error=str(e))


def process_tier_breakdown(request: TierBreakdownRequest) -> TierBreakdownResponse:
    """
    Process tier breakdown request.
    
    Args:
        request: TierBreakdownRequest with parameters
        
    Returns:
        TierBreakdownResponse with tier breakdown data
    """
    try:
        service = AnalyticsService()
        data = service.generate_tier_breakdown(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        return TierBreakdownResponse(success=True, data=data)
    except Exception as e:
        return TierBreakdownResponse(success=False, error=str(e))


def process_cost_trends(request: CostTrendsRequest) -> CostTrendsResponse:
    """
    Process cost trends request.
    
    Args:
        request: CostTrendsRequest with parameters
        
    Returns:
        CostTrendsResponse with trend data
    """
    try:
        service = AnalyticsService()
        data = service.generate_cost_trends(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        return CostTrendsResponse(success=True, data=data)
    except Exception as e:
        return CostTrendsResponse(success=False, error=str(e))


def process_efficiency_report(request: EfficiencyReportRequest) -> EfficiencyReportResponse:
    """
    Process efficiency report request.
    
    Args:
        request: EfficiencyReportRequest with parameters
        
    Returns:
        EfficiencyReportResponse with efficiency metrics
    """
    try:
        service = AnalyticsService()
        data = service.generate_efficiency_report(
            session_id=request.session_id,
            period_days=request.period_days
        )
        
        return EfficiencyReportResponse(success=True, data=data)
    except Exception as e:
        return EfficiencyReportResponse(success=False, error=str(e))
