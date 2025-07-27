from collections import defaultdict
from typing import List, Dict, Any

class KanbanManager:
    def __init__(self):
        self.signals: List[Dict[str, Any]] = []
        self.max_signal_age = 24.0
        self.signal_history = defaultdict(list)
        self.acknowledged_signals = set()  # Track processed signals

    def add_signal(self, waste_type, priority, timestamp, volume=0, source_id=None, source_type=None):
        signal_id = f"{source_id}_{waste_type}_{timestamp}"
        
        # Avoid duplicate signals
        if signal_id not in self.acknowledged_signals:
            self.signals.append({
                'id': signal_id,
                'waste_type': waste_type,
                'priority': priority,
                'timestamp': timestamp,
                'volume': volume,
                'source_id': source_id,
                "source_type": source_type
            })

    def acknowledge_signal(self, signal_id):
        """Mark signal as processed"""
        self.acknowledged_signals.add(signal_id)

    def clean_old_signals(self, current_time):
        """Remove signals older than max_signal_age"""
        self.signals = [
            signal for signal in self.signals 
            if current_time - signal['timestamp'] <= self.max_signal_age
        ]

    def get_signals(self, current_time=None):
        """Get non-acknowledged, non-expired signals"""
        if current_time:
            self.clean_old_signals(current_time)
        return [s for s in self.signals if s['id'] not in self.acknowledged_signals]

    def clear_signals(self):
        self.signals.clear()
