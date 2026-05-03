"""Auto-découverte des plugins PHOEBUS.

Tout fichier `.py` placé dans `PHOEBUS/skills_external/` (ou un répertoire
configuré via `PHOEBUS_PLUGINS_DIR`) est chargé automatiquement au
démarrage. Il suffit qu'il importe `@skill` depuis PHOEBUS.skills et
décore une coroutine, et l'action devient disponible dans le dispatcher.

Exemple minimaliste — `PHOEBUS/skills_external/coucou.py` :

    from PHOEBUS.skills import skill
    from PHOEBUS.voice import parler

    @skill("dis_coucou", risk="low",
           describe=lambda d: "dire bonjour à " + d.get("nom", "tout le monde"))
    async def dis_coucou(data):
        nom = data.get("nom", "tout le monde")
        await parler(f"Coucou {nom} !")

Aucune modification du cœur n'est nécessaire — le plugin est utilisable
dès le redémarrage.

Sécurité : aucun plugin n'est jamais auto-chargé sans qu'on le mette
dans le dossier prévu (donc volontaire). Mais on log clairement chaque
plugin chargé pour traçabilité.
"""
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import List


PLUGINS_DIR_ENV = os.getenv("PHOEBUS_PLUGINS_DIR", "").strip()


def _resolve_plugins_dir() -> Path:
    """Renvoie le dossier où chercher les plugins."""
    if PLUGINS_DIR_ENV:
        return Path(PLUGINS_DIR_ENV).expanduser().resolve()
    # Par défaut : PHOEBUS/skills_external/ à côté de ce fichier.
    return Path(__file__).parent / "skills_external"


def discover_and_load() -> List[str]:
    """Charge tous les plugins .py du dossier. Renvoie la liste des
    modules chargés (chemin court). Les erreurs sont logguées mais
    n'interrompent pas le chargement des autres plugins."""
    plugins_dir = _resolve_plugins_dir()
    if not plugins_dir.exists():
        try:
            plugins_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[PLUGINS] Création dossier {plugins_dir} impossible : {e}")
            return []
        # On crée aussi un README de bienvenue pour onboarding.
        readme = plugins_dir / "README.md"
        if not readme.exists():
            try:
                readme.write_text(_README_TEMPLATE, encoding="utf-8")
            except Exception:
                pass
        return []

    loaded: List[str] = []
    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".py":
            continue
        if entry.name.startswith("_") or entry.name == "__init__.py":
            continue

        mod_name = f"PHOEBUS_plugins.{entry.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, entry)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            loaded.append(entry.stem)
            print(f"[PLUGINS] Chargé : {entry.stem}")
        except Exception as e:
            print(f"[PLUGINS] Échec chargement {entry.name} : {e}")
    if loaded:
        print(f"[PLUGINS] {len(loaded)} plugin(s) chargé(s) depuis {plugins_dir}.")
    return loaded


_README_TEMPLATE = """# Plugins PHOEBUS

Glissez ici tout fichier `.py` qui décore une coroutine avec `@skill(...)`
de `PHOEBUS.skills`. Il est chargé automatiquement au prochain démarrage
(pas besoin de toucher au cœur).

## Squelette minimal

```python
from PHOEBUS.skills import skill
from PHOEBUS.voice import parler

@skill("mon_action",
       risk="low",
       help="Décrit ce que fait cette action.",
       describe=lambda data: "ce que je vais faire")
async def mon_action(data):
    # data est le dict JSON envoyé par le LLM
    await parler("Action exécutée !")
```

Le LLM peut désormais émettre `{"action": "mon_action", ...}` et ton
plugin sera invoqué.

## Conseils

- Garde `risk="high"` si l'action peut faire des dégâts (envoi, écrasement
  de fichiers, appels sortants...). PHOEBUS demandera confirmation vocale.
- Pour les tâches longues, ajoute `background=True` dans le décorateur
  pour que la conversation reste fluide pendant l'exécution.
- Les imports paresseux (`import X` à l'intérieur de la fonction) évitent
  de charger des libs lourdes à chaque démarrage si ton skill n'est pas
  utilisé tout de suite.
"""
