"""
Tests for DailyCostReport and generator (P4-5: Daily Cost Reporting)
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal

from src.reports.daily_report import DailyCostReport, DailyCostReportGenerator
from src.core.cost import CostEntry, TokenCount, CostTracker


class TestDailyCostReport:
    """Test DailyCostReport dataclass."""

    def test_daily_cost_report_basic(self):
        """Test basic DailyCostReport creation."""
        report = DailyCostReport(
            date=date(2026, 4, 30),
            total_cost=Decimal("10.50"),
            task_count=25,
            tier_breakdown={
                "L0-Coder": Decimal("2.50"),
                "L1-Coder": Decimal("5.00"),
                "L2-Coder": Decimal("3.00"),
            },
            model_breakdown={
                "free-tier": Decimal("2.50"),
                "economical": Decimal("5.00"),
                "balanced": Decimal("3.00"),
            }
        )
        
        assert report.date == date(2026, 4, 30)
        assert report.total_cost == Decimal("10.50")
        assert report.task_count == 25
        assert report.tier_breakdown["L0-Coder"] == Decimal("2.50")

    def test_daily_cost_report_empty(self):
        """Test DailyCostReport with no data."""
        report = DailyCostReport(
            date=date(2026, 4, 30),
            total_cost=Decimal("0.00"),
            task_count=0,
            tier_breakdown={},
            model_breakdown={}
        )
        
        assert report.total_cost == Decimal("0.00")
        assert report.task_count == 0

    def test_to_dict(self):
        """Test converting DailyCostReport to dictionary."""
        report = DailyCostReport(
            date=date(2026, 4, 30),
            total_cost=Decimal("10.50"),
            task_count=25,
            tier_breakdown={"L0-Coder": Decimal("5.00")},
            model_breakdown={"free-tier": Decimal("5.00")}
        )
        
        data = report.to_dict()
        
        assert data["date"] == "2026-04-30"
        assert data["total_cost"] == "10.50"
        assert data["task_count"] == 25
        assert data["tier_breakdown"]["L0-Coder"] == "5.00"

    def test_cost_percentages(self):
        """Test percentage calculations in report."""
        report = DailyCostReport(
            date=date(2026, 4, 30),
            total_cost=Decimal("10.00"),
            task_count=10,
            tier_breakdown={
                "L0-Coder": Decimal("2.00"),
                "L1-Coder": Decimal("8.00"),
            },
            model_breakdown={}
        )
        
        data = report.to_dict()
        assert data["tier_percentages"]["L0-Coder"] == 20.0
        assert data["tier_percentages"]["L1-Coder"] == 80.0


class TestDailyCostReportGenerator:
    """Test DailyCostReportGenerator class."""

    def test_generate_report_single_day(self):
        """Test generating report for single day."""
        tracker = CostTracker()
        
        # Use high token counts to get noticeable costs
        tracker.record(
            task_id="task-1",
            tier="L0-Coder",
            model="free-tier",
            tokens=TokenCount(10000, 5000, 15000),
            duration=1.0
        )
        tracker.record(
            task_id="task-2",
            tier="L1-Coder",
            model="economical",
            tokens=TokenCount(20000, 10000, 30000),
            duration=2.0
        )
        
        generator = DailyCostReportGenerator(tracker)
        report = generator.generate_report(datetime.now().date())
        
        assert report.date == datetime.now().date()
        assert report.task_count == 2
        # Costs should be positive
        assert report.total_cost > Decimal("0.00")

    def test_generate_report_no_data(self):
        """Test generating report when no cost data exists."""
        tracker = CostTracker()
        
        generator = DailyCostReportGenerator(tracker)
        report = generator.generate_report(datetime.now().date())
        
        assert report.date == datetime.now().date()
        assert report.total_cost == Decimal("0.00")
        assert report.task_count == 0
        assert report.tier_breakdown == {}

    def test_generate_report_tier_breakdown(self):
        """Test tier breakdown calculation."""
        tracker = CostTracker()
        
        # Record tasks with different tiers and high token counts
        tracker.record(task_id="task-1", tier="L0-Coder", model="free-tier", tokens=TokenCount(10000, 5000, 15000), duration=1.0)
        tracker.record(task_id="task-2", tier="L0-Coder", model="free-tier", tokens=TokenCount(10000, 5000, 15000), duration=1.0)
        tracker.record(task_id="task-3", tier="L1-Coder", model="economical", tokens=TokenCount(20000, 10000, 30000), duration=2.0)
        
        generator = DailyCostReportGenerator(tracker)
        report = generator.generate_report(datetime.now().date())
        
        assert "L0-Coder" in report.tier_breakdown
        assert "L1-Coder" in report.tier_breakdown
        # Total should equal sum of tier costs
        total_from_tiers = sum(report.tier_breakdown.values())
        assert report.total_cost == total_from_tiers

    def test_generate_report_model_breakdown(self):
        """Test model breakdown calculation."""
        tracker = CostTracker()
        
        tracker.record(task_id="task-1", tier="L0-Coder", model="free-tier", tokens=TokenCount(10000, 5000, 15000), duration=1.0)
        tracker.record(task_id="task-2", tier="L0-Coder", model="free-tier", tokens=TokenCount(10000, 5000, 15000), duration=1.0)
        tracker.record(task_id="task-3", tier="L1-Coder", model="balanced", tokens=TokenCount(20000, 10000, 30000), duration=2.0)
        
        generator = DailyCostReportGenerator(tracker)
        report = generator.generate_report(datetime.now().date())
        
        assert "free-tier" in report.model_breakdown
        assert "balanced" in report.model_breakdown
        # Total should equal sum of model costs
        total_from_models = sum(report.model_breakdown.values())
        assert report.total_cost == total_from_models

    def test_generate_report_with_multiple_tiers(self):
        """Test report with all tier levels."""
        tracker = CostTracker()
        
        tracker.record(task_id="task-1", tier="L0-Coder", model="free-tier", tokens=TokenCount(10000, 5000, 15000), duration=1.0)
        tracker.record(task_id="task-2", tier="L1-Coder", model="economical", tokens=TokenCount(20000, 10000, 30000), duration=2.0)
        tracker.record(task_id="task-3", tier="L2-Coder", model="balanced", tokens=TokenCount(30000, 15000, 45000), duration=3.0)
        tracker.record(task_id="task-4", tier="L3-Coder", model="premium", tokens=TokenCount(40000, 20000, 60000), duration=4.0)
        
        generator = DailyCostReportGenerator(tracker)
        report = generator.generate_report(datetime.now().date())
        
        assert len(report.tier_breakdown) == 4
        assert "L0-Coder" in report.tier_breakdown
        assert "L3-Coder" in report.tier_breakdown
        assert report.task_count == 4


class TestDailyReportWithRealCostTracker:
    """Test DailyCostReportGenerator with actual CostTracker (integration)."""

    def test_generate_from_cost_tracker(self):
        """Test generating report from real CostTracker instance."""
        tracker = CostTracker()
        
        for i in range(5):
            tracker.record(
                task_id=f"test-task-{i}",
                tier="L0-Coder",
                model="free-tier",
                tokens=TokenCount(10000, 5000, 15000),
                duration=1.0
            )
        
        generator = DailyCostReportGenerator(tracker)
        report = generator.generate_report(datetime.now().date())
        
        assert report.task_count == 5
        assert report.total_cost > Decimal("0.00")
        assert report.tier_breakdown["L0-Coder"] == report.total_cost


class TestDailyReportDateRange:
    """Test daily report with date range functionality."""

    def test_generate_multiple_dates(self):
        """Test generating reports for multiple dates."""
        tracker = CostTracker()
        
        # Add entries for different dates
        now = datetime.now()
        
        # Create entry for yesterday (manually add to entries list)
        yesterday = now - timedelta(days=1)
        tracker.entries.append(CostEntry(
            timestamp=yesterday.isoformat() + "T10:00:00Z",
            task_id="task-1",
            tier="L0-Coder",
            model="free-tier",
            tokens=TokenCount(10000, 5000, 15000),
            cost_usd=Decimal("0.01"),
            duration_seconds=1.0
        ))
        
        # Create entry for today
        today_cost = Decimal("0.02")
        tracker.record(
            task_id="task-2",
            tier="L1-Coder",
            model="economical",
            tokens=TokenCount(20000, 10000, 30000),
            duration=2.0
        )
        # Adjust the latest entry to have specific cost
        if tracker.entries:
            tracker.entries[-1].cost_usd = today_cost
        
        generator = DailyCostReportGenerator(tracker)
        
        report_yesterday = generator.generate_report(yesterday.date())
        report_today = generator.generate_report(now.date())
        
        # Verify we got different reports for different dates
        assert report_yesterday.date == yesterday.date()
        assert report_today.date == now.date()
