"""
Agent Lifecycle Manager
Wraps agent functions with crash detection, graceful shutdown, and heartbeat publishing.
"""

import signal
import sys
import time
import threading
import json
from datetime import datetime
from typing import Callable
from redis_connection import RedisConnection


class AgentLifecycleManager:
    """
    Wraps an agent's run function with lifecycle management:
    - Crash detection and reporting
    - Graceful shutdown handling (Ctrl+C)
    - Resource cleanup (Redis connections)
    - Heartbeat publishing for monitoring
    """
    
    def __init__(self, agent_name: str, run_function: Callable):
        self.agent_name = agent_name
        self.run_function = run_function
        self.is_running = True
        self.shutdown_event = threading.Event()
        self.redis_conn = None
        self.heartbeat_thread = None
        
        # Register shutdown handlers for Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C and termination signals gracefully"""
        print(f"\n🛑 [{self.agent_name}] Received shutdown signal. Cleaning up...")
        self.shutdown()
        sys.exit(0)
    
    def _publish_heartbeat(self):
        """Continuously publish heartbeat to Redis (runs in background thread)"""
        while not self.shutdown_event.is_set():
            try:
                if self.redis_conn:
                    heartbeat_data = {
                        "agent": self.agent_name,
                        "status": "alive",
                        "timestamp": datetime.now().isoformat()
                    }
                    self.redis_conn.publish("agent_heartbeats", json.dumps(heartbeat_data))
            except Exception as e:
                # Silently continue if heartbeat fails (non-critical)
                pass
            
            # Wait 5 seconds or until shutdown
            self.shutdown_event.wait(5)
    
    def _cleanup_resources(self):
        """Clean up Redis connections and publish shutdown status"""
        try:
            if self.redis_conn:
                # Publish shutdown status
                shutdown_data = {
                    "agent": self.agent_name,
                    "status": "stopped",
                    "timestamp": datetime.now().isoformat()
                }
                self.redis_conn.publish("agent_heartbeats", json.dumps(shutdown_data))
                print(f"✅ [{self.agent_name}] Redis cleanup complete")
        except Exception as e:
            print(f"⚠️ [{self.agent_name}] Redis cleanup warning: {e}")
    
    def shutdown(self):
        """Initiate graceful shutdown"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.shutdown_event.set()
        
        # Wait for heartbeat thread to stop
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2)
        
        # Cleanup resources
        self._cleanup_resources()
        
        print(f"✅ [{self.agent_name}] Shutdown complete")
    
    def run_with_lifecycle_management(self):
        """
        Run the agent with full lifecycle management.
        This wraps the original run function without modifying it.
        """
        try:
            # Initialize Redis connection
            self.redis_conn = RedisConnection.get_instance()
            
            if not self.redis_conn:
                print(f"❌ [{self.agent_name}] Failed to connect to Redis")
                return
            
            # Start heartbeat thread (runs in background)
            self.heartbeat_thread = threading.Thread(
                target=self._publish_heartbeat,
                daemon=True
            )
            self.heartbeat_thread.start()
            
            # Publish startup status
            startup_data = {
                "agent": self.agent_name,
                "status": "started",
                "timestamp": datetime.now().isoformat()
            }
            self.redis_conn.publish("agent_heartbeats", json.dumps(startup_data))
            
            print(f"✅ [{self.agent_name}] Started successfully with lifecycle management")
            
            # Run the actual agent function (your existing code runs here)
            self.run_function()
            
        except KeyboardInterrupt:
            # User pressed Ctrl+C
            print(f"\n⚠️ [{self.agent_name}] Interrupted by user")
            self.shutdown()
            
        except Exception as e:
            # Agent crashed!
            print(f"💥 [{self.agent_name}] CRASHED: {e}")
            
            # Publish crash status to Redis
            try:
                if self.redis_conn:
                    crash_data = {
                        "agent": self.agent_name,
                        "status": "crashed",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    self.redis_conn.publish("agent_heartbeats", json.dumps(crash_data))
            except:
                pass
            
            self.shutdown()
            raise  # Re-raise to show the error
        
        finally:
            # Ensure cleanup happens no matter what
            if self.is_running:
                self.shutdown()


def wrap_agent(agent_name: str, run_function: Callable):
    """
    Convenience function to wrap an agent's run function.
    
    Usage in your agent files:
        if __name__ == "__main__":
            from agent_lifecycle_manager import wrap_agent
            wrap_agent("cart", run_cart_agent)
    """
    manager = AgentLifecycleManager(agent_name, run_function)
    manager.run_with_lifecycle_management()
