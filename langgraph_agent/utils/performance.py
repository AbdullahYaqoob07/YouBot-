"""
Performance Monitoring Utilities
Track execution time and performance metrics
"""
import time
from functools import wraps
from typing import Callable, Any
from loguru import logger


class PerformanceMonitor:
    """Track performance metrics across the pipeline"""
    
    def __init__(self):
        self.metrics = {}
        self.start_time = None
    
    def start_request(self):
        """Start timing a request"""
        self.start_time = time.time()
        self.metrics = {}
    
    def record_node(self, node_name: str, duration_ms: float):
        """Record node execution time"""
        self.metrics[node_name] = duration_ms
    
    def get_total_time(self) -> float:
        """Get total request time in milliseconds"""
        if self.start_time:
            return (time.time() - self.start_time) * 1000
        return 0
    
    def get_summary(self) -> dict:
        """Get performance summary"""
        return {
            "total_time_ms": self.get_total_time(),
            "node_times": self.metrics,
            "slowest_node": max(self.metrics.items(), key=lambda x: x[1])[0] if self.metrics else None
        }


def timed_node(node_name: str):
    """Decorator to time node execution"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start = time.time()
            result = await func(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            
            # Log performance
            if duration_ms > 1000:  # Over 1 second
                logger.warning(f"⚠️  {node_name} took {duration_ms:.0f}ms (slow)")
            elif duration_ms > 500:  # Over 500ms
                logger.info(f"⏱️  {node_name} took {duration_ms:.0f}ms")
            else:
                logger.debug(f"✓ {node_name} took {duration_ms:.0f}ms")
            
            return result
        return wrapper
    return decorator


def log_performance_summary(metrics: dict):
    """Log formatted performance summary"""
    total = metrics.get('total_time_ms', 0)
    nodes = metrics.get('node_times', {})
    
    logger.info(f"""
╔══════════════════════════════════════════╗
║     PERFORMANCE SUMMARY                  ║
╠══════════════════════════════════════════╣
║ Total Time: {total:.0f}ms                     ║
║                                          ║
║ Node Breakdown:                          ║""")
    
    for node, duration in sorted(nodes.items(), key=lambda x: x[1], reverse=True):
        percentage = (duration / total * 100) if total > 0 else 0
        logger.info(f"║   {node:20s}: {duration:6.0f}ms ({percentage:4.1f}%) ║")
    
    logger.info("""╚══════════════════════════════════════════╝""")
