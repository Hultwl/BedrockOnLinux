# BedrockOnLinux

**Lancer Minecraft Bedrock (édition Windows / GDK) sur n'importe quel Linux —
multijoueur compris — avec UN seul exécutable. Pas 40 applis à installer.**

> Ubuntu · Debian · Linux Mint/LMDE · Fedora · Arch · openSUSE … (tout ce qui a
> `python3`, `tar`, `curl`/`wget` et `bwrap`).

---

## Pourquoi

Faire tourner Minecraft Bedrock « édition Windows » (build GDK) sur Linux
demandait jusqu'ici : extraire le jeu, installer Heroic, télécharger GDK‑Proton,
**le patcher au binaire** (sinon le jeu se ferme), bricoler curl/SSL, installer
Java, trouver la bonne build de ProxyPass, configurer le LAN… des heures.

BedrockOnLinux fait **tout ça automatiquement**, en un fichier. Tu fournis
seulement **tes propres fichiers de jeu** (voir Légal), tu cliques **Play**.

## Ce que ça automatise

| Étape | Détail |
|------|--------|
| GDK‑Proton | télécharge la dernière version **et applique les 2 patchs binaires** indispensables (`combase.RoOriginateErrorW`, `ntdll stub_entry_point`) |
| umu‑launcher | Steam Linux Runtime → fonctionne sur **toutes** les distros |
| Java 25 | embarqué (Temurin), requis par ProxyPass |
| ProxyPass | récupère **la build qui correspond à TA version** de Minecraft |
| Multijoueur | ProxyPass lancé en arrière‑plan, exposé en **LAN** (auth Microsoft hors Wine) |
| Prefix Wine | création, GameInput, curl/SSL, `options.txt` |

## Installation

```bash
git clone https://github.com/BedrockOnLinux/BedrockOnLinux
cd BedrockOnLinux
./bedrock-on-linux doctor          # vérifie les (rares) prérequis système
```

ou installation locale (ajoute une entrée menu + commande `bedrock-on-linux`) :

```bash
./scripts/install.sh
```

## Utilisation

```bash
# 1. Préparer (téléchargements, une seule fois)
bedrock-on-linux setup --game-dir "/chemin/vers/Minecraft for Windows"

# 2. Jouer (lance ProxyPass + Minecraft)
bedrock-on-linux play

# Changer de serveur quand tu veux
bedrock-on-linux config --server play.galaxite.net:19132
```

Sans argument et avec un écran : **interface graphique** (bouton *Setup* puis
*Play*).

### Multijoueur — important

Sous WineGDK, le bouton **« Ajouter un serveur » est grisé** (pas de compte
Microsoft *dans* le jeu) : **c'est normal**. BedrockOnLinux contourne ça :
ProxyPass authentifie ton compte **en dehors** de Wine et apparaît comme une
**partie LAN**.

➡️ En jeu : **Jouer ▸ onglet Amis ▸ rejoindre la partie LAN** (pas l'onglet
*Serveurs*). Au premier lancement, ProxyPass affiche un lien
`microsoft.com/link` + un code : connecte le compte Microsoft **propriétaire de
Minecraft** (mémorisé ensuite).

## Légal

BedrockOnLinux **ne télécharge jamais Minecraft** et n'en distribue aucun
fichier. C'est un **lanceur de compatibilité** (comme Heroic / mcpelauncher).
Tu dois fournir **tes propres fichiers** Bedrock GDK, obtenus légalement depuis
ton installation Windows / ton compte Xbox. GDK‑Proton, umu‑launcher,
ProxyPass et Temurin sont libres et téléchargés depuis leurs sources
officielles ; chacun garde sa propre licence.

Realms et la connexion Microsoft *native dans le jeu* restent non supportés
(limite de WineGDK) — le multijoueur serveurs passe par ProxyPass.

## Statut

v0.1 — pipeline validé sur LMDE 7 / RTX 4060 avec Minecraft 1.26.2101.
Voir [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) pour les détails techniques
(notamment les offsets exacts des patchs et *pourquoi* ils sont nécessaires).

## Licence

MIT — voir [`LICENSE`](LICENSE).
