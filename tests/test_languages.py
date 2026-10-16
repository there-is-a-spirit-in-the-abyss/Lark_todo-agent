import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from huiyang.adapters.long_connection import persist_event
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.agent.structured_llm import StructuredLLMAdapter
from huiyang.config import Settings
from huiyang.domain.platform import PlatformSetting
from huiyang.services.background import BackgroundJobs
from huiyang.services.summaries import build_weekly_summary
from test_live_gateway import runtime
from test_platform_adapters import event


def test_instance_language_is_chinese_by_default_and_validated():
    assert Settings(_env_file=None).app_language == 'zh-CN'
    assert Settings(_env_file=None, app_language='en-US').app_language == 'en-US'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_language='fr-FR')


@pytest.mark.asyncio
async def test_private_language_switch_persists_and_controls_actual_replies(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    persist_event(sync, event('/language en-US', chat_type='p2p', event_id='language'))
    assert await gateway.process_one()
    assert 'English' in adapter.messages[-1].text
    assert not llm.calls
    # A fresh gateway uses the persisted preference; user-authored Chinese stays intact.
    from huiyang.services.platform_gateway import PlatformGateway
    gateway = PlatformGateway(factory, llm, adapter, gateway.settings, bot_open_id='ou_bot')
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_TASK,
        understanding='create my task', payload={'title': '中文标题', 'visibility': 'personal'}))
    persist_event(sync, event('create my task', chat_type='p2p', event_id='create'))
    assert await gateway.process_one()
    assert 'Created task' in adapter.messages[-1].text
    assert '中文标题' in adapter.messages[-1].text
    assert 'No deadline' in adapter.messages[-1].text
    assert 'To do' in adapter.messages[-1].text
    assert llm.calls[-1][1]['language'] == 'en-US'
    async with factory() as session:
        assert await session.scalar(select(PlatformSetting).where(PlatformSetting.value == 'en-US'))


@pytest.mark.asyncio
async def test_team_group_english_entry_preserves_mention_and_no_llm(runtime):
    sync, _, gateway, llm, adapter, _ = runtime
    gateway.settings.team_web_enabled = True
    gateway.settings.team_public_url = 'https://team.example.com'
    gateway.settings.app_language = 'en-US'
    payload = event('team tasks', event_id='silent')
    payload['event']['message']['mentions'] = []
    persist_event(sync, payload)
    assert await gateway.process_one()
    assert not adapter.messages
    persist_event(sync, event('@_user_1 team tasks', event_id='entry'))
    assert await gateway.process_one()
    assert adapter.messages[-1].text.startswith('Team tasks:')
    assert not llm.calls


@pytest.mark.asyncio
async def test_model_system_prompt_enforces_reply_language_without_changing_schema():
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(500)
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    adapter = StructuredLLMAdapter(api_key='test', base_url='https://model.test', model='test', client=client)
    from huiyang.services.secretary import IncomingMessage
    message = IncomingMessage('u', 'c', 'p2p', 'hello', datetime.now(UTC))
    with pytest.raises(ValueError):
        await adapter.interpret(message, {'language': 'en-US'})
    assert 'English' in requests[0]['messages'][0]['content']
    assert 'en-US' in requests[0]['messages'][0]['content']
    assert '待办' in json.dumps(requests[0]['response_format'], ensure_ascii=False)
    await client.aclose()


def test_english_summary_renders_labels_without_translating_task_content():
    text = build_weekly_summary('中文项目', [], now=datetime.now(UTC), language='en-US')
    assert '中文项目' in text
    assert 'Weekly summary' in text
    assert 'Completed (0): None' in text


@pytest.mark.asyncio
async def test_chat_switch_rejects_invalid_locale_and_does_not_leak_to_another_user(runtime):
    sync, _, gateway, llm, adapter, _ = runtime
    for event_id,text,user in [('en','/language en-US','u_real'),('invalid','/language fr-FR','u_real'),
                               ('other','登记 name','u_other')]:
        persist_event(sync,event(text,event_id=event_id,user_id=user,chat_type='p2p'))
        assert await gateway.process_one()
    assert 'Usage:' in adapter.messages[1].text
    assert '无需登记' in adapter.messages[2].text
    assert not llm.calls


@pytest.mark.asyncio
async def test_persisted_language_controls_background_reminder_but_not_destination(runtime):
    from huiyang.domain.models import Task, TaskVisibility
    from huiyang.domain.persistence import User, Reminder
    from huiyang.i18n import save_language
    from uuid import uuid4
    _, factory, gateway, _, adapter, _ = runtime
    async with factory() as session:
        user=User(id=uuid4(),feishu_user_id='u_reminder',display_name='名字')
        session.add(user)
        await session.flush()
        task=Task(id=uuid4(),title='中文内容',original_instruction='',creator_id=user.id,
                  assignee_id=user.id,visibility=TaskVisibility.PERSONAL,
                  deadline=datetime(2000,1,1,tzinfo=UTC))
        session.add(task)
        await session.flush()
        session.add(Reminder(task_id=task.id,scheduled_for=datetime(2000,1,1,tzinfo=UTC),
                             kind='default',destination='private'))
        await save_language(session,private=True,identity='u_reminder',language='en-US')
        await session.commit()
    await BackgroundJobs(factory,adapter,gateway.settings).reminders()
    assert len(adapter.messages)==1
    assert adapter.messages[0].text=='“中文内容” is due now'
    assert adapter.messages[0].channel=='private'
    assert adapter.messages[0].target_id=='u_reminder'


@pytest.mark.asyncio
async def test_english_gateway_error_performs_no_task_action(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    gateway.settings.app_language='en-US'
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_TASK,
        understanding='create a task',payload={'title':'safe','assignee_feishu_user_id':'missing'}))
    persist_event(sync,event('create a task',chat_type='p2p'))
    assert await gateway.process_one()
    assert 'No task action was performed' in adapter.messages[-1].text
    from huiyang.domain.models import Task
    async with factory() as session:
        assert await session.scalar(select(Task)) is None


@pytest.mark.asyncio
async def test_deepseek_language_instruction_is_in_system_prompt():
    from huiyang.agent.deepseek_llm import DeepSeekLLMAdapter
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(500)
    client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
    adapter=DeepSeekLLMAdapter(api_key='test',base_url='https://model.test',model='test',client=client)
    from huiyang.services.secretary import IncomingMessage
    with pytest.raises(ValueError):
        await adapter.interpret(IncomingMessage('u','c','p2p','hello',datetime.now(UTC)),{'language':'en-US'})
    assert 'English (en-US)' in requests[0]['input'][0]['content']
    await client.aclose()


@pytest.mark.asyncio
async def test_locale_scope_is_isolated_across_concurrent_requests():
    import asyncio
    from huiyang.i18n import language_scope,t
    async def render(language):
        with language_scope(language):
            await asyncio.sleep(0)
            return t('无截止时间')
    assert await asyncio.gather(render('en-US'),render('zh-CN'))==['No deadline','无截止时间']
    assert t('无截止时间')=='无截止时间'


def test_catalog_templates_preserve_interpolation_fields_and_render_both_languages():
    from string import Formatter
    from huiyang.i18n import ENGLISH,t
    def fields(text):
        return {name for _,name,_,_ in Formatter().parse(text) if name is not None}
    for source,translation in ENGLISH.items():
        assert fields(source)==fields(translation),(source,translation)
        values={name:'value' for name in fields(source)}
        assert t(source,language='en-US',**values)==translation.format(**values)
        assert t(source,language='zh-CN',**values)==source.format(**values)


@pytest.mark.asyncio
async def test_legacy_group_switch_is_scoped_to_group_and_keeps_chat_routing(runtime):
    sync,_,gateway,llm,adapter,_=runtime
    persist_event(sync,event('@_user_1 /language en-US',event_id='group-language'))
    assert await gateway.process_one()
    assert adapter.messages[-1].channel=='group'
    assert adapter.messages[-1].target_id=='oc_group'
    assert not llm.calls
    llm._actions.append(StructuredAction(action_type=ActionType.LIST_TASKS,understanding='list my tasks'))
    persist_event(sync,event('@_user_1 my tasks',event_id='group-list'))
    assert await gateway.process_one()
    assert llm.calls[-1][1]['language']=='en-US'
    assert 'active tasks' in adapter.messages[-1].text
    persist_event(sync,event('登记 name',chat_type='p2p',event_id='private'))
    assert await gateway.process_one()
    assert '无需登记' in adapter.messages[-1].text


def test_catalog_covers_all_static_server_translation_calls():
    import ast
    from pathlib import Path
    from huiyang.i18n import ENGLISH
    missing=[]
    for path in (Path(__file__).parents[1]/'src'/'huiyang').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='t'
                    and node.args and isinstance(node.args[0],ast.Constant)):
                source=node.args[0].value
                if isinstance(source,str) and source not in ENGLISH:
                    missing.append((path.name,source))
    assert missing==[]
