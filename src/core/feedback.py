#!/usr/bin/env python3
"""Tool result feedback to LLM for multi-step workflows."""

import json
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class ToolFeedback:
    """Feedback from tool execution to LLM."""
    tool_name: str
    path: str
    success: bool
    result: Any
    error: str = None
    bytes_count: int = 0
    
    def to_llm_message(self) -> str:
        """Format feedback as LLM-readable message."""
        if self.success:
            if self.tool_name == "file_write":
                return f"✓ file_write('{self.path}'): SUCCESS ({self.bytes_count} bytes written)"
            elif self.tool_name == "file_read":
                content_preview = self.result[:200] + "..." if len(self.result) > 200 else self.result
                return f"✓ file_read('{self.path}'): SUCCESS ({len(self.result)} bytes)\nContent: {content_preview}"
        else:
            return f"✗ {self.tool_name}('{self.path}'): FAILED - {self.error}"


class FeedbackManager:
    """Manages tool execution feedback to LLM."""
    
    def __init__(self, max_feedback_length: int = 4000):
        self.max_feedback_length = max_feedback_length
        self.feedback_history: List[ToolFeedback] = []
    
    def add_feedback(self, feedback: ToolFeedback):
        """Add feedback to history."""
        self.feedback_history.append(feedback)
    
    def add_from_tool_result(self, tool_result: Dict[str, Any]):
        """Add feedback from ToolExecutor result."""
        for tr in tool_result.get("tool_results", []):
            feedback = ToolFeedback(
                tool_name=tr["tool"],
                path=tr.get("path", "unknown"),
                success=tr.get("success", False),
                result=tr.get("content"),
                error=tr.get("error"),
                bytes_count=tr.get("bytes", 0)
            )
            self.add_feedback(feedback)
    
    def get_feedback_context(self) -> str:
        """Get formatted feedback for LLM context."""
        if not self.feedback_history:
            return "No tool executions yet."
        
        lines = ["## Tool Execution Results:"]
        for fb in self.feedback_history:
            lines.append(fb.to_llm_message())
        
        context = "\n".join(lines)
        
        # Truncate if too long
        if len(context) > self.max_feedback_length:
            context = context[:self.max_feedback_length] + "\n... [truncated]"
        
        return context
    
    def get_last_feedback(self) -> ToolFeedback:
        """Get most recent feedback."""
        return self.feedback_history[-1] if self.feedback_history else None
    
    def all_succeeded(self) -> bool:
        """Check if all tools succeeded."""
        return all(fb.success for fb in self.feedback_history)
    
    def get_failures(self) -> List[ToolFeedback]:
        """Get list of failed tool executions."""
        return [fb for fb in self.feedback_history if not fb.success]
    
    def clear(self):
        """Clear feedback history."""
        self.feedback_history.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "total_executions": len(self.feedback_history),
            "successes": sum(1 for fb in self.feedback_history if fb.success),
            "failures": sum(1 for fb in self.feedback_history if not fb.success),
            "history": [
                {
                    "tool": fb.tool_name,
                    "path": fb.path,
                    "success": fb.success,
                    "bytes": fb.bytes_count
                }
                for fb in self.feedback_history
            ]
        }


def format_tool_response(tool_result: Dict[str, Any]) -> str:
    """Format tool executor result as LLM response."""
    manager = FeedbackManager()
    manager.add_from_tool_result(tool_result)
    return manager.get_feedback_context()
