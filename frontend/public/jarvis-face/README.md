# Assets du Face Avatar de Jarvis

Dépose ici les PNG générés (ou que tu as déjà dans la conversation) avec
**exactement** ces noms de fichiers. Le composant `src/face-avatar.ts`
les charge automatiquement au démarrage du frontend.

Les images manquantes retombent silencieusement sur `base-neutral.png`,
donc tu peux démarrer avec juste 4 ou 5 fichiers et compléter plus tard.

## Fichiers attendus

| Nom de fichier           | Rôle                                         | Essentiel |
|--------------------------|----------------------------------------------|-----------|
| `base-neutral.png`       | Visage neutre, bouche fermée (idle)          | OUI       |
| `mouth-00-closed.png`    | Bouche fermée pendant la parole              | OUI       |
| `mouth-01-slightly.png`  | Bouche légèrement entrouverte                | OUI       |
| `mouth-02-oh.png`        | Bouche arrondie en « oh »                    | OUI       |
| `mouth-03-wide.png`      | Bouche grande ouverte (voyelles ouvertes)    | OUI       |
| `expr-thinking.png`      | Visage pensif / yeux mi-clos                 | optionnel |
| `expr-attentive.png`     | Visage attentif (état listening)             | optionnel |
| `expr-smile.png`         | Sourire subtil (salutations, blagues)        | optionnel |
| `eyes-closed.png`        | Frame de clignement (yeux complètement fermés)| optionnel |

## Correspondance avec les 5 images déjà générées

Les 5 images envoyées dans la conversation correspondent à :

```
image 1 (bouche fermée, lèvres légèrement pressées) → mouth-00-closed.png
image 2 (bouche arrondie en « oh »)                → mouth-02-oh.png
image 3 (bouche grande ouverte, dents visibles)    → mouth-03-wide.png
image 4 (neutre / déterminé)                       → base-neutral.png
image 5 (yeux mi-clos)                             → expr-thinking.png
```

Il manque encore : `mouth-01-slightly.png`, `eyes-closed.png`,
`expr-attentive.png`, `expr-smile.png`. Tant qu'elles ne sont pas là, le
composant utilise `base-neutral.png` à la place — tout fonctionne, juste
avec une amplitude d'expressions un peu plus faible.

## Format recommandé

- **Dimensions** : 1024×1024 (ou 512×512 minimum), carré
- **Format** : PNG, fond noir uniforme (ou transparent)
- **Poids cible** : < 500 Ko par image après compression

Pour compresser rapidement :
```bash
# ImageMagick
for f in *.png; do convert "$f" -strip -quality 92 "$f"; done

# ou pngquant (plus agressif)
pngquant --quality=80-95 --ext .png --force *.png
```
