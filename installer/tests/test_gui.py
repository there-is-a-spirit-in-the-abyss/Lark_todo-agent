import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip('tkinter')
pytestmark = pytest.mark.skipif(sys.platform != 'win32' and not os.environ.get('DISPLAY'), reason='Native GUI is exercised on Windows; this runner has no display.')

def run_gui(code):
    # One Tk interpreter per process, as in the packaged application. Recreating
    # Tcl repeatedly is unreliable with this host's Unicode Python installation.
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    prefix = 'import tkinter as tk\nfrom deployer.gui import InstallerApp\nfrom deployer.models import Bundle, get_profile\n'
    result = subprocess.run([sys.executable, '-c', prefix + textwrap.dedent(code)], env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode == 0, result.stderr


def test_todo_wizard_uses_english_default_and_hides_feishu_fields():
    run_gui('''
    root = tk.Tk()
    root.withdraw()
    try:
        app = InstallerApp(root, Bundle(get_profile('team-todo')), preview=True)
        root.update_idletasks()
        assert app.directory.get() == '/team-todo'
        assert 'FEISHU_APP_SECRET' not in app.fields
        assert app.preview
        assert not app.state.connected
        assert app.open_button.instate(['disabled'])
    finally:
        root.destroy()
''')


def test_huiyang_wizard_masks_credentials_and_imports_only_selected_values():
    run_gui('''
    root = tk.Tk()
    root.withdraw()
    try:
        app = InstallerApp(root, Bundle(get_profile('huiyang')), preview=True)
        app.apply_import({'FEISHU_APP_ID':'cli_example', 'FEISHU_APP_SECRET':'test-feishu-secret', 'LLM_API_KEY':'test-model-secret'})
        root.update_idletasks()
        assert app.directory.get() == '/Lark_todo-agent'
        assert app.fields['FEISHU_APP_SECRET'].get() == 'test-feishu-secret'
        assert app.field_widgets['FEISHU_APP_SECRET'].cget('show') == '•'
        assert 'test-feishu-secret' not in app.log_text.get('1.0', 'end')
        assert app.https.get()
    finally:
        root.destroy()
''')


def test_preview_can_never_start_a_remote_connection():
    run_gui('''
    root = tk.Tk()
    root.withdraw()
    try:
        app = InstallerApp(root, Bundle(get_profile('team-todo')), preview=True)
        app.connect_server()
        assert not app.state.busy
        assert app.session is None
    finally:
        root.destroy()
''')
