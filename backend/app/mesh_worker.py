import json
import sys
from pathlib import Path
from .mesh_geometry import inspect_mesh

def main():
    try:
        path,fmt,unit=sys.argv[1:]
        result=inspect_mesh(Path(path).read_bytes(),fmt,unit)
        print(json.dumps({'ok':True,'metadata':result},allow_nan=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)}))
        sys.exit(1)

if __name__=='__main__': main()
