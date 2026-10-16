"""Native desktop wizard. Network work never runs on the Tk event thread."""
import posixpath
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .config import IMPORT_KEYS, import_env, normalize_directory, redact, validate_connection, validate_host
from .models import Bundle, Connection, DeployRequest
from .state import WizardState

GREEN = '#137c6b'
BG = '#f3f7f6'
TEXT = '#153d35'


class InstallerApp:
    def __init__(self, root: tk.Tk, bundle: Bundle, *, preview: bool = False):
        self.root, self.bundle, self.profile = root, bundle, bundle.profile
        self.preview = preview
        self.state = WizardState()
        self.session = None
        self.events = queue.Queue()
        self.closed = False
        self.secrets: list[str] = []
        self.controls: list[tuple[ttk.Widget, str]] = []
        self.fields: dict[str, tk.StringVar] = {}
        self.field_widgets: dict[str, ttk.Entry] = {}
        self.host, self.user, self.ssh_port = tk.StringVar(), tk.StringVar(value='root'), tk.StringVar(value='22')
        self.password, self.key_path, self.passphrase, self.sudo_password = [tk.StringVar() for _ in range(4)]
        self.auth_mode = tk.StringVar(value='password')
        self.directory = tk.StringVar(value=self.profile.default_directory)
        self.public_host, self.http_port = tk.StringVar(), tk.StringVar(value='8080')
        self.https, self.allow_docker = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.show_secrets = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='请先填写服务器信息。' if not preview else '本机界面预览 · 不会连接服务器')
        self.access_url = tk.StringVar()
        self.server_info = tk.StringVar(value='连接成功后显示系统、运行环境和可用空间。')
        self.summary = tk.StringVar()
        self._build()
        for var in (self.host, self.user, self.ssh_port, self.password, self.key_path, self.passphrase, self.sudo_password, self.auth_mode):
            var.trace_add('write', self._connection_edited)
        self.directory.trace_add('write', self._destination_edited)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(80, self._pump)

    def _build(self):
        root = self.root
        root.title(f'{self.profile.title} · 服务器安装向导')
        root.geometry('1020x810')
        root.minsize(920, 740)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10), background=BG, foreground=TEXT)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG)
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', padding=(18, 10))
        style.configure('TButton', padding=(12, 7))
        style.configure('Accent.TButton', background=GREEN, foreground='white', padding=(18, 8))
        style.map('Accent.TButton', background=[('active', '#0e6657'), ('disabled', '#a9c3bb')])
        header = tk.Frame(root, bg=GREEN, height=100)
        header.pack(fill='x')
        tk.Label(header, text=f'{self.profile.title}  /  安装到服务器', bg=GREEN, fg='white', font=('Microsoft YaHei UI', 21, 'bold')).pack(anchor='w', padx=28, pady=(18, 4))
        mode = '发布镜像，直接下载运行' if self.bundle.image else '本地源码包，由服务器 Docker 自动构建'
        tk.Label(header, text=f'{self.bundle.version}  ·  {mode}  ·  本机无需配置应用依赖', bg=GREEN, fg='#d8f0e8').pack(anchor='w', padx=30, pady=(0, 17))
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill='both', expand=True, padx=24, pady=(18, 8))
        self.connection_tab, self.destination_tab, self.config_tab, self.result_tab = [ttk.Frame(self.tabs, padding=22) for _ in range(4)]
        for frame, title in zip((self.connection_tab, self.destination_tab, self.config_tab, self.result_tab), ('1  连接服务器', '2  选择安装位置', '3  项目配置', '4  部署与维护')):
            self.tabs.add(frame, text=title)
        self.connection_body = self._scrollable(self.connection_tab)
        self.config_body = self._scrollable(self.config_tab)
        self._connection_ui()
        self._destination_ui()
        self._config_ui()
        self._result_ui()
        footer = ttk.Frame(root, padding=(28, 8, 28, 14))
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.status, wraplength=920).pack(anchor='w')
        self.progress = ttk.Progressbar(footer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(8, 0))
        if self.preview:
            self.connect_button.state(['disabled'])
            self.deploy_button.state(['disabled'])
            self.maintenance_button.state(['disabled'])

    def _scrollable(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        return body

    def _entry(self, parent, row, title, variable, *, secret=False, browse=None):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky='w', pady=8, padx=(0, 18))
        widget = ttk.Entry(parent, textvariable=variable, show='•' if secret else '')
        widget.grid(row=row, column=1, sticky='ew', pady=7)
        self.controls.append((widget, 'normal'))
        if browse:
            button = ttk.Button(parent, text='选择文件…', command=browse)
            button.grid(row=row, column=2, padx=(10, 0))
            self.controls.append((button, 'normal'))
        return widget

    def _button(self, parent, text, command, *, accent=False):
        button = ttk.Button(parent, text=text, command=command, style='Accent.TButton' if accent else 'TButton')
        self.controls.append((button, 'normal'))
        return button

    def _connection_ui(self):
        frame = self.connection_body
        ttk.Label(frame, text='使用服务器的 SSH 登录信息', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='密码和私钥口令仅用于本次连接，不保存在本机配置或日志中。', wraplength=860).pack(anchor='w', pady=(6, 14))
        form = ttk.Frame(frame)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, '服务器 IP / 域名', self.host)
        self._entry(form, 1, 'SSH 端口', self.ssh_port)
        self._entry(form, 2, '用户名', self.user)
        modes = ttk.Frame(form)
        modes.grid(row=3, column=1, sticky='w', pady=5)
        for label, mode in (('使用密码', 'password'), ('使用私钥', 'key')):
            radio = ttk.Radiobutton(modes, text=label, variable=self.auth_mode, value=mode)
            radio.pack(side='left', padx=(0, 22))
            self.controls.append((radio, 'normal'))
        self._entry(form, 4, 'SSH 密码', self.password, secret=True)
        self._entry(form, 5, '私钥文件', self.key_path, browse=self._choose_key)
        self._entry(form, 6, '私钥口令（如有）', self.passphrase, secret=True)
        self._entry(form, 7, 'sudo 密码（如需）', self.sudo_password, secret=True)
        ttk.Label(frame, text='推荐使用 root；其他用户需有 sudo 权限。首次连接会显示服务器指纹供你核对。', wraplength=860).pack(anchor='w', pady=12)
        self.connect_button = self._button(frame, '连接并检查服务器', self.connect_server, accent=True)
        self.connect_button.pack(anchor='w')
        ttk.Label(frame, textvariable=self.server_info, wraplength=860, justify='left').pack(anchor='w', pady=18)

    def _destination_ui(self):
        frame = self.destination_tab
        ttk.Label(frame, text='选择服务器上的安装文件夹', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='默认在服务器根目录下创建英文项目文件夹，也可自定义位置。', wraplength=860).pack(anchor='w', pady=(7, 18))
        form = ttk.Frame(frame)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, '安装目录', self.directory)
        self._button(form, '浏览服务器…', self.browse_server).grid(row=0, column=2, padx=(10, 0))
        self._button(frame, '恢复默认目录', lambda: self.directory.set(self.profile.default_directory)).pack(anchor='w', pady=(12, 20))
        ttk.Label(frame, text='应用配置、数据和备份保存在所选目录。已有本安装器创建的项目可在原处升级；其他非空文件夹会被保护。', wraplength=840).pack(anchor='w', pady=10)
        ttk.Label(frame, text='HTTPS 网关由两个项目共用，配置保存在 /var/lib/huiyang-installer。已占用的现有网站端口不会被自动接管。', wraplength=840).pack(anchor='w', pady=10)
        self._button(frame, '下一步：项目配置', lambda: self.tabs.select(self.config_tab), accent=True).pack(anchor='w', pady=20)

    def _config_ui(self):
        frame = self.config_body
        ttk.Label(frame, text='访问地址与项目连接信息', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        form = ttk.Frame(frame)
        form.pack(fill='x', pady=(10, 0))
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, '公网 IP / 域名', self.public_host)
        check = ttk.Checkbutton(form, text='自动配置 HTTPS（需要公网 80 / 443 端口可达）', variable=self.https)
        check.grid(row=1, column=1, sticky='w', pady=6)
        if self.profile.requires_feishu:
            check.state(['disabled'])
        else:
            self.controls.append((check, 'normal'))
            self._entry(form, 2, 'HTTP 测试端口', self.http_port)
        if self.profile.requires_feishu:
            row = 2
            for key, label, default, secret in (
                ('FEISHU_APP_ID', '飞书 App ID', '', False),
                ('FEISHU_APP_SECRET', '飞书 App Secret', '', True),
                ('LLM_API_BASE_URL', '模型 HTTPS API 地址', '', False),
                ('LLM_API_KEY', '模型 API Key', '', True),
                ('LLM_MODEL', '模型名称', '', False),
                ('LLM_PROVIDER', '模型协议', 'openai_compatible', False),
            ):
                variable = self.fields[key] = tk.StringVar(value=default)
                if key == 'LLM_PROVIDER':
                    ttk.Label(form, text=label).grid(row=row, column=0, sticky='w')
                    widget = ttk.Combobox(form, textvariable=variable, state='readonly', values=('openai_compatible', 'deepseek'))
                    widget.grid(row=row, column=1, sticky='ew', pady=7)
                    self.controls.append((widget, 'readonly'))
                else:
                    widget = self._entry(form, row, label, variable, secret=secret)
                    self.field_widgets[key] = widget
                row += 1
            toolbar = ttk.Frame(frame)
            toolbar.pack(fill='x', pady=10)
            self._button(toolbar, '导入本地 .env…', self.import_local).pack(side='left', padx=(0, 8))
            self._button(toolbar, '导入服务器配置…', self.import_remote).pack(side='left', padx=(0, 12))
            show = ttk.Checkbutton(toolbar, text='显示密钥', variable=self.show_secrets, command=self._toggle_secrets)
            show.pack(side='left')
            self.controls.append((show, 'normal'))
            ttk.Label(frame, text='App ID / Secret 属于具体飞书应用，无法从“当前账号”自动取得。可导入自己已有的配置；新应用仍需在飞书控制台创建、授权和发布。', wraplength=860).pack(anchor='w', pady=(3, 10))
        else:
            ttk.Label(frame, text='团队任务版不需要飞书或模型账号。部署后打开网页，注册自己的账号即可。', wraplength=850).pack(anchor='w', pady=22)
        install = ttk.Checkbutton(frame, text='自动安装缺失的 Docker 和 Compose（支持的 Linux 系统）', variable=self.allow_docker)
        install.pack(anchor='w', pady=6)
        self.controls.append((install, 'normal'))
        self._button(frame, '下一步：检查并部署', self.review, accent=True).pack(anchor='w', pady=12)

    def _result_ui(self):
        frame = self.result_tab
        ttk.Label(frame, text='部署进度与后续维护', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, textvariable=self.summary, wraplength=860, justify='left').pack(anchor='w', pady=(10, 8))
        bar = ttk.Frame(frame)
        bar.pack(fill='x', pady=8)
        self.deploy_button = self._button(bar, '开始部署 / 更新', self.deploy, accent=True)
        self.deploy_button.pack(side='left', padx=(0, 12))
        self.open_button = ttk.Button(bar, text='打开网页', command=self.open_site, state='disabled')
        self.open_button.pack(side='left')
        ttk.Label(frame, textvariable=self.access_url, foreground=GREEN, wraplength=860).pack(anchor='w', pady=(2, 10))
        self.log_text = tk.Text(frame, height=14, state='disabled', wrap='word', bg='#102d27', fg='#e0f0e9', relief='flat', font=('Microsoft YaHei UI', 9), padx=12, pady=10)
        self.log_text.pack(fill='both', expand=True)
        maintenance = ttk.Frame(frame)
        maintenance.pack(fill='x', pady=(15, 4))
        self.action = tk.StringVar(value='查看状态')
        combo = ttk.Combobox(maintenance, textvariable=self.action, state='readonly', values=('查看状态', '查看日志', '重启应用', '备份数据', '升级到本安装包版本', '回退应用镜像'))
        combo.pack(side='left', fill='x', expand=True, padx=(0, 12))
        self.controls.append((combo, 'readonly'))
        self.maintenance_button = self._button(maintenance, '执行维护', self.maintain)
        self.maintenance_button.pack(side='left')
        ttk.Label(frame, text='维护操作只作用于所选目录内、由本安装器管理的同一项目。回退应用镜像不会自动回退数据库。', wraplength=860).pack(anchor='w', pady=5)

    def _choose_key(self):
        filename = filedialog.askopenfilename(parent=self.root, title='选择 SSH 私钥（不要选择 .pub 公钥）')
        if filename:
            self.key_path.set(filename)
            self.auth_mode.set('key')

    def _connection_edited(self, *_):
        if self.state.connected and not self.state.busy:
            self.state.disconnect()
            if self.session:
                self.session.close()
                self.session = None
            self.access_url.set('')
            self.open_button.state(['disabled'])
            self.status.set('连接信息已变更，请重新连接。')

    def _destination_edited(self, *_):
        if not self.state.busy:
            self.state.url = ''
            self.access_url.set('')
            self.open_button.state(['disabled'])

    def _connection(self):
        try:
            port = int(self.ssh_port.get())
        except ValueError:
            raise ValueError('SSH 端口需要填写数字。') from None
        use_key = self.auth_mode.get() == 'key'
        key = self.key_path.get().strip() if use_key else ''
        if use_key and (not key or not Path(key).is_file() or key.endswith('.pub')):
            raise ValueError('请选择有效的 SSH 私钥文件。')
        connection = validate_connection(Connection(self.host.get(), self.user.get().strip(), port, '' if use_key else self.password.get(), key, self.passphrase.get(), self.sudo_password.get()))
        self.secrets.extend(x for x in (connection.password, connection.passphrase, connection.sudo_password) if x)
        return connection

    def connect_server(self):
        if self.preview:
            self.status.set('预览模式不会连接服务器。')
            return
        try:
            connection = self._connection()
        except ValueError as error:
            self._show_error(str(error))
            return
        if self.session:
            self.session.close()
            self.session = None
        self.state.disconnect()

        def work():
            from .remote import RemoteSession
            session = RemoteSession(connection, self._trust_host)
            try:
                info = session.connect()
                return session, info
            except Exception:
                session.close()
                raise

        def done(result):
            self.session, info = result
            self.state.connected = True
            if not self.public_host.get().strip():
                self.public_host.set(connection.host)
            self.server_info.set(f'系统：{info.system} {info.version}    架构：{info.architecture}\nDocker：{info.docker or "未安装"}    Compose：{info.compose or "未安装"}\n可用磁盘：{info.free_mb:,} MB    内存：{info.memory_mb:,} MB\n{info.message}')
            self.status.set('已连接。请选择服务器上的安装位置。')
            self.tabs.select(self.destination_tab)

        self._submit('connect', work, done)

    def _trust_host(self, host, fingerprint):
        if self.closed:
            return False
        event, result = threading.Event(), []
        self.events.put(('trust', (host, fingerprint, event, result)))
        while not event.wait(.2):
            if self.closed:
                return False
        return bool(result and result[0])

    def _set_busy(self, busy):
        for widget, normal in self.controls:
            try:
                widget.configure(state='disabled' if busy else normal)
            except tk.TclError:
                pass
        if busy:
            self.open_button.state(['disabled'])
            self.progress.start(12)
        else:
            self.progress.stop()
            if self.state.url:
                self.open_button.state(['!disabled'])
        if self.preview:
            for widget in (self.connect_button, self.deploy_button, self.maintenance_button):
                widget.state(['disabled'])

    def _submit(self, operation, work, done=lambda result: None):
        if self.preview:
            self.status.set('预览模式不会操作服务器。')
            return
        try:
            self.state.begin(operation)
        except ValueError as error:
            self._show_error(str(error))
            return
        self._set_busy(True)
        self.status.set('正在执行，请稍候…')

        def worker():
            try:
                result = work()
                self.events.put(('done', (done, result)))
            except Exception as error:
                self.events.put(('error', redact(str(error), self.secrets)))

        threading.Thread(target=worker, daemon=True).start()

    def _pump(self):
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.log(value)
                elif kind == 'trust':
                    host, fingerprint, event, result = value
                    try:
                        result.append(messagebox.askyesno('首次连接：核对服务器指纹', f'服务器：{host}\n\nSSH 指纹：\n{fingerprint}\n\n请与服务器控制台提供的指纹核对。确认信任这台服务器并继续连接？', parent=self.root))
                    finally:
                        event.set()
                elif kind == 'done':
                    callback, result = value
                    self.state.finish()
                    self._set_busy(False)
                    self.status.set('操作完成。')
                    try:
                        callback(result)
                    except Exception as error:
                        self.state.finish(error=redact(str(error), self.secrets))
                        self._show_error(self.state.error)
                elif kind == 'error':
                    if self.state.operation == 'connect':
                        self.state.disconnect()
                    self.state.finish(error=value)
                    self._set_busy(False)
                    self.access_url.set('')
                    self.log('失败：' + value)
                    self._show_error(value)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def log(self, text):
        safe = redact(str(text), self.secrets)
        self.log_text.configure(state='normal')
        self.log_text.insert('end', safe + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _show_error(self, text):
        text = redact(text, self.secrets)
        self.status.set(text)
        if not self.preview:
            messagebox.showerror('操作未完成', text, parent=self.root)

    def browse_server(self):
        if not self.state.connected:
            self._show_error('请先连接服务器，再浏览服务器目录。')
            return
        DirectoryBrowser(self)

    def apply_import(self, values):
        count = 0
        for key, value in values.items():
            if key in IMPORT_KEYS and value:
                if key not in self.fields:
                    self.fields[key] = tk.StringVar()
                self.fields[key].set(value)
                if key.endswith(('SECRET', 'KEY')):
                    self.secrets.append(value)
                count += 1
        self.log(f'已导入 {count} 个配置项。密钥已隐藏。')
        self.status.set('配置已导入，请核对访问地址和模型信息。')

    def import_local(self):
        filename = filedialog.askopenfilename(parent=self.root, title='选择自己已有的 .env 配置', filetypes=(('环境配置', '*.env .env'), ('所有文件', '*')))
        if not filename:
            return
        try:
            with open(filename, encoding='utf-8-sig') as handle:
                self.apply_import(import_env(handle.read(1_048_577)))
        except (OSError, UnicodeError, ValueError) as error:
            self._show_error(str(error))

    def import_remote(self):
        if not self.state.connected:
            self._show_error('请先连接服务器。')
            return
        path = simpledialog.askstring('导入已有配置', '输入要读取的服务器 .env 文件路径：', initialvalue=self.directory.get().rstrip('/') + '/.env', parent=self.root)
        if path:
            self._submit('import', lambda: self.session.read_env(path), self.apply_import)

    def _toggle_secrets(self):
        for key in ('FEISHU_APP_SECRET', 'LLM_API_KEY'):
            if key in self.field_widgets:
                self.field_widgets[key].configure(show='' if self.show_secrets.get() else '•')

    def request(self):
        path = normalize_directory(self.directory.get())
        host = validate_host(self.public_host.get() or self.host.get())
        try:
            port = int(self.http_port.get())
        except ValueError:
            raise ValueError('HTTP 测试端口需要填写数字。') from None
        if not 1024 <= port <= 65535:
            raise ValueError('HTTP 测试端口必须是 1024 到 65535。')
        if self.profile.requires_feishu and not self.https.get():
            raise ValueError('汇漾飞书网页登录需要 HTTPS。')
        values = {key: var.get() for key, var in self.fields.items() if var.get() and key in IMPORT_KEYS}
        self.secrets.extend(value for key, value in values.items() if key.endswith(('SECRET', 'KEY')))
        return DeployRequest(self.profile, path, host, self.https.get(), port, values, self.allow_docker.get())

    def review(self):
        try:
            request = self.request()
        except ValueError as error:
            self._show_error(str(error))
            return
        self.summary.set(f'项目：{self.profile.title}\n服务器：{self.user.get()}@{self.host.get()}:{self.ssh_port.get()}\n安装目录：{request.directory}\n访问地址：{request.url}\n方式：' + ('拉取预构建镜像' if self.bundle.image else '上传本安装包源码，由服务器 Docker 自动构建'))
        self.tabs.select(self.result_tab)

    def deploy(self):
        if self.preview:
            return
        try:
            request = self.request()
        except ValueError as error:
            self._show_error(str(error))
            return
        self.review()
        self.access_url.set('')
        self.log('开始检查部署条件；现有数据和无关服务受到保护。')
        self._submit('deploy', lambda: self.session.deploy(request, self.bundle, lambda line: self.events.put(('log', line))), self._deployed)

    def _deployed(self, receipt):
        url = receipt.get('url', '')
        if not url:
            raise ValueError('部署没有返回可验证的访问地址，请查看日志。')
        self.state.finish(url=url)
        self.access_url.set(url)
        self.open_button.state(['!disabled'])
        self.status.set('部署完成。可以打开网页。')
        self.log(receipt.get('message') or '容器及访问检查完成。')
        if self.profile.requires_feishu:
            self.log('请在飞书应用控制台登记 OAuth 回调：' + self.request().origin + '/api/team/callback')
            self.log('飞书应用的发布审批、真实成员登录及模型任务响应仍需由你完成验证。')

    def maintain(self):
        if self.preview:
            return
        if self.action.get() == '升级到本安装包版本':
            self.deploy()
            return
        actions = {'查看状态':'status', '查看日志':'logs', '重启应用':'restart', '备份数据':'backup', '回退应用镜像':'rollback'}
        action = actions[self.action.get()]
        try:
            path = normalize_directory(self.directory.get())
        except ValueError as error:
            self._show_error(str(error))
            return
        if action == 'rollback' and not messagebox.askyesno('回退应用镜像', '只回退应用镜像及相应配置，不恢复旧数据库。数据库迁移不兼容时会拒绝回退。继续？', parent=self.root):
            return

        def done(result):
            text = result.get('message') or result.get('backup_path') or str(result)
            self.log(text)
            self.status.set('维护操作完成。')
            if action == 'rollback':
                self.access_url.set('')

        self.tabs.select(self.result_tab)
        self._submit(action, lambda: self.session.maintain(action, path, lambda line: self.events.put(('log', line)), profile_id=self.profile.id), done)

    def open_site(self):
        if self.state.url:
            webbrowser.open(self.state.url)

    def close(self):
        if self.state.busy and not messagebox.askyesno('操作仍在进行', '关闭窗口将断开 SSH 连接。服务器上已开始的操作可能仍会继续。确定关闭？', parent=self.root):
            return
        self.closed = True
        if self.session:
            self.session.close()
        for variable in (self.password, self.passphrase, self.sudo_password, *self.fields.values()):
            variable.set('')
        self.secrets.clear()
        self.root.destroy()


class DirectoryBrowser:
    def __init__(self, app: InstallerApp):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title('选择服务器安装目录')
        self.window.geometry('760x540')
        self.window.transient(app.root)
        self.window.grab_set()
        self.path = tk.StringVar(value='/')
        self.entries = []
        form = ttk.Frame(self.window, padding=16)
        form.pack(fill='both', expand=True)
        row = ttk.Frame(form)
        row.pack(fill='x', pady=(0, 10))
        ttk.Entry(row, textvariable=self.path).pack(side='left', fill='x', expand=True, padx=(0, 8))
        ttk.Button(row, text='转到', command=self.load).pack(side='left')
        ttk.Button(row, text='上一级', command=self.up).pack(side='left', padx=(8, 0))
        self.tree = ttk.Treeview(form, columns=('name',), show='headings', selectmode='browse')
        self.tree.heading('name', text='服务器文件夹（双击进入）')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', self.enter)
        footer = ttk.Frame(form)
        footer.pack(fill='x', pady=(14, 0))
        ttk.Button(footer, text='新建文件夹…', command=self.create).pack(side='left')
        ttk.Button(footer, text='使用当前目录', command=self.choose).pack(side='right')
        ttk.Label(form, text='也可以关闭此窗口，直接在安装目录输入一个尚未创建的完整路径。', wraplength=690).pack(anchor='w', pady=(12, 0))
        self.load()

    def load(self):
        path = self.path.get()
        if not path.startswith('/') or any(ord(c) < 32 for c in path):
            self.app._show_error('请输入服务器上的绝对目录。')
            return

        def done(entries):
            if not self.window.winfo_exists():
                return
            self.entries = entries
            self.tree.delete(*self.tree.get_children())
            for i, entry in enumerate(entries):
                self.tree.insert('', 'end', iid=str(i), values=(entry.name,))

        self.app._submit('browse', lambda: self.app.session.list_directories(path), done)

    def enter(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self.path.set(self.entries[int(selected[0])].path)
            self.load()

    def up(self):
        self.path.set(posixpath.dirname(self.path.get().rstrip('/')) or '/')
        self.load()

    def create(self):
        name = simpledialog.askstring('新建服务器文件夹', '文件夹名称：', initialvalue=posixpath.basename(self.app.profile.default_directory), parent=self.window)
        if not name:
            return
        if name in ('.', '..') or '/' in name or any(ord(c) < 32 for c in name):
            self.app._show_error('请输入单个文件夹名称。')
            return
        path = posixpath.join(self.path.get(), name)
        self.app._submit('mkdir', lambda: self.app.session.mkdir(path), lambda _value: self.load())

    def choose(self):
        if self.app.state.busy:
            return
        try:
            path = normalize_directory(self.path.get())
        except ValueError as error:
            self.app._show_error(str(error))
            return
        self.app.directory.set(path)
        self.window.destroy()
