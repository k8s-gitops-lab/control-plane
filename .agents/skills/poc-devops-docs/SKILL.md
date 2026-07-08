---
name: poc-devops-docs
description: 'Conventions for writing and maintaining documentation across the poc-devops multi-repo workspace (README.md, AGENTS.md, CONTEXT.md, docs/{prd,spec-fonctionnelle,spec-technique}.md). Use when creating or updating documentation in any poc-devops repo, auditing docs for staleness/redundancy, or deciding what belongs in which file.'
---

# Documentation poc-devops

Conventions extraites de l'usage reel dans les repos du workspace
(`control-plane`, `infrastructure`, `platform-cicd`, `platform-gitops`,
`gitlab-projects-iac`, `ci-templates`, `helloworld`, `helloworld-iac`,
`toolbox`), verifiees en dernier @ control-plane f040e3e (2026-07-07).
Pour des conseils de redaction generiques (Diataxis), voir le skill
`documentation-writer` ; ce skill-ci porte les regles specifiques a ce
workspace.

## Quand l'utiliser

- Ecrire ou mettre a jour un `README.md`, `AGENTS.md`, `CONTEXT.md` ou
  `docs/*.md` dans un repo du workspace.
- Auditer la documentation existante pour detecter une derive (doc qui ne
  correspond plus au code), de la redondance ou du hors-scope.
- Decider dans quel fichier une information doit vivre.

## Audit outille

Lancer d'abord le script du skill, puis traiter ses signalements :

```bash
scripts/audit-docs.sh [racine-du-workspace]   # defaut : ../..
```

Il verifie, pour chaque repo du workspace : la presence du layout attendu,
les liens relatifs morts (intra- et inter-repos) dans les `.md`, et les
references a des cibles Make inexistantes. Le script signale, l'humain
tranche : une absence de `prd.md` peut etre un choix assume (cf. note
ci-dessous).

## Structure documentaire par repo

Chaque repo suit le meme layout ; ne pas en inventer un autre.

| Fichier | Role | Audience |
|---|---|---|
| `README.md` | Point d'entree humain : ce que fait le repo, usage, liens vers le reste | Nouvel arrivant, operateur |
| `AGENTS.md` | Regles actionnables pour un agent/operateur : commandes, fichiers cles, ce qu'il ne faut pas faire | Agent IA, mainteneur |
| `CONTEXT.md` | Vocabulaire du domaine (ubiquitous language) : termes, definitions, formulations a eviter | Agent IA, redacteur |
| `docs/prd.md` | Vision, perimetre, non-objectifs, criteres d'acceptation | Le "pourquoi" |
| `docs/spec-fonctionnelle.md` | Regles de comportement : flow, contrats, ce qui se passe et quand | Le "quoi" |
| `docs/spec-technique.md` | Detail d'implementation : fichiers, scripts, contraintes infra | Le "comment" |

Etat reel verifie : tous les repos ont `AGENTS.md` et les deux `spec-*.md` ;
`gitlab-projects-iac` n'a pas de `docs/prd.md` (sa vision est portee par le
PRD de `platform-gitops`). `CONTEXT.md` n'existe aujourd'hui que dans
`control-plane`. Ne pas "corriger" ces ecarts sans decision explicite.

`control-plane` est le point d'entree du workspace : `docs/repo-map.md` y
liste le role de chaque repo, et `README.md` y porte les parcours
utilisateurs qui traversent plusieurs repos (voir plus bas).

## Principe : une seule source de verite

Ne jamais expliquer la meme chose en detail a deux endroits.

- **Meme repo** (ex. la meme regle dans `AGENTS.md` et
  `spec-fonctionnelle.md`) : garder le detail dans le fichier le plus
  specifique (en general le `spec-*`), remplacer l'autre par un renvoi d'une
  phrase.
- **Repos differents** (ex. `control-plane` qui redecrit le detail des jobs
  CI de `ci-templates`) : ne garder qu'un resume + un lien vers le repo qui
  possede l'information. Un repo ne documente en detail que ses propres
  internes.

Symptome a corriger si trouve : deux paragraphes quasi identiques dans deux
fichiers, ou un `spec-technique.md` qui detaille l'implementation d'un
**autre** repo plutot que la sienne.

## Parcours utilisateurs (`control-plane/README.md`)

Le README de `control-plane` porte le recit de bout en bout pour les profils
qui traversent plusieurs repos, par exemple :

- **Operateur DevOps** qui met en place la plateforme (commandes, prerequis,
  ce que ca produit, comment verifier).
- **Equipe applicative** qui onboarde un projet (etapes, ce qui se
  declenche automatiquement au merge).

Chaque parcours reste un resume avec les commandes cles et renvoie vers le
repo qui porte le detail technique de chaque etape (ex. `toolbox/README.md`
pour l'onboarding, `platform-cicd/AGENTS.md` pour le bootstrap). Ne pas
dupliquer le recit complet ailleurs — les autres repos gardent seulement
leur reference technique et peuvent pointer vers ce recit avec une phrase
d'intro ("ce repo porte le detail du Parcours 2, voir control-plane/README.md").

## Discipline d'exactitude

Avant d'ecrire qu'une commande, un script ou un fichier existe :

- `grep`/`ls`/`find` pour verifier qu'il existe reellement dans le code
  (`Makefile`, `scripts/`, manifests generes) — ne jamais recopier une
  affirmation d'une autre doc sans la verifier sur le code actuel.
- Verifier la valeur reelle (namespace cible, version epinglee, chemin de
  fichier) dans le manifeste ou le code qui fait foi.
- Pour une regle "X fait Y", lire le code qui l'implemente (playbook, job
  CI, script Python) plutot que de faire confiance a une doc existante.
- Une doc qui decrit un composant qui a disparu (ex. migration vers un
  nouveau registre d'images) laisse souvent des traces eparpillees dans
  plusieurs repos : chercher le terme dans tout le workspace, pas seulement
  dans le repo en cours d'edition.

## Style

- Francais direct, technique, sans remplissage. Pas de ton marketing.
- Titres `##`/`###`, blocs de code pour les commandes, tables pour les
  references structurees (fichier -> role, variable -> usage).
- `AGENTS.md` se termine par une section "Ce qu'il ne faut pas faire", avec
  la raison quand elle n'est pas evidente.

## A faire / A eviter

### A faire

- Lancer `scripts/audit-docs.sh` avant et apres une passe de doc.
- Verifier chaque affirmation factuelle sur le code avant de l'ecrire.
- Renvoyer vers le repo/fichier qui possede le detail plutot que de le
  recopier.
- Garder le README court et oriente parcours ; les `docs/*.md` portent le
  detail.

### A eviter

- Dupliquer un paragraphe entier entre `AGENTS.md` et un `spec-*.md` du
  meme repo.
- Documenter en detail l'implementation d'un autre repo (scope creep).
- Laisser une doc affirmer un etat du systeme (registry, chemin de script,
  cible make, namespace) sans l'avoir verifie sur le code actuel.
