# Guide de démarrage pas à pas (débutants)

Ce guide t'accompagne **de zéro** : installer ce qu'il faut, démarrer le serveur
`claude-wrapper`, puis t'en servir depuis **opencode** pour discuter avec Claude
comme dans un chat normal.

> **En une phrase :** ce projet transforme l'outil en ligne de commande
> « Claude Code » en un petit serveur que d'autres applications (comme opencode)
> peuvent appeler pour envoyer un message à Claude et recevoir sa réponse.

Aucune connaissance en programmation n'est nécessaire. Suis les étapes dans
l'ordre. Les commandes sont à taper dans **PowerShell** (Windows). Sur macOS /
Linux, remplace `\` par `/` et `.venv\Scripts\python` par `.venv/bin/python`.

---
> 🟢 **Mode Laizy ?** Si tu n'y connais rien :
> Vas dans le répertoire de ton second cerveau : fait click-droit choisit "Ouvrir dans le terminal".
> tappe "Claude" + Entrée. Lorsque tu es dans claude copie le prompt suivant :
> ```Installe cette extension https://github.com/SINOVATIA/ClaudeWrapper/ , installe toute les dépendances, compile le, et crée deux raccourcis vers l'exécutable généré dans le répertoire courant. L'un pour une ouverture standard claude-wrapper.exe --permission-mode acceptEdits --root [ton répertoire de travail], et un autre pour entrer en "GodMode" toutes les permissions actives : claude-wrapper.exe --dangerous --permission-mode bypassPermissions --root [ton répertoire de travail]. Dans le répertoire de opencode ou prisme dans agent l'utilisateur doit placer le prompt au bon endroit pour opencode. Le guider pas à pas avec la documentation. ```

---

## Sommaire

1. [Prérequis (à installer une seule fois)](#1-prérequis)
2. [Récupérer le code](#2-récupérer-le-code)
3. [Installer le wrapper](#3-installer-le-wrapper)
4. [Démarrer le serveur](#4-démarrer-le-serveur)
5. [Vérifier que ça marche](#5-vérifier-que-ça-marche)
6. [Installer et connecter opencode](#6-installer-et-connecter-opencode)
7. [Choisir le modèle de relais](#7-choisir-le-modèle-de-relais)
8. [Utilisation au quotidien](#8-utilisation-au-quotidien)
9. [Dépannage](#9-dépannage)
10. [Options avancées](#10-options-avancées)

---

## 1. Prérequis

À installer **une fois** sur ta machine. Après chaque installation, ouvre un
**nouveau** terminal pour que les commandes soient reconnues.

### a) Node.js
Télécharge la version **LTS** sur <https://nodejs.org> et installe-la.
Vérifie :
```powershell
node --version
```
Tu dois voir un numéro (ex. `v22.18.0`).

### b) Claude Code (l'outil officiel d'Anthropic)
```powershell
npm install -g @anthropic-ai/claude-code
```
Vérifie :
```powershell
claude --version
```

### c) Connecter Claude à ton compte
Lance simplement :
```powershell
claude
```
Suis l'invite pour te connecter avec ton **abonnement Claude** (ou ta clé API).
Une fois connecté, tape `/exit`. C'est cette connexion que le wrapper réutilise.

> 💡 Chaque message envoyé via le wrapper consomme ton quota/crédits Anthropic,
> exactement comme si tu parlais à Claude directement.

### d) Python 3.11 ou plus
Télécharge sur <https://www.python.org/downloads/> et, **important**, coche
**« Add Python to PATH »** pendant l'installation. Vérifie :
```powershell
python --version
```

### e) Git (optionnel, pour récupérer le code)
<https://git-scm.com/downloads>. Vérifie : `git --version`.

---

## 2. Récupérer le code

Choisis **A** ou **B**.

**A. Avec Git** (recommandé) :
```powershell
cd C:\DATA\DEVELOPPEMENT
git clone https://github.com/SINOVATIA/ClaudeWrapper.git Wrapper-Claude
cd Wrapper-Claude
```

**B. Sans Git** : copie simplement le dossier du projet sur ta machine, par
exemple dans `C:\DATA\DEVELOPPEMENT\Wrapper-Claude`, puis :
```powershell
cd C:\DATA\DEVELOPPEMENT\Wrapper-Claude
```

À partir d'ici, **toutes les commandes se lancent depuis ce dossier**.

---

## 3. Installer le wrapper

Crée un environnement Python isolé puis installe le projet dedans :
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
```
La première ligne crée un dossier `.venv` (l'« environnement »). La seconde y
installe le wrapper et ses dépendances. À refaire seulement si tu changes de
machine ou supprimes `.venv`.

---

## 4. Démarrer le serveur

```powershell
.venv\Scripts\python -m claude_wrapper
```
Tu dois voir une ligne comme :
```
claude-wrapper on http://127.0.0.1:8787/mcp  (model=cli-default, permission_mode=default, root=any, dangerous=off, auth=none)
```
✅ Le serveur tourne. **Laisse ce terminal ouvert** : tant qu'il est ouvert, le
service est disponible. Pour l'arrêter : `Ctrl + C`.

> L'adresse `http://127.0.0.1:8787/mcp` n'est accessible que depuis **ta propre
> machine** (c'est voulu, pour la sécurité).

> 🔢 **Connaître ta version** (utile pour signaler un problème ou vérifier une
> mise à jour) :
> ```powershell
> .venv\Scripts\python -m claude_wrapper --version
> ```
> La version s'affiche aussi au démarrage (dans la bannière). L'historique des
> changements est dans [`CHANGELOG.md`](../CHANGELOG.md).

---

## 5. Vérifier que ça marche

Ouvre un **second** terminal PowerShell (laisse le serveur tourner dans le
premier), va dans le dossier du projet, et lance le test :
```powershell
cd C:\DATA\DEVELOPPEMENT\Wrapper-Claude
.venv\Scripts\python tests\smoke_client.py
```
Tu dois voir la liste des outils et une ligne `HEALTH:` avec
`"ready": true` et `"authenticated": true`. Si c'est le cas, tout est bon.

> ❌ `authenticated: false` → reviens à l'étape **1c** (`claude` puis connexion).

---

## 6. Installer et connecter opencode

**opencode** est l'agent de code en terminal qui va te servir d'interface de
chat. Installe-le (voir <https://opencode.ai/docs>) :
```powershell
npm install -g opencode-ai
```

Il faut ensuite **deux fichiers de configuration**. Des modèles prêts à copier
sont fournis dans `examples/opencode/` de ce projet.

### a) Déclarer le serveur — `opencode.json`
Copie `examples/opencode/opencode.json` à l'un de ces endroits :
- **Global** (recommandé, vaut partout) : `C:\Users\<TON-NOM>\.config\opencode\opencode.json`
- **Projet** (vaut seulement dans le dossier où tu lances opencode) : `opencode.json`

Contenu :
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "claude-wrapper": {
      "type": "remote",
      "url": "http://127.0.0.1:8787/mcp",
      "enabled": true
    }
  }
}
```

### b) Créer l'agent « boîte aux lettres » — `claude.md`
Copie `examples/opencode/agent/claude-agent.md` dans le dossier des agents
d'opencode **en le renommant `claude.md`** (le nom du fichier devient le nom de
l'agent) :
- **Global** : `C:\Users\<TON-NOM>\.config\opencode\agent\claude.md`
- **Projet** : `.opencode\agent\claude.md`

Cet agent fait d'opencode un simple **relais** : tout ce que tu écris est
transmis à Claude, et la réponse de Claude t'est renvoyée telle quelle.

> Dans le fichier, la valeur du **dossier de travail par défaut** est
> `C:\DATA\_ASSISTANT`. Modifie-la pour pointer vers **ton** dossier de travail
> (la ligne `Tu mémorises un "dossier courant", valeur initiale : "..."`).

### c) Démarrer opencode
Dans le dossier de travail voulu :
```powershell
opencode
```
Appuie sur **Tab** pour basculer sur l'agent **claude**, puis écris « bonjour ».
La réponse vient de Claude. 🎉

---

## 7. Choisir le modèle de relais

L'agent de relais a besoin d'un petit modèle (peu importe lequel, il ne fait que
transmettre). Le **vrai** moteur reste Claude Opus 4.8 côté wrapper ; le modèle
de relais ne sert qu'à recopier ton message et la réponse.

Modèles **testés et qui marchent bien** (du meilleur au plus capricieux) :

| Modèle | Coût | Remarque |
|---|---|---|
| **Nemotron 3 Super (Free)** | gratuit | ⭐ Meilleur suivi des consignes |
| **Mistral Small 4** | ~0,01 € / 25 messages | Très fiable, coût négligeable |
| **DeepSeek V4 Flash (Free)** | gratuit | Fonctionne, mais parfois bavard |

> 💰 Le coût ci-dessus est celui **du relais**, minime. Le coût principal vient
> des appels à **Claude Opus 4.8** (ton quota/crédits Anthropic).

**Comment le régler :** ouvre le sélecteur de modèles d'opencode pour voir les
identifiants exacts disponibles chez ton fournisseur (la plupart de ces modèles
gratuits passent par OpenRouter), puis renseigne la ligne `model:` en haut du
fichier `claude.md`, par exemple :
```yaml
model: openrouter/nvidia/nemotron-3-super
```
Si tu laisses `model:` commenté, opencode utilise son modèle par défaut.

---

## 8. Utilisation au quotidien

1. **Démarre le serveur** (étape 4) — laisse le terminal ouvert.
2. **Lance opencode**, appuie sur **Tab** pour l'agent `claude`.
3. **Discute** normalement : chaque message va à Claude, la réponse revient.
4. **Changer de dossier de travail** en cours de discussion : écris
   ```
   cd C:\DATA\PROJET_X
   ```
   L'agent répond `📁 C:\DATA\PROJET_X`. À partir de là, tu parles à Claude
   **dans ce dossier**. Chaque dossier garde **sa propre conversation** : revenir
   à un dossier précédent retrouve sa mémoire.

> Tu peux ouvrir **plusieurs fenêtres opencode** en même temps : chacune a sa
> propre conversation Claude, parfaitement isolée des autres.

---

## 9. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| opencode ne voit pas l'outil `claude_chat` | serveur arrêté, ou mauvaise URL | Vérifie que le terminal du serveur tourne ; l'URL doit finir par `/mcp` |
| `authenticated: false` dans le health | Claude pas connecté | Relance `claude`, connecte-toi, réessaie |
| `invalid_working_dir` | dossier inexistant / chemin relatif | Donne un chemin **absolu** qui **existe** (ex. `C:\DATA\PROJET_X`) |
| `working_dir_forbidden` | dossier hors de `--root` | Choisis un dossier sous la racine, ou démarre le serveur sans `--root` |
| L'agent ajoute « Claude répond : » ou bavarde | modèle de relais faible | Mets **Nemotron 3 Super** ou **Mistral Small 4** (étape 7) ; vérifie que `claude.md` est bien pris en compte |
| Les modifs de `claude.md` ne s'appliquent pas | opencode a mis en cache l'agent | **Redémarre opencode** |
| L'agent `claude` n'apparaît pas | mauvais dossier | Place `claude.md` dans `.opencode\agent\` (projet) ou `~\.config\opencode\agent\` (global), puis redémarre |
| `unauthorized` (401) | un token est exigé | Ajoute l'en-tête `Authorization` dans `opencode.json` (voir §10) |

---

## 10. Options avancées

Toutes ces options se mettent à la fin de la commande de démarrage (étape 4).

### Restreindre les dossiers accessibles
```powershell
.venv\Scripts\python -m claude_wrapper --root C:\DATA
```
Tout `working_dir` devra alors être **sous** `C:\DATA`.

### Exiger un mot de passe partagé (token)
Serveur :
```powershell
.venv\Scripts\python -m claude_wrapper --token MON_SECRET
```
`opencode.json` (ajoute le bloc `headers`) :
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "claude-wrapper": {
      "type": "remote",
      "url": "http://127.0.0.1:8787/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer MON_SECRET" }
    }
  }
}
```

### Changer le port
```powershell
.venv\Scripts\python -m claude_wrapper --port 9000
```
(Pense à mettre la même valeur dans l'`url` d'opencode.)

### Construire un exécutable autonome (sans Python à lancer)
```powershell
.venv\Scripts\python -m pip install -e ".[build]"
.venv\Scripts\python -m PyInstaller build\claude-wrapper.spec --distpath build\dist --workpath build\work --noconfirm
```
Tu obtiens `build\dist\claude-wrapper.exe`, à lancer comme le serveur (il a
toujours besoin de Node + Claude Code installés).

---

Besoin d'aide ? Regarde aussi le [README](../README.md) et la
[spécification complète](../claude_wrapper_specification.md).
