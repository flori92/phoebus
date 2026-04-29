from .registry import (
    SKILL_REGISTRY,
    execute_skill,
    is_skill_registered,
    describe_skill,
    get_skill,
    list_skills,
    risk_of,
    skill,
)
import PHOEBUS.skills.timer_skills
import PHOEBUS.skills.system_skills
import PHOEBUS.skills.spotify_skills
import PHOEBUS.skills.home_skills
import PHOEBUS.skills.google_skills
import PHOEBUS.skills.vision_skills
import PHOEBUS.skills.files_skills
import PHOEBUS.skills.hardware_skills
import PHOEBUS.skills.scheduler_skills
import PHOEBUS.skills.creative_skills
import PHOEBUS.skills.fully_kiosk_skills
import PHOEBUS.skills.education_skills
import PHOEBUS.skills.knowledge_skills
import PHOEBUS.skills.media_skills

__all__ = [
    "SKILL_REGISTRY",
    "execute_skill",
    "is_skill_registered",
    "describe_skill",
    "get_skill",
    "list_skills",
    "risk_of",
    "skill",
]
