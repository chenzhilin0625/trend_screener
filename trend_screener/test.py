from data.manager import DataManager
from analyzer import analyze_single
import json

dm = DataManager()
result = analyze_single(dm, '600015', 'stock')
print(json.dumps(result, ensure_ascii=False, indent=2))
dm.close()