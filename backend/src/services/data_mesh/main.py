from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

SERVICE_MAIN = (
    Path(__file__).resolve().parent
    / "src"
    / "main.py"
)

spec = spec_from_file_location("data_mesh_service_main", SERVICE_MAIN)
if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load Data Mesh service backend from {SERVICE_MAIN}")

service_src = str(SERVICE_MAIN.parent)
if service_src not in sys.path:
    sys.path.insert(0, service_src)

module = module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app
