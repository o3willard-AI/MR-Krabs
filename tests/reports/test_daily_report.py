"""
Tests for Daily Cost Report module (reports/daily_report.py).

These tests cover daily cost reporting functionality.

P4-5: Daily Cost Reporting - Daily Report Tests  
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from src.reports.daily_report import DailyCostReport, DailyCostReportGenerator


class TestDailyCostReportDataclass:
    """Tests for the DailyCostReport dataclass."""
    
    def test_daily_cost_report_creation(self):
        """Test creating a basic DailyCostReport object."""
        report = DailyCostReport(
            date=date.today(),
            total_cost=Decimal("50.00"),
            task_count=100,
            tier_breakdown={"L0": Decimal("30.00"), "L1": Decimal("20.00")},
            model_breakdown={"model1": Decimal("40.00"), "model2": Decimal("10.00")}
        )
        
        assert report.total_cost == Decimal("50.00")
        assert report.task_count == 100
    
    def test_daily_cost_report_zero_cost(self):
        """Test DailyCostReport with zero cost."""
        report = DailyCostReport(
            date=date.today(),
            total_cost=Decimal("0.00"),
            task_count=0,
            tier_breakdown={},
            model_breakdown={}
        )
        
        assert report.total_cost == Decimal("0.00")


class TestDailyCostReportGenerator:
    """Tests for the DailyCostReportGenerator class."""
    
    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        generator = DailyCostReportGenerator()
        
        assert hasattr(generator, 'generate_report')
    
    def test_generate_report_basic(self):
        """Test generating a basic daily report from tracker."""
        generator = DailyCostReportGenerator()
        
        # With no tracker, should return empty report
        report = generator.generate_report(date.today())
        
        assert isinstance(report, DailyCostReport)


class TestReportContent:
    """Tests for report content and formatting."""
    
    def test_to_dict(self):
        """Test converting report to dictionary."""
        report = DailyCostReport(
            date=date.today(),
            total_cost=Decimal("50.00"),
            task_count=100,
            tier_breakdown={"L0": Decimal("30.00")},
            model_breakdown={"model1": Decimal("30.00")}
        )
        
        d = report.to_dict()
        
        assert "total_cost" in d
        assert "tier_breakdown" in d
    
    def test_str_representation(self):
        """Test string representation of report."""
        report = DailyCostReport(
            date=date.today(),
            total_cost=Decimal("50.00"),
            task_count=100,
            tier_breakdown={"L0": Decimal("30.00")},
            model_breakdown={"model1": Decimal("30.00")}
        )
        
        s = str(report)
        
        assert isinstance(s, str)
        assert len(s) > 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_zero_task_count(self):
        """Test report with zero tasks."""
        report = DailyCostReport(
            date=date.today(),
            total_cost=Decimal("50.00"),
            task_count=0,
            tier_breakdown={},
            model_breakdown={}
        )
        
        # String representation should handle zero count
        s = str(report)
        assert isinstance(s, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
