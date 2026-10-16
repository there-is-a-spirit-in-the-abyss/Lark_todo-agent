"""System-owned presentation text; domain values and user content stay unchanged."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256

LANGUAGES = ('zh-CN', 'en-US')
_language = ContextVar('huiyang_language', default='zh-CN')

ENGLISH = {
    '已创建任务「{title}」。': 'Created task “{title}”.',
    '已删除任务「{title}」。': 'Deleted task “{title}”.',
    '已修改任务。': 'Updated task.',
    '当前共有 {count} 个进行中的任务。': 'There are {count} active tasks.',
    '已创建项目「{name}」。': 'Created project “{name}”.',
    '无截止时间': 'No deadline',
    '待办': 'To do', '进行中': 'In progress', '阻塞': 'Blocked',
    '已完成': 'Completed', '已取消': 'Canceled', '已逾期': 'Overdue',
    '属于哪个项目': 'which project it belongs to',
    '指的是哪个任务': 'which task you mean', '负责人是谁': 'who is responsible',
    '我理解你要{understanding}。目前不能确定{field}，{question}':
        'I understand: {understanding}. I need to clarify {field}. {question}',
    '我理解并执行的是：\n{understanding}。': 'What I understood and executed:\n{understanding}.',
    '{assignee}当前任务：\n': 'Current tasks for {assignee}:\n',
    '{name} 项目周总结': 'Weekly summary: {name}',
    '{label}（{count}）：{detail}': '{label} ({count}): {detail}',
    '无': 'None', '、': ', ',
    '「{title}」已到截止时间': '“{title}” is due now',
    '「{title}」将在 1 小时后截止': '“{title}” is due in 1 hour',
    '提醒：{title}': 'Reminder: {title}',
    '团队任务：': 'Team tasks: ',
    '已自动同步飞书名称「{name}」，无需登记或绑定码。':
        'Your Feishu name “{name}” was synced automatically. No registration or binding code is needed.',
    '我理解你希望操作任务；权限检查未通过，只能管理自己负责的任务。':
        'Permission denied. You can only manage tasks assigned to you.',
    '未执行任务操作：解析结果未通过校验，请补充或明确指令。':
        'No task action was performed: the request could not be validated. Please clarify your instruction.',
    '未执行任务操作：相关人员、任务或项目尚未找到，请明确对象。':
        'No task action was performed: the person, task or project was not found. Please specify it.',
    '语言已切换为简体中文。': 'Language switched to English.',
    '用法：/language zh-CN 或 /language en-US': 'Usage: /language zh-CN or /language en-US',
}


ENGLISH.update({'请通过飞书登录': 'Please sign in with Feishu',
 '你不在此飞书群中，无法访问团队空间': 'You are not in this Feishu group and cannot access the team space',
 '暂时无法验证群成员身份，请稍后重试': 'Unable to verify group membership. Please try again later',
 '暂时无法读取群信息': 'Unable to read group information',
 '已退群成员': 'Former group member',
 '群成员': 'Group member',
 '已退群': 'Left group',
 '团队空间': 'Team space',
 '页面验证失效，请刷新': 'Page verification expired. Please refresh',
 '其他成员已更新，请刷新后重试': 'Another member updated the board. Refresh and try again',
 '登录已失效，请重新打开群链接': 'Login expired. Open the group link again',
 '登录凭证已使用': 'Login credential already used',
 '飞书登录未完成，请重试': 'Feishu login did not complete. Please try again',
 '团队网页尚未构建': 'The team webpage has not been built',
 '无效的群入口': 'Invalid group link',
 '请输入 1 至 {maximum} 个字符': 'Enter 1 to {maximum} characters',
 '任务或项目已不存在，请刷新': 'Task or project no longer exists. Please refresh',
 '连接不能形成循环': 'Connections cannot create a cycle',
 '任务已不存在': 'Task no longer exists',
 '你已不在此飞书群中': 'You are no longer in this Feishu group',
 '无效操作': 'Invalid action',
 '操作字段不正确': 'Invalid action fields',
 '任务和项目必须使用有效 UUID 标识': 'Tasks and projects must have valid UUID identifiers',
 '无效的连接位置': 'Invalid connection target',
 '标识重复': 'Duplicate identifier',
 '项目数量已达上限': 'Project limit reached',
 '任务数量已达上限': 'Task limit reached',
 '只有项目当前任务负责人可以修改项目名称': 'Only an assignee of a current project task can rename this project',
 '只有发布者可以维护此任务': 'Only the author can manage this task',
 '无效的任务状态': 'Invalid task status',
 '任务备注最多 2000 个字符': 'Task notes must be at most 2000 characters',
 '不能接到自身或自己的后代': 'Cannot attach to itself or its descendants',
 '团队任务请在网页查看': 'View team tasks on the webpage',
 '私聊仅维护个人任务': 'Private chat only manages personal tasks'})

def current_language():
    return _language.get()


@contextmanager
def language_scope(language):
    token = _language.set(language if language in LANGUAGES else 'zh-CN')
    try:
        yield
    finally:
        _language.reset(token)


def t(text, *, language=None, **values):
    template = ENGLISH.get(text, text) if (language or current_language()) == 'en-US' else text
    return template.format(**values) if values else template


def reply_language_prompt(context):
    language = context.get('language', current_language())
    name = 'English (en-US)' if language == 'en-US' else 'Simplified Chinese (zh-CN)'
    return (f'\nOutput understanding and ambiguity.question in {name}. '
            'Keep user names, task/project titles, identifiers, JSON keys, action types '
            'and canonical status enum values unchanged. This language rule also applies '
            'when the incoming message or previous conversation uses another language.')


def preference_key(*, private, identity):
    return 'language:' + ('user:' if private else 'group:') + sha256(identity.encode()).hexdigest()


async def preferred_language(session, *, private, identity, default='zh-CN'):
    from huiyang.domain.platform import PlatformSetting
    row = await session.get(PlatformSetting, preference_key(private=private, identity=identity))
    return row.value if row is not None and row.value in LANGUAGES else default


async def save_language(session, *, private, identity, language):
    from huiyang.domain.platform import PlatformSetting
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    statement = insert(PlatformSetting).values(
        key=preference_key(private=private, identity=identity), value=language)
    await session.execute(statement.on_conflict_do_update(
        index_elements=['key'], set_={'value': language}))
