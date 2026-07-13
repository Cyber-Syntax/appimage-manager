# UI CLI

Install Command

```bash
appman install standard-notes ytmdesktop qownnotes appflowy super-productivity keepassxc weektodo obsidian
:: Querying upstream releases...
GitHub                            92.1 MiB   4.7 MB/s 01:50  [####################] 100%
error: failed retrieving appimage 'standard-notes' : Could not resolve host: gitlab.com
error: failed retrieving appimage 'ytmdesktop' : AppImage asset not found : appimage builds take time so it may still be building, try again later, if this persists please report an issue on github
:: Retrieving appimages...
qownnotes                         40.6 MiB   4.7 MB/s 00:40  [####################] 100%
appflowy                          70.6 MiB   4.2 MB/s 00:50  [####################] 100%
super-productivity                120.5 MiB  4.7 MB/s 01:50  [####################] 100%
keepassxc                         80.2 MiB   4.7 MB/s 01:50  [####################] 100%
weektodo                          120.5 MiB  4.7 MB/s 01:50  [####################] 100%
obsidian                          92.1 MiB   4.7 MB/s 01:50  [####################] 100%
Total (6/6)                       339.5 MiB  4.7 MB/s 04:10  [####################] 100%
:: Processing package changes...
(1/6) installing qownnotes
(2/6) installing appflowy
(3/6) installing super-productivity
warning: checksum asset not found for super-productivity : some developers not provide any, please report an issue for the package maintainers if you verified this isn't appman fault
(4/6) installing weektodo
skipped: no checksum provided by upstream : skipping verification
(5/6) installing obsidian
(6/6) installing notion
error: failed to install 'notion' : Permission denied
:: Creating transaction summary...
INSTALLED  qownnotes    26.2.4
INSTALLED  appflowy     0.11.1
INSTALLED  super-productivity
INSTALLED  weektodo     1.30.1
INSTALLED  obsidian     1.8.10
FAILED     ytmdesktop
FAILED     notion
:: Done.
```

::Already Installed

```bash
:: Transaction summary
SKIPPED  appflowy    already installed
SKIPPED  qownnotes   already installed
```

Update Command

```bash
appman update standard-notes qownnotes appflowy weektodo legcord
:: Querying upstream releases...
GitHub                            92.1 MiB   4.7 MB/s 01:50  [####################] 100%
error: failed retrieving appimage 'standard-notes' : Could not resolve host: gitlab.com
error: failed retrieving appimage 'ytmdesktop' : AppImage asset not found : appimage builds take time so it may still be building, try again later, if this persists please report an issue on github
:: Retrieving appimages...
qownnotes                         40.6 MiB   4.7 MB/s 00:40  [####################] 100%
appflowy                          70.6 MiB   4.2 MB/s 00:50  [####################] 100%
weektodo                          120.5 MiB  4.7 MB/s 01:50  [####################] 100%
legcord                           120.5 MiB  4.7 MB/s 01:35  [################    ]  95%
error: network error while downloading legcord
Total (3/4)                       339.5 MiB  4.7 MB/s 04:10  [####################] 100%
:: Processing package changes...
(1/3) upgrading qownnotes
(2/3) upgrading appflowy
(3/3) upgrading weektodo
skipped: no checksum provided by upstream : skipping verification
:: Creating transaction summary...
UPDATED    qownnotes    26.2.4 -> 26.2.5
UPDATED    appflowy     0.11.0 -> 0.11.1
UPDATED    weektodo     1.30.0 -> 1.30.1
FAILED     standard-notes
FAILED     ytmdesktop
:: Done.
```

Upgrade Command

```bash
appman upgrade
🚀 Starting appman upgrade...
Updating appman from 2.5.1a0 to 2.5.2-alpha
Handing off to uv — terminal will update now...
```

```bash
appman upgrade
:: Starting appman upgrade...
Retrieving status...

current version: 2.5.1-alpha
latest version: 2.5.2-alpha

:: Proceed with installation? [Y/n]
:: Preparing upgrade...
(1/1) upgrading appman
:: Handing off to uv — terminal will update now...
```

Remove Command

```bash
appman remove qownnotes appflowy
:: Processing package changes...
(1/2) removing qownnotes
(2/2) removing appflowy
:: Done.
```

catalog command

```bash
appman list --available
affine
appflowy
beekeeper-studio
freecad
joplin
obsidian
qownnotes
```

```bash
appman list --available --verbose
:: Searching available package...

affine 12.0.0-1
    Privacy-focused knowledge base notion alternative

appflowy 0.11.8-1
    Open source Notion alternative with offline-first approach

beekeeper-studio 5.7.2-1
    Cross platform SQL editor and database manager

freecad 24.2.0-1
    Parametric 3D CAD modeler

joplin 3.5.13-1
    Open source note taking and to-do app with sync capabilities

obsidian 1.12.7-1
    Proprietary powerful knowledge base on top of local Markdown files

qownnotes 1.0.0-1
    Plain-text note-taking with Markdown support
```

```bash
appman search qownnotes --verbose
:: Searching available package...

qownnotes 26.2.4-1
    Plain-text note-taking with Markdown support
```

```bash
appman info appflowy
Repository      : AppFlowy-IO/AppFlowy
Name            : appflowy
Version         : 0.11.8-1
Description     : Open source Notion alternative
Architecture    : x86_64
Download Size   : 70.6 MiB
Upstream URL    : https://github.com/AppFlowy-IO/AppFlowy
License         : AGPL-3.0
Verification    : github_api_digest (Embedded in GitHub API)
Checksum File   : qownnotes.AppImage.sha256
Status          : Installed
Install Date    : 2026-05-07
```

```bash
appman list --installed
appflowy 0.11.8-1
beekeeper-studio 5.7.2-1
flameshot 13.3.0-1
joplin 3.5.13-1
obsidian 1.12.7-1
```

## auth

```bash
appman auth --status
:: Checking authentication status...
GitHub token: configured
:: Fetching GitHub API rate limit...
Remaining: 4998/5000
Resets in: 1m 33s
Resets at: 2026-05-08 05:48:27 UTC
```

### Confirmation (good-to-have)

```bash
appman install qownnotes appflowy
resolving package operations...

AppImage (2)        New Version  Net Change

qownnotes           3.5.1-1.1      0,48 MiB
appflowy            3.5.1-1.1      0,48 MiB

Total Installed Size:  0,96 MiB

:: Proceed with installation? [Y/n] y
```

```bash
appman remove qownnotes
resolving package operations...

AppImage (1)  Old Version  Net Change

qownnotes     1.0.0        -0,48 MiB

Total Removed Size:  0,48 MiB

:: Do you want to remove these packages? [Y/n] y
```

### Searching via category (good-to-have)

```bash
appman search music

spotube 5.1.1-1
    Open source music streaming app

nuclear 1.35.0-1
    Music streaming player using YouTube sources

muffon 2.4.0-1
    Multi-source music streaming client
```
