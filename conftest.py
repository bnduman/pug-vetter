import pathlib
import sys

# Make the project root importable (so `import app...` works under pytest).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
