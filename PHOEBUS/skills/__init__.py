import importlib

from .registry import (
    SKILL_REGISTRY,
    execute_skill,
    is_skill_registered,
    describe_skill,
    capability_manifest,
    get_skill,
    list_skills,
    risk_of,
    skill,
)

SKILL_MODULES = (
    "PHOEBUS.skills.timer_skills",
    "PHOEBUS.skills.system_skills",
    "PHOEBUS.skills.spotify_skills",
    "PHOEBUS.skills.home_skills",
    "PHOEBUS.skills.google_skills",
    "PHOEBUS.skills.vision_skills",
    "PHOEBUS.skills.files_skills",
    "PHOEBUS.skills.hardware_skills",
    "PHOEBUS.skills.scheduler_skills",
    "PHOEBUS.skills.creative_skills",
    "PHOEBUS.skills.fully_kiosk_skills",
    "PHOEBUS.skills.education_skills",
    "PHOEBUS.skills.knowledge_skills",
    "PHOEBUS.skills.media_skills",
    "PHOEBUS.skills.obsidian_skills",
    "PHOEBUS.skills.phone_skills",
    "PHOEBUS.skills.network_skills",
    "PHOEBUS.skills.developer_skills",
)
IMPORT_ERRORS: dict[str, str] = {}


def _load_skill_modules() -> None:
    # 1. Charger les modules natifs
    for module_name in SKILL_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            IMPORT_ERRORS[module_name] = f"{type(exc).__name__}: {exc}"
            print(f"[SKILLS] module ignore {module_name}: {exc}")
            
    # 2. Charger les modules custom auto-générés
    import os
    from PHOEBUS.config import BASE_DIR
    custom_dir = os.path.join(BASE_DIR, "skills", "custom")
    if os.path.isdir(custom_dir):
        for f in os.listdir(custom_dir):
            if f.endswith(".py") and not f.startswith("__"):
                module_name = f"PHOEBUS.skills.custom.{f[:-3]}"
                try:
                    importlib.import_module(module_name)
                except Exception as exc:
                    IMPORT_ERRORS[module_name] = f"{type(exc).__name__}: {exc}"
                    print(f"[SKILLS] auto-skill ignore {module_name}: {exc}")


_load_skill_modules()

__all__ = [
    "SKILL_REGISTRY",
    "SKILL_MODULES",
    "IMPORT_ERRORS",
    "execute_skill",
    "is_skill_registered",
    "describe_skill",
    "capability_manifest",
    "get_skill",
    "list_skills",
    "risk_of",
    "skill",
]
