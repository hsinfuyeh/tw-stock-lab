"""CLI: serve, update, status, export. Uses current saved settings."""
import argparse
import json
from pathlib import Path
import sys
from marketlab.service import ResearchService
from marketlab.server import make_server

def main():
    parser=argparse.ArgumentParser(description="臺股研究台")
    parser.add_argument("command",choices=["serve","update","status","export"])
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--data-dir",default=str(Path(__file__).parent/"data"))
    parser.add_argument("--horizon",type=int,default=7)
    parser.add_argument("--output")
    args=parser.parse_args()
    service=ResearchService(args.data_dir)
    if args.command=="serve":
        server=make_server(service,args.port)
        print(f"臺股研究台 http://127.0.0.1:{args.port}",flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
    elif args.command=="update":
        try:
            snapshot=service.update()
            print(json.dumps(dict(id=snapshot["id"],as_of=snapshot["as_of"],summary=snapshot["summary"]),ensure_ascii=False))
        except Exception as exc:
            print(str(exc),file=sys.stderr)
            return 1
    elif args.command=="status":
        state=service.state()
        print(json.dumps(dict(job=state["job"],history=state["history"],settings=state["settings"]),ensure_ascii=False))
    elif args.command=="export":
        output=Path(args.output or "research.csv")
        output.write_text(service.export_csv(args.horizon),encoding="utf-8")
        print(output.resolve())
    return 0

if __name__=="__main__": raise SystemExit(main())
