import asyncio
import logging
import sys
from contextlib import asynccontextmanager, suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from huiyang.adapters.feishu_api import FeishuAPIAdapter
from huiyang.agent.structured_llm import StructuredLLMAdapter
from huiyang.database import Database
from huiyang.services.background import BackgroundJobs
from huiyang.services.platform_gateway import PlatformGateway
from huiyang.services.scheduling import configure_jobs

log = logging.getLogger(__name__)


async def supervise_receiver(app):
    try:
        while True:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "huiyang.adapters.long_connection",
            )
            app.state.receiver = process
            code = await process.wait()
            log.warning("Feishu receiver exited (%s); restarting in 10s", code)
            await asyncio.sleep(10)
    finally:
        process = getattr(app.state, "receiver", None)
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


def live_lifespan(settings):
    @asynccontextmanager
    async def lifespan(app):
        settings.validate_live()
        database = Database(settings)
        adapter = FeishuAPIAdapter(settings.feishu_app_id, settings.feishu_app_secret)
        adapter_type = StructuredLLMAdapter
        if settings.llm_provider == "deepseek":
            from huiyang.agent.deepseek_llm import DeepSeekLLMAdapter
            adapter_type = DeepSeekLLMAdapter
        interpreter = adapter_type(
            api_key=settings.llm_api_key, base_url=settings.llm_api_base_url, model=settings.llm_model,
        )
        scheduler = AsyncIOScheduler(timezone=settings.app_timezone)
        tasks = []
        try:
            bot_id = await adapter.bot_open_id()
            gateway = PlatformGateway(database.session_factory, interpreter, adapter, settings, bot_open_id=bot_id)
            jobs = BackgroundJobs(database.session_factory, adapter, settings)
            configure_jobs(scheduler, reminder_job=jobs.reminders,
                           weekly_summary_job=None if settings.team_web_enabled else jobs.weekly_summary,
                           timezone=settings.app_timezone)
            scheduler.start()
            tasks = [asyncio.create_task(gateway.run()), asyncio.create_task(supervise_receiver(app))]
            app.state.platform_running = True
            yield
        finally:
            app.state.platform_running = False
            if scheduler.running:
                scheduler.shutdown(wait=False)
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task
            await interpreter.close()
            await adapter.close()
            await database.dispose()
    return lifespan
