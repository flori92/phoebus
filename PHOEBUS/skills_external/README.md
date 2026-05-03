# Plugins PHOEBUS

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
