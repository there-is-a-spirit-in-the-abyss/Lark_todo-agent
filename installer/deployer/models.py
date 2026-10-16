from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    default_directory: str
    requires_feishu: bool = False


PROFILES = {
    'huiyang': Profile('huiyang', '汇漾飞书版', '/Lark_todo-agent', True),
    'team-todo': Profile('team-todo', '团队任务', '/team-todo'),
}


def get_profile(project_id: str) -> Profile:
    try:
        return PROFILES[project_id]
    except KeyError:
        raise ValueError('安装包的项目标识无效。') from None


@dataclass
class Connection:
    host: str
    user: str = 'root'
    port: int = 22
    password: str = field(default='', repr=False)
    key_path: str = ''
    passphrase: str = field(default='', repr=False)
    sudo_password: str = field(default='', repr=False)
    known_hosts_path: Path | None = None


@dataclass(frozen=True)
class Bundle:
    profile: Profile
    version: str = 'local'
    image: str = ''
    payload: Path | None = None
    sha256: str = ''


@dataclass
class DeployRequest:
    profile: Profile
    directory: str
    public_host: str
    https: bool = True
    port: int = 8080
    values: dict[str, str] = field(default_factory=dict, repr=False)
    allow_install_docker: bool = True

    @property
    def origin(self) -> str:
        host = f'[{self.public_host}]' if ':' in self.public_host else self.public_host
        return f'https://{host}' if self.https else f'http://{host}:{self.port}'

    @property
    def url(self) -> str:
        return self.origin + ('/team' if self.profile.requires_feishu else '/')


@dataclass(frozen=True)
class RemoteDirectory:
    name: str
    path: str


@dataclass
class ServerInfo:
    system: str = ''
    version: str = ''
    architecture: str = ''
    user: str = ''
    docker: str = ''
    compose: str = ''
    free_mb: int = 0
    memory_mb: int = 0
    message: str = ''
