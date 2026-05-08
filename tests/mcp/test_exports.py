"""Tests for MR-Krabs analytics CSV/JSON export functionality."""

import pytest
import json
import csv
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from src.mcp.analytics_tools import (
    CSVExporter, 
    JSONExporter, 
    ExportRequest, 
    ExportResponse,
    process_export_csv,
    process_export_json,
    AnalyticsService
)


class TestCSVExporter:
    """Test CSVExporter class functionality."""
    
    def test_export_creates_csv_format(self):
        """Test that CSV export creates proper CSV format."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = CSVExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        assert result is not None
        assert isinstance(result, str)
        # Check for CSV structure (comma-separated values)
        assert "," in result
        
    def test_export_contains_summary_section(self):
        """Test that CSV export contains summary section."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = CSVExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        assert "SUMMARY" in result
        assert "period" in result.lower() or "total_spent" in result.lower()
        
    def test_export_contains_tier_section(self):
        """Test that CSV export contains tier breakdown section."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = CSVExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        assert "TIER" in result
        # Check for tier levels
        assert "L0" in result or "L1" in result
        
    def test_export_to_file_creates_file(self):
        """Test that export_to_file creates a file on disk."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        with TemporaryDirectory() as tmpdir:
            exporter = CSVExporter(output_dir=tmpdir)
            file_path = exporter.export_to_file(
                summary_data, 
                tier_data, 
                trend_data, 
                efficiency_data,
                'test.csv'
            )
            
            assert file_path is not None
            assert os.path.exists(file_path)
            assert file_path.endswith('.csv')
            
    def test_export_to_file_with_output_dir(self):
        """Test that export_to_file respects output_dir parameter."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        with TemporaryDirectory() as tmpdir:
            exporter = CSVExporter(output_dir=tmpdir)
            file_path = exporter.export_to_file(
                summary_data, 
                tier_data, 
                trend_data, 
                efficiency_data,
                'report.csv'
            )
            
            # Verify file is in the specified directory
            assert tmpdir in file_path
            
    def test_export_parsable_by_csv_reader(self):
        """Test that exported CSV can be read by csv module."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = CSVExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        # Try to parse at least some lines (skip header comments)
        lines = result.split('\n')
        data_lines = [l for l in lines if ',' in l and not l.startswith('===')]
        
        assert len(data_lines) > 0
        
        # Parse first valid CSV line
        import io
        reader = csv.reader(io.StringIO(data_lines[0]))
        rows = list(reader)
        
        assert len(rows) >= 1
        assert len(rows[0]) >= 2  # At least two columns


class TestJSONExporter:
    """Test JSONExporter class functionality."""
    
    def test_export_creates_json_format(self):
        """Test that JSON export creates valid JSON."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = JSONExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        assert result is not None
        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        
    def test_export_contains_all_sections(self):
        """Test that JSON export contains all required sections."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = JSONExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        parsed = json.loads(result)
        
        assert "export_info" in parsed
        assert "summary" in parsed
        assert "tier_breakdown" in parsed
        assert "daily_trends" in parsed  # Correct key name
        assert "efficiency_report" in parsed  # Correct key name
        
    def test_export_to_file_creates_file(self):
        """Test that export_to_file creates a JSON file on disk."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        with TemporaryDirectory() as tmpdir:
            exporter = JSONExporter(output_dir=tmpdir)
            file_path = exporter.export_to_file(
                summary_data, 
                tier_data, 
                trend_data, 
                efficiency_data,
                'test.json'
            )
            
            assert file_path is not None
            assert os.path.exists(file_path)
            assert file_path.endswith('.json')
            
    def test_export_to_file_valid_json(self):
        """Test that exported JSON file contains valid JSON."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        with TemporaryDirectory() as tmpdir:
            exporter = JSONExporter(output_dir=tmpdir)
            file_path = exporter.export_to_file(
                summary_data, 
                tier_data, 
                trend_data, 
                efficiency_data,
                'report.json'
            )
            
            # Read and parse the file
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            assert isinstance(data, dict)
            assert "summary" in data
            
    def test_export_includes_export_info(self):
        """Test that export includes metadata about the export."""
        service = AnalyticsService()
        summary_data = service.generate_summary(period_days=7)
        tier_data = service.generate_tier_breakdown(period_days=7)
        trend_data = service.generate_cost_trends(period_days=7)
        efficiency_data = service.generate_efficiency_report(period_days=7)
        
        exporter = JSONExporter()
        result = exporter.export(
            summary_data, 
            tier_data, 
            trend_data, 
            efficiency_data
        )
        
        parsed = json.loads(result)
        export_info = parsed["export_info"]
        
        assert "format" in export_info
        assert export_info["format"] == "JSON"
        assert "exported_at" in export_info
        assert "period" in export_info


class TestExportRequest:
    """Test ExportRequest model."""
    
    def test_request_defaults(self):
        """Test that ExportRequest has correct defaults."""
        request = ExportRequest()
        
        assert request.period_days == 7
        assert request.session_id is None
        
    def test_request_custom_period(self):
        """Test that period_days can be customized."""
        request = ExportRequest(period_days=30)
        
        assert request.period_days == 30
        
    def test_request_validation_min_period(self):
        """Test that period_days has minimum value validation."""
        with pytest.raises(Exception):  # pydantic ValidationError
            ExportRequest(period_days=0)
            
    def test_request_with_output_options(self):
        """Test request with output directory and file parameters."""
        request = ExportRequest(
            period_days=14,
            output_dir="/tmp/reports",
            output_file="my_report.csv"
        )
        
        assert request.period_days == 14
        assert request.output_dir == "/tmp/reports"
        assert request.output_file == "my_report.csv"


class TestExportResponse:
    """Test ExportResponse model."""
    
    def test_response_minimal(self):
        """Test minimal ExportResponse."""
        response = ExportResponse(
            success=True,
            format="csv",
            filename="test.csv"
        )
        
        assert response.success is True
        assert response.format == "csv"
        assert response.filename == "test.csv"
        assert response.file_path is None
        
    def test_response_with_file_path(self):
        """Test ExportResponse with file path."""
        response = ExportResponse(
            success=True,
            format="json",
            filename="report.json",
            file_path="/tmp/reports/report.json"
        )
        
        assert response.file_path == "/tmp/reports/report.json"


class TestProcessExportCSV:
    """Test process_export_csv function."""
    
    def test_process_export_csv_success(self):
        """Test successful CSV export processing."""
        with TemporaryDirectory() as tmpdir:
            request = ExportRequest(
                period_days=7,
                output_dir=tmpdir,
                output_file="test.csv"
            )
            
            response = process_export_csv(request)
            
            assert response.success is True
            assert response.format == "csv"
            assert response.file_path is not None
            assert os.path.exists(response.file_path)
            
    def test_process_export_csv_without_output_dir(self):
        """Test CSV export without output directory (in-memory)."""
        request = ExportRequest(period_days=7)
        
        response = process_export_csv(request)
        
        assert response.success is True
        assert response.format == "csv"
        assert response.data_preview is not None
        
    def test_process_export_csv_different_periods(self):
        """Test CSV export with different period lengths."""
        for days in [1, 7, 14, 30]:
            with TemporaryDirectory() as tmpdir:
                request = ExportRequest(
                    period_days=days,
                    output_dir=tmpdir,
                    output_file=f"test_{days}d.csv"
                )
                
                response = process_export_csv(request)
                
                assert response.success is True


class TestProcessExportJSON:
    """Test process_export_json function."""
    
    def test_process_export_json_success(self):
        """Test successful JSON export processing."""
        with TemporaryDirectory() as tmpdir:
            request = ExportRequest(
                period_days=7,
                output_dir=tmpdir,
                output_file="test.json"
            )
            
            response = process_export_json(request)
            
            assert response.success is True
            assert response.format == "json"
            assert response.file_path is not None
            assert os.path.exists(response.file_path)
            
    def test_process_export_json_valid_content(self):
        """Test that JSON export produces valid JSON file."""
        with TemporaryDirectory() as tmpdir:
            request = ExportRequest(
                period_days=7,
                output_dir=tmpdir,
                output_file="test.json"
            )
            
            response = process_export_json(request)
            
            # Verify file content is valid JSON
            with open(response.file_path, 'r') as f:
                data = json.load(f)
                
            assert "summary" in data
            assert "tier_breakdown" in data
            
    def test_process_export_json_without_output_dir(self):
        """Test JSON export without output directory (in-memory)."""
        request = ExportRequest(period_days=7)
        
        response = process_export_json(request)
        
        assert response.success is True
        assert response.format == "json"
        assert response.data_preview is not None
        
        # Preview might be truncated, so check full_data instead
        assert response.full_data is not None
        data = json.loads(response.full_data)
        assert isinstance(data, dict)


class TestExportIntegration:
    """Integration tests for complete export workflow."""
    
    def test_csv_export_workflow(self):
        """Test complete CSV export workflow from request to file."""
        with TemporaryDirectory() as tmpdir:
            # Create request
            request = ExportRequest(
                period_days=7,
                output_dir=tmpdir,
                output_file="workflow_test.csv"
            )
            
            # Process export
            response = process_export_csv(request)
            
            # Verify response
            assert response.success is True
            assert response.filename == "workflow_test.csv"
            
            # Verify file exists and is readable
            assert os.path.exists(response.file_path)
            
            # Parse CSV content
            with open(response.file_path, 'r') as f:
                content = f.read()
                
            assert "SUMMARY" in content
            assert "TIER" in content
            
    def test_json_export_workflow(self):
        """Test complete JSON export workflow from request to file."""
        with TemporaryDirectory() as tmpdir:
            # Create request
            request = ExportRequest(
                period_days=7,
                output_dir=tmpdir,
                output_file="workflow_test.json"
            )
            
            # Process export
            response = process_export_json(request)
            
            # Verify response
            assert response.success is True
            assert response.filename == "workflow_test.json"
            
            # Verify file exists and contains valid JSON
            assert os.path.exists(response.file_path)
            
            with open(response.file_path, 'r') as f:
                data = json.load(f)
                
            assert all(key in data for key in [
                "export_info", "summary", "tier_breakdown", "daily_trends", "efficiency_report"
            ])
            
    def test_multiple_exports_same_directory(self):
        """Test multiple exports to same directory."""
        with TemporaryDirectory() as tmpdir:
            filenames = []
            
            # Export 3 CSV files
            for i in range(3):
                request = ExportRequest(
                    period_days=7,
                    output_dir=tmpdir,
                    output_file=f"export_{i}.csv"
                )
                
                response = process_export_csv(request)
                filenames.append(response.filename)
                
            # Verify all files exist
            assert len(filenames) == 3
            for filename in filenames:
                filepath = os.path.join(tmpdir, filename)
                assert os.path.exists(filepath)
