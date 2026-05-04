"""
Tests for CLI report commands (P4-5: Daily Cost Reporting)
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from src.cli.commands import (
    cmd_daily_report,
    cmd_efficiency_report,
    cmd_trend_report,
    cmd_optimization_report,
)


class TestReportCLICommands:
    """Test CLI report commands."""

    def test_daily_report_command(self):
        """Test daily report CLI command."""
        with patch('src.cli.commands.load_config') as mock_load_config:
            mock_config = {
                "budget": {
                    "daily_limit_usd": "100.00",
                    "failure_mode": "fail_open_with_alert"
                },
                "warning_threshold": "0.80"
            }
            mock_load_config.return_value = mock_config
            
            # Mock the MetricsCollector
            with patch('src.core.metrics.MetricsCollector') as mock_metrics:
                mock_instance = MagicMock()
                mock_instance.get_daily_summary.return_value = {
                    'total_cost': Decimal("45.00"),
                    'total_tasks': 500,
                    'cost_by_tier': {
                        'L0-Coder': Decimal("10.00"),
                        'L1-Coder': Decimal("20.00"),
                        'L2-Coder': Decimal("15.00")
                    },
                    'date': date.today()
                }
                mock_metrics.return_value = mock_instance
                
                # Should not raise
                result = cmd_daily_report()
                assert result == 0
    
    def test_efficiency_report_command(self):
        """Test efficiency report CLI command."""
        with patch('src.cli.commands.load_config') as mock_load_config:
            mock_load_config.return_value = {"budget": {}}
            
            # Mock the MetricsCollector
            with patch('src.core.metrics.MetricsCollector') as mock_metrics:
                mock_instance = MagicMock()
                mock_instance.get_tier_metrics.return_value = {
                    'L0-Coder': {
                        'count': 1000,
                        'cost': Decimal("25.00"),
                        'success_count': 980
                    },
                    'L1-Coder': {
                        'count': 500,
                        'cost': Decimal("125.00"),
                        'success_count': 475
                    }
                }
                mock_metrics.return_value = mock_instance
                
                # Should not raise
                result = cmd_efficiency_report()
                assert result == 0
    
    def test_trend_report_command(self):
        """Test trend report CLI command."""
        # Mock the MetricsCollector
        with patch('src.core.metrics.MetricsCollector') as mock_metrics:
            mock_instance = MagicMock()
            mock_instance.get_daily_costs_7day.return_value = [
                Decimal("10.00"), Decimal("12.00"), Decimal("11.00"),
                Decimal("15.00"), Decimal("14.00"), Decimal("16.00"), Decimal("18.00")
            ]
            mock_metrics.return_value = mock_instance
            
            # Should not raise
            result = cmd_trend_report(days=7)
            assert result == 0
    
    def test_optimization_report_command(self):
        """Test optimization report CLI command."""
        # Mock the MetricsCollector first
        with patch('src.core.metrics.MetricsCollector') as mock_metrics:
            mock_instance = MagicMock()
            mock_instance.get_summary.return_value = {
                'total_cost': Decimal("45.00"),
                'total_tasks': 500,
                'cost_by_tier': {}
            }
            mock_instance.get_daily_costs_7day.return_value = [Decimal("10.00")] * 7
            mock_metrics.return_value = mock_instance
            
            # Now mock load_config at the source to prevent reading actual config
            with patch('src.core.config.load_config') as mock_load_config:
                mock_load_config.return_value = {
                    "budget": {
                        "daily_limit_usd": "100.00",
                        "failure_mode": "fail_open_with_alert"
                    }
                }
                
                # Also need to patch in commands module since it's imported there
                with patch('src.cli.commands.load_config') as mock_load_config2:
                    mock_load_config2.return_value = {
                        "budget": {
                            "daily_limit_usd": "100.00",
                            "failure_mode": "fail_open_with_alert"
                        }
                    }
                    
                    # Should not raise
                    result = cmd_optimization_report()
                    assert result == 0


class TestReportFormatting:
    """Test report formatting."""

    def test_format_cost_summary(self):
        """Test formatting cost summary."""
        from src.reports.daily_report import DailyCostReportGenerator
        
        generator = DailyCostReportGenerator()
        
        output = generator.format_cost_summary(
            Decimal("123.45"),
            1000,
            {
                'L0-Coder': Decimal("50.00"),
                'L1-Coder': Decimal("40.00"),
                'L2-Coder': Decimal("33.45")
            }
        )
        
        assert "Total Cost" in output
        assert "$123.45" in output
        assert "1,000" in output  # Number is formatted with comma
    
    def test_format_tier_breakdown(self):
        """Test formatting tier breakdown."""
        from src.reports.daily_report import DailyCostReportGenerator
        
        generator = DailyCostReportGenerator()
        
        output = generator.format_tier_breakdown({
            'L0-Coder': Decimal("50.00"),
            'L1-Coder': Decimal("40.00"),
            'L2-Coder': Decimal("30.00")
        })
        
        assert "L0-Coder" in output
        assert "L1-Coder" in output
        assert "L2-Coder" in output
        assert "50.00" in output
