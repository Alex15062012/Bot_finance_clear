from __future__ import annotations

from app.scenarios.base import Scenario
from app.scenarios.bot_lifecycle import BotLifecycleScenario
from app.scenarios.materials import MaterialsScenario
from app.scenarios.menu import MenuScenario
from app.scenarios.new_subscriber import NewSubscriberScenario
from app.scenarios.question import QuestionScenario


def build_scenarios() -> list[Scenario]:
    """Порядок важен: более специфичные сценарии раньше."""
    return [
        BotLifecycleScenario(),
        NewSubscriberScenario(),
        MaterialsScenario(),
        MenuScenario(),
        QuestionScenario(),
    ]
