import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.currency import typescript_table

target = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "currencies.ts"
target.write_text(typescript_table())
print("wrote", target)
