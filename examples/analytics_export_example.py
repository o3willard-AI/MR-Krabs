#!/usr/bin/env python3
"""
Example script demonstrating MR-Krabs analytics export functionality.

This script shows how to use the CSV and JSON exporters to generate
comprehensive cost and usage reports from your AI orchestration data.
"""

import tempfile
import os
import json
from src.mcp.analytics_tools import (
    AnalyticsService,
    CSVExporter,
    JSONExporter,
    ExportRequest,
    process_export_csv,
    process_export_json
)


def example_in_memory_exports():
    """Example 1: Generate exports in-memory (no files created)."""
    print("=" * 60)
    print("Example 1: In-Memory Exports")
    print("=" * 60)
    
    # Create service instance
    service = AnalyticsService()
    
    # Generate data
    summary_data = service.generate_summary(period_days=7)
    tier_data = service.generate_tier_breakdown(period_days=7)
    trend_data = service.generate_cost_trends(period_days=7)
    efficiency_data = service.generate_efficiency_report(period_days=7)
    
    # CSV export in-memory
    csv_exporter = CSVExporter()
    csv_content = csv_exporter.export(
        summary_data, tier_data, trend_data, efficiency_data
    )
    
    print("\n📊 CSV Export (first 500 chars):")
    print("-" * 40)
    print(csv_content[:500])
    print("...")
    
    # JSON export in-memory
    json_exporter = JSONExporter()
    json_content = json_exporter.export(
        summary_data, tier_data, trend_data, efficiency_data
    )
    
    parsed_json = json.loads(json_content)
    print("\n📊 JSON Export (summary section):")
    print("-" * 40)
    print(json.dumps(parsed_json["summary"], indent=2))
    
    return csv_content, json_content


def example_file_exports():
    """Example 2: Generate exports to files."""
    print("\n" + "=" * 60)
    print("Example 2: File Exports")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\n📁 Using temporary directory: {tmpdir}")
        
        # Create service instance
        service = AnalyticsService()
        
        # Generate data
        summary_data = service.generate_summary(period_days=14)
        tier_data = service.generate_tier_breakdown(period_days=14)
        trend_data = service.generate_cost_trends(period_days=14)
        efficiency_data = service.generate_efficiency_report(period_days=14)
        
        # CSV export to file
        csv_exporter = CSVExporter(output_dir=tmpdir)
        csv_path = csv_exporter.export_to_file(
            summary_data, tier_data, trend_data, efficiency_data,
            filename='14day_report.csv'
        )
        
        print(f"\n✅ CSV written to: {csv_path}")
        print(f"   File size: {os.path.getsize(csv_path)} bytes")
        
        # JSON export to file
        json_exporter = JSONExporter(output_dir=tmpdir)
        json_path = json_exporter.export_to_file(
            summary_data, tier_data, trend_data, efficiency_data,
            filename='14day_report.json'
        )
        
        print(f"\n✅ JSON written to: {json_path}")
        print(f"   File size: {os.path.getsize(json_path)} bytes")
        
        # Read and display file contents
        with open(csv_path, 'r') as f:
            csv_content = f.read()
        
        with open(json_path, 'r') as f:
            json_data = json.load(f)
        
        print(f"\n📋 CSV file contains {len(csv_content.split(chr(10)))} lines")
        print(f"📋 JSON file contains {len(json.dumps(json_data))} bytes")


def example_process_functions():
    """Example 3: Using process_export functions (HTTP endpoint simulation)."""
    print("\n" + "=" * 60)
    print("Example 3: Process Export Functions")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # CSV export using process function
        print("\n🔄 Processing CSV export request...")
        csv_request = ExportRequest(
            period_days=7,
            output_dir=tmpdir,
            output_file="process_csv_report.csv"
        )
        
        csv_response = process_export_csv(csv_request)
        
        if csv_response.success:
            print(f"✅ CSV export successful!")
            print(f"   File: {csv_response.filename}")
            print(f"   Path: {csv_response.file_path}")
            print(f"   Message: {csv_response.message}")
        else:
            print(f"❌ CSV export failed: {csv_response.error}")
        
        # JSON export using process function
        print("\n🔄 Processing JSON export request...")
        json_request = ExportRequest(
            period_days=30,
            output_dir=tmpdir,
            output_file="process_json_report.json"
        )
        
        json_response = process_export_json(json_request)
        
        if json_response.success:
            print(f"✅ JSON export successful!")
            print(f"   File: {json_response.filename}")
            print(f"   Path: {json_response.file_path}")
            print(f"   Message: {json_response.message}")
            
            # Parse and display summary
            data = json.loads(json_response.full_data)
            print(f"\n📊 Report Summary:")
            print(f"   Period: {data['export_info']['period']}")
            print(f"   Total Spent: ${data['summary']['total_spent']:.2f}")
            print(f"   Task Count: {data['summary']['task_count']}")
            print(f"   Avg Cost/Task: ${data['summary']['avg_cost_per_task']:.4f}")
        else:
            print(f"❌ JSON export failed: {json_response.error}")


def example_different_periods():
    """Example 4: Exporting different time periods."""
    print("\n" + "=" * 60)
    print("Example 4: Different Time Periods")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        service = AnalyticsService()
        
        periods = [1, 7, 14, 30]
        
        for days in periods:
            # Generate data for period
            summary_data = service.generate_summary(period_days=days)
            
            print(f"\n📅 {days}-day period:")
            print(f"   Total Spent: ${summary_data['total_spent']:.2f}")
            print(f"   Task Count: {summary_data['task_count']}")
            print(f"   Trend Direction: {summary_data['trend_direction']}")
            
            # Export to file
            json_exporter = JSONExporter(output_dir=tmpdir)
            filepath = json_exporter.export_to_file(
                summary_data, 
                service.generate_tier_breakdown(period_days=days),
                service.generate_cost_trends(period_days=days),
                service.generate_efficiency_report(period_days=days),
                filename=f'period_{days}d.json'
            )
            
            print(f"   Exported to: {os.path.basename(filepath)}")


def example_custom_filename():
    """Example 5: Using custom filenames and session IDs."""
    print("\n" + "=" * 60)
    print("Example 5: Custom Filenames and Session IDs")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Export with custom filename
        request = ExportRequest(
            period_days=7,
            session_id="demo-session-123",
            output_dir=tmpdir,
            output_file="custom_analytics_report.csv"
        )
        
        response = process_export_csv(request)
        
        print(f"\n📝 Custom filename export:")
        print(f"   Requested: custom_analytics_report.csv")
        print(f"   Created: {response.filename}")
        print(f"   Path: {response.file_path}")
        
        # Verify file exists
        if os.path.exists(response.file_path):
            print(f"   ✅ File exists and is ready to use")


def main():
    """Run all examples."""
    print("\n🚀 MR-Krabs Analytics Export Examples\n")
    
    try:
        example_in_memory_exports()
        example_file_exports()
        example_process_functions()
        example_different_periods()
        example_custom_filename()
        
        print("\n" + "=" * 60)
        print("✅ All examples completed successfully!")
        print("=" * 60)
        print("\n💡 Next Steps:")
        print("   1. Review the generated files in your temporary directories")
        print("   2. Modify the examples to fit your use case")
        print("   3. Integrate with your application using process_export_* functions")
        print("   4. Use the MCP endpoints for HTTP-based access")
        print()
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
