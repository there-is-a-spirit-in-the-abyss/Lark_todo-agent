"""PyInstaller entry point. Never connects until a user starts an operation."""
import argparse
import json
import sys
from pathlib import Path

from deployer.bundle import load_bundle, resource_root


def main():
    parser = argparse.ArgumentParser(description='Huiyang deployment installer')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--self-test-output', type=Path)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--smoke-ui', action='store_true')
    args = parser.parse_args()
    bundle = load_bundle()
    metadata = json.loads((resource_root() / 'project.json').read_text(encoding='utf-8'))
    if metadata['project'] != bundle.profile.id:
        raise ValueError('安装包项目标识与资源不匹配。')
    import tkinter as tk
    result = {'project':bundle.profile.id, 'version':bundle.version, 'image':bundle.image, 'default_directory':bundle.profile.default_directory,
              'source_sha256':bundle.sha256, 'bundled':bool(getattr(sys, 'frozen', False)),
              'credentials_embedded':False, 'gui_available':True}

    def write_result():
        if args.self_test_output:
            args.self_test_output.parent.mkdir(parents=True, exist_ok=True)
            args.self_test_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        if sys.stdout:
            print(json.dumps(result, ensure_ascii=False))

    if args.self_test:
        write_result()
        return
    from deployer.gui import InstallerApp
    root = tk.Tk()
    app = InstallerApp(root, bundle, preview=args.preview or args.smoke_ui)
    if args.smoke_ui:
        def exercise():
            app.tabs.select(app.config_tab)
            root.update_idletasks()
            assert app.directory.get() == bundle.profile.default_directory
            assert not app.state.connected
            result['gui_ready'] = True
            write_result()
            app.close()
        root.after(1800, exercise)
    root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if sys.stderr:
            print(f'Installer failed: {type(error).__name__}: {error}', file=sys.stderr)
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror('安装器无法启动', str(error), parent=root)
            root.destroy()
        raise SystemExit(1)
