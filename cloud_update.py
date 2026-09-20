"""GitHub Actions entrypoint. No credentials are needed by the market pipeline."""
import argparse
import json
from marketlab.service import MarketService
from marketlab.publish import export_site


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='data')
    parser.add_argument('--output',default='dist')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--export-only',action='store_true')
    args=parser.parse_args()
    service=MarketService(args.data_dir,workers=max(1,min(4,args.workers)))
    if not args.export_only: service.update()
    print(json.dumps(export_site(service,args.output),ensure_ascii=False))


if __name__=='__main__': main()
