import json
import sys
from pathlib import Path
from .pipeline import analyze_mesh

def main():
    path,fmt,unit,asset_id,expected_hash=sys.argv[1:]
    result=analyze_mesh(Path(path).read_bytes(),fmt,unit,asset_id,expected_hash)
    print(json.dumps(result.model_dump(),allow_nan=False))

if __name__=='__main__': main()
