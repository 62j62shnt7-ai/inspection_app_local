import argparse
import sys
import threading
import webbrowser
from pathlib import Path
# Windows embeddable Python does not automatically add the script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inspection_app.store import Store
from inspection_app.server import create_server
from inspection_app.lock import data_lock
from inspection_app.recovery import backup_status, configure_backup_folder

def main():
    # Redirected Windows consoles can use a legacy encoding. Keep errors printable.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    parser = argparse.ArgumentParser(description='Local Master Inspection Plan')
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parent / 'data')
    parser.add_argument('--port', type=int, default=8642)
    args = parser.parse_args()
    try:
        args.data.mkdir(parents=True, exist_ok=True)
        with data_lock(args.data):
            store=Store(args.data / 'inspection_plan.db')
            if not backup_status(store).get('folder'):
                destination=args.data / 'recovery-copies'
                try:
                    destination.mkdir(parents=True,exist_ok=True)
                    configure_backup_folder(store,str(destination))
                except (OSError,ValueError) as exc:
                    print('Automatic backup copy folder needs attention. Choose a folder in Data & backups:',exc,flush=True)
            server = create_server(store, args.port)
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
