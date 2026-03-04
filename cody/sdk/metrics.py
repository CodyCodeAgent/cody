"""Cody SDK - Metrics collection.

Provides metrics for monitoring SDK performance and usage.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class TokenUsage:
    """Token usage statistics."""
    
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def add(self, other: "TokenUsage") -> "TokenUsage":
        """Add another TokenUsage to this one."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class ToolMetrics:
    """Tool execution metrics."""
    
    tool_name: str
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration: float = 0.0
    
    @property
    def avg_duration(self) -> float:
        """Average duration per call."""
        if self.call_count == 0:
            return 0.0
        return self.total_duration / self.call_count
    
    @property
    def success_rate(self) -> float:
        """Success rate (0.0 - 1.0)."""
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count


@dataclass
class RunMetrics:
    """Single run metrics."""
    
    prompt_length: int = 0
    output_length: int = 0
    duration: float = 0.0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: int = 0
    thinking_enabled: bool = False
    session_id: Optional[str] = None


@dataclass
class SessionMetrics:
    """Session-level metrics."""
    
    session_id: str
    run_count: int = 0
    total_tokens: TokenUsage = field(default_factory=TokenUsage)
    total_duration: float = 0.0
    total_tool_calls: int = 0
    created_at: float = field(default_factory=time.time)


class MetricsCollector:
    """Collects and aggregates SDK metrics.
    
    Usage:
        collector = MetricsCollector()
        
        async with AsyncCodyClient(metrics=collector) as client:
            result = await client.run("task")
        
        # Get metrics
        metrics = collector.get_summary()
        print(f"Total tokens: {metrics.total_tokens.total_tokens}")
        print(f"Tool calls: {metrics.total_tool_calls}")
        print(f"Duration: {metrics.total_duration:.2f}s")
    """
    
    def __init__(self):
        self._runs: list[RunMetrics] = []
        self._tools: dict[str, ToolMetrics] = defaultdict(
            lambda: ToolMetrics(tool_name="unknown")
        )
        self._sessions: dict[str, SessionMetrics] = {}
        self._current_run: Optional[RunMetrics] = None
        self._start_time: float = 0.0
        self._enabled: bool = True
    
    def enable(self) -> None:
        """Enable metrics collection."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable metrics collection."""
        self._enabled = False
    
    def start_run(self, prompt: str, session_id: Optional[str] = None, thinking: bool = False) -> None:
        """Start tracking a run."""
        if not self._enabled:
            return
        
        self._current_run = RunMetrics(
            prompt_length=len(prompt),
            thinking_enabled=thinking,
            session_id=session_id,
        )
        self._start_time = time.time()
    
    def end_run(self, output: str, token_usage: TokenUsage) -> None:
        """End tracking a run."""
        if not self._enabled or not self._current_run:
            return
        
        self._current_run.output_length = len(output)
        self._current_run.duration = time.time() - self._start_time
        self._current_run.token_usage = token_usage
        
        self._runs.append(self._current_run)
        
        # Update session metrics
        if self._current_run.session_id:
            session_id = self._current_run.session_id
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionMetrics(session_id=session_id)
            
            session = self._sessions[session_id]
            session.run_count += 1
            session.total_tokens = session.total_tokens.add(token_usage)
            session.total_duration += self._current_run.duration
            session.total_tool_calls += self._current_run.tool_calls
        
        self._current_run = None
    
    def record_tool_call(
        self,
        tool_name: str,
        duration: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Record a tool call."""
        if not self._enabled:
            return
        
        if tool_name not in self._tools:
            self._tools[tool_name] = ToolMetrics(tool_name=tool_name)
        
        metrics = self._tools[tool_name]
        metrics.call_count += 1
        metrics.total_duration += duration
        
        if success:
            metrics.success_count += 1
        else:
            metrics.error_count += 1
        
        # Update current run
        if self._current_run:
            self._current_run.tool_calls += 1
    
    def record_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage for current run."""
        if not self._enabled or not self._current_run:
            return
        
        self._current_run.token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
    
    def get_summary(self) -> dict:
        """Get aggregated metrics summary."""
        total_tokens = TokenUsage()
        total_duration = 0.0
        total_tool_calls = 0
        
        for run in self._runs:
            total_tokens = total_tokens.add(run.token_usage)
            total_duration += run.duration
            total_tool_calls += run.tool_calls
        
        return {
            "total_runs": len(self._runs),
            "total_tokens": total_tokens.total_tokens,
            "input_tokens": total_tokens.input_tokens,
            "output_tokens": total_tokens.output_tokens,
            "total_duration": total_duration,
            "total_tool_calls": total_tool_calls,
            "avg_run_duration": total_duration / len(self._runs) if self._runs else 0.0,
            "avg_tokens_per_run": total_tokens.total_tokens / len(self._runs) if self._runs else 0,
            "tool_metrics": {
                name: {
                    "call_count": m.call_count,
                    "success_rate": m.success_rate,
                    "avg_duration": m.avg_duration,
                }
                for name, m in self._tools.items()
            },
            "session_count": len(self._sessions),
        }
    
    def get_run_history(self) -> list[RunMetrics]:
        """Get history of all runs."""
        return list(self._runs)
    
    def get_tool_metrics(self, tool_name: Optional[str] = None) -> dict[str, ToolMetrics]:
        """Get tool metrics, optionally filtered by tool name."""
        if tool_name:
            return {tool_name: self._tools.get(tool_name, ToolMetrics(tool_name=tool_name))}
        return dict(self._tools)
    
    def get_session_metrics(self, session_id: str) -> Optional[SessionMetrics]:
        """Get metrics for a specific session."""
        return self._sessions.get(session_id)
    
    def reset(self) -> None:
        """Reset all metrics."""
        self._runs.clear()
        self._tools.clear()
        self._sessions.clear()
        self._current_run = None
    
    def export_json(self) -> dict:
        """Export metrics as JSON-serializable dict."""
        summary = self.get_summary()
        summary["runs"] = [
            {
                "prompt_length": r.prompt_length,
                "output_length": r.output_length,
                "duration": r.duration,
                "token_usage": {
                    "input": r.token_usage.input_tokens,
                    "output": r.token_usage.output_tokens,
                    "total": r.token_usage.total_tokens,
                },
                "tool_calls": r.tool_calls,
                "session_id": r.session_id,
            }
            for r in self._runs
        ]
        return summary
