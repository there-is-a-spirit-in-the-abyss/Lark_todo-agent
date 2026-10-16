from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass
class WizardState:
    connected: bool = False
    busy: bool = False
    operation: str = ''
    url: str = ''
    error: str = ''

    def begin(self, operation: str) -> None:
        if self.busy:
            raise ValueError('上一项操作还在进行，请稍候。')
        if not self.connected and operation != 'connect':
            raise ValueError('请先连接服务器。')
        self.busy, self.operation, self.error = True, operation, ''
        if operation in ('deploy', 'upgrade', 'rollback', 'connect'):
            self.url = ''

    def finish(self, *, error: str = '', url: str = '') -> None:
        self.busy, self.operation = False, ''
        self.error = error
        if error:
            self.url = ''
        elif url:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                self.url = ''
                raise ValueError('部署结果没有返回有效的网址。')
            self.url = url

    def disconnect(self) -> None:
        self.connected, self.url = False, ''

