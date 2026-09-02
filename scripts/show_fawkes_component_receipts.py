#!/usr/bin/env python3
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.component_supervision import ComponentReceiptStore

for receipt in ComponentReceiptStore().latest():
    print(json.dumps(receipt, sort_keys=True))
