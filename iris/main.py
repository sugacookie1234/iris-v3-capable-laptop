from iris.boot import boot
from iris.terminal import chat, create_brain, load_config
from iris.memory.store import MemoryStore
from iris.tasks.store import TaskStore
from iris.preflight import diagnostics_values
from iris.automation import AutomationStore
from iris.notifications import NotificationStore
from contextlib import nullcontext
from iris.local_config import activate_saved_configuration
import sys
import sqlite3


def main() -> int:
    try:
        try:
            activate_saved_configuration()
            config = load_config()
            brain = create_brain(config)
            memory_store = MemoryStore()
        except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
            print(f"I.R.I.S. startup error: {exc}", file=sys.stderr)
            return 1
        try:
            with TaskStore(config.tasks_path) as task_store:
                automation_context = (AutomationStore(config.automation_path)
                                      if config.automation_path else nullcontext(None))
                with automation_context as automation_store:
                    notification_context = (NotificationStore(config.notifications_path)
                                            if config.notifications_path else nullcontext(None))
                    with notification_context as notification_store:
                        if notification_store is not None:
                            brain._workflow_executor.set_publisher(notification_store.publish)
                        # Startup shares the local diagnostics used by /diagnostics,
                        # but deliberately never probes the configured provider.
                        boot(diagnostics_values(config, brain, memory_store, task_store,
                                                check_provider_reachability=False))
                        chat(
                            brain,
                            max_history_turns=config.max_history_turns,
                            memory_store=memory_store,
                            task_store=task_store,
                            automation_store=automation_store,
                            notification_store=notification_store,
                            timezone=config.timezone,
                        )
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"I.R.I.S. task storage error: {exc}", file=sys.stderr)
            return 1
        finally:
            memory_store.close()
    except (KeyboardInterrupt, EOFError):
        pass
    print("\nI.R.I.S. session ended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
