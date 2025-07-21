from typing import List, Dict, Any

class KanbanManager:
    def __init__(self):
        self.signals: List[Dict[str, Any]] = []

    def add_signal(self, waste_type, priority, timestamp):
        self.signals.append({
            'waste_type': waste_type,
            'priority': priority,
            'timestamp': timestamp
        })

    def get_signals(self):
        # Sort signals by priority (descending) and timestamp (ascending)
        return sorted(self.signals, key=lambda x: (-x['priority'], x['timestamp']))

    def clear_signals(self):
        self.signals.clear()
