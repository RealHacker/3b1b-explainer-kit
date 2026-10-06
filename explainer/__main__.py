"""Allow `python -m explainer` from the kit root (or with PYTHONPATH=<KIT>)."""
from .cli import main
import sys

sys.exit(main())
