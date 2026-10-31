import argparse
import threading
import webbrowser
from pathlib import Path
from inspection_app.store import Store
from inspection_app.server import create_server
from inspection_app.lock import data_lock

def main():
    parser = argparse.ArgumentParser(description='Local Master Inspection Plan')
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parent / 'data')
    parser.add_argument('--port', type=int, default=8642)
    args = parser.parse_args(); args.data.mkdir(parents=True, exist_ok=True)
    try:
        with data_lock(args.data):
            server = create_server(Store(args.data / 'inspection_plan.db'), args.port)
            url = 'http://127.0.0.1:%s/' % server.server_port
            print('Master Inspection Plan running at', url, flush=True)
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
    except (OSError, RuntimeError) as exc:
        print('Unable to start the inspection app:', exc, flush=True)
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
