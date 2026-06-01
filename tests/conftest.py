# Prime the import graph in the order main.py uses so importing the monitoring
# package under pytest does not trip the known monitoring/__init__ circular
# import (see CLAUDE.md). Importing config.base_config first pulls
# models.data_classes -> monitoring.waste_monitor in cleanly, before the
# monitoring package __init__ runs.
import config.base_config  # noqa: F401
