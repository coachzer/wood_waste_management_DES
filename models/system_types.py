"""Type definitions for system components to avoid circular imports"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.treatment import TreatmentOperator
    from core.collector import CollectorCompany
    from core.generator import WasteGenerator

# Export type aliases
TreatmentOperator = 'TreatmentOperator'
CollectorCompany = 'CollectorCompany'
WasteGenerator = 'WasteGenerator'
