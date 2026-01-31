"""
Agent Health Dashboard (Optional)
Shows real-time status of all agents via heartbeats.
Run this in a separate terminal to monitor your agents.

Usage: python agent_health_dashboard.py
"""

import json
import time
from datetime import datetime, timedelta
from redis_connection import RedisConnection
from typing import Dict
import os


class AgentHealthDashboard:
    """Lightweight dashboard that displays agent status."""
    
    def __init__(self):
        self.redis_conn = RedisConnection.get_instance()
        self.agent_status: Dict[str, dict] = {}
        
    def display_status(self):
        """Display current agent status in a formatted table"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("=" * 80)
        print(f"{'KHADIM AGENT HEALTH DASHBOARD':^80}")
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^80}")
        print("=" * 80)
        print(f"{'AGENT':<15} | {'STATUS':<10} | {'LAST SEEN':<20} | {'TIME SINCE':<15}")
        print("-" * 80)
        
        if not self.agent_status:
            print(f"{'Waiting for agents to start...':<80}")
        else:
            for agent_name, status in sorted(self.agent_status.items()):
                last_seen = status['last_seen']
                time_since = datetime.now() - last_seen
                
                # Determine status emoji
                agent_status_str = status['status']
                
                if agent_status_str == 'alive' and time_since < timedelta(seconds=15):
                    emoji = "✅"
                    status_text = "ALIVE"
                elif agent_status_str == 'crashed':
                    emoji = "💥"
                    status_text = "CRASHED"
                elif agent_status_str == 'stopped':
                    emoji = "🛑"
                    status_text = "STOPPED"
                elif agent_status_str == 'started':
                    emoji = "🚀"
                    status_text = "STARTED"
                else:
                    emoji = "⚠️"
                    status_text = "UNKNOWN"
                
                # Check if heartbeat is stale
                if time_since > timedelta(seconds=15) and agent_status_str == 'alive':
                    emoji = "⚠️"
                    status_text = "TIMEOUT"
                
                last_seen_str = last_seen.strftime('%H:%M:%S')
                time_since_str = f"{time_since.seconds}s ago"
                
                print(f"{emoji} {agent_name:<13} | {status_text:<10} | {last_seen_str:<20} | {time_since_str:<15}")
                
                # Show error if crashed
                if status.get('error'):
                    print(f"   └─ Error: {status['error'][:60]}")
        
        print("=" * 80)
        print("\nPress Ctrl+C to exit")
        print("-" * 80)
    
    def listen_and_display(self):
        """Listen to heartbeats and continuously update display"""
        print("👂 Starting health dashboard...")
        print("Listening for agent heartbeats on Redis...\n")
        time.sleep(1)
        
        try:
            pubsub = self.redis_conn.pubsub()
            pubsub.subscribe("agent_heartbeats")
            
            last_display = time.time()
            
            for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        agent_name = data.get('agent')
                        
                        if agent_name:
                            self.agent_status[agent_name] = {
                                'status': data.get('status'),
                                'last_seen': datetime.now(),
                                'timestamp': data.get('timestamp'),
                                'error': data.get('error')
                            }
                    except json.JSONDecodeError:
                        pass
                
                # Update display every 2 seconds
                if time.time() - last_display > 2:
                    self.display_status()
                    last_display = time.time()
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Dashboard stopped")
        except Exception as e:
            print(f"\n❌ Dashboard error: {e}")


if __name__ == "__main__":
    dashboard = AgentHealthDashboard()
    dashboard.listen_and_display()
